from __future__ import annotations

from dataclasses import dataclass, field

import ifcopenshell.entity_instance
import ifcopenshell.file

from api.ifc.geometry import GeometryHandler
from api.ifc.helpers import get_entity_id

ADJACENCY_CLEARANCE = 0.05
OVERLAP_EPSILON = 1e-6


@dataclass(frozen=True)
class BoundingBox:
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    def min_value(self, axis: int) -> float:
        return (self.min_x, self.min_y, self.min_z)[axis]

    def max_value(self, axis: int) -> float:
        return (self.max_x, self.max_y, self.max_z)[axis]


@dataclass
class _ModelTopology:
    boxes: dict[str, BoundingBox | None] = field(default_factory=dict)
    relation_cache: dict[tuple[str, str, tuple[str, ...]], list[str]] = field(
        default_factory=dict
    )


class TopologyService:
    def __init__(self):
        self._models: dict[int, _ModelTopology] = {}

    def intersects(
        self,
        ifc_model: ifcopenshell.file,
        source: ifcopenshell.entity_instance,
        candidates: list[ifcopenshell.entity_instance],
    ) -> list[ifcopenshell.entity_instance]:
        return self._related(ifc_model, source, candidates, "intersects")

    def adjacent(
        self,
        ifc_model: ifcopenshell.file,
        source: ifcopenshell.entity_instance,
        candidates: list[ifcopenshell.entity_instance],
    ) -> list[ifcopenshell.entity_instance]:
        return self._related(ifc_model, source, candidates, "adjacent")

    def _related(
        self,
        ifc_model: ifcopenshell.file,
        source: ifcopenshell.entity_instance,
        candidates: list[ifcopenshell.entity_instance],
        relation: str,
    ) -> list[ifcopenshell.entity_instance]:
        candidates = [
            candidate
            for candidate in candidates
            if get_entity_id(candidate) != get_entity_id(source)
        ]
        candidate_by_id = {get_entity_id(candidate): candidate for candidate in candidates}
        if not candidates:
            return []

        topology = self._model_topology(ifc_model)
        cache_key = (
            relation,
            get_entity_id(source),
            tuple(candidate_by_id.keys()),
        )
        if cache_key not in topology.relation_cache:
            topology.relation_cache[cache_key] = self._resolve_related_ids(
                topology,
                source,
                candidates,
                relation,
            )

        return [
            candidate_by_id[entity_id]
            for entity_id in topology.relation_cache[cache_key]
            if entity_id in candidate_by_id
        ]

    def _model_topology(self, ifc_model: ifcopenshell.file) -> _ModelTopology:
        model_key = id(ifc_model)
        if model_key not in self._models:
            self._models[model_key] = _ModelTopology()
        return self._models[model_key]

    def _resolve_related_ids(
        self,
        topology: _ModelTopology,
        source: ifcopenshell.entity_instance,
        candidates: list[ifcopenshell.entity_instance],
        relation: str,
    ) -> list[str]:
        source_box = self._box(topology, source)
        if source_box is None:
            return []

        related_ids: list[str] = []
        for candidate in candidates:
            candidate_box = self._box(topology, candidate)
            if candidate_box is None:
                continue
            if relation == "intersects" and boxes_intersect(source_box, candidate_box):
                related_ids.append(get_entity_id(candidate))
            elif relation == "adjacent" and boxes_adjacent(source_box, candidate_box):
                related_ids.append(get_entity_id(candidate))
        return related_ids

    def _box(
        self,
        topology: _ModelTopology,
        entity: ifcopenshell.entity_instance,
    ) -> BoundingBox | None:
        entity_id = get_entity_id(entity)
        if entity_id not in topology.boxes:
            topology.boxes[entity_id] = self._compute_box(entity)
        return topology.boxes[entity_id]

    def _compute_box(
        self,
        entity: ifcopenshell.entity_instance,
    ) -> BoundingBox | None:
        try:
            raw_box = GeometryHandler(entity).bbox()
        except Exception:
            return None
        return BoundingBox(
            min_x=float(raw_box["min"]["x"]),
            min_y=float(raw_box["min"]["y"]),
            min_z=float(raw_box["min"]["z"]),
            max_x=float(raw_box["max"]["x"]),
            max_y=float(raw_box["max"]["y"]),
            max_z=float(raw_box["max"]["z"]),
        )


def boxes_intersect(
    box_a: BoundingBox,
    box_b: BoundingBox,
    epsilon: float = OVERLAP_EPSILON,
) -> bool:
    return all(_overlap_length(box_a, box_b, axis) > epsilon for axis in range(3))


def boxes_adjacent(
    box_a: BoundingBox,
    box_b: BoundingBox,
    clearance: float = ADJACENCY_CLEARANCE,
    epsilon: float = OVERLAP_EPSILON,
) -> bool:
    if boxes_intersect(box_a, box_b, epsilon):
        return False

    for axis in range(3):
        if _axis_gap(box_a, box_b, axis) > clearance:
            continue
        other_axes = [other_axis for other_axis in range(3) if other_axis != axis]
        if all(_overlap_length(box_a, box_b, other_axis) > epsilon for other_axis in other_axes):
            return True
    return False


def _overlap_length(box_a: BoundingBox, box_b: BoundingBox, axis: int) -> float:
    return min(box_a.max_value(axis), box_b.max_value(axis)) - max(
        box_a.min_value(axis),
        box_b.min_value(axis),
    )


def _axis_gap(box_a: BoundingBox, box_b: BoundingBox, axis: int) -> float:
    return max(
        box_b.min_value(axis) - box_a.max_value(axis),
        box_a.min_value(axis) - box_b.max_value(axis),
        0.0,
    )


topology_service = TopologyService()
