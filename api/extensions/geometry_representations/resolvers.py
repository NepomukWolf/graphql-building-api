from __future__ import annotations

from typing import Any

from ariadne import InterfaceType, ObjectType
import numpy as np
import ifcopenshell.entity_instance
from ifcopenshell.util.placement import (
    get_axis2placement,
    get_local_placement,
    get_mappeditem_transformation,
)
from ifcopenshell.util.unit import calculate_unit_scale


geometry = ObjectType("Geometry")
geometry_representation = InterfaceType("GeometryRepresentation")
profile = InterfaceType("Profile")


@geometry_representation.type_resolver
@profile.type_resolver
def resolve_normalized_type(obj: dict[str, Any], *_: Any) -> str | None:
    return obj.get("__typename")


def _identity() -> np.ndarray:
    return np.eye(4, dtype=float)


def _placement(value: Any) -> np.ndarray:
    return get_axis2placement(value) if value is not None else _identity()


def _model_matrix(entity: ifcopenshell.entity_instance) -> np.ndarray:
    return get_local_placement(getattr(entity, "ObjectPlacement", None))


def _si_matrix(matrix: np.ndarray, unit_scale: float) -> list[float]:
    converted = np.array(matrix, dtype=float, copy=True)
    converted[:3, 3] *= unit_scale
    return converted.reshape(16).tolist()


def _local_direction(direction: Any, profile_matrix: np.ndarray) -> dict[str, float]:
    vector = np.asarray(direction.DirectionRatios, dtype=float)
    vector = np.linalg.inv(profile_matrix[:3, :3]) @ vector
    length = np.linalg.norm(vector)
    if length:
        vector /= length
    return {"x": float(vector[0]), "y": float(vector[1]), "z": float(vector[2])}


def _normalized_profile(profile: Any, unit_scale: float) -> dict[str, Any] | None:
    profile_type = profile.is_a()
    common = {"name": profile.ProfileName}
    if profile_type == "IfcRectangleProfileDef":
        return {
            "__typename": "RectangleProfile",
            **common,
            "width": float(profile.XDim) * unit_scale,
            "height": float(profile.YDim) * unit_scale,
        }
    if profile_type == "IfcCircleProfileDef":
        return {
            "__typename": "CircleProfile",
            **common,
            "radius": float(profile.Radius) * unit_scale,
        }
    return None


def _normalized_extrusion(
    item: Any,
    identifier: str | None,
    parent_matrix: np.ndarray,
    unit_scale: float,
) -> dict[str, Any] | None:
    normalized_profile = _normalized_profile(item.SweptArea, unit_scale)
    if normalized_profile is None:
        return None

    profile_matrix = _placement(getattr(item.SweptArea, "Position", None))
    matrix = parent_matrix @ _placement(item.Position) @ profile_matrix
    return {
        "__typename": "ExtrusionRepresentation",
        "identifier": identifier,
        "placement": {"matrix": _si_matrix(matrix, unit_scale)},
        "profile": normalized_profile,
        "depth": float(item.Depth) * unit_scale,
        "direction": _local_direction(item.ExtrudedDirection, profile_matrix),
    }


def _normalized_items(
    items: Any,
    identifier: str | None,
    parent_matrix: np.ndarray,
    unit_scale: float,
    active_mappings: frozenset[int] = frozenset(),
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items or ():
        if item.is_a("IfcExtrudedAreaSolid"):
            extrusion = _normalized_extrusion(
                item,
                identifier,
                parent_matrix,
                unit_scale,
            )
            if extrusion is not None:
                normalized.append(extrusion)
            continue

        if not item.is_a("IfcMappedItem") or item.id() in active_mappings:
            continue

        mapped_representation = item.MappingSource.MappedRepresentation
        mapped_matrix = get_mappeditem_transformation(item)
        if mapped_matrix is None:
            continue
        normalized.extend(
            _normalized_items(
                mapped_representation.Items,
                identifier,
                parent_matrix @ mapped_matrix,
                unit_scale,
                active_mappings | {item.id()},
            )
        )
    return normalized


def normalized_representations(entity: Any) -> list[dict[str, Any]]:
    product_representation = getattr(entity, "Representation", None)
    if product_representation is None:
        return []

    unit_scale = calculate_unit_scale(entity.file)
    product_matrix = _model_matrix(entity)
    normalized: list[dict[str, Any]] = []
    for representation in product_representation.Representations or ():
        normalized.extend(
            _normalized_items(
                representation.Items,
                representation.RepresentationIdentifier,
                product_matrix,
                unit_scale,
            )
        )
    return normalized


@geometry.field("representations")
def resolve_geometry_representations(obj: dict[str, Any], _info: Any):
    return normalized_representations(obj["_ifc"])


all_types = [geometry, geometry_representation, profile]
