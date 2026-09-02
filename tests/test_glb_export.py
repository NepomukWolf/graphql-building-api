from __future__ import annotations

import json
import struct

import numpy as np

from graphql_building_api.ifc.geometry import GeometryHandler, pbr_material


class FakeColour:
    def __init__(self, red, green, blue):
        self.values = red, green, blue

    def r(self): return self.values[0]
    def g(self): return self.values[1]
    def b(self): return self.values[2]


class FakeStyle:
    def __init__(self, instance_id, colour, transparency, specularity):
        self._instance_id = instance_id
        self._colour = FakeColour(*colour)
        self.transparency = transparency
        self.specularity = specularity
        self.name = f"rendering-{instance_id}"

    def instance_id(self): return self._instance_id
    def get_color(self): return self._colour


class FakeSurfaceStyle:
    def __init__(self, name, side="BOTH"):
        self.Name = name
        self.Side = side

    def is_a(self, name): return name == "IfcSurfaceStyle"


class FakeFile:
    def __init__(self, styles): self.styles = styles
    def by_id(self, step_id): return self.styles[step_id]
    def get_inverse(self, _entity): return []


class FakeElement:
    def __init__(self, styles): self.file = FakeFile(styles)


class FakeGeometry:
    verts = (0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0)
    faces = (0, 1, 2, 0, 2, 3)
    material_ids = (0, 1)

    def __init__(self, materials): self.materials = materials


def parse_glb(data: bytes) -> dict:
    json_length = struct.unpack_from("<I", data, 12)[0]
    return json.loads(data[20 : 20 + json_length])


def make_handler():
    surfaces = {10: FakeSurfaceStyle("Glass"), 20: FakeSurfaceStyle("Frame")}
    styles = (
        FakeStyle(10, (0.1, 0.4, 0.8), 0.8, 16),
        FakeStyle(20, (0.7, 0.5, 0.2), 0.0, 64),
    )
    handler = GeometryHandler.__new__(GeometryHandler)
    handler.element = FakeElement(surfaces)
    handler.geometry = FakeGeometry(styles)
    handler._generate_mesh()
    return handler


def test_glb_contains_explicit_flat_unit_normals():
    handler = make_handler()
    assert len(handler.scene.geometry) == 2
    for mesh in handler.scene.geometry.values():
        assert mesh.faces.shape == (1, 3)
        assert len(mesh.vertices) == 3
        assert np.allclose(np.linalg.norm(mesh.vertex_normals, axis=1), 1.0)
        assert np.allclose(mesh.vertex_normals, mesh.face_normals[0])

    document = parse_glb(handler.export("glb"))
    assert all(
        "NORMAL" in mesh["primitives"][0]["attributes"]
        for mesh in document["meshes"]
    )


def test_glb_preserves_per_face_ifc_materials():
    document = parse_glb(make_handler().export("glb"))
    materials = {material["name"]: material for material in document["materials"]}
    assert set(materials) == {"Glass", "Frame"}
    glass = materials["Glass"]
    frame = materials["Frame"]
    assert glass["alphaMode"] == "BLEND"
    assert glass["doubleSided"] is True
    assert np.allclose(
        glass["pbrMetallicRoughness"]["baseColorFactor"],
        [0.1, 0.4, 0.8, 0.2],
        atol=1 / 255,
    )
    assert frame["alphaMode"] == "OPAQUE"
    assert frame["pbrMetallicRoughness"]["baseColorFactor"][3] == 1.0
    assert glass["pbrMetallicRoughness"]["metallicFactor"] == 0.0
    assert glass["pbrMetallicRoughness"]["roughnessFactor"] > frame["pbrMetallicRoughness"]["roughnessFactor"]


def test_missing_style_uses_neutral_fallback_material():
    material = pbr_material(FakeElement({}))
    assert material.name == "IFC default material"
    assert material.alphaMode == "OPAQUE"
    assert material.metallicFactor == 0.0
