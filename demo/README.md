# Demo Queries

Start the server:

```sh
uv run api/app.py
```

Open `http://127.0.0.1:5050/graphql` in a GraphQL client, then paste one of the
queries from this folder.

`topology.graphql` demonstrates the narrow topology fields. The current sample
model may return empty lists because these fields use direct IfcOpenShell
intersection and clearance checks, not approximate bounding boxes.

You can also run a query file with `curl`:

```sh
curl -X POST http://127.0.0.1:5050/graphql \
  -H 'Content-Type: application/json' \
  --data-binary '{"query":"query ExternalWallSelectorDemo { model(name: \"2026-SampleModel\") { elements(where: { type: \"Wall\", filters: [EXTERNAL], selector: \"IfcWall\" }) { guid name type dataSheetURL properties(pset: \"Pset_WallCommon\") { name value pset } geometry(format: OBJ) { url extension contentType } } } }"}'
```
