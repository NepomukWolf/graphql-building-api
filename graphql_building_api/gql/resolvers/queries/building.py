from __future__ import annotations

from ariadne import QueryType
from graphql.type.definition import GraphQLResolveInfo

from graphql_building_api.gql.resolvers.context import attach_model_context, load_model_context
from graphql_building_api.gql.resolvers.selection import all_model_zones, apply_element_query
from graphql_building_api.ifc.helpers import element_info, zone_info

building_queries = QueryType()


@building_queries.field("modelId")
def resolve_model_id(_, info: GraphQLResolveInfo):
    return load_model_context(info).name


@building_queries.field("building")
def resolve_building(_, info: GraphQLResolveInfo):
    context = load_model_context(info)
    buildings = context.model.by_type("IfcBuilding")
    return attach_model_context(zone_info(buildings[0]), context) if buildings else None


@building_queries.field("storeys")
def resolve_storeys(_, info: GraphQLResolveInfo, where: dict | None = None):
    return all_model_zones(load_model_context(info), "IfcBuildingStorey", where)


@building_queries.field("spaces")
def resolve_spaces(_, info: GraphQLResolveInfo, where: dict | None = None):
    return all_model_zones(load_model_context(info), "IfcSpace", where)


@building_queries.field("elements")
def resolve_elements(_, info: GraphQLResolveInfo, where: dict | None = None):
    context = load_model_context(info)
    elements = apply_element_query(
        context.model,
        list(context.model.by_type("IfcBuildingElement")),
        where,
    )
    return [attach_model_context(element_info(entity), context) for entity in elements]
