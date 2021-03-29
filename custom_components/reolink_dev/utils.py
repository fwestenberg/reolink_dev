""" Utility functions """

from typing import Callable, Dict, Optional, TypeVar


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
