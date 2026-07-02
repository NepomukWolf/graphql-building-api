# Demo Queries

Start the server:

```sh
uv run api/app.py
```

Open `http://127.0.0.1:5050/graphql` in a GraphQL client, then paste one of the
queries from this folder.

The repository does not ship IFC model files. These demo queries use
`example-model`; replace that model name and any hard-coded GUIDs with values
from your local IFC model.

`topology.graphql` demonstrates the narrow topology fields. These fields use
cached axis-aligned bounding boxes, so they are approximate rather than exact
solid-geometry relations.

`geometry-formats.graphql` demonstrates `WKT` and self-contained `GLTF`
payloads generated from the loaded model.

You can also run a query file with `curl`:

```sh
curl -X POST http://127.0.0.1:5050/graphql \
  -H 'Content-Type: application/json' \
  --data-binary '{"query":"query ExternalWallSelectorDemo { model(name: \"example-model\") { elements(where: { type: \"Wall\", filters: [EXTERNAL], selector: \"IfcWall\" }) { guid name type dataSheetURL properties(pset: \"Pset_WallCommon\") { name value pset } geometry(format: OBJ) { url extension contentType } } } }"}'
```
