from ariadne import MutationType
from graphql import GraphQLError
from graphql.type.definition import GraphQLResolveInfo
from api.gql.resolvers.context import load_model_context, ModelContext
from ifcopenshell.util.element import get_pset
from typing import Any, NotRequired, TypedDict
from ifcopenshell.api.pset import edit_pset
from api.gql.resolvers.context import attach_model_context
from api.ifc.helpers import element_info


class UpdatePropertyInput(TypedDict):
    model: NotRequired[str | None]
    guid: str
    propertySet: str
    property: str
    value: Any


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
