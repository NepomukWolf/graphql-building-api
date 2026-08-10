from __future__ import annotations

from typing import Any, Optional, TypedDict

from ariadne import MutationType
from graphql import GraphQLError
from graphql.type.definition import GraphQLResolveInfo
from ifcopenshell.api.pset import add_pset, edit_pset, remove_pset
from ifcopenshell.entity_instance import entity_instance
from ifcopenshell.util.element import get_pset, get_type

from api.gql.resolvers.context import (
    ModelContext,
    attach_model_context,
    load_model_context,
)
from api.ifc.helpers import element_info


class OptionalModelInput(TypedDict, total=False):
    model: Optional[str]


class UpdatePropertyInput(OptionalModelInput):
    guid: str
    propertySet: str
    property: str
    value: Any


class OptionalPatchPropertiesInput(OptionalModelInput, total=False):
    includeInherited: bool


class PatchPropertiesInput(OptionalPatchPropertiesInput):
    guid: str
    patch: Any


PropertySetPatch = Optional[dict[str, Any]]


property_mutations = MutationType()


@property_mutations.field("updateProperty")
def resolve_update_property(_obj, info: GraphQLResolveInfo, input: UpdatePropertyInput):
    model_name = input.get("model")
    guid = input["guid"]
    pset_name = input["propertySet"]
    property_name = input["property"]
    new_value = input["value"]

    model_context: ModelContext = load_model_context(info, model_name)
    model = model_context.model

    # Try accessing the element.
    try:
        element = model.by_guid(guid)
    except RuntimeError as exc:
        raise GraphQLError(f"Entity with GUID {guid!r} was not found") from exc

    pset_data = get_pset(
        element=element, name=pset_name, psets_only=True, should_inherit=False
    )

    if not isinstance(pset_data, dict):
        raise GraphQLError(f"Property set {pset_name!r} was not found.")

    if property_name not in pset_data:
        raise GraphQLError(
            f"Property {property_name!r} does not exist in {pset_name!r}."
        )

    pset = model.by_id(pset_data["id"])
    edit_pset(model, pset=pset, properties={property_name: new_value})

    return attach_model_context(element_info(element), model_context)


@property_mutations.field("patchProperties")
def resolve_patch_properties(
    _obj,
    info: GraphQLResolveInfo,
    input: PatchPropertiesInput,
):
    model_context = load_model_context(info, input.get("model"))
    model = model_context.model
    element = _entity_by_guid(model, input["guid"])
    patch = _validate_property_patch(input["patch"])
    include_inherited = input.get("includeInherited", False)

    model.begin_transaction()
    try:
        for pset_name, pset_patch in patch.items():
            _apply_property_set_patch(
                model,
                element,
                pset_name,
                pset_patch,
                include_inherited,
            )
    except GraphQLError:
        model.discard_transaction()
        raise
    except (TypeError, ValueError, NotImplementedError) as exc:
        model.discard_transaction()
        raise GraphQLError(f"Could not apply property patch: {exc}") from exc
    except Exception:
        model.discard_transaction()
        raise
    else:
        model.end_transaction()

    return attach_model_context(element_info(element), model_context)


def _entity_by_guid(model, guid: str) -> entity_instance:
    try:
        return model.by_guid(guid)
    except RuntimeError as exc:
        raise GraphQLError(f"Entity with GUID {guid!r} was not found") from exc


def _validate_property_patch(patch: Any) -> dict[str, PropertySetPatch]:
    if not isinstance(patch, dict):
        raise GraphQLError("Property patch must be a JSON object.")

    for pset_name, pset_patch in patch.items():
        _validate_name(pset_name, "Property-set")
        if pset_patch is None:
            continue
        if not isinstance(pset_patch, dict):
            raise GraphQLError(
                f"Patch for property set {pset_name!r} must be an object or null."
            )
        for property_name in pset_patch:
            _validate_name(property_name, "Property")
            if property_name == "id":
                raise GraphQLError("Property name 'id' is reserved.")

    return patch


def _validate_name(name: Any, kind: str) -> None:
    if not isinstance(name, str) or not name.strip():
        raise GraphQLError(f"{kind} names must be non-empty strings.")


def _apply_property_set_patch(
    model,
    element: entity_instance,
    pset_name: str,
    patch: PropertySetPatch,
    include_inherited: bool,
) -> None:
    target = _find_property_set(model, element, pset_name, include_inherited)

    if patch is None:
        if target is not None:
            pset, owner = target
            remove_pset(model, product=owner, pset=pset)
        return

    if target is None:
        if not any(value is not None for value in patch.values()):
            return
        pset = add_pset(model, product=element, name=pset_name)
    else:
        pset, _owner = target

    if patch:
        edit_pset(model, pset=pset, properties=dict(patch), should_purge=True)


def _find_property_set(
    model,
    element: entity_instance,
    pset_name: str,
    include_inherited: bool,
) -> tuple[entity_instance, entity_instance] | None:
    direct = get_pset(
        element,
        pset_name,
        psets_only=True,
        should_inherit=False,
    )
    if isinstance(direct, dict):
        return model.by_id(direct["id"]), element

    if not include_inherited:
        return None

    element_type = get_type(element)
    if element_type is None or element_type == element:
        return None
    inherited = get_pset(
        element_type,
        pset_name,
        psets_only=True,
        should_inherit=False,
    )
    if not isinstance(inherited, dict):
        return None
    return model.by_id(inherited["id"]), element_type
