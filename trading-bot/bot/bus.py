"""A tiny in-process message bus so agents talk through topics, not direct calls."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Message:
    topic: str
    sender: str
    payload: dict[str, Any]
    step: int = 0


@dataclass
class MessageBus:
    log: list[Message] = field(default_factory=list)
    keep_log: bool = True
    _subs: dict[str, list[Callable[[Message], None]]] = field(default_factory=lambda: defaultdict(list))

    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        self._subs[topic].append(handler)

    def publish(self, msg: Message) -> None:
        if self.keep_log:
            self.log.append(msg)
        for handler in self._subs[msg.topic]:
            handler(msg)

    def publish_from(self, sender: str, topic: str, step: int, **payload: Any) -> None:
        self.publish(Message(topic=topic, sender=sender, payload=payload, step=step))
