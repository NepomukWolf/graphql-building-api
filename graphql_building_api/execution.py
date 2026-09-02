from __future__ import annotations

from pathlib import Path
from typing import Any, Collection

from ariadne import graphql_sync, load_schema_from_path, make_executable_schema
from graphql.type.schema import GraphQLSchema

from graphql_building_api.config import API_DIR, GeometryConfig
from graphql_building_api.gql.extensions import load_extensions
from graphql_building_api.gql.resolvers import all_types
from graphql_building_api.events import model_change_subscription


def build_building_schema(
    *,
    api_dir: Path = API_DIR,
    disabled_extensions: Collection[str] = (),
) -> GraphQLSchema:
    type_defs = load_schema_from_path(str(api_dir / "gql" / "schema.graphql"))
    extension_type_defs, extension_types = load_extensions(
        api_dir / "extensions",
        disabled=disabled_extensions,
    )
    return make_executable_schema(
        [type_defs, *extension_type_defs],
        *all_types,
        *extension_types,
        model_change_subscription,
    )


def execute_building_graphql(
    schema: GraphQLSchema,
    data: dict[str, Any],
    *,
    model_store: Any,
    models_dir: Path,
    models_base_url: str,
    geometry_config: GeometryConfig,
    change_hints: list[dict[str, Any]] | None = None,
    debug: bool = False,
) -> tuple[dict[str, Any], int]:
    variables = data.get("variables") or {}
    requested_format = variables.get("format") if isinstance(variables, dict) else None
    success, result = graphql_sync(
        schema,
        data,
        context_value={
            "ifc_models": model_store,
            "models_dir": models_dir,
            "models_base_url": models_base_url,
            "geometry_format": requested_format or "obj",
            "geometry_config": geometry_config,
            "change_hints": change_hints,
        },
        debug=debug,
    )
    return result, 200 if success else 400
