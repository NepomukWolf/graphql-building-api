from __future__ import annotations

import logging
from pathlib import Path
import unittest
from unittest.mock import patch

from ariadne import graphql_sync
import ifcopenshell
from ifcopenshell.api.material import (
    add_constituent,
    add_layer,
    add_material,
    add_material_set,
    add_profile,
    assign_material,
    edit_layer,
)
from ifcopenshell.api.root import create_entity
from ifcopenshell.api.type import assign_type

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


class MaterialResolverTests(unittest.TestCase):
    def setUp(self):
        self.model = ifcopenshell.file(schema="IFC4")
        self.wall = create_entity(self.model, ifc_class="IfcWall", name="Wall")
        self.context = {
            "ifc_models": InMemoryModelStore(self.model),
            "models_dir": Path("/tmp/models"),
            "models_base_url": "http://example.test/models/",
        }

    def query(self, selection: str):
        success, result = graphql_sync(
            schema,
            {
                "query": f"""
                    query {{
                      model {{
                        elements(where: {{ id: \"{self.wall.GlobalId}\" }}) {{
                          materials {{
                            __typename
                            {selection}
                          }}
                        }}
                      }}
                    }}
                """
            },
            context_value=self.context,
        )
        self.assertTrue(success)
        return result

    @staticmethod
    def assignment(result):
        return result["data"]["model"]["elements"][0]["materials"]

    def test_element_without_material_returns_null(self):
        result = self.query("... on Material { id }")

        self.assertIsNone(self.assignment(result))

    def test_direct_material_exposes_identity_category_and_properties(self):
        concrete = add_material(
            self.model,
            name="Concrete",
            category="concrete",
        )
        density = self.model.create_entity(
            "IfcPropertySingleValue",
            Name="Density",
            NominalValue=self.model.create_entity("IfcReal", 2400.0),
        )
        self.model.create_entity(
            "IfcMaterialProperties",
            Name="MaterialData",
            Properties=[density],
            Material=concrete,
        )
        assign_material(
            self.model,
            products=[self.wall],
            type="IfcMaterial",
            material=concrete,
        )

        result = self.query(
            """
            ... on Material {
              id name category
              properties { name value pset }
            }
            """
        )

        self.assertEqual(
            self.assignment(result),
            {
                "__typename": "Material",
                "id": str(concrete.id()),
                "name": "Concrete",
                "category": "concrete",
                "properties": [
                    {"name": "Density", "value": 2400.0, "pset": "MaterialData"}
                ],
            },
        )

    def test_material_properties_support_pset_and_name_filters(self):
        concrete = add_material(self.model, name="Concrete")
        density = self.model.create_entity(
            "IfcPropertySingleValue",
            Name="Density",
            NominalValue=self.model.create_entity("IfcReal", 2400.0),
        )
        conductivity = self.model.create_entity(
            "IfcPropertySingleValue",
            Name="Conductivity",
            NominalValue=self.model.create_entity("IfcReal", 1.7),
        )
        self.model.create_entity(
            "IfcMaterialProperties",
            Name="MaterialData",
            Properties=[density, conductivity],
            Material=concrete,
        )
        assign_material(
            self.model,
            products=[self.wall],
            type="IfcMaterial",
            material=concrete,
        )

        result = self.query(
            """
            ... on Material {
              properties(pset: "MaterialData", name: "Density") {
                name value pset
              }
            }
            """
        )

        self.assertEqual(
            self.assignment(result),
            {
                "__typename": "Material",
                "properties": [
                    {"name": "Density", "value": 2400.0, "pset": "MaterialData"}
                ],
            },
        )

    def test_layer_set_preserves_order_thickness_and_missing_materials(self):
        outside = add_material(self.model, name="Outside")
        inside = add_material(self.model, name="Inside")
        layer_set = add_material_set(
            self.model,
            name="Wall construction",
            set_type="IfcMaterialLayerSet",
        )
        outside_layer = add_layer(
            self.model,
            layer_set=layer_set,
            material=outside,
        )
        inside_layer = add_layer(
            self.model,
            layer_set=layer_set,
            material=inside,
        )
        edit_layer(
            self.model,
            layer=outside_layer,
            attributes={"LayerThickness": 0.12},
        )
        edit_layer(
            self.model,
            layer=inside_layer,
            attributes={"LayerThickness": 0.08},
        )
        missing_layer = self.model.create_entity(
            "IfcMaterialLayer",
            Material=None,
            LayerThickness=0.01,
        )
        layer_set.MaterialLayers = [outside_layer, missing_layer, inside_layer]
        assign_material(
            self.model,
            products=[self.wall],
            type="IfcMaterialLayerSet",
            material=layer_set,
        )

        result = self.query(
            """
            ... on MaterialLayerSet {
              layers { thickness material { name } }
            }
            """
        )

        self.assertEqual(
            self.assignment(result),
            {
                "__typename": "MaterialLayerSet",
                "layers": [
                    {"thickness": 0.12, "material": {"name": "Outside"}},
                    {"thickness": 0.01, "material": None},
                    {"thickness": 0.08, "material": {"name": "Inside"}},
                ],
            },
        )

    def test_inherited_layer_set_usage_is_unwrapped(self):
        wall_type = create_entity(
            self.model,
            ifc_class="IfcWallType",
            name="Wall type",
        )
        assign_type(
            self.model,
            related_objects=[self.wall],
            relating_type=wall_type,
        )
        concrete = add_material(self.model, name="Concrete")
        layer_set = add_material_set(
            self.model,
            name="Concrete wall",
            set_type="IfcMaterialLayerSet",
        )
        layer = add_layer(self.model, layer_set=layer_set, material=concrete)
        edit_layer(
            self.model,
            layer=layer,
            attributes={"LayerThickness": 0.2},
        )
        assign_material(
            self.model,
            products=[wall_type],
            type="IfcMaterialLayerSet",
            material=layer_set,
        )
        assign_material(
            self.model,
            products=[self.wall],
            type="IfcMaterialLayerSetUsage",
        )

        result = self.query(
            """
            ... on MaterialLayerSet {
              layers { thickness material { name } }
            }
            """
        )

        self.assertEqual(
            self.assignment(result),
            {
                "__typename": "MaterialLayerSet",
                "layers": [
                    {"thickness": 0.2, "material": {"name": "Concrete"}}
                ],
            },
        )

    def test_occurrence_material_overrides_inherited_type_material(self):
        wall_type = create_entity(
            self.model,
            ifc_class="IfcWallType",
            name="Wall type",
        )
        assign_type(
            self.model,
            related_objects=[self.wall],
            relating_type=wall_type,
        )
        inherited = add_material(self.model, name="Inherited")
        direct = add_material(self.model, name="Direct")
        assign_material(
            self.model,
            products=[wall_type],
            type="IfcMaterial",
            material=inherited,
        )
        assign_material(
            self.model,
            products=[self.wall],
            type="IfcMaterial",
            material=direct,
        )

        result = self.query("... on Material { name }")

        self.assertEqual(
            self.assignment(result),
            {"__typename": "Material", "name": "Direct"},
        )

    def test_single_constituent_flattens_to_material(self):
        concrete = add_material(self.model, name="Concrete")
        constituent_set = add_material_set(
            self.model,
            name="Single constituent",
            set_type="IfcMaterialConstituentSet",
        )
        add_constituent(
            self.model,
            constituent_set=constituent_set,
            material=concrete,
        )
        assign_material(
            self.model,
            products=[self.wall],
            type="IfcMaterialConstituentSet",
            material=constituent_set,
        )

        result = self.query("... on Material { name }")

        self.assertEqual(
            self.assignment(result),
            {"__typename": "Material", "name": "Concrete"},
        )

    def test_single_profile_flattens_to_material(self):
        steel = add_material(self.model, name="Steel")
        profile_set = add_material_set(
            self.model,
            name="Steel profile",
            set_type="IfcMaterialProfileSet",
        )
        add_profile(
            self.model,
            profile_set=profile_set,
            material=steel,
        )
        assign_material(
            self.model,
            products=[self.wall],
            type="IfcMaterialProfileSet",
            material=profile_set,
        )

        result = self.query("... on Material { name }")

        self.assertEqual(
            self.assignment(result),
            {"__typename": "Material", "name": "Steel"},
        )

    def test_single_material_list_entry_flattens_to_material(self):
        timber = add_material(self.model, name="Timber")
        material_list = add_material_set(
            self.model,
            set_type="IfcMaterialList",
        )
        material_list.Materials = [timber]
        assign_material(
            self.model,
            products=[self.wall],
            type="IfcMaterialList",
            material=material_list,
        )

        result = self.query("... on Material { name }")

        self.assertEqual(
            self.assignment(result),
            {"__typename": "Material", "name": "Timber"},
        )

    def test_multiple_constituents_become_synthetic_layers(self):
        concrete = add_material(self.model, name="Concrete")
        steel = add_material(self.model, name="Steel")
        constituent_set = add_material_set(
            self.model,
            name="Composite",
            set_type="IfcMaterialConstituentSet",
        )
        add_constituent(
            self.model,
            constituent_set=constituent_set,
            material=concrete,
        )
        add_constituent(
            self.model,
            constituent_set=constituent_set,
            material=steel,
        )
        assign_material(
            self.model,
            products=[self.wall],
            type="IfcMaterialConstituentSet",
            material=constituent_set,
        )

        result = self.query(
            """
            ... on MaterialLayerSet {
              layers { thickness material { name } }
            }
            """
        )

        self.assertEqual(
            self.assignment(result),
            {
                "__typename": "MaterialLayerSet",
                "layers": [
                    {"thickness": None, "material": {"name": "Concrete"}},
                    {"thickness": None, "material": {"name": "Steel"}},
                ],
            },
        )

    def test_unnamed_material_raises_clear_graphql_error(self):
        class UnnamedMaterial:
            Name = None

            @staticmethod
            def is_a(ifc_type=None):
                return "IfcMaterial" if ifc_type is None else ifc_type == "IfcMaterial"

            @staticmethod
            def id():
                return 42

        logging.disable(logging.ERROR)
        try:
            with patch(
                "graphql_building_api.gql.resolvers.types.materials.el.get_material",
                return_value=UnnamedMaterial(),
            ):
                result = self.query("... on Material { name }")
        finally:
            logging.disable(logging.NOTSET)

        self.assertIsNone(self.assignment(result))
        self.assertIn(
            "IFC material #42 has no name",
            result["errors"][0]["message"],
        )


if __name__ == "__main__":
    unittest.main()
