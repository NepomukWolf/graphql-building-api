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


def matches_filter(
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
