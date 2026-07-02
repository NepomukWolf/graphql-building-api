from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from api.gql import resolvers
from api.ifc.topology import TopologyService


class FakeEntity:
    def __init__(self, ifc_type: str, guid: str, name: str | None = None):
        self._ifc_type = ifc_type
        self.GlobalId = guid
        self.Name = name

    def is_a(self, ifc_type: str | None = None):
        if ifc_type is None:
            return self._ifc_type
        return self._ifc_type == ifc_type


class FakeModel:
    def __init__(self, elements: list[FakeEntity]):
        self.elements = elements

    def by_type(self, ifc_type: str):
        if ifc_type == "IfcBuildingElement":
            return [
                entity
                for entity in self.elements
                if entity.is_a() not in {"IfcBuilding", "IfcBuildingStorey", "IfcSpace"}
            ]
        return [entity for entity in self.elements if entity.is_a(ifc_type)]


class FakeTree:
    def __init__(self, intersections=(), clearances=(), error: Exception | None = None):
        self.intersections = intersections
        self.clearances = clearances
        self.error = error

    def clash_intersection_many(self, *_):
        if self.error:
            raise self.error
        return self.intersections

    def clash_clearance_many(self, *_):
        if self.error:
            raise self.error
        return self.clearances


class TopologyServiceTests(unittest.TestCase):
    def test_intersections_are_deduplicated_and_preserve_candidate_order(self):
        source = FakeEntity("IfcWall", "source")
        candidate_a = FakeEntity("IfcDoor", "a")
        candidate_b = FakeEntity("IfcDoor", "b")
        tree = FakeTree(
            intersections=[
                SimpleNamespace(a=source, b=candidate_b),
                SimpleNamespace(a=candidate_a, b=source),
                SimpleNamespace(a=source, b=candidate_a),
            ]
        )

        result_ids = TopologyService()._resolve_related_ids(
            tree,
            source,
            [candidate_a, candidate_b],
            "intersects",
        )

        self.assertEqual(result_ids, ["a", "b"])

    def test_adjacent_uses_clearance_results(self):
        source = FakeEntity("IfcWall", "source")
        candidate = FakeEntity("IfcDoor", "candidate")
        tree = FakeTree(clearances=[SimpleNamespace(a=source, b=candidate)])

        result_ids = TopologyService()._resolve_related_ids(
            tree,
            source,
            [candidate],
            "adjacent",
        )

        self.assertEqual(result_ids, ["candidate"])

    def test_tree_errors_return_empty_relations(self):
        source = FakeEntity("IfcWall", "source")
        candidate = FakeEntity("IfcDoor", "candidate")
        tree = FakeTree(error=RuntimeError("no geometry"))

        result_ids = TopologyService()._resolve_related_ids(
            tree,
            source,
            [candidate],
            "intersects",
        )

        self.assertEqual(result_ids, [])

    def test_model_tree_build_errors_return_empty_relations(self):
        service = TopologyService()
        source = FakeEntity("IfcWall", "source")
        candidate = FakeEntity("IfcDoor", "candidate")

        with patch.object(
            service,
            "_model_topology",
            side_effect=RuntimeError("tree failed"),
        ):
            result = service.intersects(object(), source, [candidate])

        self.assertEqual(result, [])


class TopologyResolverTests(unittest.TestCase):
    def test_element_intersects_applies_element_query_to_candidates(self):
        source = FakeEntity("IfcWall", "source")
        wall = FakeEntity("IfcWall", "wall")
        door = FakeEntity("IfcDoor", "door")
        model = FakeModel([source, wall, door])
        obj = {
            "_ifc": source,
            "_ifc_model": model,
            "_model_name": "demo",
            "_geometry_base_url": "http://example.test/models/demo/elements/",
            "_geometry_elements_dir": "/tmp/elements",
        }

        with patch("api.ifc.helpers.el.get_psets", return_value={}), patch(
            "api.gql.resolvers.topology_service.intersects",
            return_value=[door],
        ) as intersects:
            result = resolvers.resolve_element_intersects(
                obj,
                None,
                where={"type": "Door"},
            )

        candidates = intersects.call_args.args[2]
        self.assertEqual(candidates, [door])
        self.assertEqual(result[0]["guid"], "door")

    def test_zone_adjacent_applies_zone_query_to_candidates(self):
        source = FakeEntity("IfcSpace", "source", "Room A")
        space_a = FakeEntity("IfcSpace", "space-a", "Room A")
        space_b = FakeEntity("IfcSpace", "space-b", "Room B")
        building = FakeEntity("IfcBuilding", "building", "Building")
        model = FakeModel([source, space_a, space_b, building])
        obj = {
            "_ifc": source,
            "_ifc_model": model,
            "_model_name": "demo",
            "_geometry_base_url": "http://example.test/models/demo/elements/",
            "_geometry_elements_dir": "/tmp/elements",
        }

        with patch(
            "api.gql.resolvers.topology_service.adjacent",
            return_value=[space_a],
        ) as adjacent:
            result = resolvers.resolve_zone_adjacent(
                obj,
                None,
                where={"search": "Room A"},
            )

        candidates = adjacent.call_args.args[2]
        self.assertEqual(candidates, [source, space_a])
        self.assertEqual(result[0]["id"], "space-a")


if __name__ == "__main__":
    unittest.main()
