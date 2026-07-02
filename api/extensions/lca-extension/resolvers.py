from __future__ import annotations

from ariadne import ObjectType

building_element = ObjectType("BuildingElement")

DEMO_DATA_SHEET_URLS_BY_TYPE = {
    "IfcWall": "https://example.org/product-data/ifc-wall",
    "IfcWindow": "https://example.org/product-data/ifc-window",
    "IfcDoor": "https://example.org/product-data/ifc-door",
}


@building_element.field("dataSheetURL")
def resolve_data_sheet_url(obj, _info):
    element_type = obj.get("type") if isinstance(obj, dict) else None
    if not element_type:
        return None
    return DEMO_DATA_SHEET_URLS_BY_TYPE.get(element_type)


all_types = [building_element]
