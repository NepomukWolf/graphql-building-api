from __future__ import annotations

from graphql import GraphQLError
import ifcopenshell.entity_instance
import ifcopenshell.file
import ifcopenshell.util.selector as selector

from api.gql.resolvers.context import (
    ModelContext,
    attach_model_context,
    get_model_context,
)
from api.ifc.helpers import (
    get_entity_id,
    matches_element_filters,
    matches_element_type,
    matches_search,
    zone_info,
)


def element_query_values(
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


def matches_element_query(
    entity: ifcopenshell.entity_instance,
    where: dict | None = None,
) -> bool:
    id_value, type_value, search_value, filters, _selector_value = element_query_values(
        where
    )
    return (
        (not id_value or get_entity_id(entity) == id_value)
        and matches_element_type(entity, type_value)
        and matches_search(entity, search_value)
        and matches_element_filters(entity, filters)
    )


def apply_element_query(
    model: ifcopenshell.file,
    candidates: list[ifcopenshell.entity_instance],
    where: dict | None = None,
) -> list[ifcopenshell.entity_instance]:
    elements = [entity for entity in candidates if matches_element_query(entity, where)]
    selector_value = (where or {}).get("selector")
    if not selector_value or not selector_value.strip():
        return elements

    try:
        selected = selector.filter_elements(
            model,
            selector_value,
            elements=set(elements),
        )
    except Exception as exc:
        raise GraphQLError(f"Invalid IFC selector: {selector_value}") from exc

    return [entity for entity in elements if entity in selected]


def zone_query_search(where: dict | None = None) -> str | None:
    return (where or {}).get("search")


def all_model_zones(
    context: ModelContext,
    ifc_type: str,
    where: dict | None = None,
) -> list[dict]:
    return [
        attach_model_context(zone_info(entity), context)
        for entity in context.model.by_type(ifc_type)
        if matches_search(entity, zone_query_search(where))
    ]


def all_supported_zone_entities(
    model: ifcopenshell.file,
    where: dict | None = None,
) -> list[ifcopenshell.entity_instance]:
    search_value = zone_query_search(where)
    zones = []
    for ifc_type in ("IfcBuilding", "IfcBuildingStorey", "IfcSpace"):
        zones.extend(model.by_type(ifc_type))
    return [zone for zone in zones if matches_search(zone, search_value)]


def element_topology_candidates(
    obj: dict,
    where: dict | None = None,
) -> list[ifcopenshell.entity_instance]:
    model = get_model_context(obj).model
    return apply_element_query(
        model,
        list(model.by_type("IfcBuildingElement")),
        where,
    )


def zone_topology_candidates(
    obj: dict,
    where: dict | None = None,
) -> list[ifcopenshell.entity_instance]:
    return all_supported_zone_entities(get_model_context(obj).model, where)
