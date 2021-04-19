"""This component provides support for Reolink IP VoD support."""
import datetime as dt
import asyncio
import logging
import os
from typing import Optional

from dateutil import relativedelta
import homeassistant.util.dt as dt_utils

from homeassistant.components.sensor import DEVICE_CLASS_TIMESTAMP, SensorEntity

from .const import BASE, DOMAIN, THUMBNAIL_EXTENSION
from .entity import ReolinkEntity
from .base import ReolinkBase, searchtime_to_datetime

_LOGGER = logging.getLogger(__name__)


@asyncio.coroutine
async def async_setup_entry(hass, config_entry, async_add_devices):
    """Set up the Reolink IP Camera switches."""
    devices = []
    base: ReolinkBase = hass.data[DOMAIN][config_entry.entry_id][BASE]

    # TODO : add playback (based off of hdd_info) to capabilities
    await base.api.get_switch_capabilities()
    if base.api.hdd_info:
        devices.append(ReolinkLastEvent(hass, config_entry))

    async_add_devices(devices, update_before_add=False)


class ReolinkLastEvent(ReolinkEntity, SensorEntity):
    """An implementation of a Reolink IP camera FTP switch."""

    def __init__(self, hass, config):
        """Initialize a Reolink camera."""
        ReolinkEntity.__init__(self, hass, config)
        SensorEntity.__init__(self)
        self._oldest_day: Optional[dt.datetime] = None
        self._most_recent_day: Optional[dt.datetime] = None
        self._duration: Optional[dt.timedelta] = None
        self._event_id: Optional[str] = None
        self._filename: Optional[str] = None

    async def async_added_to_hass(self) -> None:
        """Entity created."""
        await super().async_added_to_hass()
        self.hass.bus.async_listen(self._base.event_id, self.handle_event)
        await self._update_event_range()

    async def _update_event_range(self):
        end = dt_utils.now()
        if self._most_recent_day:
            start = self._most_recent_day
        else:
            start = dt.datetime.combine(end.date().replace(day=1), dt.time.min)
            if self._base.playback_months > 1:
                start -= relativedelta.relativedelta(
                    months=int(self._base.playback_months)
                )
        search, _ = await self._base.send_search(start, end, True)
        if len(search) < 1:
            return
        if not self._oldest_day:
            entry = search[0]
            self._oldest_day = dt.datetime(
                entry["year"],
                entry["mon"],
                next((i for (i, e) in enumerate(entry["table"], start=1) if e == "1")),
                tzinfo=end.tzinfo,
            )
        entry = search[-1]
        self._most_recent_day = dt.datetime(
            entry["year"],
            entry["mon"],
            len(entry["table"])
            - next(
                (
                    i
                    for (i, e) in enumerate(reversed(entry["table"]), start=0)
                    if e == "1"
                )
            ),
            tzinfo=end.tzinfo,
        )
        start = self._most_recent_day
        end = dt.datetime.combine(start.date(), dt.time.max, tzinfo=end.tzinfo)
        _, files = await self._base.send_search(start, end)
        file = files[-1] if files and len(files) > 0 else None
        if not file:
            return

        end = searchtime_to_datetime(file["EndTime"], start.tzinfo)
        start = searchtime_to_datetime(file["StartTime"], end.tzinfo)
        self._state = start
        self._duration = end - start
        self._event_id = str(start.timestamp())
        self._filename = file["name"]

    async def handle_event(self, event):
        """Handle incoming event for VoD update"""

        try:
            motion = event.data["motion"]
        except KeyError:
            return

        await self._update_event_range()

    @property
    def unique_id(self):
        """Return Unique ID string."""
        return f"reolink_lastevent_{self._base.unique_id}"

    @property
    def name(self):
        """Return the name of this sensor."""
        return f"{self._base.name} Last Event"

    @property
    def device_class(self):
        """Device class of the sensor."""
        return DEVICE_CLASS_TIMESTAMP

    @property
    def state(self):
        """Return the state of the sensor."""

        if self._state is None:
            return None

        return self._state.isoformat()

    @property
    def icon(self):
        """Icon of the sensor."""
        return "mdi:history"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = super().extra_state_attributes

        if self._state:
            if attrs is None:
                attrs = {}

            if self._oldest_day:
                attrs["oldest_day"] = self._oldest_day.isoformat()
            if self._event_id:
                attrs["event_id"] = self._event_id
                attrs["thumbnail"] = os.path.isfile(
                    os.path.join(
                        self._base.thumbnail_path,
                        self._event_id + f".{THUMBNAIL_EXTENSION}",
                    )
                )
            if self._filename:
                attrs["filename"] = self._filename
            if self._duration:
                attrs["duration"] = str(self._duration)

        return attrs
