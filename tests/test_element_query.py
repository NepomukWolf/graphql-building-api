from __future__ import annotations

import unittest
from unittest.mock import patch

from graphql import GraphQLError

from graphql_building_api.gql.resolvers.selection import apply_element_query
from graphql_building_api.ifc.helpers import matches_element_filters


class FakeEntity:
    def __init__(self, ifc_type: str, guid: str, name: str | None = None):
        self._ifc_type = ifc_type
        self.GlobalId = guid
        self.Name = name

    def is_a(self, ifc_type: str | None = None):
        if ifc_type is None:
            return self._ifc_type
        return self._ifc_type == ifc_type


class ElementFilterTests(unittest.TestCase):
    def test_external_internal_and_load_bearing_filters_match_explicit_booleans(self):
        entity = FakeEntity("IfcWall", "wall")
        with patch(
            "graphql_building_api.ifc.helpers.el.get_psets",
            return_value={
                "Pset_WallCommon": {
                    "id": 1,
                    "IsExternal": True,
                    "LoadBearing": True,
                }
            },
        ):
            self.assertTrue(matches_element_filters(entity, ["EXTERNAL"]))
            self.assertTrue(matches_element_filters(entity, ["LOAD_BEARING"]))
            self.assertTrue(matches_element_filters(entity, ["EXTERNAL", "LOAD_BEARING"]))
            self.assertFalse(matches_element_filters(entity, ["INTERNAL"]))

    def test_internal_filter_matches_explicit_false(self):
        entity = FakeEntity("IfcWall", "wall")
        with patch(
            "graphql_building_api.ifc.helpers.el.get_psets",
            return_value={"Pset_WallCommon": {"IsExternal": False}},
        ):
            self.assertTrue(matches_element_filters(entity, ["INTERNAL"]))
            self.assertFalse(matches_element_filters(entity, ["EXTERNAL"]))

    def test_missing_properties_do_not_match_semantic_filters(self):
        entity = FakeEntity("IfcWall", "wall")
        with patch("graphql_building_api.ifc.helpers.el.get_psets", return_value={}):
            self.assertFalse(matches_element_filters(entity, ["EXTERNAL"]))
            self.assertFalse(matches_element_filters(entity, ["INTERNAL"]))
            self.assertFalse(matches_element_filters(entity, ["LOAD_BEARING"]))
            self.assertFalse(matches_element_filters(entity, ["FIRE_RATED"]))

    def test_fire_rated_filter_matches_non_empty_fire_rating(self):
        entity = FakeEntity("IfcDoor", "door")
        with patch(
            "graphql_building_api.ifc.helpers.el.get_psets",
            return_value={"Pset_DoorCommon": {"FireRating": "EI30"}},
        ):
            self.assertTrue(matches_element_filters(entity, ["FIRE_RATED"]))


class ElementSelectorTests(unittest.TestCase):
    def test_selector_is_scoped_to_filtered_candidates_and_preserves_order(self):
        wall_a = FakeEntity("IfcWall", "wall-a", "Alpha")
        wall_b = FakeEntity("IfcWall", "wall-b", "Beta")
        door = FakeEntity("IfcDoor", "door", "Door")
        candidates = [wall_a, door, wall_b]

        with patch("graphql_building_api.ifc.helpers.el.get_psets", return_value={}), patch(
            "graphql_building_api.gql.resolvers.selection.selector.filter_elements",
            return_value={wall_b, wall_a},
        ) as filter_elements:
            result = apply_element_query(
                object(),
                candidates,
                {"type": "Wall", "selector": "IfcWall"},
            )

        self.assertEqual(result, [wall_a, wall_b])
        _ifc_model, selector_query = filter_elements.call_args.args[:2]
        scoped_elements = filter_elements.call_args.kwargs["elements"]
        self.assertEqual(selector_query, "IfcWall")
        self.assertEqual(scoped_elements, {wall_a, wall_b})

    def test_invalid_selector_raises_graphql_error(self):
        wall = FakeEntity("IfcWall", "wall")

        with patch("graphql_building_api.ifc.helpers.el.get_psets", return_value={}), patch(
            "graphql_building_api.gql.resolvers.selection.selector.filter_elements",
            side_effect=ValueError("bad selector"),
        ):
            with self.assertRaises(GraphQLError):
                apply_element_query(
                    object(),
                    [wall],
                    {"selector": "???"},
                )


if __name__ == "__main__":
    unittest.main()
