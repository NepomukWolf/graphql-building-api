from __future__ import annotations

from ariadne import ObjectType
from graphql.type.definition import GraphQLResolveInfo

from api.gql.resolvers.context import get_model_context, ifc_entity
from api.ifc.geometry_formats import get_geometry_format, normalize_geometry_format
from api.ifc.geometry_service import GeometryRequest, geometry_service
from api.ifc.helpers import get_entity_id

geometry = ObjectType("Geometry")


def geometry_format(info: GraphQLResolveInfo, format: str | None) -> str:
    return normalize_geometry_format(format or info.context.get("geometry_format"))


def geometry_source(info: GraphQLResolveInfo, source: str | None) -> str:
    config = info.context["geometry_config"]
    if source and config.respect_client_source:
        return source.upper()
    return config.default_source


def geometry_request(obj) -> GeometryRequest:
    return GeometryRequest(
        entity=obj["_ifc"],
        guid=obj["_guid"],
        format_name=obj["_format"],
        elements_dir=obj["_elements_dir"],
        geometry_base_url=obj["_geometry_base_url"],
        source=obj["_source"],
        config=obj["_geometry_config"],
    )


def resolve_geometry_context(
    obj,
    info: GraphQLResolveInfo,
    format: str | None = None,
    source: str | None = None,
):
    entity = ifc_entity(obj)
    context = get_model_context(obj)
    return {
        "_ifc": entity,
        "_guid": get_entity_id(entity),
        "_format": geometry_format(info, format),
        "_source": geometry_source(info, source),
        "_geometry_config": info.context["geometry_config"],
        "_geometry_base_url": context.geometry_base_url,
        "_elements_dir": context.geometry_elements_dir,
    }


@geometry.field("url")
def resolve_geometry_url(obj, _info: GraphQLResolveInfo):
    return geometry_service.url(geometry_request(obj))


@geometry.field("payload")
def resolve_geometry_payload(obj, _info: GraphQLResolveInfo):
    return geometry_service.payload(geometry_request(obj))


@geometry.field("encoding")
def resolve_geometry_encoding(obj, _info: GraphQLResolveInfo):
    return get_geometry_format(obj["_format"]).encoding


@geometry.field("format")
def resolve_geometry_format(obj, _info: GraphQLResolveInfo):
    return get_geometry_format(obj["_format"]).name


@geometry.field("extension")
def resolve_geometry_extension(obj, _info: GraphQLResolveInfo):
    return get_geometry_format(obj["_format"]).extension


@geometry.field("contentType")
def resolve_geometry_content_type(obj, _info: GraphQLResolveInfo):
    return get_geometry_format(obj["_format"]).content_type
