from __future__ import annotations

import unittest
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import api.app as app_module
from api.ifc.models import IfcModelStore


class IfcModelStoreTests(unittest.TestCase):
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

            with patch("api.ifc.models.ifcopenshell.open", return_value="loaded") as open_ifc:
                self.assertEqual(store.get("my-model"), "loaded")

            open_ifc.assert_called_once_with(str(model_path))


class ModelGraphQLTests(unittest.TestCase):
    def test_graphql_models_query_works_without_local_models(self):
        with TemporaryDirectory() as temp_dir:
            original_store = app_module.ifc_models
            app_module.ifc_models = IfcModelStore(Path(temp_dir), "example-model")
            try:
                response = app_module.app.test_client().post(
                    "/graphql",
                    json={"query": "{ models { name isDefault } }"},
                )
            finally:
                app_module.ifc_models = original_store

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"data": {"models": []}})

    def test_graphql_missing_model_returns_clear_error(self):
        with TemporaryDirectory() as temp_dir:
            original_store = app_module.ifc_models
            app_module.ifc_models = IfcModelStore(Path(temp_dir), "example-model")
            logging.disable(logging.ERROR)
            try:
                response = app_module.app.test_client().post(
                    "/graphql",
                    json={"query": "{ model { name } }"},
                )
            finally:
                logging.disable(logging.NOTSET)
                app_module.ifc_models = original_store

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(body["data"]["model"])
        self.assertIn("IFC model 'example-model' is not available", body["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main()
