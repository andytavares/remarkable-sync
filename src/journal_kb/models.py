from typing import Literal

from pydantic import BaseModel

Bullet = Literal["task", "delegated", "event", "decision", "question", "note"]
State = Literal["open", "done", "migrated", "scheduled", "dropped"]
Confidence = Literal["high", "medium", "low"]

SYMBOL = {"task": "•", "delegated": "→", "event": "○", "decision": "△", "question": "?", "note": "–"}


class Entry(BaseModel):
    bullet: Bullet
    signal: bool
    priority: bool
    state: State
    text: str
    owner: str | None
    due: str | None
    project: str | None
    meeting: str | None
    confidence: Confidence


class Event(BaseModel):
    time: str | None
    title: str
    people: list[str]


class PageRead(BaseModel):
    date: str | None
    events: list[Event]
    entries: list[Entry]
    transcription: str
