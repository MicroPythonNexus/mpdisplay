# SPDX-FileCopyrightText: 2024 Brad Barnett
#
# SPDX-License-Identifier: MIT
from ._devices import Devices, Events


class _BaseDisplay:
    def __init__(self):
        self.devices = []

        # Function to call when the window close button is clicked.
        # Set it like `display_drv.quit_func = cleanup_func` where `cleanup_func` is a
        # function that cleans up resources and calls `sys.exit()`.
        # .poll_event() must be called periodically to check for the quit event.
        self.quit_func = lambda: print(".quit_func not set")

    @property
    def width(self):
        """The width of the display in pixels."""
        if ((self._rotation // 90) & 0x1) == 0x1:  # if rotation index is odd
            return self._height
        return self._width

    @property
    def height(self):
        """The height of the display in pixels."""
        if ((self._rotation // 90) & 0x1) == 0x1:  # if rotation index is odd
            return self._width
        return self._height

    def create_device(self, type, *args, **kwargs):
        """
        Create a device object.

        :param type: The type of device to create.
        :type dev: int
        """
        dev = Devices(type, *args, display=self, **kwargs)
        self.register_device(dev)
        return dev

    def register_device(self, dev):
        """
        Register a device to be polled.

        :param dev: The device object to register.
        :type dev: _Device
        """
        dev.display = self
        self.devices.append(dev)

    def unregister_device(self, dev):
        """
        Unregister a device.

        :param dev: The device object to unregister.
        :type dev: _Device
        """
        if dev in self.devices:
            self.devices.remove(dev)
            dev.display = None

    def poll_event(self):
        """
        Provides a similar interface to PyGame's and SDL2's event queues.
        The returned event is a namedtuple from the Events class.
        The type of event is in the .type field.

        Currently returns as soon as an event is found and begins with the first
        device registered the next time called, placing priority on the first
        device registered.  Register less frequently fired or higher priority devices
        first if you have problems with this.  This may change in the future.

        It is recommended to run poll_event repeatedly until all events have been
        processed on a timed schedule.  For instance, schedule the following on a recurring basis:

            while (event := display_drv.poll_event()):
                ...
        """
        for device in self.devices:
            if (event := device.read()) is not None:
                if event.type in Events.types:
                    if event.type == Events.QUIT:
                        self.quit_func()
                    return event
        return None

    def __del__(self):
        """
        Deinitializes the display instance.
        """
        self.deinit()

    ######## Overridden functions ########

    def set_render_mode_full(self, render_mode_full=False):
        return

    @property
    def power(self):
        return -1

    @power.setter
    def power(self, value):
        return

    @property
    def brightness(self):
        return -1

    @brightness.setter
    def brightness(self, value):
        return

    def reset(self):
        return

    def hard_reset(self):
        return

    def soft_reset(self):
        return

    def sleep_mode(self, value):
        return