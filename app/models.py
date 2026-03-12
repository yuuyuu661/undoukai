from pydantic import BaseModel
from typing import Any


class MetaUpdate(BaseModel):
    room_id: str
    title: str
    teamAName: str
    teamBName: str
    editor: str | None = None


class EventUpdate(BaseModel):
    room_id: str
    event_id: str
    payload: dict[str, Any]
    editor: str | None = None


class EventLockUpdate(BaseModel):
    room_id: str
    event_id: str
    locked: bool
    editor: str | None = None


class ResetRequest(BaseModel):
    room_id: str
    editor: str | None = None