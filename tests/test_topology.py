from __future__ import annotations

import unittest
from unittest.mock import patch

from api.gql.resolvers.types.elements import resolve_element_intersects
from api.gql.resolvers.types.zones import resolve_zone_adjacent
from api.ifc.topology import BoundingBox, TopologyService, boxes_adjacent, boxes_intersect


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


class TopologyServiceTests(unittest.TestCase):
    def test_boxes_intersect_when_all_axes_overlap_with_positive_volume(self):
        box_a = BoundingBox(0, 0, 0, 2, 2, 2)
        box_b = BoundingBox(1, 1, 1, 3, 3, 3)
        box_c = BoundingBox(2, 1, 1, 3, 3, 3)

        self.assertTrue(boxes_intersect(box_a, box_b))
        self.assertFalse(boxes_intersect(box_a, box_c))

    def test_boxes_adjacent_when_close_on_one_axis_and_overlapping_on_others(self):
        box_a = BoundingBox(0, 0, 0, 1, 1, 1)
        adjacent_box = BoundingBox(1.03, 0.2, 0.2, 2, 0.8, 0.8)
        far_box = BoundingBox(1.10, 0.2, 0.2, 2, 0.8, 0.8)
        intersecting_box = BoundingBox(0.5, 0.2, 0.2, 2, 0.8, 0.8)

        self.assertTrue(boxes_adjacent(box_a, adjacent_box))
        self.assertFalse(boxes_adjacent(box_a, far_box))
        self.assertFalse(boxes_adjacent(box_a, intersecting_box))

    def test_intersections_preserve_candidate_order(self):
        source = FakeEntity("IfcWall", "source")
        candidate_a = FakeEntity("IfcDoor", "a")
        candidate_b = FakeEntity("IfcDoor", "b")
        topology = TopologyService()

        with patch.object(
            topology,
            "_compute_box",
            side_effect=[
                BoundingBox(0, 0, 0, 2, 2, 2),
                BoundingBox(3, 3, 3, 4, 4, 4),
                BoundingBox(1, 1, 1, 3, 3, 3),
            ],
        ):
            result = topology.intersects(object(), source, [candidate_a, candidate_b])

        self.assertEqual(result, [candidate_b])

    def test_adjacent_uses_bounding_box_clearance(self):
        source = FakeEntity("IfcWall", "source")
        candidate = FakeEntity("IfcDoor", "candidate")
        topology = TopologyService()
        model = object()

        with patch.object(
            topology,
            "_compute_box",
            side_effect=[
                BoundingBox(0, 0, 0, 1, 1, 1),
                BoundingBox(1.03, 0, 0, 2, 1, 1),
            ],
        ):
            result = topology.adjacent(object(), source, [candidate])

        self.assertEqual(result, [candidate])

    def test_geometry_errors_return_empty_relations(self):
        source = FakeEntity("IfcWall", "source")
        candidate = FakeEntity("IfcDoor", "candidate")
        topology = TopologyService()

        with patch.object(topology, "_compute_box", return_value=None):
            result = topology.intersects(object(), source, [candidate])

        self.assertEqual(result, [])

    def test_computed_boxes_are_cached(self):
        source = FakeEntity("IfcWall", "source")
        candidate = FakeEntity("IfcDoor", "candidate")
        topology = TopologyService()
        model = object()

        with patch.object(
            topology,
            "_compute_box",
            side_effect=[
                BoundingBox(0, 0, 0, 1, 1, 1),
                BoundingBox(0.5, 0.5, 0.5, 2, 2, 2),
            ],
        ) as compute_box:
            topology.intersects(model, source, [candidate])
            topology.intersects(model, source, [candidate])

        self.assertEqual(compute_box.call_count, 2)


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
            "api.gql.resolvers.types.elements.topology_service.intersects",
            return_value=[door],
        ) as intersects:
            result = resolve_element_intersects(
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
            "api.gql.resolvers.types.zones.topology_service.adjacent",
            return_value=[space_a],
        ) as adjacent:
            result = resolve_zone_adjacent(
                obj,
                None,
                where={"search": "Room A"},
            )

        candidates = adjacent.call_args.args[2]
        self.assertEqual(candidates, [source, space_a])
        self.assertEqual(result[0]["id"], "space-a")


if __name__ == "__main__":
    unittest.main()
