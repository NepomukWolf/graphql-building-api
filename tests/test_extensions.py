from __future__ import annotations

import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ariadne import QueryType, graphql_sync, make_executable_schema

from graphql_building_api.gql.extensions import load_extensions


class ExtensionLoaderTests(unittest.TestCase):
    def test_loads_schema_and_resolvers_from_extension_directory(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            extension_dir = base_dir / "demo-extension"
            extension_dir.mkdir()
            (extension_dir / "schema.graphql").write_text(
                "extend type BuildingElement { dataSheetURL: String }\n",
                encoding="utf-8",
            )
            (extension_dir / "resolvers.py").write_text(
                textwrap.dedent(
                    """
                    from ariadne import ObjectType

                    building_element = ObjectType("BuildingElement")

                    @building_element.field("dataSheetURL")
                    def resolve_data_sheet_url(obj, _info):
                        return f"https://example.org/{obj['guid']}"

                    all_types = [building_element]
                    """
                ),
                encoding="utf-8",
            )

            schemas, bindables = load_extensions(base_dir)

            self.assertEqual(
                schemas, ["extend type BuildingElement { dataSheetURL: String }\n"]
            )
            self.assertEqual(len(bindables), 1)

            query = QueryType()

            @query.field("element")
            def resolve_element(*_):
                return {"guid": "abc"}

            schema = make_executable_schema(
                [
                    "type Query { element: BuildingElement }",
                    "type BuildingElement { guid: ID! }",
                    *schemas,
                ],
                query,
                *bindables,
            )
            success, result = graphql_sync(
                schema,
                {"query": "{ element { guid dataSheetURL } }"},
            )

            self.assertTrue(success)
            self.assertEqual(
                result,
                {
                    "data": {
                        "element": {
                            "guid": "abc",
                            "dataSheetURL": "https://example.org/abc",
                        }
                    }
                },
            )

    def test_ignores_extension_directories_without_schema(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            (base_dir / "not-an-extension").mkdir()

            schemas, bindables = load_extensions(base_dir)

            self.assertEqual(schemas, [])
            self.assertEqual(bindables, [])

    def test_missing_extension_directory_is_empty(self):
        schemas, bindables = load_extensions(Path("/definitely/not/a/real/path"))

        self.assertEqual(schemas, [])
        self.assertEqual(bindables, [])

    def test_skips_disabled_extension_directory(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            enabled = base_dir / "enabled"
            disabled = base_dir / "disabled"
            enabled.mkdir()
            disabled.mkdir()
            (enabled / "schema.graphql").write_text(
                "extend type Query { enabled: String }\n",
                encoding="utf-8",
            )
            (disabled / "schema.graphql").write_text(
                "extend type Query { disabled: String }\n",
                encoding="utf-8",
            )

            schemas, bindables = load_extensions(base_dir, disabled={"disabled"})

            self.assertEqual(schemas, ["extend type Query { enabled: String }\n"])
            self.assertEqual(bindables, [])

    def test_shipped_lca_extension_resolves_data_sheet_url(self):
        project_root = Path(__file__).resolve().parents[1]
        schemas, bindables = load_extensions(
            project_root / "graphql_building_api" / "extensions",
            disabled={"geometry_representations"},
        )
        query = QueryType()

        @query.field("element")
        def resolve_element(*_):
            return {"guid": "abc", "type": "IfcWall"}

        schema = make_executable_schema(
            [
                "type Query { element: BuildingElement }",
                "type BuildingElement { guid: ID!, type: String }",
                *schemas,
            ],
            query,
            *bindables,
        )
        success, result = graphql_sync(
            schema,
            {"query": "{ element { guid type dataSheetURL } }"},
        )

        self.assertTrue(success)
        self.assertEqual(
            result["data"]["element"],
            {
                "guid": "abc",
                "type": "IfcWall",
                "dataSheetURL": "https://example.org/product-data/ifc-wall",
            },
        )


if __name__ == "__main__":
    unittest.main()
