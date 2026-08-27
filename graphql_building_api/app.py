from __future__ import annotations

import json
import os
from pathlib import Path

import uvicorn
from ariadne.asgi import GraphQL
from ariadne.asgi.handlers import GraphQLTransportWSHandler
from ariadne.explorer import ExplorerApollo
from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.staticfiles import StaticFiles

from graphql_building_api.config import (
    API_DIR, DEFAULT_MODEL, DEFAULT_PORT, DISABLED_EXTENSIONS, GEOMETRY_CONFIG, MODELS_DIR,
)
from graphql_building_api.events import InMemoryEventBroker, ModelChangeEvent
from graphql_building_api.execution import build_building_schema, execute_building_graphql
from graphql_building_api.ifc.models import IfcModelStore


GRAPHQL_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": {
            "type": "object", "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "operationName": {"type": ["string", "null"]},
                "variables": {"type": "object", "additionalProperties": True},
            },
        }}},
    }
}
GRAPHQL_RESPONSES = {200: {"description": "GraphQL response; use introspection for the data shape."}}


class ScopedModelStore:
    def __init__(self, store, model_id: str):
        self.store = store
        self.default_model = model_id
    def get(self, _name=None): return self.store.get(self.default_model)
    def model_folder_name(self, _name=None): return self.default_model
    def available_models(self): return [self.default_model]


def create_app(
    model_store=None,
    executable_schema=None,
    event_broker: InMemoryEventBroker | None = None,
) -> FastAPI:
    app = FastAPI(title="GraphQL Building API")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    store = model_store or IfcModelStore(MODELS_DIR, DEFAULT_MODEL)
    schema_value = executable_schema or build_building_schema(
        api_dir=API_DIR, disabled_extensions=DISABLED_EXTENSIONS
    )
    broker = event_broker or InMemoryEventBroker()
    revisions: dict[str, int] = {}
    explorer = ExplorerApollo()

    def subscription_context(request_or_ws, _data):
        selected = request_or_ws.scope.get("path_params", {}).get("model_id")
        return {"event_broker": broker, "model_id": selected or store.default_model}

    subscription_app = GraphQL(
        schema_value,
        context_value=subscription_context,
        websocket_handler=GraphQLTransportWSHandler(),
    )
    app.state.model_store = store
    app.state.schema = schema_value
    app.state.event_broker = broker

    async def execute(request: Request, model_id: str | None, get_data=None):
        if get_data is None:
            try:
                data = await request.json()
            except Exception:
                data = None
        else:
            data = get_data
        if not isinstance(data, dict):
            return JSONResponse(
                {"errors": [{"message": "Expected a JSON GraphQL request body."}]},
                status_code=400,
            )
        selected_store = ScopedModelStore(store, model_id) if model_id else store
        selected_id = model_id or store.default_model

        def run():
            before = None
            try:
                before = selected_store.get().to_string()
            except Exception:
                pass
            result, status = execute_building_graphql(
                schema_value, data, model_store=selected_store, models_dir=MODELS_DIR,
                models_base_url=str(request.base_url) + "models/",
                geometry_config=GEOMETRY_CONFIG, debug=app.debug,
            )
            changed = (
                not result.get("errors") and before is not None
                and selected_store.get().to_string() != before
            )
            return result, status, changed

        result, status, changed = await run_in_threadpool(run)
        if changed:
            revisions[selected_id] = revisions.get(selected_id, 0) + 1
            await broker.publish(ModelChangeEvent(selected_id, revisions[selected_id], "UPDATED", "BUILDING_GRAPHQL"))
        return JSONResponse(result, status_code=status)

    @app.get("/")
    async def root():
        return {"name": "IFC GraphQL API", "graphql": "/graphql", "default_model": store.default_model}

    @app.get("/graphql", include_in_schema=False)
    async def graphql_explorer(request: Request):
        if "query" in request.query_params:
            variables = request.query_params.get("variables")
            try:
                decoded = json.loads(variables) if variables else {}
            except json.JSONDecodeError:
                decoded = {}
            return await execute(request, None, {
                "query": request.query_params.get("query"),
                "operationName": request.query_params.get("operationName"),
                "variables": decoded,
            })
        return HTMLResponse(explorer.html(None))

    @app.post(
        "/graphql",
        tags=["Building GraphQL"],
        summary="Execute simplified GraphQL for the default model",
        description=(
            "Domain-oriented building GraphQL. GET opens the explorer; the same URL "
            "supports subscriptions over WebSocket using graphql-transport-ws. Use "
            "introspection for the complete schema."
        ),
        responses=GRAPHQL_RESPONSES,
        openapi_extra=GRAPHQL_OPENAPI,
    )
    async def graphql_http(request: Request): return await execute(request, None)

    @app.websocket("/graphql")
    async def graphql_ws(websocket: WebSocket):
        await subscription_app.handle_websocket(websocket)

    @app.get("/models/{model_id}/graphql", include_in_schema=False)
    async def scoped_explorer(model_id: str):
        try: store.get(model_id)
        except (FileNotFoundError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        return HTMLResponse(explorer.html(None))

    @app.post(
        "/models/{model_id}/graphql",
        tags=["Building GraphQL"],
        summary="Execute model-scoped simplified GraphQL",
        description=(
            "Domain-oriented building GraphQL scoped by the URL model ID. GET opens the "
            "explorer; the same URL supports subscriptions over WebSocket using "
            "graphql-transport-ws. Use introspection for the complete schema."
        ),
        responses=GRAPHQL_RESPONSES,
        openapi_extra=GRAPHQL_OPENAPI,
    )
    async def scoped_http(request: Request, model_id: str): return await execute(request, model_id)

    @app.websocket("/models/{model_id}/graphql")
    async def scoped_ws(websocket: WebSocket, model_id: str):
        try: store.get(model_id)
        except (FileNotFoundError, ValueError) as exc:
            await websocket.close(code=4404, reason=str(exc)); return
        await subscription_app.handle_websocket(websocket)

    static_dir = API_DIR / "static"
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir), name="static")
    return app


schema = build_building_schema(api_dir=API_DIR, disabled_extensions=DISABLED_EXTENSIONS)
ifc_models = IfcModelStore(MODELS_DIR, DEFAULT_MODEL)
app = create_app(ifc_models, schema)


def start_ifc_server():
    uvicorn.run("graphql_building_api.app:app", host="127.0.0.1", port=DEFAULT_PORT,
                reload=os.environ.get("DEBUG", "").lower() in {"1", "true", "yes"})


if __name__ == "__main__":
    start_ifc_server()
