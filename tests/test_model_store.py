from __future__ import annotations

import unittest
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from fastapi.testclient import TestClient
import ifcopenshell

import graphql_building_api.app as app_module
from graphql_building_api.config import CONFIG
from graphql_building_api.ifc.models import IfcModelStore


class IfcModelStoreTests(unittest.TestCase):
    def test_repository_default_model_is_the_sample_model(self):
        self.assertEqual(CONFIG.default_model, "2026-SampleModel")

    def test_empty_models_directory_constructs_and_lists_no_models(self):
        with TemporaryDirectory() as temp_dir:
            store = IfcModelStore(Path(temp_dir), "example-model")

            self.assertEqual(store.available_models(), [])

    def test_missing_default_model_is_loaded_lazily(self):
        with TemporaryDirectory() as temp_dir:
            store = IfcModelStore(Path(temp_dir), "example-model")

            with self.assertRaises(FileNotFoundError):
                store.get()

    def test_available_models_returns_named_ifc_folders(self):
        with TemporaryDirectory() as temp_dir:
            models_dir = Path(temp_dir)
            model_dir = models_dir / "my-model"
            model_dir.mkdir()
            (model_dir / "my-model.ifc").write_text("ISO-10303-21;", encoding="utf-8")
            (models_dir / "ignored").mkdir()

            store = IfcModelStore(models_dir, "my-model")

            self.assertEqual(store.available_models(), ["my-model"])

    def test_model_name_cannot_escape_models_directory(self):
        with TemporaryDirectory() as temp_dir:
            store = IfcModelStore(Path(temp_dir), "example-model")

            with self.assertRaises(ValueError):
                store.get("../secret")

    def test_existing_model_loads_when_requested(self):
        with TemporaryDirectory() as temp_dir:
            models_dir = Path(temp_dir)
            model_dir = models_dir / "my-model"
            model_dir.mkdir()
            model_path = model_dir / "my-model.ifc"
            model_path.write_text("ISO-10303-21;", encoding="utf-8")
            store = IfcModelStore(models_dir, "example-model")

            with patch("graphql_building_api.ifc.models.ifcopenshell.open", return_value="loaded") as open_ifc:
                self.assertEqual(store.get("my-model"), "loaded")

            open_ifc.assert_called_once_with(str(model_path))


class ModelGraphQLTests(unittest.TestCase):
    def test_schema_exposes_flattened_model_query(self):
        with TemporaryDirectory() as temp_dir:
            store = IfcModelStore(Path(temp_dir), "example-model")
            response = TestClient(app_module.create_app(store, app_module.schema)).post(
                "/graphql",
                json={"query": "{ __schema { queryType { fields { name } } } }"},
            )

        self.assertEqual(response.status_code, 200)
        fields = {
            field["name"]
            for field in response.json()["data"]["__schema"]["queryType"]["fields"]
        }
        self.assertEqual(fields, {"modelId", "building", "storeys", "spaces", "elements"})
        self.assertIsNone(app_module.schema.get_type("Model"))
        self.assertIsNone(app_module.schema.get_type("ModelInfo"))
        self.assertNotIn(
            "model",
            app_module.schema.get_type("UpdatePropertyInput").fields,
        )
        self.assertNotIn(
            "model",
            app_module.schema.get_type("PatchPropertiesInput").fields,
        )

    def test_default_and_scoped_routes_select_the_model(self):
        with TemporaryDirectory() as temp_dir:
            models_dir = Path(temp_dir)
            for model_id in ("default", "selected"):
                model_dir = models_dir / model_id
                model_dir.mkdir()
                ifcopenshell.file(schema="IFC4").write(
                    str(model_dir / f"{model_id}.ifc")
                )
            store = IfcModelStore(models_dir, "default")
            client = TestClient(app_module.create_app(store, app_module.schema))

            default = client.post("/graphql", json={"query": "{ modelId }"})
            selected = client.post(
                "/models/selected/graphql",
                json={"query": "{ modelId }"},
            )

        self.assertEqual(default.json(), {"data": {"modelId": "default"}})
        self.assertEqual(selected.json(), {"data": {"modelId": "selected"}})

    def test_graphql_missing_model_returns_clear_error(self):
        with TemporaryDirectory() as temp_dir:
            store = IfcModelStore(Path(temp_dir), "example-model")
            logging.disable(logging.ERROR)
            try:
                response = TestClient(app_module.create_app(store, app_module.schema)).post(
                    "/graphql",
                    json={"query": "{ modelId }"},
                )
            finally:
                logging.disable(logging.NOTSET)

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(body["data"])
        self.assertIn("IFC model 'example-model' is not available", body["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main()
