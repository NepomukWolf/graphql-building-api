from __future__ import annotations

from typing import Any

from ariadne import ObjectType, UnionType
from graphql import GraphQLError
from graphql.type.definition import GraphQLResolveInfo
import ifcopenshell.entity_instance
import ifcopenshell.util.element as el

from api.gql.resolvers.context import (
    ModelContext,
    attach_model_context,
    get_model_context,
    ifc_entity,
)
from api.ifc.helpers import get_entity_id, get_properties

material = ObjectType("Material")
material_layer = ObjectType("MaterialLayer")
material_layer_set = ObjectType("MaterialLayerSet")
material_assignment = UnionType("MaterialAssignment")


def _material_info(
    entity: ifcopenshell.entity_instance,
    context: ModelContext,
) -> dict[str, Any]:
    return attach_model_context(
        {"_ifc": entity, "__typename": "Material"},
        context,
    )


def _layer_info(
    material_entity: ifcopenshell.entity_instance | None,
    thickness: float | None,
    context: ModelContext,
) -> dict[str, Any]:
    return {
        "material": (
            _material_info(material_entity, context) if material_entity else None
        ),
        "thickness": thickness,
    }


def _layer_set_info(
    layers: list[dict[str, Any]],
    assignment: ifcopenshell.entity_instance,
    context: ModelContext,
) -> dict[str, Any]:
    return attach_model_context(
        {
            "_ifc": assignment,
            "__typename": "MaterialLayerSet",
            "layers": layers,
        },
        context,
    )


def _collection_materials(
    assignment: ifcopenshell.entity_instance,
) -> list[ifcopenshell.entity_instance | None] | None:
    if assignment.is_a("IfcMaterialProfileSet"):
        return [profile.Material for profile in assignment.MaterialProfiles or []]
    if assignment.is_a("IfcMaterialConstituentSet"):
        return [
            constituent.Material
            for constituent in assignment.MaterialConstituents or []
        ]
    if assignment.is_a("IfcMaterialList"):
        return list(assignment.Materials or [])
    return None


def resolve_material_assignment(obj):
    context = get_model_context(obj)
    assignment = el.get_material(
        ifc_entity(obj),
        should_skip_usage=True,
        should_inherit=True,
    )
    if assignment is None:
        return None

    if assignment.is_a("IfcMaterial"):
        return _material_info(assignment, context)

    if assignment.is_a("IfcMaterialLayerSet"):
        layers = [
            _layer_info(layer.Material, layer.LayerThickness, context)
            for layer in assignment.MaterialLayers or []
        ]
        return _layer_set_info(layers, assignment, context)

    collection = _collection_materials(assignment)
    if collection is None:
        return None
    if len(collection) == 1 and collection[0] is not None:
        return _material_info(collection[0], context)

    layers = [
        _layer_info(material_entity, None, context)
        for material_entity in collection
    ]
    return _layer_set_info(layers, assignment, context)


@material_assignment.type_resolver
def resolve_material_assignment_type(obj, *_):
    if isinstance(obj, dict):
        return obj.get("__typename")
    return None


@material.field("id")
def resolve_material_id(obj, _info: GraphQLResolveInfo):
    return get_entity_id(ifc_entity(obj))


@material.field("name")
def resolve_material_name(obj, _info: GraphQLResolveInfo):
    entity = ifc_entity(obj)
    name = getattr(entity, "Name", None)
    if name is None:
        raise GraphQLError(f"IFC material #{entity.id()} has no name.")
    return name


@material.field("category")
def resolve_material_category(obj, _info: GraphQLResolveInfo):
    return getattr(ifc_entity(obj), "Category", None)


@material.field("properties")
def resolve_material_properties(obj, _info: GraphQLResolveInfo):
    return get_properties(ifc_entity(obj))


@material_layer.field("material")
def resolve_layer_material(obj, _info: GraphQLResolveInfo):
    return obj["material"]


@material_layer.field("thickness")
def resolve_layer_thickness(obj, _info: GraphQLResolveInfo):
    return obj["thickness"]


@material_layer_set.field("layers")
def resolve_layer_set_layers(obj, _info: GraphQLResolveInfo):
    return obj["layers"]
