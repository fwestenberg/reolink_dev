""" Typing declarations for strongly typed dictionaries """

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Type, TypeVar, TypedDict, Union
from datetime import datetime

from voluptuous.schema_builder import Object


@dataclass
class ReolinkMediaSourceVodEntry:
    """ Camera search result representing a recorded video """

    start: datetime
    end: Optional[datetime] = None
    file: Optional[str] = None
    thumbnail: Optional[Union[str, bytes]] = None
    token: Optional[str] = None

    @property
    def incomplete(self):
        """ check if entry if complete """
        return self.end is None or self.file is None


@dataclass
class ReolinkMediaSourceCacheEntry:
    """ entry in the media source cache for a camera instance """

    entry_id: str
    thumbnail_path: Optional[str] = None
    events: Dict[str, ReolinkMediaSourceVodEntry] = field(default_factory=dict)


class ReolinkMediaSourceConfigEntry(TypedDict, total=False):
    """ Dynamic configuration entry """

    thumbnail_path: str


class ReolinkMediaSourceConfig(TypedDict, total=False):
    """ Dynamic configuration entries for storage """

    configs: Dict[str, ReolinkMediaSourceConfigEntry]


class ReolinkMediaSourceHelper:
    """ stub entries to ducktype MediaSource functions in other modules """

    async def async_motion_snapshot(self, system_now: datetime, base):
        """ generate a snapshot of the current motion event """


TKEY = TypeVar("TKEY")
TVALUE = TypeVar("TVALUE")


def try_get_or_create_item(
    self: Dict[TKEY, TVALUE], key: TKEY, factory: Callable[[TKEY], Optional[TVALUE]]
):
    """ dict extension to get a value or factory create it """

    value = self.get(key, None)
    if not value is None:
        return value
    value = factory(key)
    if not value is None:
        return self.setdefault(key, value)
    return None
