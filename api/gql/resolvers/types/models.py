from __future__ import annotations

from ariadne import ObjectType
from graphql.type.definition import GraphQLResolveInfo

from api.gql.resolvers.context import ifc_model, with_model_context
from api.gql.resolvers.selection import all_model_zones, apply_element_query
from api.ifc.helpers import element_info, zone_info

model = ObjectType("Model")
model_info = ObjectType("ModelInfo")


@model.field("name")
def resolve_model_name(obj, _info: GraphQLResolveInfo):
    return obj["_model_name"]


@model.field("building")
def resolve_model_building(obj, _info: GraphQLResolveInfo):
    buildings = ifc_model(obj).by_type("IfcBuilding")
    return with_model_context(zone_info(buildings[0]), obj) if buildings else None


@model.field("storeys")
def resolve_model_storeys(obj, _info: GraphQLResolveInfo, where: dict | None = None):
    return all_model_zones(obj, "IfcBuildingStorey", where)


@model.field("spaces")
def resolve_model_spaces(obj, _info: GraphQLResolveInfo, where: dict | None = None):
    return all_model_zones(obj, "IfcSpace", where)


@model.field("elements")
def resolve_model_elements(obj, _info: GraphQLResolveInfo, where: dict | None = None):
    elements = apply_element_query(
        ifc_model(obj),
        list(ifc_model(obj).by_type("IfcBuildingElement")),
        where,
    )
    return [with_model_context(element_info(entity), obj) for entity in elements]
