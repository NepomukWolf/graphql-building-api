from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator

from ariadne import SubscriptionType


@dataclass(frozen=True)
class ModelChangeEvent:
    modelId: str
    revision: int
    kind: str
    source: str


class InMemoryEventBroker:
    def __init__(self) -> None:
        self._subscribers: dict[asyncio.Queue[ModelChangeEvent], str | None] = {}

    async def publish(self, event: ModelChangeEvent) -> None:
        for queue, model_id in tuple(self._subscribers.items()):
            if model_id is None or model_id == event.modelId:
                queue.put_nowait(event)

    async def subscribe(self, model_id: str | None) -> AsyncIterator[ModelChangeEvent]:
        queue: asyncio.Queue[ModelChangeEvent] = asyncio.Queue()
        self._subscribers[queue] = model_id
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.pop(queue, None)


model_change_subscription = SubscriptionType()


@model_change_subscription.source("modelChanged")
async def model_changed_source(_, info):
    context = info.context
    async for event in context["event_broker"].subscribe(context.get("model_id")):
        yield event


@model_change_subscription.field("modelChanged")
def model_changed_resolver(event, _info):
    return event
