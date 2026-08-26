from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeometryFormatSpec:
    name: str
    extension: str
    content_type: str
    encoding: str
    is_text: bool
    trimesh_file_type: str | None = None
    trimesh_export_kwargs: dict[str, str] | None = None
    provider_hint: str | None = None


GEOMETRY_FORMATS = {
    "OBJ": GeometryFormatSpec(
        name="OBJ",
        extension=".obj",
        content_type="text/plain",
        encoding="PLAIN",
        is_text=True,
        trimesh_file_type="obj",
    ),
    "GLB": GeometryFormatSpec(
        name="GLB",
        extension=".glb",
        content_type="model/gltf-binary",
        encoding="BASE64",
        is_text=False,
        trimesh_file_type="glb",
    ),
    "GLTF": GeometryFormatSpec(
        name="GLTF",
        extension=".gltf",
        content_type="model/gltf+json",
        encoding="PLAIN",
        is_text=True,
        provider_hint="gltf",
    ),
    "STL": GeometryFormatSpec(
        name="STL",
        extension=".stl",
        content_type="model/stl",
        encoding="BASE64",
        is_text=False,
        trimesh_file_type="stl",
    ),
    "STL_ASCII": GeometryFormatSpec(
        name="STL_ASCII",
        extension=".ascii.stl",
        content_type="model/stl",
        encoding="PLAIN",
        is_text=True,
        trimesh_file_type="stl_ascii",
    ),
    "PLY": GeometryFormatSpec(
        name="PLY",
        extension=".ply",
        content_type="application/octet-stream",
        encoding="BASE64",
        is_text=False,
        trimesh_file_type="ply",
        trimesh_export_kwargs={"encoding": "binary"},
    ),
    "PLY_ASCII": GeometryFormatSpec(
        name="PLY_ASCII",
        extension=".ascii.ply",
        content_type="text/plain",
        encoding="PLAIN",
        is_text=True,
        trimesh_file_type="ply",
        trimesh_export_kwargs={"encoding": "ascii"},
    ),
    "OFF": GeometryFormatSpec(
        name="OFF",
        extension=".off",
        content_type="text/plain",
        encoding="PLAIN",
        is_text=True,
        trimesh_file_type="off",
    ),
    "WKT": GeometryFormatSpec(
        name="WKT",
        extension=".wkt",
        content_type="text/plain",
        encoding="PLAIN",
        is_text=True,
        provider_hint="wkt",
    ),
    "BREP": GeometryFormatSpec(
        name="BREP",
        extension=".brep",
        content_type="application/octet-stream",
        encoding="PLAIN",
        is_text=True,
        provider_hint="opencascade",
    ),
}


def normalize_geometry_format(format_name: str | None) -> str:
    if not format_name:
        return "OBJ"

    normalized = format_name.strip().upper()
    if normalized not in GEOMETRY_FORMATS:
        raise ValueError(f"Unsupported geometry format: {format_name}")
    return normalized


def get_geometry_format(format_name: str | None) -> GeometryFormatSpec:
    return GEOMETRY_FORMATS[normalize_geometry_format(format_name)]
