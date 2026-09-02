from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Any, AsyncIterator

from ariadne import SubscriptionType
from graphql import GraphQLError
import ifcopenshell


@dataclass(frozen=True)
class ModelChangeEvent:
    modelId: str
    revision: int
    kind: str
    source: str


@dataclass(frozen=True)
class BuildingElementChange:
    stepId: str
    globalId: str
    ifcType: str
    kind: str
    aspects: tuple[str, ...]


@dataclass(frozen=True)
class BuildingElementsChangedEvent:
    modelId: str
    revision: int
    kind: str
    source: str
    fullRefetchRequired: bool
    changes: tuple[BuildingElementChange, ...] = ()


def _filters(value: dict[str, Any] | None) -> dict[str, set[str]]:
    normalized = {
        key: {str(item) for item in (value or {}).get(key, [])}
        for key in ("aspects", "stepIds", "globalIds", "ifcTypes")
    }
    normalized = {key: values for key, values in normalized.items() if values}
    for step_id in normalized.get("stepIds", set()):
        if not step_id.isdigit() or int(step_id) <= 0:
            raise GraphQLError("Building-element change filter STEP IDs must be positive integers")
    for global_id in normalized.get("globalIds", set()):
        try:
            ifcopenshell.guid.expand(global_id)
        except Exception as exc:
            raise GraphQLError(f"Invalid IFC GlobalId in change filter: {global_id}") from exc
    return normalized


def _filter_event(event, filters):
    if event.fullRefetchRequired or not filters:
        return event
    matches = []
    for change in event.changes:
        if filters.get("stepIds") and change.stepId not in filters["stepIds"]:
            continue
        if filters.get("globalIds") and change.globalId not in filters["globalIds"]:
            continue
        if filters.get("ifcTypes") and change.ifcType not in filters["ifcTypes"]:
            continue
        bypass = change.kind in {"CREATED", "DELETED"} or "UNKNOWN" in change.aspects
        if filters.get("aspects") and not bypass and not filters["aspects"].intersection(change.aspects):
            continue
        matches.append(change)
    return replace(event, changes=tuple(matches)) if matches else None


class InMemoryEventBroker:
    def __init__(self) -> None:
        self._subscribers: dict[asyncio.Queue[Any], tuple[str | None, str, dict[str, set[str]]]] = {}

    async def publish(self, event) -> None:
        event_type = "ELEMENTS" if isinstance(event, BuildingElementsChangedEvent) else "MODEL"
        for queue, (model_id, subscribed_type, filters) in tuple(self._subscribers.items()):
            if subscribed_type != event_type or (model_id is not None and model_id != event.modelId):
                continue
            delivered = _filter_event(event, filters) if event_type == "ELEMENTS" else event
            if delivered is not None:
                queue.put_nowait(delivered)

    async def subscribe(
        self, model_id: str | None, event_type: str = "MODEL", filters=None
    ) -> AsyncIterator[Any]:
        queue: asyncio.Queue[Any] = asyncio.Queue()
        self._subscribers[queue] = (model_id, event_type, _filters(filters))
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.pop(queue, None)


model_change_subscription = SubscriptionType()


@model_change_subscription.source("modelChanged")
async def model_changed_source(_, info):
    context = info.context
    async for event in context["event_broker"].subscribe(context.get("model_id"), "MODEL"):
        yield event


@model_change_subscription.field("modelChanged")
def model_changed_resolver(event, _info):
    return event


@model_change_subscription.source("buildingElementsChanged")
async def building_elements_changed_source(_, info, filter=None):
    context = info.context
    async for event in context["event_broker"].subscribe(
        context.get("model_id"), "ELEMENTS", filter
    ):
        yield event


@model_change_subscription.field("buildingElementsChanged")
def building_elements_changed_resolver(event, _info, **_kwargs):
    return event
