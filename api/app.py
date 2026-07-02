from ariadne import load_schema_from_path, make_executable_schema, graphql_sync
from flask import Flask, jsonify, request, url_for
from flask_cors import CORS
import json
import logging
from pathlib import Path

if __package__ is None or __package__ == "":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.config import API_DIR, DEFAULT_MODEL, DEFAULT_PORT, GEOMETRY_CONFIG, MODELS_DIR
from api.gql.extensions import load_extensions
from api.gql.resolvers import all_types
from api.ifc.models import IfcModelStore

# Server Setup
app = Flask(__name__, static_url_path="", static_folder=str(API_DIR / "static"))
CORS(app, resources={r"/graphql": {"origins": "*"}})  # Adjust origins as needed
logging.basicConfig(level=logging.INFO)

# Construct the executable schema
type_defs = load_schema_from_path(str(API_DIR / "gql" / "schema.graphql"))
extension_type_defs, extension_types = load_extensions(API_DIR / "extensions")
schema = make_executable_schema(
    [type_defs, *extension_type_defs],
    *all_types,
    *extension_types,
)

# Load IFC model once (on server start)
ifc_models = IfcModelStore(MODELS_DIR, DEFAULT_MODEL)


# ---------------ROUTES-------------------
@app.route("/")
def hello():
    return jsonify(
        {
            "name": "IFC GraphQL API",
            "graphql": "/graphql",
            "default_model": DEFAULT_MODEL,
        }
    )


@app.route("/graphql", methods=["GET"])
def graphql_playground():
    if "query" in request.args:
        data = {
            "query": request.args.get("query"),
            "operationName": request.args.get("operationName"),
            "variables": _decode_json_arg(request.args.get("variables")) or {},
        }
        return execute_graphql(data)

    return jsonify(
        {
            "message": "GraphQL endpoint. Send POST requests or GET requests with a query parameter."
        }
    )


# API
@app.route("/graphql", methods=["POST"])
def graphql_api():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify(
            {"errors": [{"message": "Expected a JSON GraphQL request body."}]}
        ), 400

    return execute_graphql(data)


def _decode_json_arg(value):
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def execute_graphql(data):
    requested_format = None

    # Read GraphQL variables
    if isinstance(data, dict):
        variables = data.get("variables") or {}
        requested_format = variables.get("format")

    # Actual GrahpQL execution
    success, result = graphql_sync(
        schema,
        data,
        context_value={
            "ifc_models": ifc_models,
            "models_dir": MODELS_DIR,
            "models_base_url": url_for("static", filename="models/", _external=True),
            "geometry_format": (requested_format or "obj"),
            "geometry_config": GEOMETRY_CONFIG,
        },
        debug=app.debug,
    )
    status_code = 200 if success else 400
    return jsonify(result), status_code


# === Entrypoint ===
def start_ifc_server():
    app.run(host="127.0.0.1", port=DEFAULT_PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    start_ifc_server()
