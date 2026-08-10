from __future__ import annotations

import unittest

import ifcopenshell
from ifcopenshell.api.pset import add_pset, edit_pset
from ifcopenshell.api.root import create_entity

from api.ifc.helpers import get_properties


class ElementPropertiesTests(unittest.TestCase):
    def setUp(self):
        self.model = ifcopenshell.file(schema="IFC4")
        self.wall = create_entity(self.model, ifc_class="IfcWall", name="Wall")

        wall_common = add_pset(
            self.model,
            product=self.wall,
            name="Pset_WallCommon",
        )
        edit_pset(
            self.model,
            pset=wall_common,
            properties={"IsExternal": True},
        )

        environmental = add_pset(
            self.model,
            product=self.wall,
            name="Company_Environmental",
        )
        edit_pset(
            self.model,
            pset=environmental,
            properties={"CarbonFactor": 12.5},
        )

    def test_omitted_pset_returns_properties_from_all_property_sets(self):
        self.assertCountEqual(
            get_properties(self.wall),
            [
                {
                    "name": "IsExternal",
                    "value": True,
                    "pset": "Pset_WallCommon",
                },
                {
                    "name": "CarbonFactor",
                    "value": 12.5,
                    "pset": "Company_Environmental",
                },
            ],
        )

    def test_named_pset_returns_only_that_property_set(self):
        self.assertEqual(
            get_properties(self.wall, "Company_Environmental"),
            [
                {
                    "name": "CarbonFactor",
                    "value": 12.5,
                    "pset": "Company_Environmental",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
