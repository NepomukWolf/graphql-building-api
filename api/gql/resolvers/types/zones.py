from __future__ import annotations

from typing import cast

from ariadne import InterfaceType, ObjectType
from graphql.type.definition import GraphQLResolveInfo
import ifcopenshell.entity_instance

from api.gql.resolvers.context import (
    attach_model_context,
    get_model_context,
    ifc_entity,
)
from api.gql.resolvers.selection import (
    all_model_zones,
    apply_element_query,
    zone_topology_candidates,
)
from api.gql.resolvers.types.geometry import resolve_geometry_context
from api.ifc.helpers import (
    element_info,
    get_children,
    get_parent,
    is_building_element,
    is_zone,
    zone_info,
)
from api.ifc.topology import topology_service

zone = InterfaceType("Zone")
building = ObjectType("Building")
storey = ObjectType("Storey")
space = ObjectType("Space")


def zone_children(obj) -> list[dict]:
    return [
        attach_model_context(zone_info(child), get_model_context(obj))
        for child in get_children(ifc_entity(obj))
        if is_zone(child)
    ]


def zone_parent(obj) -> list[dict]:
    parent = get_parent(ifc_entity(obj))
    if not is_zone(parent):
        return []
    parent = cast(ifcopenshell.entity_instance, parent)
    return [attach_model_context(zone_info(parent), get_model_context(obj))]


def zone_elements(obj, where: dict | None = None) -> list[dict]:
    candidates = [
        child
        for child in get_children(ifc_entity(obj))
        if is_building_element(child)
    ]
    context = get_model_context(obj)
    elements = apply_element_query(context.model, candidates, where)
    return [attach_model_context(element_info(element), context) for element in elements]


@zone.type_resolver
def resolve_zone_type(obj, *_):
    entity = ifc_entity(obj)
    if entity and entity.is_a("IfcBuilding"):
        return "Building"
    if entity and entity.is_a("IfcBuildingStorey"):
        return "Storey"
    if entity and entity.is_a("IfcSpace"):
        return "Space"
    return None


def resolve_zone_contains(obj, _info: GraphQLResolveInfo):
    return zone_children(obj)


def resolve_zone_elements(
    obj,
    _info: GraphQLResolveInfo,
    where: dict | None = None,
):
    return zone_elements(obj, where)


def resolve_zone_part_of(obj, _info: GraphQLResolveInfo):
    return zone_parent(obj)


def resolve_zone_intersects(obj, _info: GraphQLResolveInfo, where: dict | None = None):
    context = get_model_context(obj)
    related = topology_service.intersects(
        context.model,
        ifc_entity(obj),
        zone_topology_candidates(obj, where),
    )
    return [attach_model_context(zone_info(entity), context) for entity in related]


def resolve_zone_adjacent(obj, _info: GraphQLResolveInfo, where: dict | None = None):
    context = get_model_context(obj)
    related = topology_service.adjacent(
        context.model,
        ifc_entity(obj),
        zone_topology_candidates(obj, where),
    )
    return [attach_model_context(zone_info(entity), context) for entity in related]


for zone_type in (building, storey, space):
    zone_type.set_field("geometry", resolve_geometry_context)
    zone_type.set_field("contains", resolve_zone_contains)
    zone_type.set_field("elements", resolve_zone_elements)
    zone_type.set_field("partOf", resolve_zone_part_of)
    zone_type.set_field("intersects", resolve_zone_intersects)
    zone_type.set_field("adjacent", resolve_zone_adjacent)


@building.field("storeys")
def resolve_building_storeys(obj, _info: GraphQLResolveInfo):
    return all_model_zones(get_model_context(obj), "IfcBuildingStorey")


@building.field("spaces")
def resolve_building_spaces(obj, _info: GraphQLResolveInfo):
    return all_model_zones(get_model_context(obj), "IfcSpace")


@storey.field("spaces")
def resolve_storey_spaces(obj, _info: GraphQLResolveInfo):
    entity = ifc_entity(obj)
    return [
        attach_model_context(zone_info(child), get_model_context(obj))
        for child in get_children(entity)
        if child.is_a("IfcSpace")
    ]
