from __future__ import annotations

import math

import ifcopenshell
import ifcopenshell.geom
import numpy as np
import trimesh
from trimesh.visual.material import PBRMaterial


DEFAULT_MATERIAL_COLOR = (0.78, 0.8, 0.82, 1.0)


def _colour_components(colour) -> tuple[float, float, float]:
    return (float(colour.r()), float(colour.g()), float(colour.b()))


def _style_identity(element, style) -> tuple[str, bool]:
    name = str(getattr(style, "name", "") or "IFC material")
    double_sided = True
    try:
        instance = element.file.by_id(style.instance_id())
        surface_style = (
            instance
            if instance.is_a("IfcSurfaceStyle")
            else next(
                inverse
                for inverse in element.file.get_inverse(instance)
                if inverse.is_a("IfcSurfaceStyle")
            )
        )
        name = str(surface_style.Name or name)
        double_sided = str(surface_style.Side) == "BOTH"
    except (AttributeError, IndexError, RuntimeError, StopIteration, TypeError, ValueError):
        pass
    return name, double_sided


def pbr_material(element, style=None) -> PBRMaterial:
    if style is None:
        return PBRMaterial(
            name="IFC default material",
            baseColorFactor=DEFAULT_MATERIAL_COLOR,
            metallicFactor=0.0,
            roughnessFactor=0.7,
            alphaMode="OPAQUE",
            doubleSided=True,
        )

    name, double_sided = _style_identity(element, style)
    try:
        colour = _colour_components(style.get_color())
    except (AttributeError, RuntimeError, TypeError, ValueError):
        colour = DEFAULT_MATERIAL_COLOR[:3]
    transparency = min(1.0, max(0.0, float(getattr(style, "transparency", 0.0))))
    alpha = 1.0 - transparency
    try:
        exponent = max(0.0, float(style.specularity))
        roughness = min(1.0, max(0.15, math.sqrt(2.0 / (exponent + 2.0))))
    except (AttributeError, TypeError, ValueError):
        roughness = 0.7
    return PBRMaterial(
        name=name,
        baseColorFactor=(*colour, alpha),
        metallicFactor=0.0,
        roughnessFactor=roughness,
        alphaMode="BLEND" if alpha < 1.0 else "OPAQUE",
        doubleSided=double_sided,
    )


class GeometryHandler:
    def __init__(self, element: ifcopenshell.entity_instance):
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        self.element = element
        self.shape = ifcopenshell.geom.create_shape(settings, element)
        self.geometry = self.shape.geometry
        self.mesh: trimesh.Trimesh
        self.scene: trimesh.Scene
        self._generate_mesh()

    def _generate_mesh(self):
        vertices = np.asarray(self.geometry.verts, dtype=np.float64).reshape(-1, 3)
        faces = np.asarray(self.geometry.faces, dtype=np.int64).reshape(-1, 3)
        raw_material_ids = np.asarray(self.geometry.material_ids, dtype=np.int64)
        material_ids = (
            raw_material_ids.copy()
            if len(raw_material_ids) == len(faces)
            else np.full(len(faces), -1, dtype=np.int64)
        )

        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        unique = mesh.unique_faces()
        mesh.update_faces(unique)
        material_ids = material_ids[unique]
        mesh.remove_unreferenced_vertices()
        mesh.fix_normals(multibody=True)
        self.mesh = mesh
        self.scene = self._material_scene(material_ids)

    def _material_scene(self, material_ids: np.ndarray) -> trimesh.Scene:
        scene = trimesh.Scene()
        styles = tuple(self.geometry.materials)
        for material_id in np.unique(material_ids):
            face_mask = material_ids == material_id
            submesh = trimesh.Trimesh(
                vertices=self.mesh.vertices.copy(),
                faces=self.mesh.faces[face_mask].copy(),
                process=False,
            )
            submesh.remove_unreferenced_vertices()
            # glTF stores one normal per vertex. Giving every triangle its own
            # vertices preserves sharp BIM edges and deterministic face normals.
            submesh.unmerge_vertices()
            _ = submesh.vertex_normals
            style = styles[material_id] if 0 <= material_id < len(styles) else None
            material = pbr_material(self.element, style)
            submesh.visual = trimesh.visual.TextureVisuals(material=material)
            key = f"material-{int(material_id)}"
            scene.add_geometry(submesh, node_name=key, geom_name=key)
        return scene

    def export(self, file_type: str, **kwargs):
        if file_type.lower() in {"glb", "gltf"}:
            return self.scene.export(
                file_type=file_type,
                include_normals=True,
                **kwargs,
            )
        return self.mesh.export(file_type=file_type, **kwargs)

    def string(self, format) -> str:
        return self.export(format)

    def bbox(self):
        bounds = self.mesh.bounds
        return {
            "min": {"x": bounds[0][0], "y": bounds[0][1], "z": bounds[0][2]},
            "max": {"x": bounds[1][0], "y": bounds[1][1], "z": bounds[1][2]},
        }

    def file(self, path):
        self.mesh.export(path)
