from __future__ import annotations

import unittest
from pathlib import Path

from ariadne import QueryType, graphql_sync, make_executable_schema
import ifcopenshell
from ifcopenshell.api.root import create_entity

from graphql_building_api.extensions.geometry_representations.resolvers import (
    all_types as representation_types,
    normalized_representations,
)
from graphql_building_api.gql.extensions import load_extensions


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS_DIR = PROJECT_ROOT / "graphql_building_api" / "extensions"


class GeometryFixture:
    def __init__(self, millimetres: bool = False):
        self.model = ifcopenshell.file(schema="IFC4")
        if millimetres:
            length_unit = self.model.create_entity(
                "IfcSIUnit",
                UnitType="LENGTHUNIT",
                Prefix="MILLI",
                Name="METRE",
            )
            units = self.model.create_entity("IfcUnitAssignment", Units=[length_unit])
            self.model.create_entity(
                "IfcProject",
                GlobalId="0YvctVUKr0kugbFTf53O9L",
                Name="Test project",
                UnitsInContext=units,
            )

        self.context = self.model.create_entity(
            "IfcGeometricRepresentationContext",
            ContextIdentifier="Model",
            ContextType="Model",
            CoordinateSpaceDimension=3,
            Precision=1e-5,
            WorldCoordinateSystem=self.axis3(),
        )

    def point2(self, x: float = 0, y: float = 0):
        return self.model.create_entity("IfcCartesianPoint", (float(x), float(y)))

    def point3(self, x: float = 0, y: float = 0, z: float = 0):
        return self.model.create_entity(
            "IfcCartesianPoint",
            (float(x), float(y), float(z)),
        )

    def axis2(self, x: float = 0, y: float = 0, direction=(1.0, 0.0)):
        return self.model.create_entity(
            "IfcAxis2Placement2D",
            Location=self.point2(x, y),
            RefDirection=self.model.create_entity("IfcDirection", direction),
        )

    def axis3(self, x: float = 0, y: float = 0, z: float = 0):
        return self.model.create_entity(
            "IfcAxis2Placement3D",
            Location=self.point3(x, y, z),
        )

    def rectangle(
        self,
        width: float = 2,
        height: float = 0.2,
        position=None,
    ):
        return self.model.create_entity(
            "IfcRectangleProfileDef",
            ProfileType="AREA",
            ProfileName="Rectangle",
            Position=position,
            XDim=width,
            YDim=height,
        )

    def circle(self, radius: float = 2):
        return self.model.create_entity(
            "IfcCircleProfileDef",
            ProfileType="AREA",
            ProfileName="Circle",
            Position=None,
            Radius=radius,
        )

    def arbitrary_profile(self):
        points = [
            self.point2(0, 0),
            self.point2(1, 0),
            self.point2(1, 1),
            self.point2(0, 0),
        ]
        curve = self.model.create_entity("IfcPolyline", Points=points)
        return self.model.create_entity(
            "IfcArbitraryClosedProfileDef",
            ProfileType="AREA",
            ProfileName="Unsupported",
            OuterCurve=curve,
        )

    def extrusion(self, profile, depth: float = 4, position=None):
        return self.model.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=profile,
            Position=position or self.axis3(),
            ExtrudedDirection=self.model.create_entity(
                "IfcDirection",
                (0.0, 0.0, 1.0),
            ),
            Depth=depth,
        )

    def shape(self, items, identifier: str = "Body", kind: str = "SweptSolid"):
        return self.model.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=self.context,
            RepresentationIdentifier=identifier,
            RepresentationType=kind,
            Items=items,
        )

    def wall(self, representations, placement=None):
        wall = create_entity(self.model, ifc_class="IfcWall", name="Wall")
        wall.Representation = self.model.create_entity(
            "IfcProductDefinitionShape",
            Representations=representations,
        )
        wall.ObjectPlacement = self.model.create_entity(
            "IfcLocalPlacement",
            RelativePlacement=placement or self.axis3(),
        )
        return wall


