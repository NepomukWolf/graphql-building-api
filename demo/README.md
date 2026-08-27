# Demo Queries

Start the server:

```sh
uv run app.py
```

Open `http://127.0.0.1:8000/graphql` in a GraphQL client, then paste one of the
queries from this folder.

The repository does not ship IFC model files. The endpoint selects the model:
`/graphql` uses the configured default, while `/models/<model-id>/graphql` uses
the model ID in the URL. Replace hard-coded GUIDs with values from that model.

`topology.graphql` demonstrates the narrow topology fields. These fields use
cached axis-aligned bounding boxes, so they are approximate rather than exact
solid-geometry relations.

`geometry-formats.graphql` demonstrates `WKT` and self-contained `GLTF`
payloads generated from the loaded model.

You can also run a query file with `curl`:

```sh
curl -X POST http://127.0.0.1:8000/models/example-model/graphql \
  -H 'Content-Type: application/json' \
  --data-binary '{"query":"query ExternalWallSelectorDemo { elements(where: { type: \"Wall\", filters: [EXTERNAL], selector: \"IfcWall\" }) { guid name type dataSheetURL properties(pset: \"Pset_WallCommon\") { name value pset } geometry(format: OBJ) { url extension contentType } } }"}'
```
