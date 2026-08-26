from __future__ import annotations

from ariadne import ObjectType
from graphql.type.definition import GraphQLResolveInfo

from graphql_building_api.gql.resolvers.context import ModelContext, attach_model_context
from graphql_building_api.gql.resolvers.selection import all_model_zones, apply_element_query
from graphql_building_api.ifc.helpers import element_info, zone_info

model = ObjectType("Model")
model_info = ObjectType("ModelInfo")


@model.field("name")
def resolve_model_name(context: ModelContext, _info: GraphQLResolveInfo):
    return context.name


@model.field("building")
def resolve_model_building(context: ModelContext, _info: GraphQLResolveInfo):
    buildings = context.model.by_type("IfcBuilding")
    return attach_model_context(zone_info(buildings[0]), context) if buildings else None


@model.field("storeys")
def resolve_model_storeys(
    context: ModelContext,
    _info: GraphQLResolveInfo,
    where: dict | None = None,
):
    return all_model_zones(context, "IfcBuildingStorey", where)


@model.field("spaces")
def resolve_model_spaces(
    context: ModelContext,
    _info: GraphQLResolveInfo,
    where: dict | None = None,
):
    return all_model_zones(context, "IfcSpace", where)


@model.field("elements")
def resolve_model_elements(
    context: ModelContext,
    _info: GraphQLResolveInfo,
    where: dict | None = None,
):
    elements = apply_element_query(
        context.model,
        list(context.model.by_type("IfcBuildingElement")),
        where,
    )
    return [attach_model_context(element_info(entity), context) for entity in elements]
