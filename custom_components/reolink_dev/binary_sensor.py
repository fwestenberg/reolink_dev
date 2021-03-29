"""This component provides support for Reolink motion events."""
import asyncio
import datetime

# import logging
from typing import cast

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.media_source.const import DOMAIN as MEDIA_SOURCE_DOMAIN

from .const import EVENT_DATA_RECEIVED, DOMAIN
from .entity import ReolinkEntity
from .typings import ReolinkMediaSourceHelper

# _LOGGER = logging.getLogger(__name__)

DEFAULT_DEVICE_CLASS = "motion"


@asyncio.coroutine
async def async_setup_entry(hass, config_entry, async_add_devices):
    """Set up the Reolink IP Camera switches."""
    sensor = MotionSensor(hass, config_entry)
    async_add_devices([sensor], update_before_add=False)


class MotionSensor(ReolinkEntity, BinarySensorEntity):
    """An implementation of a Reolink IP camera motion sensor."""

    def __init__(self, hass, config):
        """Initialize a the switch."""
        ReolinkEntity.__init__(self, hass, config)
        BinarySensorEntity.__init__(self)

        self._available = False
        self._event_state = False
        self._last_motion = datetime.datetime.min

    @property
    def unique_id(self):
        """Return Unique ID string."""
        return f"reolink_motion_{self._base.unique_id}"

    @property
    def name(self):
        """Return the name of this camera."""
        return f"{self._base.name} motion"

    @property
    def is_on(self):
        """Return the state of the sensor."""
        if not self._base.motion_detection_state:
            self._state = False
            return self._state

        if self._event_state or self._base.motion_off_delay == 0:
            self._state = self._event_state
            return self._state

        if (
            datetime.datetime.now() - self._last_motion
        ).total_seconds() < self._base.motion_off_delay:
            self._state = True
        else:
            self._state = False

        return self._state

    @property
    def available(self):
        """Return True if entity is available."""
        return self._available

    @property
    def device_class(self):
        """Return the class of this device."""
        return DEFAULT_DEVICE_CLASS

    async def async_added_to_hass(self) -> None:
        """Entity created."""
        await super().async_added_to_hass()
        self.hass.bus.async_listen(self._base.event_id, self.handle_event)

    async def handle_event(self, event):
        """Handle incoming event for motion detection and availability."""

        try:
            self._available = event.data["available"]
            return
        except KeyError:
            pass

        if not self._available:
            return

        try:
            self._event_state = event.data["motion"]
        except KeyError:
            return

        if self._base.api.channels > 1:
            # Pull the motion state for the NVR channel, it has only 1 event
            self._event_state = await self._base.api.get_motion_state()

        if self._event_state:
            self._last_motion = datetime.datetime.now()
            media_source: ReolinkMediaSourceHelper = cast(
                dict, self.hass.data.get(MEDIA_SOURCE_DOMAIN, {})
            ).get(DOMAIN, None)
            if media_source and self._base.api.hdd_info:
                # we spin off the motion capture task, ideally we want it to be at
                # the same time as the motion event, but we do not want to block
                # anything and a few microseconds off should not hurt
                self.hass.async_add_job(
                    media_source.async_motion_snapshot, self._last_motion, self._base
                )
        else:
            if self._base.motion_off_delay > 0:
                await asyncio.sleep(self._base.motion_off_delay)

        self.async_schedule_update_ha_state()
