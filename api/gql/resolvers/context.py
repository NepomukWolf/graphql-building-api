from __future__ import annotations

from typing import Any, cast

from graphql import GraphQLError
from graphql.type.definition import GraphQLResolveInfo
import ifcopenshell.entity_instance
import ifcopenshell.file


def model_store(info: GraphQLResolveInfo):
    return info.context["ifc_models"]


def model_context(info: GraphQLResolveInfo, model_name: str | None = None) -> dict:
    store = model_store(info)
    selected_name = store.model_folder_name(model_name)
    try:
        ifc_model_value = store.get(model_name)
    except (FileNotFoundError, ValueError) as exc:
        available = ", ".join(store.available_models()) or "none"
        raise GraphQLError(
            f"IFC model '{selected_name}' is not available. "
            "Add a local model at "
            f"api/static/models/{selected_name}/{selected_name}.ifc "
            f"or request one of the available models: {available}."
        ) from exc

    return {
        "_model_name": selected_name,
        "_ifc_model": ifc_model_value,
        "_geometry_base_url": (
            info.context["models_base_url"] + f"{selected_name}/elements/"
        ),
        "_geometry_elements_dir": (
            info.context["models_dir"] / selected_name / "elements"
        ),
    }


def ifc_model(obj: dict) -> ifcopenshell.file:
    return obj["_ifc_model"]


def ifc_entity(obj: Any) -> ifcopenshell.entity_instance:
    entity = obj.get("_ifc") if isinstance(obj, dict) else obj
    return cast(ifcopenshell.entity_instance, entity)


def with_model_context(obj: dict, model_obj: dict) -> dict:
    obj.update(
        {
            "_model_name": model_obj["_model_name"],
            "_ifc_model": model_obj["_ifc_model"],
            "_geometry_base_url": model_obj["_geometry_base_url"],
            "_geometry_elements_dir": model_obj["_geometry_elements_dir"],
        }
    )
    return obj
