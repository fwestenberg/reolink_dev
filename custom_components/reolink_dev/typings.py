from typing import TypedDict
from datetime import datetime


class VodEvent(TypedDict):
    start: datetime
    end: datetime
    file: str
