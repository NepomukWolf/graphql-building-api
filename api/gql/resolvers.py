from __future__ import annotations

from typing import Any, cast

from ariadne import InterfaceType, ObjectType, QueryType
from graphql import GraphQLError
from graphql.type.definition import GraphQLResolveInfo
import ifcopenshell.entity_instance
import ifcopenshell.file
import ifcopenshell.util.selector as selector

from api.ifc.helpers import (
    element_info,
    get_children,
    get_entity_id,
    get_parent,
    get_properties,
    is_building_element,
    is_zone,
    matches_element_filters,
    matches_element_type,
    matches_search,
    zone_info,
)
from api.ifc.geometry_formats import get_geometry_format, normalize_geometry_format
from api.ifc.geometry_service import GeometryRequest, geometry_service

query = QueryType()
model = ObjectType("Model")
model_info = ObjectType("ModelInfo")
zone = InterfaceType("Zone")
building = ObjectType("Building")
storey = ObjectType("Storey")
space = ObjectType("Space")
building_element = ObjectType("BuildingElement")
geometry = ObjectType("Geometry")


def _model_store(info: GraphQLResolveInfo):
    return info.context["ifc_models"]


def _model_context(info: GraphQLResolveInfo, model_name: str | None = None) -> dict:
    store = _model_store(info)
    selected_name = store.model_folder_name(model_name)
    return {
        "_model_name": selected_name,
        "_ifc_model": store.get(model_name),
        "_geometry_base_url": (
            info.context["models_base_url"] + f"{selected_name}/elements/"
        ),
        "_geometry_elements_dir": (
            info.context["models_dir"] / selected_name / "elements"
        ),
    }


def _ifc_model(obj: dict) -> ifcopenshell.file:
    return obj["_ifc_model"]


def _ifc_entity(obj: Any) -> ifcopenshell.entity_instance:
    entity = obj.get("_ifc") if isinstance(obj, dict) else obj
    return cast(ifcopenshell.entity_instance, entity)


def _with_model_context(obj: dict, model_obj: dict) -> dict:
    obj.update(
        {
            "_model_name": model_obj["_model_name"],
            "_ifc_model": model_obj["_ifc_model"],
            "_geometry_base_url": model_obj["_geometry_base_url"],
            "_geometry_elements_dir": model_obj["_geometry_elements_dir"],
        }
    )
    return obj


def _geometry_format(info: GraphQLResolveInfo, format: str | None) -> str:
    return normalize_geometry_format(format or info.context.get("geometry_format"))


def _geometry_request(obj) -> GeometryRequest:
    return GeometryRequest(
        entity=obj["_ifc"],
        guid=obj["_guid"],
        format_name=obj["_format"],
        elements_dir=obj["_elements_dir"],
        geometry_base_url=obj["_geometry_base_url"],
        source=obj["_source"],
        config=obj["_geometry_config"],
    )


def _geometry_source(info: GraphQLResolveInfo, source: str | None) -> str:
    config = info.context["geometry_config"]
    if source and config.respect_client_source:
        return source.upper()
    return config.default_source


def _zone_children(obj) -> list[dict]:
    return [
        _with_model_context(zone_info(child), obj)
        for child in get_children(_ifc_entity(obj))
        if is_zone(child)
    ]


def _zone_parent(obj) -> list[dict]:
    parent = get_parent(_ifc_entity(obj))
    if not is_zone(parent):
        return []
    parent = cast(ifcopenshell.entity_instance, parent)
    return [_with_model_context(zone_info(parent), obj)]


def _element_query_values(
    where: dict | None = None,
) -> tuple[str | None, str | None, str | None, list[str] | None, str | None]:
    where = where or {}
    return (
        where.get("id"),
        where.get("type"),
        where.get("search"),
        where.get("filters"),
        where.get("selector"),
    )


def _matches_element_query(
    entity: ifcopenshell.entity_instance,
    where: dict | None = None,
) -> bool:
    id_value, type_value, search_value, filters, _selector_value = _element_query_values(
        where
    )
    return (
        (not id_value or get_entity_id(entity) == id_value)
        and matches_element_type(entity, type_value)
        and matches_search(entity, search_value)
        and matches_element_filters(entity, filters)
    )


def _apply_element_query(
    ifc_model: ifcopenshell.file,
    candidates: list[ifcopenshell.entity_instance],
    where: dict | None = None,
) -> list[ifcopenshell.entity_instance]:
    elements = [entity for entity in candidates if _matches_element_query(entity, where)]
    selector_value = (where or {}).get("selector")
    if not selector_value or not selector_value.strip():
        return elements

    try:
        selected = selector.filter_elements(
            ifc_model,
            selector_value,
            elements=set(elements),
        )
    except Exception as exc:
        raise GraphQLError(f"Invalid IFC selector: {selector_value}") from exc

    return [entity for entity in elements if entity in selected]


def _zone_elements(
    obj,
    where: dict | None = None,
) -> list[dict]:
    candidates = [
        child
        for child in get_children(_ifc_entity(obj))
        if is_building_element(child)
    ]
    elements = _apply_element_query(_ifc_model(obj), candidates, where)
    return [_with_model_context(element_info(element), obj) for element in elements]


def _zone_query_search(where: dict | None = None) -> str | None:
    return (where or {}).get("search")


