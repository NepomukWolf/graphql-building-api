from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from api.config import GeometryConfig
from api.ifc.geometry_formats import get_geometry_format, normalize_geometry_format
from api.ifc.geometry_service import (
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
        with patch("api.ifc.geometry_service.GeometryHandler", FakeGeometryHandler):
            artifact = WktGeometryProvider().generate(geometry_request("WKT"))

        self.assertIsNotNone(artifact)
        payload = artifact.data.decode("utf-8")
        self.assertTrue(payload.startswith("GEOMETRYCOLLECTION Z"))
        self.assertIn("POLYGON Z", payload)

    def test_gltf_provider_embeds_external_buffers(self):
        with patch("api.ifc.geometry_service.GeometryHandler", FakeGeometryHandler):
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


if __name__ == "__main__":
    unittest.main()
