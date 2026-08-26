from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from graphql import GraphQLError
from graphql.type.definition import GraphQLResolveInfo
import ifcopenshell.entity_instance
import ifcopenshell.file


@dataclass(frozen=True)
class ModelContext:
    name: str
    model: ifcopenshell.file
    geometry_base_url: str
    geometry_elements_dir: Path


def model_store(info: GraphQLResolveInfo):
    return info.context["ifc_models"]


def load_model_context(
    info: GraphQLResolveInfo,
    model_name: str | None = None,
) -> ModelContext:
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

    return ModelContext(
        name=selected_name,
        model=ifc_model_value,
        geometry_base_url=(
            info.context["models_base_url"] + f"{selected_name}/elements/"
        ),
        geometry_elements_dir=(
            info.context["models_dir"] / selected_name / "elements"
        ),
    )


def ifc_entity(obj: Any) -> ifcopenshell.entity_instance:
    entity = obj.get("_ifc") if isinstance(obj, dict) else obj
    return cast(ifcopenshell.entity_instance, entity)


def get_model_context(obj: dict) -> ModelContext:
    return cast(ModelContext, obj["_model_context"])


def attach_model_context(obj: dict, context: ModelContext) -> dict:
    obj["_model_context"] = context
    return obj
