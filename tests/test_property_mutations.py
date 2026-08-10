from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import ANY, patch

from ariadne import graphql_sync
from graphql import GraphQLError
import ifcopenshell
from ifcopenshell.api.pset import add_pset, edit_pset
from ifcopenshell.api.root import create_entity
from ifcopenshell.api.type import assign_type
from ifcopenshell.util.element import get_pset

from api.app import schema
from api.gql.resolvers.mutations.properties import resolve_patch_properties


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


class PropertyPatchMutationTests(unittest.TestCase):
    def setUp(self):
        self.model = ifcopenshell.file(schema="IFC4")
        self.wall = create_entity(self.model, ifc_class="IfcWall", name="Wall")
        self.store = InMemoryModelStore(self.model)
        self.context = {
            "ifc_models": self.store,
            "models_dir": Path("/tmp/models"),
            "models_base_url": "http://example.test/models/",
        }
        self.info = SimpleNamespace(context=self.context)

    def add_properties(self, product, pset_name: str, properties: dict):
        pset = add_pset(self.model, product=product, name=pset_name)
        edit_pset(self.model, pset=pset, properties=properties)
        return pset

    def patch(self, patch_value, *, include_inherited: bool = False):
        return resolve_patch_properties(
            None,
            self.info,
            {
                "guid": self.wall.GlobalId,
                "includeInherited": include_inherited,
                "patch": patch_value,
            },
        )

    def test_patch_updates_adds_and_deletes_properties_and_property_sets(self):
        self.add_properties(
            self.wall,
            "Direct",
            {"Keep": "old", "Remove": True},
        )

        result = self.patch(
            {
                "Direct": {"Keep": "new", "Remove": None, "Added": 12},
                "Created": {"Value": 3.5},
                "AlreadyMissing": None,
            }
        )

        self.assertEqual(
            get_pset(self.wall, "Direct", should_inherit=False),
            {"Keep": "new", "Added": 12, "id": ANY},
        )
        self.assertEqual(
            get_pset(self.wall, "Created", should_inherit=False),
            {"Value": 3.5, "id": ANY},
        )
        self.assertEqual(result["guid"], self.wall.GlobalId)

        self.patch({"Direct": None})
        self.assertIsNone(get_pset(self.wall, "Direct", should_inherit=False))

    def test_deletion_only_patch_does_not_create_a_property_set(self):
        self.patch({"Missing": {"Property": None}})

        self.assertIsNone(get_pset(self.wall, "Missing", should_inherit=False))

    def test_inherited_patch_defaults_to_occurrence_override(self):
        wall_type = create_entity(self.model, ifc_class="IfcWallType", name="Wall type")
        other_wall = create_entity(self.model, ifc_class="IfcWall", name="Other wall")
        assign_type(
            self.model,
            related_objects=[self.wall, other_wall],
            relating_type=wall_type,
        )
        self.add_properties(wall_type, "Shared", {"Value": "type"})

        self.patch({"Shared": {"Value": "occurrence"}})

        self.assertEqual(
            get_pset(self.wall, "Shared", should_inherit=False)["Value"],
            "occurrence",
        )
        self.assertEqual(get_pset(wall_type, "Shared")["Value"], "type")
        self.assertEqual(get_pset(other_wall, "Shared")["Value"], "type")

    def test_include_inherited_updates_the_shared_type_property_set(self):
        wall_type = create_entity(self.model, ifc_class="IfcWallType", name="Wall type")
        other_wall = create_entity(self.model, ifc_class="IfcWall", name="Other wall")
        assign_type(
            self.model,
            related_objects=[self.wall, other_wall],
            relating_type=wall_type,
        )
        self.add_properties(wall_type, "Shared", {"Value": "old"})

        self.patch({"Shared": {"Value": "new"}}, include_inherited=True)

        self.assertIsNone(get_pset(self.wall, "Shared", should_inherit=False))
        self.assertEqual(get_pset(self.wall, "Shared")["Value"], "new")
        self.assertEqual(get_pset(other_wall, "Shared")["Value"], "new")

        self.patch({"Shared": None}, include_inherited=True)
        self.assertIsNone(get_pset(self.wall, "Shared"))
        self.assertIsNone(get_pset(other_wall, "Shared"))

    def test_invalid_patch_is_rejected_before_changes_are_applied(self):
        self.add_properties(self.wall, "Direct", {"Value": "old"})

        invalid_patches = [
            {"Direct": {"Value": "new"}, "Invalid": []},
            {"": {}},
            {"Direct": {"id": 123}},
            [],
        ]
        for invalid_patch in invalid_patches:
            with self.subTest(patch=invalid_patch), self.assertRaises(GraphQLError):
                self.patch(invalid_patch)

        self.assertEqual(get_pset(self.wall, "Direct")["Value"], "old")

    def test_missing_entity_is_reported_as_graphql_error(self):
        with self.assertRaisesRegex(GraphQLError, "was not found"):
            resolve_patch_properties(
                None,
                self.info,
                {"guid": "missing", "patch": {}},
            )

    def test_ifcopenshell_failure_rolls_back_the_complete_patch(self):
        self.add_properties(self.wall, "First", {"Value": "old"})
        real_edit_pset = edit_pset

        def edit_or_fail(model, *, pset, properties, should_purge=True):
            if pset.Name == "Second":
                raise ValueError("unsupported value")
            return real_edit_pset(
                model,
                pset=pset,
                properties=properties,
                should_purge=should_purge,
            )

        with patch(
            "api.gql.resolvers.mutations.properties.edit_pset",
            side_effect=edit_or_fail,
        ), self.assertRaises(GraphQLError):
            self.patch(
                {
                    "First": {"Value": "new"},
                    "Second": {"Value": {"unsupported": True}},
                }
            )

        self.assertEqual(get_pset(self.wall, "First")["Value"], "old")
        self.assertIsNone(get_pset(self.wall, "Second", should_inherit=False))

    def test_patch_executes_through_graphql_and_returns_updated_value(self):
        self.add_properties(self.wall, "Direct", {"Value": "old"})

        success, result = graphql_sync(
            schema,
            {
                "query": """
                    mutation PatchProperties($input: PatchPropertiesInput!) {
                      patchProperties(input: $input) {
                        guid
                        properties(pset: "Direct") { name value pset }
                      }
                    }
                """,
                "variables": {
                    "input": {
                        "guid": self.wall.GlobalId,
                        "patch": {"Direct": {"Value": "new"}},
                    }
                },
            },
            context_value=self.context,
        )

        self.assertTrue(success)
        self.assertEqual(
            result,
            {
                "data": {
                    "patchProperties": {
                        "guid": self.wall.GlobalId,
                        "properties": [
                            {"name": "Value", "value": "new", "pset": "Direct"}
                        ],
                    }
                }
            },
        )


if __name__ == "__main__":
    unittest.main()
