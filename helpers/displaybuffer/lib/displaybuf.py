# SPDX-FileCopyrightText: 2020 Peter Hinch, 2024 Brad Barnett
#
# SPDX-License-Identifier: MIT

'''
displaybuf.py
FrameBuffer wrapper for using framebuf based GUIs with MPDisplay.
Works with MicroPython Nano-GUI, Micro-GUI and MicroPython-Touch from Peter Hinch,
but may also be used without them.

Usage:
    'color_setup.py'
        from displaybuf import DisplayBuffer as SSD
        from board_config import display_drv

        format = SSD.RGB565  # or .GS8 or .GS4_HMSB

        ssd = SSD(display_drv, format)

    'main.py'
        from color_setup import ssd
        <your code here>
'''

import framebuf
import gc
import sys
if sys.implementation.name == 'micropython':
    from displaybuf_bounce import _bounce8, _bounce4

# Define how line buffers are allocated.  Allows being overridden by platforms with DMA specific allocations, such as ESP32's heap_caps.
alloc_buffer = lambda size: bytearray(size)


class DisplayBuffer(framebuf.FrameBuffer):
    '''
    DisplayBuffer: A class to wrap an MPDisplay driver and provide a framebuf
    compatible interface to it.  It provides a show() method to copy the framebuf
    to the display.  The show() method is optimized for the format.
    The format must be one of the following:
        DisplayBuffer.RGB565
        DisplayBuffer.GS8
        DisplayBuffer.GS4_HMSB
    '''

    rgb = None  # Function to convert r, g, b to a color value; used by Nano-GUI and Micro-GUI.
    colors_registered = 0  # For .color().  Not used in Nano-GUI or Micro-GUI.

    RGB565 = framebuf.RGB565
    GS8 = framebuf.GS8 if hasattr(framebuf, "GS8") else None
    GS4_HMSB = framebuf.GS4_HMSB if hasattr(framebuf, "GS4_HMSB") else None

    def __init__(self, display_drv, format=framebuf.RGB565, stride=8):
        self.display_drv = display_drv
        self.height = display_drv.height
        self.width = display_drv.width
        self.palette = BoolPalette(format)  # a 2-value color palette for rendering monochrome glyphs
                                          # with ssd.blit(glyph_buf, x, y, key=-1, pallette=ssd.pallette)

        # If byte swapping is required and the display bus is capable of having byte swapping disabled,
        # disable it and set a flag so we can swap the color bytes as they are created.
        if self.display_drv.requires_byte_swap:
            # self.display_drv.bus_swap_disable(True) returns True if it was successful, False if not.
            self.needs_swap = self.display_drv.bus_swap_disable(True)
        else:
            self.needs_swap = False

        # Set the DisplayBuffer.rgb function to the appropriate one for the format and byte swapping
        if format == DisplayBuffer.GS8 and DisplayBuffer.GS8 != None:
            DisplayBuffer.rgb = self._rgb332
        else:
            if self.needs_swap:
                DisplayBuffer.rgb = self._rgb565_swapped
            else:
                DisplayBuffer.rgb = self._rgb565

        # Set the show function to the appropriate one for the format and
        # allocate the buffer.  Also create the line buffer and lut if needed.
        gc.collect()
        if format == DisplayBuffer.RGB565:
            self._buffer = bytearray(self.width * self.height * 2)
            self.show = self._show16
        elif format == DisplayBuffer.GS8 and DisplayBuffer.GS8 != None:
            self._stride = stride
            self._bounce_buf = alloc_buffer(self.width * self._stride * 2)
            self._buffer = bytearray(self.width * self.height)
            self.show = self._show8
        elif format == DisplayBuffer.GS4_HMSB and DisplayBuffer.GS4_HMSB != None:
            DisplayBuffer.lut = bytearray(0x00 for _ in range(32))
            self._stride = stride
            self._bounce_buf = alloc_buffer(self.width * self._stride * 2)
            self._buffer = bytearray(self.width * self.height // 2)
            self.show = self._show4
        else:
            raise ValueError(f"Unsupported format: {format}")

        super().__init__(self._buffer, self.width, self.height, format)
        self._mvb = memoryview(self._buffer)
        self.show()  # Clear the display
        gc.collect()

    def _show16(self):
        # Copy the buffer to the display in one go
        self.display_drv.blit(0, 0, self.width, self.height, self._mvb)

    def _show8(self):
        # Convert the 8 bit RGB332 values to 16 bit RGB565 values and then copy the line
        # to the display, line by line.
        swap = self.needs_swap
        buf = self._mvb
        bb = self._bounce_buf
        wd = self.width
        ht = self.height
        lines = self._stride
        stride = lines * wd
        chunks, remainder = divmod(ht, lines)
        for chunk in range(chunks):
            start = chunk * stride
            _bounce8(bb, buf[start :], stride, swap)
            self.display_drv.blit(0, chunk * lines, wd, lines, bb)
        if remainder:
            start = chunks * stride
            _bounce8(bb, buf[start :], remainder * wd, swap)
            self.display_drv.blit(0, chunks * lines, wd, remainder, bb)

    def _show4(self):
        # Convert the 4 bit index values to 16 bit RGB565 values using a lookup table
        # and then copy the line to the display, line by line.
        clut = DisplayBuffer.lut
        buf = self._mvb
        bb = self._bounce_buf
        wd = self.width
        ht = self.height
        lines = self._stride
        stride = lines * wd // 2  # 2 pixels per byte
        chunks, remainder = divmod(ht, lines)
        for chunk in range(chunks):
            start = chunk * stride
            _bounce4(bb, buf[start :], stride, clut)
            self.display_drv.blit(0, chunk * lines, wd, lines, bb)
        if remainder:
            start = chunks * stride
            _bounce4(bb, buf[start :], remainder * wd // 2, clut)
            self.display_drv.blit(0, chunks * lines, wd, remainder, bb)

    @staticmethod
    def _rgb332(r, g, b):
        # Convert r, g, b in range 0-255 to an 8 bit color value RGB332
        # rrrgggbb
        return (r & 0xe0) | ((g >> 3) & 0x1c) | (b >> 6)

    @staticmethod
    def _rgb565(r, g, b):
        # Convert r, g, b in range 0-255 to a 16 bit color value RGB565
        # rrrrrggg gggbbbbb
        return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    
    @staticmethod
    def _rgb565_swapped(r, g, b):
        # Convert r, g, b in range 0-255 to a 16 bit color value RGB565
        # gggbbbbb rrrrrggg
        color = DisplayBuffer._rgb565(r, g, b)
        return (color & 0xff) << 8 | (color & 0xff00) >> 8

    @staticmethod
    def color(r, g, b, idx=None):
        """
        Get an RGB565 or RGB332 value for a color and optionally register it in the display's LUT.
        This is a convenience function for using this framework WITHOUT Nano-GUI or Micro-GUI.
        Those packages have their own methods of registering colors.
    
        :param r: Red component (0-255)
        :param g: Green component (0-255)
        :param b: Blue component (0-255)
        :param idx: Optional index to register the color in the display's LUT (0-15);
                    ignored if the display doesn't use a LUT in its current format
        :return: RGB565 color value in RG565 format;
                 RGB332 color value in GS8 format;
                 the index of the registered color in the LUT in GS4_HMSB format
        """
        c = DisplayBuffer.rgb(r, g, b)  # Convert the color to RGB565 or RGB332
        if not hasattr(DisplayBuffer, 'lut'):  # If the ssd doesn't use a LUT in its current format
            return c  # Return the color as-is
        if idx == None:  # If no index was provided
            if DisplayBuffer.colors_registered < 16:  # If there are fewer than 16 colors registered
                idx = DisplayBuffer.colors_registered  # Set the index to the next index 
                DisplayBuffer.colors_registered += 1  # Increment the number of colors registered
            else:  # If there are already 16 colors registered
                raise ValueError("16 colors have already been registered")
        if not 0 <= idx <= 15:  # If the index is out of range
            raise ValueError("Color numbers must be 0..15")
        offset = idx << 1  # Multiply by 2 (2 bytes per 16-bit color)
        DisplayBuffer.lut[offset] = c & 0xff  # Set the lower 8 bits of the color
        DisplayBuffer.lut[offset + 1] = c >> 8  # Set the upper 8 bits of the color
        return idx  # Return the index of the registered color
    

class BoolPalette(framebuf.FrameBuffer):
    # This is a 2-value color palette for rendering monochrome glyphs to color
    # FrameBuffer instances. Supports destinations with up to 16 bit color.

    # Copyright (c) Peter Hinch 2021
    # Released under the MIT license see LICENSE
    def __init__(self, format):
        buf = bytearray(4)  # OK for <= 16 bit color
        super().__init__(buf, 2, 1, format)
    
    def fg(self, color):  # Set foreground color
        self.pixel(1, 0, color)

    def bg(self, color):
        self.pixel(0, 0, color)