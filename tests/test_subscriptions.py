from pathlib import Path

import ifcopenshell
from fastapi.testclient import TestClient
from ifcopenshell.api.root import create_entity

from graphql_building_api.app import create_app, schema
from graphql_building_api.ifc.models import IfcModelStore


def test_openapi_includes_generic_graphql_endpoints(tmp_path: Path):
    client = TestClient(create_app(IfcModelStore(tmp_path, "demo"), schema))
    paths = client.get("/openapi.json").json()["paths"]

    for path in ("/graphql", "/models/{model_id}/graphql"):
        operation = paths[path]["post"]
        assert operation["tags"] == ["Building GraphQL"]
        assert "requestBody" in operation
        assert "graphql-transport-ws" in operation["description"]


def test_standalone_mutation_publishes_model_change(tmp_path: Path):
    model_id = "demo"
    folder = tmp_path / model_id
    folder.mkdir()
    model = ifcopenshell.file(schema="IFC4")
    wall = create_entity(model, ifc_class="IfcWall", name="Wall")
    model.write(str(folder / f"{model_id}.ifc"))
    client = TestClient(create_app(IfcModelStore(tmp_path, model_id), schema))

    with client.websocket_connect(
        f"/models/{model_id}/graphql", subprotocols=["graphql-transport-ws"]
    ) as websocket:
        websocket.send_json({"type": "connection_init"})
        assert websocket.receive_json()["type"] == "connection_ack"
        websocket.send_json({
            "id": "change",
            "type": "subscribe",
            "payload": {
                "query": "subscription { modelChanged { modelId revision kind source } }"
            },
        })
        response = client.post(
            f"/models/{model_id}/graphql",
            json={
                "query": "mutation Patch($input: PatchPropertiesInput!) { patchProperties(input: $input) { guid } }",
                "variables": {"input": {
                    "guid": wall.GlobalId,
                    "patch": {"Pset_Showcase": {"Status": "Ready"}},
                }},
            },
        )
        assert response.status_code == 200
        message = websocket.receive_json()

    assert message["payload"]["data"]["modelChanged"] == {
        "modelId": model_id,
        "revision": 1,
        "kind": "UPDATED",
        "source": "BUILDING_GRAPHQL",
    }
