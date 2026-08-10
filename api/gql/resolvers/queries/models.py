from __future__ import annotations

from ariadne import QueryType
from graphql.type.definition import GraphQLResolveInfo

from api.gql.resolvers.context import load_model_context, model_store

model_queries = QueryType()


@model_queries.field("model")
def resolve_model(_, info: GraphQLResolveInfo, name: str | None = None):
    return load_model_context(info, name)


@model_queries.field("models")
def resolve_models(_, info: GraphQLResolveInfo):
    store = model_store(info)
    return [
        {"name": model_name, "isDefault": model_name == store.default_model}
        for model_name in store.available_models()
    ]
