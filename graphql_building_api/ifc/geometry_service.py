from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urljoin

import ifcopenshell.entity_instance
from shapely.geometry import GeometryCollection, Polygon
from shapely import to_wkt

from graphql_building_api.config import GeometryConfig

from .geometry import GeometryHandler
from .geometry_formats import GeometryFormatSpec, get_geometry_format


@dataclass(frozen=True)
class GeometryArtifact:
    data: bytes
    format: GeometryFormatSpec


@dataclass(frozen=True)
class GeometryRequest:
    entity: ifcopenshell.entity_instance
    guid: str
    format_name: str
    elements_dir: Path
    geometry_base_url: str
    source: str
    config: GeometryConfig

    @property
    def format(self) -> GeometryFormatSpec:
        return get_geometry_format(self.format_name)


class FileGeometryProvider:
    def file_name(self, request: GeometryRequest) -> str:
        return f"geometry{request.format.extension}"

    def file_path(self, request: GeometryRequest) -> Path:
        return request.elements_dir / request.guid / self.file_name(request)

    def url(self, request: GeometryRequest) -> str | None:
        if not self.file_path(request).is_file():
            return None

        return self.url_for(request)

    def url_for(self, request: GeometryRequest) -> str:
        base = (
            request.geometry_base_url
            if request.geometry_base_url.endswith("/")
            else request.geometry_base_url + "/"
        )
        relative_url = f"{quote(request.guid, safe='')}/{quote(self.file_name(request))}"
        return urljoin(base, relative_url)

    def read(self, request: GeometryRequest) -> GeometryArtifact | None:
        path = self.file_path(request)
        if not path.is_file():
            return None

        return GeometryArtifact(path.read_bytes(), request.format)

    def write(self, request: GeometryRequest, artifact: GeometryArtifact) -> Path:
        path = self.file_path(request)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(artifact.data)
        return path


class TrimeshGeometryProvider:
    def generate(self, request: GeometryRequest) -> GeometryArtifact | None:
        if not request.format.trimesh_file_type:
            return None

        try:
            handler = GeometryHandler(request.entity)
            data = handler.export(
                request.format.trimesh_file_type,
                **(request.format.trimesh_export_kwargs or {}),
            )
        except Exception:
            return None

        if isinstance(data, str):
            data = data.encode("utf-8")
        return GeometryArtifact(data, request.format)


class GltfGeometryProvider:
    def generate(self, request: GeometryRequest) -> GeometryArtifact | None:
        if request.format.provider_hint != "gltf":
            return None

        try:
            handler = GeometryHandler(request.entity)
            exported = handler.export("gltf")
            if not isinstance(exported, dict):
                return None
            data = embed_gltf_buffers(exported)
        except Exception:
            return None

        return GeometryArtifact(data, request.format)


class WktGeometryProvider:
    def generate(self, request: GeometryRequest) -> GeometryArtifact | None:
        if request.format.provider_hint != "wkt":
            return None

        try:
            handler = GeometryHandler(request.entity)
            triangles = [
                Polygon([handler.mesh.vertices[index] for index in face])
                for face in handler.mesh.faces
            ]
            data = to_wkt(GeometryCollection(triangles), output_dimension=3).encode(
                "utf-8"
            )
        except Exception:
            return None

        return GeometryArtifact(data, request.format)


class OpenCascadeGeometryProvider:
    def generate(self, request: GeometryRequest) -> GeometryArtifact | None:
        if request.format.provider_hint != "opencascade":
            return None

        # Placeholder for future exact-shape export, e.g. BREP via OpenCascade.
        return None


class GeometryService:
    def __init__(self):
        self.file_provider = FileGeometryProvider()
        self.generation_providers = [
            OpenCascadeGeometryProvider(),
            GltfGeometryProvider(),
            WktGeometryProvider(),
            TrimeshGeometryProvider(),
        ]

    def url(self, request: GeometryRequest) -> str | None:
        if request.source == "FILE":
            existing_url = self.file_provider.url(request)
            if existing_url:
                return existing_url
            if not request.config.allow_dynamic_generation:
                return None
            if not request.config.cache_generated:
                return None

            artifact = self.generate(request)
            if artifact is None:
                return None
            self.file_provider.write(request, artifact)
            return self.file_provider.url_for(request)

        if request.source == "MODEL":
            if not request.config.allow_dynamic_generation:
                return None
            if not request.config.cache_generated:
                return None

            artifact = self.generate(request)
            if artifact is None:
                return None
            self.file_provider.write(request, artifact)
            return self.file_provider.url_for(request)

        return None

    def payload(self, request: GeometryRequest) -> str | None:
        artifact = None
        if request.source == "FILE":
            artifact = self.file_provider.read(request)
            if artifact is None and request.config.allow_dynamic_generation:
                artifact = self.generate(request)
        elif request.source == "MODEL" and request.config.allow_dynamic_generation:
            artifact = self.generate(request)

        if artifact is None:
            return None

        if request.config.cache_generated and request.source == "MODEL":
            self.file_provider.write(request, artifact)
        elif request.config.cache_generated and not self.file_provider.file_path(request).is_file():
            self.file_provider.write(request, artifact)

        return encode_geometry_payload(artifact.data, artifact.format)

    def generate(self, request: GeometryRequest) -> GeometryArtifact | None:
        for provider in self.generation_providers:
            artifact = provider.generate(request)
            if artifact is not None:
                return artifact
        return None


def encode_geometry_payload(data: bytes, format_spec: GeometryFormatSpec) -> str:
    if format_spec.encoding == "BASE64":
        return base64.b64encode(data).decode("utf-8")
    return data.decode("utf-8", errors="ignore")


def embed_gltf_buffers(exported: dict[str, bytes]) -> bytes:
    gltf_bytes = exported.get("model.gltf")
    if gltf_bytes is None:
        raise ValueError("Trimesh GLTF export did not include model.gltf")

    gltf = json.loads(gltf_bytes.decode("utf-8"))
    for buffer in gltf.get("buffers", []):
        uri = buffer.get("uri")
        if not uri or uri.startswith("data:"):
            continue
        buffer_data = exported.get(uri)
        if buffer_data is None:
            raise ValueError(f"Trimesh GLTF export did not include buffer: {uri}")
        buffer["uri"] = (
            "data:application/octet-stream;base64,"
            + base64.b64encode(buffer_data).decode("ascii")
        )

    return json.dumps(gltf, separators=(",", ":")).encode("utf-8")


geometry_service = GeometryService()