def _all_model_zones(model_obj, ifc_type: str, where: dict | None = None) -> list[dict]:
    return [
        _with_model_context(zone_info(entity), model_obj)
        for entity in _ifc_model(model_obj).by_type(ifc_type)
        if matches_search(entity, _zone_query_search(where))
    ]


@query.field("model")
def resolve_model(_, info: GraphQLResolveInfo, name: str | None = None):
    return _model_context(info, name)


@query.field("models")
def resolve_models(_, info: GraphQLResolveInfo):
    store = _model_store(info)
    return [
        {"name": model_name, "isDefault": model_name == store.default_model}
        for model_name in store.available_models()
    ]


@model.field("name")
def resolve_model_name(obj, _info: GraphQLResolveInfo):
    return obj["_model_name"]


@model.field("building")
def resolve_model_building(obj, _info: GraphQLResolveInfo):
    buildings = _ifc_model(obj).by_type("IfcBuilding")
    return _with_model_context(zone_info(buildings[0]), obj) if buildings else None


@model.field("storeys")
def resolve_model_storeys(obj, _info: GraphQLResolveInfo, where: dict | None = None):
    return _all_model_zones(obj, "IfcBuildingStorey", where)


@model.field("spaces")
def resolve_model_spaces(obj, _info: GraphQLResolveInfo, where: dict | None = None):
    return _all_model_zones(obj, "IfcSpace", where)


@model.field("elements")
def resolve_model_elements(obj, _info: GraphQLResolveInfo, where: dict | None = None):
    elements = _apply_element_query(
        _ifc_model(obj),
        list(_ifc_model(obj).by_type("IfcBuildingElement")),
        where,
    )
    return [
        _with_model_context(element_info(entity), obj)
        for entity in elements
    ]


@zone.type_resolver
def resolve_zone_type(obj, *_):
    entity = _ifc_entity(obj)
    if entity and entity.is_a("IfcBuilding"):
        return "Building"
    if entity and entity.is_a("IfcBuildingStorey"):
        return "Storey"
    if entity and entity.is_a("IfcSpace"):
        return "Space"
    return None


def resolve_geometry_context(
    obj,
    info: GraphQLResolveInfo,
    format: str | None = None,
    source: str | None = None,
):
    entity = _ifc_entity(obj)
    return {
        "_ifc": entity,
        "_guid": get_entity_id(entity),
        "_format": _geometry_format(info, format),
        "_source": _geometry_source(info, source),
        "_geometry_config": info.context["geometry_config"],
        "_geometry_base_url": obj["_geometry_base_url"],
        "_elements_dir": obj["_geometry_elements_dir"],
    }


def resolve_zone_contains(obj, _info: GraphQLResolveInfo):
    return _zone_children(obj)


def resolve_zone_elements(
    obj,
    _info: GraphQLResolveInfo,
    where: dict | None = None,
):
    return _zone_elements(obj, where)


def resolve_zone_part_of(obj, _info: GraphQLResolveInfo):
    return _zone_parent(obj)


def resolve_empty_zone_list(*_):
    return []


for zone_type in (building, storey, space):
    zone_type.set_field("geometry", resolve_geometry_context)
    zone_type.set_field("contains", resolve_zone_contains)
    zone_type.set_field("elements", resolve_zone_elements)
    zone_type.set_field("partOf", resolve_zone_part_of)
    zone_type.set_field("intersects", resolve_empty_zone_list)
    zone_type.set_field("adjacent", resolve_empty_zone_list)


@building.field("storeys")
def resolve_building_storeys(obj, _info: GraphQLResolveInfo):
    return _all_model_zones(obj, "IfcBuildingStorey")


@building.field("spaces")
def resolve_building_spaces(obj, _info: GraphQLResolveInfo):
    return _all_model_zones(obj, "IfcSpace")


@storey.field("spaces")
def resolve_storey_spaces(obj, _info: GraphQLResolveInfo):
    entity = _ifc_entity(obj)
    return [
        _with_model_context(zone_info(child), obj)
        for child in get_children(entity)
        if child.is_a("IfcSpace")
    ]


@building_element.field("geometry")
def resolve_element_geometry(
    obj,
    info: GraphQLResolveInfo,
    format: str | None = None,
    source: str | None = None,
):
    return resolve_geometry_context(obj, info, format, source)


@geometry.field("url")
def resolve_geometry_url(obj, _info: GraphQLResolveInfo):
    return geometry_service.url(_geometry_request(obj))


@geometry.field("payload")
def resolve_geometry_payload(obj, _info: GraphQLResolveInfo):
    return geometry_service.payload(_geometry_request(obj))


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


@building_element.field("contains")
def resolve_element_contains(obj, _info: GraphQLResolveInfo):
    entity = _ifc_entity(obj)
    return [
        _with_model_context(element_info(child), obj)
        for child in get_children(entity)
        if is_building_element(child)
    ]


@building_element.field("partOf")
def resolve_element_part_of(obj, _info: GraphQLResolveInfo):
    parent = get_parent(_ifc_entity(obj))
    if not is_building_element(parent):
        return []
    parent = cast(ifcopenshell.entity_instance, parent)
    return [_with_model_context(element_info(parent), obj)]


@building_element.field("properties")
def resolve_element_properties(
    obj,
    _info: GraphQLResolveInfo,
    pset: str | None = None,
):
    entity = _ifc_entity(obj)
    return get_properties(entity, pset)


all_types = [
    query,
    model,
    model_info,
    zone,
    building,
    storey,
    space,
    building_element,
    geometry,
]
