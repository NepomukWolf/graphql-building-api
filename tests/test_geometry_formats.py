from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

from graphql_building_api.config import GeometryConfig
from graphql_building_api.ifc.geometry_formats import get_geometry_format, normalize_geometry_format
from graphql_building_api.ifc.geometry_service import (
    GENERATED_GEOMETRY_CACHE_VERSION,
    FileGeometryProvider,
    GeometryArtifact,
    GeometryService,
    GeometryRequest,
    GltfGeometryProvider,
    WktGeometryProvider,
    embed_gltf_buffers,
    encode_geometry_payload,
)


class FakeMesh:
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ]
    )
    faces = np.array([[0, 1, 2]])


class FakeGeometryHandler:
    mesh = FakeMesh()

    def __init__(self, _entity):
        pass

    def export(self, file_type: str, **_kwargs):
        if file_type != "gltf":
            raise ValueError(file_type)
        return {
            "model.gltf": json.dumps(
                {
                    "asset": {"version": "2.0"},
                    "buffers": [
                        {
                            "uri": "gltf_buffer_0.bin",
                            "byteLength": 3,
                        }
                    ],
                }
            ).encode("utf-8"),
            "gltf_buffer_0.bin": b"abc",
        }


def geometry_request(format_name: str) -> GeometryRequest:
    return GeometryRequest(
        entity=object(),
        guid="element",
        format_name=format_name,
        elements_dir=Path("/tmp"),
        geometry_base_url="http://example.test/",
        source="MODEL",
        config=GeometryConfig(),
    )


class GeometryFormatTests(unittest.TestCase):
    def test_wkt_and_gltf_formats_normalize(self):
        self.assertEqual(normalize_geometry_format("wkt"), "WKT")
        self.assertEqual(normalize_geometry_format("gltf"), "GLTF")
        self.assertEqual(get_geometry_format("WKT").extension, ".wkt")
        self.assertEqual(get_geometry_format("GLTF").content_type, "model/gltf+json")

    def test_wkt_provider_exports_triangle_geometry_collection(self):
        with patch("graphql_building_api.ifc.geometry_service.GeometryHandler", FakeGeometryHandler):
            artifact = WktGeometryProvider().generate(geometry_request("WKT"))

        self.assertIsNotNone(artifact)
        payload = artifact.data.decode("utf-8")
        self.assertTrue(payload.startswith("GEOMETRYCOLLECTION Z"))
        self.assertIn("POLYGON Z", payload)

    def test_gltf_provider_embeds_external_buffers(self):
        with patch("graphql_building_api.ifc.geometry_service.GeometryHandler", FakeGeometryHandler):
            artifact = GltfGeometryProvider().generate(geometry_request("GLTF"))

        self.assertIsNotNone(artifact)
        payload = json.loads(artifact.data.decode("utf-8"))
        uri = payload["buffers"][0]["uri"]
        self.assertTrue(uri.startswith("data:application/octet-stream;base64,"))
        self.assertNotIn(".bin", artifact.data.decode("utf-8"))

    def test_embed_gltf_buffers_requires_model_file(self):
        with self.assertRaises(ValueError):
            embed_gltf_buffers({"gltf_buffer_0.bin": b"abc"})

    def test_payload_encoding_for_text_and_binary_formats(self):
        self.assertEqual(encode_geometry_payload(b"abc", get_geometry_format("WKT")), "abc")
        self.assertEqual(encode_geometry_payload(b"abc", get_geometry_format("GLTF")), "abc")
        self.assertEqual(encode_geometry_payload(b"abc", get_geometry_format("GLB")), "YWJj")

    def test_generated_cache_requires_matching_version_sidecar(self):
        with TemporaryDirectory() as temporary:
            request = GeometryRequest(
                entity=object(),
                guid="element",
                format_name="GLB",
                elements_dir=Path(temporary),
                geometry_base_url="http://example.test/",
                source="MODEL",
                config=GeometryConfig(cache_generated=True),
            )
            provider = FileGeometryProvider()
            artifact = GeometryArtifact(b"glb", get_geometry_format("GLB"))
            provider.write(request, artifact)
            self.assertFalse(provider.generated_cache_is_current(request))

            provider.write_generated(request, artifact)
            self.assertTrue(provider.generated_cache_is_current(request))
            metadata = json.loads(provider.metadata_path(request).read_text())
            self.assertEqual(metadata["version"], GENERATED_GEOMETRY_CACHE_VERSION)

            metadata["version"] -= 1
            provider.metadata_path(request).write_text(json.dumps(metadata))
            self.assertFalse(provider.generated_cache_is_current(request))

            provider.metadata_path(request).write_text("not json")
            self.assertFalse(provider.generated_cache_is_current(request))

    def test_file_source_accepts_legacy_cache_without_sidecar(self):
        with TemporaryDirectory() as temporary:
            request = replace(
                geometry_request("GLB"),
                elements_dir=Path(temporary),
                source="FILE",
                config=GeometryConfig(allow_dynamic_generation=False),
            )
            service = GeometryService()
            service.file_provider.write(
                request, GeometryArtifact(b"legacy", get_geometry_format("GLB"))
            )
            self.assertEqual(
                service.url(request), "http://example.test/element/geometry.glb"
            )

    def test_model_source_regenerates_legacy_cache_and_writes_sidecar(self):
        with TemporaryDirectory() as temporary:
            request = replace(
                geometry_request("GLB"),
                elements_dir=Path(temporary),
                config=GeometryConfig(cache_generated=True),
            )
            service = GeometryService()
            legacy = GeometryArtifact(b"legacy", get_geometry_format("GLB"))
            generated = GeometryArtifact(b"generated", get_geometry_format("GLB"))
            service.file_provider.write(request, legacy)
            with patch.object(service, "generate", return_value=generated) as generate:
                self.assertEqual(
                    service.url(request), "http://example.test/element/geometry.glb"
                )
            generate.assert_called_once_with(request)
            self.assertEqual(service.file_provider.file_path(request).read_bytes(), b"generated")
            self.assertTrue(service.file_provider.generated_cache_is_current(request))


if __name__ == "__main__":
    unittest.main()
