from __future__ import annotations

from dataclasses import dataclass, field

import ifcopenshell.entity_instance
import ifcopenshell.file
import ifcopenshell.geom

from api.ifc.helpers import get_entity_id

INTERSECTION_TOLERANCE = 0.002
ADJACENCY_CLEARANCE = 0.05


@dataclass
class _ModelTopology:
    tree: ifcopenshell.geom.tree
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

        try:
            topology = self._model_topology(ifc_model)
        except Exception:
            return []
        cache_key = (
            relation,
            get_entity_id(source),
            tuple(candidate_by_id.keys()),
        )
        if cache_key not in topology.relation_cache:
            topology.relation_cache[cache_key] = self._resolve_related_ids(
                topology.tree,
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
            settings = ifcopenshell.geom.settings()
            settings.set(settings.USE_WORLD_COORDS, True)
            tree = ifcopenshell.geom.tree()
            tree.add_file(ifc_model, settings)
            self._models[model_key] = _ModelTopology(tree)
        return self._models[model_key]

    def _resolve_related_ids(
        self,
        tree: ifcopenshell.geom.tree,
        source: ifcopenshell.entity_instance,
        candidates: list[ifcopenshell.entity_instance],
        relation: str,
    ) -> list[str]:
        try:
            if relation == "intersects":
                clashes = tree.clash_intersection_many(
                    [source],
                    candidates,
                    INTERSECTION_TOLERANCE,
                    True,
                )
            elif relation == "adjacent":
                clashes = tree.clash_clearance_many(
                    [source],
                    candidates,
                    ADJACENCY_CLEARANCE,
                    False,
                )
            else:
                return []
        except Exception:
            return []

        related_ids: set[str] = set()
        source_id = get_entity_id(source)
        for clash in clashes:
            entity_a = getattr(clash, "a", None)
            entity_b = getattr(clash, "b", None)
            if entity_a is not None and get_entity_id(entity_a) == source_id:
                if entity_b is not None:
                    related_ids.add(get_entity_id(entity_b))
            elif entity_b is not None and get_entity_id(entity_b) == source_id:
                if entity_a is not None:
                    related_ids.add(get_entity_id(entity_a))

        return [
            get_entity_id(candidate)
            for candidate in candidates
            if get_entity_id(candidate) in related_ids
        ]


topology_service = TopologyService()
