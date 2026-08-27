from __future__ import annotations

import unittest
from pathlib import Path

from ariadne import graphql_sync
import ifcopenshell
from ifcopenshell.api.pset import add_pset, edit_pset
from ifcopenshell.api.root import create_entity

from graphql_building_api.ifc.helpers import get_properties
from graphql_building_api.app import schema


class InMemoryModelStore:
    def __init__(self, model):
        self.model = model
        self.default_model = "demo"

    def get(self, _model_name=None):
        return self.model

    def model_folder_name(self, model_name=None):
        return model_name or self.default_model

    def available_models(self):
        return [self.default_model]


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

    def test_property_name_filters_across_all_property_sets(self):
        self.assertEqual(
            get_properties(self.wall, property_name="IsExternal"),
            [
                {
                    "name": "IsExternal",
                    "value": True,
                    "pset": "Pset_WallCommon",
                }
            ],
        )

    def test_pset_and_property_name_filters_use_and_semantics(self):
        self.assertEqual(
            get_properties(
                self.wall,
                "Company_Environmental",
                "CarbonFactor",
            ),
            [
                {
                    "name": "CarbonFactor",
                    "value": 12.5,
                    "pset": "Company_Environmental",
                }
            ],
        )
        self.assertEqual(
            get_properties(
                self.wall,
                "Company_Environmental",
                "IsExternal",
            ),
            [],
        )

    def test_name_filter_returns_duplicate_names_from_different_psets(self):
        duplicate_set = add_pset(
            self.model,
            product=self.wall,
            name="Company_Duplicate",
        )
        edit_pset(
            self.model,
            pset=duplicate_set,
            properties={"IsExternal": False},
        )

        self.assertCountEqual(
            get_properties(self.wall, property_name="IsExternal"),
            [
                {
                    "name": "IsExternal",
                    "value": True,
                    "pset": "Pset_WallCommon",
                },
                {
                    "name": "IsExternal",
                    "value": False,
                    "pset": "Company_Duplicate",
                },
            ],
        )

    def test_missing_property_name_returns_empty_list(self):
        self.assertEqual(
            get_properties(self.wall, property_name="DoesNotExist"),
            [],
        )

    def test_property_name_filter_executes_through_graphql(self):
        success, result = graphql_sync(
            schema,
            {
                "query": f"""
                    query {{
                      elements(where: {{ id: \"{self.wall.GlobalId}\" }}) {{
                        properties(name: \"IsExternal\") {{
                          name value pset
                        }}
                      }}
                    }}
                """
            },
            context_value={
                "ifc_models": InMemoryModelStore(self.model),
                "models_dir": Path("/tmp/models"),
                "models_base_url": "http://example.test/models/",
            },
        )

        self.assertTrue(success)
        self.assertEqual(
            result,
            {
                "data": {
                    "elements": [
                        {
                            "properties": [
                                {
                                    "name": "IsExternal",
                                    "value": True,
                                    "pset": "Pset_WallCommon",
                                }
                            ]
                        }
                    ]
                }
            },
        )


if __name__ == "__main__":
    unittest.main()