class GeometryRepresentationTests(unittest.TestCase):
    def test_rectangle_extrusion_has_normalized_values_and_world_placement(self):
        fixture = GeometryFixture()
        profile = fixture.rectangle(position=fixture.axis2(2, 3, (0.0, 1.0)))
        solid = fixture.extrusion(profile, depth=4, position=fixture.axis3(1, 0, 0))
        wall = fixture.wall([fixture.shape([solid])], fixture.axis3(10, 0, 0))

        representations = normalized_representations(wall)

        self.assertEqual(len(representations), 1)
        result = representations[0]
        self.assertEqual(result["__typename"], "ExtrusionRepresentation")
        self.assertEqual(result["identifier"], "Body")
        self.assertEqual(
            result["profile"],
            {
                "__typename": "RectangleProfile",
                "name": "Rectangle",
                "width": 2.0,
                "height": 0.2,
            },
        )
        self.assertEqual(result["depth"], 4.0)
        self.assertEqual(result["direction"], {"x": 0.0, "y": 0.0, "z": 1.0})
        self.assertEqual(
            result["placement"]["matrix"],
            [
                0.0, -1.0, 0.0, 13.0,
                1.0, 0.0, 0.0, 3.0,
                0.0, 0.0, 1.0, 0.0,
                0.0, 0.0, 0.0, 1.0,
            ],
        )

    def test_circle_and_rectangle_resolve_through_graphql_interfaces(self):
        fixture = GeometryFixture()
        rectangle = fixture.extrusion(fixture.rectangle())
        circle = fixture.extrusion(fixture.circle(), depth=3)
        wall = fixture.wall([fixture.shape([rectangle, circle])])
        extension_schema = (
            EXTENSIONS_DIR / "geometry_representations" / "schema.graphql"
        ).read_text(encoding="utf-8")
        query_type = QueryType()

        @query_type.field("geometry")
        def resolve_geometry(*_):
            return {"_ifc": wall}

        schema = make_executable_schema(
            [
                "type Query { geometry: Geometry! } type Geometry { url: String }",
                extension_schema,
            ],
            query_type,
            *representation_types,
        )
        success, result = graphql_sync(
            schema,
            {
                "query": """
                    {
                      geometry {
                        representations {
                          __typename
                          identifier
                          placement { matrix }
                          ... on ExtrusionRepresentation {
                            depth
                            profile {
                              __typename
                              ... on RectangleProfile { width height }
                              ... on CircleProfile { radius }
                            }
                          }
                        }
                      }
                    }
                """
            },
        )

        self.assertTrue(success)
        values = result["data"]["geometry"]["representations"]
        self.assertEqual(
            [value["profile"]["__typename"] for value in values],
            ["RectangleProfile", "CircleProfile"],
        )
        self.assertEqual(values[1]["profile"]["radius"], 2.0)
        self.assertEqual(len(values[0]["placement"]["matrix"]), 16)

    def test_converts_lengths_and_translation_to_metres(self):
        fixture = GeometryFixture(millimetres=True)
        solid = fixture.extrusion(
            fixture.rectangle(width=2000, height=200),
            depth=4000,
        )
        wall = fixture.wall([fixture.shape([solid])], fixture.axis3(1000, 0, 0))

        result = normalized_representations(wall)[0]

        self.assertEqual(result["profile"]["width"], 2.0)
        self.assertEqual(result["profile"]["height"], 0.2)
        self.assertEqual(result["depth"], 4.0)
        self.assertEqual(result["placement"]["matrix"][3], 1.0)

    def test_resolves_nested_mapped_extrusion_and_composes_instance_transform(self):
        fixture = GeometryFixture()
        solid = fixture.extrusion(
            fixture.circle(),
            depth=3,
            position=fixture.axis3(1, 0, 0),
        )
        source = fixture.shape([solid])
        representation_map = fixture.model.create_entity(
            "IfcRepresentationMap",
            MappingOrigin=fixture.axis3(),
            MappedRepresentation=source,
        )
        target = fixture.model.create_entity(
            "IfcCartesianTransformationOperator3D",
            Axis1=None,
            Axis2=None,
            LocalOrigin=fixture.point3(5, 0, 0),
            Scale=2.0,
            Axis3=None,
        )
        inner_mapped_item = fixture.model.create_entity(
            "IfcMappedItem",
            MappingSource=representation_map,
            MappingTarget=target,
        )
        middle = fixture.shape([inner_mapped_item], kind="MappedRepresentation")
        outer_map = fixture.model.create_entity(
            "IfcRepresentationMap",
            MappingOrigin=fixture.axis3(),
            MappedRepresentation=middle,
        )
        outer_target = fixture.model.create_entity(
            "IfcCartesianTransformationOperator3D",
            Axis1=None,
            Axis2=None,
            LocalOrigin=fixture.point3(3, 0, 0),
            Scale=1.0,
            Axis3=None,
        )
        outer_mapped_item = fixture.model.create_entity(
            "IfcMappedItem",
            MappingSource=outer_map,
            MappingTarget=outer_target,
        )
        outer = fixture.shape([outer_mapped_item], kind="MappedRepresentation")
        wall = fixture.wall([outer], fixture.axis3(10, 0, 0))

        result = normalized_representations(wall)[0]

        self.assertEqual(result["identifier"], "Body")
        self.assertEqual(result["profile"]["__typename"], "CircleProfile")
        self.assertEqual(result["placement"]["matrix"][0], 2.0)
        self.assertEqual(result["placement"]["matrix"][3], 20.0)

    def test_omits_unsupported_items_and_preserves_supported_order(self):
        fixture = GeometryFixture()
        unsupported = fixture.extrusion(fixture.arbitrary_profile())
        first = fixture.extrusion(fixture.rectangle(width=1))
        second = fixture.extrusion(fixture.circle(radius=3))
        wall = fixture.wall(
            [
                fixture.shape([unsupported], identifier="Axis"),
                fixture.shape([first, second], identifier="Body"),
            ]
        )

        representations = normalized_representations(wall)

        self.assertEqual(
            [item["profile"]["__typename"] for item in representations],
            ["RectangleProfile", "CircleProfile"],
        )
        self.assertEqual([item["identifier"] for item in representations], ["Body", "Body"])

    def test_returns_empty_list_without_supported_geometry(self):
        fixture = GeometryFixture()
        wall = fixture.wall(
            [fixture.shape([fixture.extrusion(fixture.arbitrary_profile())])]
        )

        self.assertEqual(normalized_representations(wall), [])

    def test_extension_is_absent_when_disabled(self):
        schemas, bindables = load_extensions(
            EXTENSIONS_DIR,
            disabled={"geometry_representations", "lca-extension"},
        )
        query_type = QueryType()

        @query_type.field("geometry")
        def resolve_geometry(*_):
            return {}

        schema = make_executable_schema(
            [
                "type Query { geometry: Geometry! } type Geometry { url: String }",
                *schemas,
            ],
            query_type,
            *bindables,
        )
        success, result = graphql_sync(
            schema,
            {"query": '{ __type(name: "Geometry") { fields { name } } }'},
        )

        self.assertTrue(success)
        self.assertEqual(result["data"]["__type"]["fields"], [{"name": "url"}])


if __name__ == "__main__":
    unittest.main()
