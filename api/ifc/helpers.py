from __future__ import annotations

import ifcopenshell.entity_instance
import ifcopenshell.util.element as el


def get_entity_id(entity: ifcopenshell.entity_instance) -> str:
    """Return a stable GraphQL id for IFC entities."""
    return getattr(entity, "GlobalId", None) or str(entity.id())


def get_entity_name(entity: ifcopenshell.entity_instance) -> str | None:
    return getattr(entity, "Name", None)


def get_zone_type(entity: ifcopenshell.entity_instance) -> str:
    if entity.is_a("IfcBuilding"):
        return "Building"
    if entity.is_a("IfcBuildingStorey"):
        return "Storey"
    if entity.is_a("IfcSpace"):
        return "Space"
    return "Zone"


def is_zone(entity: ifcopenshell.entity_instance | None) -> bool:
    return bool(
        entity
        and (
            entity.is_a("IfcBuilding")
            or entity.is_a("IfcBuildingStorey")
            or entity.is_a("IfcSpace")
        )
    )


def is_building_element(entity: ifcopenshell.entity_instance | None) -> bool:
    return bool(entity and entity.is_a("IfcBuildingElement"))


def zone_info(entity: ifcopenshell.entity_instance) -> dict:
    return {
        "_ifc": entity,
        "id": get_entity_id(entity),
        "name": get_entity_name(entity),
        "__typename": get_zone_type(entity),
    }


def element_info(entity: ifcopenshell.entity_instance) -> dict:
    return {
        "_ifc": entity,
        "guid": get_entity_id(entity),
        "name": get_entity_name(entity),
        "type": entity.is_a(),
    }


def get_children(
    entity: ifcopenshell.entity_instance,
) -> list[ifcopenshell.entity_instance]:
    return list(el.get_decomposition(entity) or [])


def get_parent(
    entity: ifcopenshell.entity_instance,
) -> ifcopenshell.entity_instance | None:
    parent = el.get_parent(entity)
    void = el.get_filled_void(entity)
    if void:
        parent = el.get_voided_element(void)
    return parent


def get_common_pset_name(entity: ifcopenshell.entity_instance) -> str:
    return "Pset_" + entity.is_a()[3:] + "Common"


def get_properties(
    entity: ifcopenshell.entity_instance, pset_name: str | None = None
) -> list[dict]:
    pset_name = pset_name or get_common_pset_name(entity)
    pset = el.get_pset(entity, pset_name) or {}
    return [
        {"name": name, "value": value, "pset": pset_name}
        for name, value in pset.items()
        if name != "id"
    ]


def matches_search(
    entity: ifcopenshell.entity_instance, filter_value: str | None
) -> bool:
    if not filter_value:
        return True

    needle = filter_value.casefold()
    values = [
        get_entity_id(entity),
        get_entity_name(entity),
        entity.is_a(),
        entity.is_a()[3:] if entity.is_a().startswith("Ifc") else entity.is_a(),
    ]
    return any(value and needle in str(value).casefold() for value in values)


def matches_filter(
    entity: ifcopenshell.entity_instance, filter_value: str | None
) -> bool:
    return matches_search(entity, filter_value)


def matches_element_type(
    entity: ifcopenshell.entity_instance, type_value: str | None
) -> bool:
    if not type_value:
        return True

    normalized = type_value.strip()
    if not normalized:
        return True

    if not normalized.startswith("Ifc"):
        normalized = "Ifc" + normalized[:1].upper() + normalized[1:]

    if normalized.endswith("s"):
        singular = normalized[:-1]
    else:
        singular = normalized

    return entity.is_a(normalized) or entity.is_a(singular)


def matches_element_filters(
    entity: ifcopenshell.entity_instance,
    filters: list[str] | None,
) -> bool:
    return all(matches_element_filter(entity, filter_name) for filter_name in filters or [])


def matches_element_filter(
    entity: ifcopenshell.entity_instance,
    filter_name: str,
) -> bool:
    properties = _all_pset_properties(entity)
    if filter_name == "EXTERNAL":
        return _property_bool(properties, "IsExternal") is True
    if filter_name == "INTERNAL":
        return _property_bool(properties, "IsExternal") is False
    if filter_name == "LOAD_BEARING":
        return _property_bool(properties, "LoadBearing") is True
    if filter_name == "FIRE_RATED":
        return _has_non_empty_property(
            properties,
            ["FireRating", "FireResistanceRating"],
        )
    return False


def _all_pset_properties(entity: ifcopenshell.entity_instance) -> dict[str, object]:
    properties: dict[str, object] = {}
    for pset in (el.get_psets(entity) or {}).values():
        for name, value in pset.items():
            if name != "id":
                properties[name] = value
    return properties


def _property_bool(properties: dict[str, object], name: str) -> bool | None:
    if name not in properties:
        return None

    value = properties[name]
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
    return None


def _has_non_empty_property(
    properties: dict[str, object],
    names: list[str],
) -> bool:
    for name in names:
        value = properties.get(name)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return True
    return False
