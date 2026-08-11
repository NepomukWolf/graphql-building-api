from __future__ import annotations

from typing import cast

from ariadne import ObjectType
from graphql.type.definition import GraphQLResolveInfo
import ifcopenshell.entity_instance

from api.gql.resolvers.context import (
    attach_model_context,
    get_model_context,
    ifc_entity,
)
from api.gql.resolvers.selection import element_topology_candidates
from api.gql.resolvers.types.geometry import resolve_geometry_context
from api.gql.resolvers.types.materials import resolve_material_assignment
from api.ifc.helpers import (
    element_info,
    get_children,
    get_parent,
    get_properties,
    is_building_element,
)
from api.ifc.topology import topology_service

building_element = ObjectType("BuildingElement")


@building_element.field("geometry")
def resolve_element_geometry(
    obj,
    info: GraphQLResolveInfo,
    format: str | None = None,
    source: str | None = None,
):
    return resolve_geometry_context(obj, info, format, source)


@building_element.field("contains")
def resolve_element_contains(obj, _info: GraphQLResolveInfo):
    entity = ifc_entity(obj)
    return [
        attach_model_context(element_info(child), get_model_context(obj))
        for child in get_children(entity)
        if is_building_element(child)
    ]


@building_element.field("partOf")
def resolve_element_part_of(obj, _info: GraphQLResolveInfo):
    parent = get_parent(ifc_entity(obj))
    if not is_building_element(parent):
        return []
    parent = cast(ifcopenshell.entity_instance, parent)
    return [attach_model_context(element_info(parent), get_model_context(obj))]


@building_element.field("intersects")
def resolve_element_intersects(
    obj,
    _info: GraphQLResolveInfo,
    where: dict | None = None,
):
    context = get_model_context(obj)
    related = topology_service.intersects(
        context.model,
        ifc_entity(obj),
        element_topology_candidates(obj, where),
    )
    return [attach_model_context(element_info(entity), context) for entity in related]


@building_element.field("adjacent")
def resolve_element_adjacent(
    obj,
    _info: GraphQLResolveInfo,
    where: dict | None = None,
):
    context = get_model_context(obj)
    related = topology_service.adjacent(
        context.model,
        ifc_entity(obj),
        element_topology_candidates(obj, where),
    )
    return [attach_model_context(element_info(entity), context) for entity in related]


@building_element.field("properties")
def resolve_element_properties(
    obj,
    _info: GraphQLResolveInfo,
    pset: str | None = None,
):
    return get_properties(ifc_entity(obj), pset)


@building_element.field("materials")
def resolve_element_materials(obj, _info: GraphQLResolveInfo):
    return resolve_material_assignment(obj)
