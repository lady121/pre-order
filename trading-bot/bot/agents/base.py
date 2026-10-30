from __future__ import annotations

from typing import Any

from ..bus import Message, MessageBus


class Agent:
    """Base class: every agent has a name, a single job, and talks via the bus."""

    name = "agent"
    role = ""

    def __init__(self, bus: MessageBus):
        self.bus = bus
        self.step = 0

    def send(self, topic: str, **payload: Any) -> None:
        self.bus.publish(Message(topic=topic, sender=self.name, payload=payload, step=self.step))
