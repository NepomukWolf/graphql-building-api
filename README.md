# GraphQL API for simplified access to IFC

Lightweight prototype that exposes IFC model elements over a simple GraphQL API and can emit per-element geometry, properties and a simplified spatial hierarchy.

The geometry can either be generated while resolving a query directly from the IFC file (using IfcOpenShell Trimesh, OpenCascade), or can be pre-generated and served from static geometry files.

## Highlights

- Exposes a compact BOT-like spatial structure with buildings, storeys, spaces, and generic building elements.
- Resolver returns element metadata plus a flat `geometry` object, so clients can request file URLs, inline payloads, or both.

## Requirements and Setup

- Tested with Python 3.11, but other versions might also work.
- Dependencies are managed with `uv` through `pyproject.toml` and `uv.lock`.
- Runtime defaults are configured in `config.toml` at the project root. `PORT`
  and `DEFAULT_MODEL` environment variables still override the matching
  defaults.

Install the dependencies with:

```
uv sync
```

## Data and Model Files

This repository does not redistribute IFC model files or generated geometry.
Both can be large and may have project-specific licensing constraints. Local
model folders under `api/static/models/` are intentionally ignored by git.

Use this folder layout for your own IFC files:

```text
api/static/models/2026-SampleModel/2026-SampleModel.ifc
```

The folder name and IFC filename must match. `2026-SampleModel` is the configured
default; use another matching folder and filename or set `DEFAULT_MODEL` when
starting the server to select a different default.

## Quickstart

Once the python environment is setup and activated, you can proceed with the following steps:

1. **Add your model:** Place your IFC model in `api/static/models/<model name>/<model name>.ifc`.

   For the default configuration:

   ```shell
   mkdir -p api/static/models/2026-SampleModel
   cp /path/to/your/model.ifc api/static/models/2026-SampleModel/2026-SampleModel.ifc
   ```

   To use a different startup model, set `DEFAULT_MODEL` to the folder/model name:

   ```shell
   DEFAULT_MODEL=my-model uv run api/app.py
   ```

2. **Pre-generate geometry model:** There is a small CLI to extract and save element-wise geometry for an IFC model. Example usage:

   ```shell
   uv run python -m scripts.generate_geometry api/static/models/2026-SampleModel/2026-SampleModel.ifc --formats OBJ GLB GLTF WKT STL
   ```

   The generated geometry files will be located at `api/static/models/<model name>/elements/<element guid>/`.

3. **Start the GraphQL server:** The repository provides a small Flask + Ariadne server in `api/app.py` that serves a GraphQL endpoint (by default `/graphql`). Start it like:

   ```shell
   uv run api/app.py
   ```

   The server can start without local models. `models` will return an empty
   list until you add an IFC file. Model-specific queries return a clear error
   if the requested model is not available.

4. **Explore the API:** Use your preferred GraphQL client against:

   ```text
   http://127.0.0.1:5050/graphql
   ```

   For example, Apollo Sandbox and Altair can introspect the schema and help compose queries.

5. **Query the endpoint:** Send GraphQL requests to `/graphql` using POST. GET requests with a `query` parameter are also supported for clients that introspect via GET.

## GraphQL: schema shape and example queries

The schema exposes IFC data through `model(name: String)`. If `name` is omitted,
the configured default model is used. `models` returns the available model names.
Within a model, `building` returns the root building zone, while `storeys`,
`spaces`, and `elements(where: ElementQuery)` return list selections.

Each building element returned by the API provides at least the following fields:

- `guid`: the element GlobalId (GUID)
- `name`: element name
- `type`: concrete IFC type name, such as `IfcWall`, `IfcDoor`, or `IfcBeam`
- `geometry`: an object with:
  - `url`: stable URL pointing to a pre-generated geometry file, when available
  - `payload`: inline geometry content read from file or generated dynamically
  - `encoding`, `format`, `extension`, and `contentType`: metadata for consuming the geometry
- `properties(pset: String, name: String)`: values from all property sets,
  optionally restricted by exact property-set and/or property names, as
  `{ name, value, pset }`
- `partOf` / `contains`: relationships to parent/children elements

Supported geometry formats are `OBJ`, `GLB`, `GLTF`, `STL`, `STL_ASCII`,
`PLY`, `PLY_ASCII`, `OFF`, `WKT`, and `BREP`. `GLTF` is exported as a
self-contained `.gltf` JSON file with embedded base64 buffers so it still fits
the single URL/payload geometry model. `GLB` remains the compact single-file
binary glTF option. `WKT` is exported from the triangulated mesh as a
`GEOMETRYCOLLECTION Z` of triangular polygons. `BREP` is exposed for future
exact-geometry support and currently resolves from existing `.brep` files only.

Geometry source can be requested per field:

```graphql
geometry(format: PLY, source: MODEL) {
	payload
	encoding
}
```

The server decides whether client source preferences are honored through
`config.toml`. Generated geometry is only written to `api/static/models/` when
`geometry.cache_generated = true`.

## Schema Extensions

At startup, the server automatically loads GraphQL extensions from
`api/extensions/`. Each direct child folder with a `schema.graphql` file is
treated as an extension. A folder may also include `resolvers.py` exporting
`all_types`, a list of Ariadne bindables such as `ObjectType` instances.

Extensions are enabled by default. A server can omit individual extensions
from its schema by listing their directory names in `config.toml`:

```toml
[extensions]
disabled = ["geometry_representations"]
```

```text
api/extensions/my-extension/
  schema.graphql
  resolvers.py
```

The prototype includes `api/extensions/lca-extension/`, which extends
`BuildingElement` with `dataSheetURL` and resolves deterministic demo URLs for
common element types. The `geometry_representations` extension adds normalized
structured IFC extrusions to the core geometry facade. It currently supports
rectangle and circle profiles; unsupported representation items are omitted.

```graphql
query StructuredGeometry {
  model(name: "duplex_arch") {
    elements(where: { type: "Wall" }) {
      guid
      geometry {
        representations {
          __typename
          identifier
          placement { matrix }
          ... on ExtrusionRepresentation {
            depth
            direction { x y z }
            profile {
              __typename
              name
              ... on RectangleProfile { width height }
              ... on CircleProfile { radius }
            }
          }
        }
      }
    }
  }
}
```

Representation placement matrices contain 16 row-major values and transform
primitive-local coordinates into model coordinates. Translation is stored at
indices 3, 7, and 11 in metres. The parent geometry field's `format` and
`source` arguments affect artifact fields only, not `representations`.

### Example Queries

Some example queries.
**list walls (minimal):**

```graphql
query ListWalls {
  model {
    name
    elements(where: { type: "Wall" }) {
      guid
      name
      geometry(format: OBJ) {
        url
        extension
        contentType
      }
    }
  }
}
```

This query returns a list of wall elements with URLs pointing to static geometry files. Type filters accept both friendly names like `"Wall"` and IFC names like `"IfcWall"`.

**List external walls with a curated semantic filter:**

```graphql
query ExternalWalls {
  model {
    elements(where: { type: "Wall", filters: [EXTERNAL] }) {
      guid
      name
      type
      properties(pset: "Pset_WallCommon", name: "IsExternal") {
        name
        value
        pset
      }
    }
  }
}
```

Curated filters use explicit IFC property values. For example, `EXTERNAL`
requires `IsExternal = true`, while `LOAD_BEARING` requires
`LoadBearing = true`. Multiple filters are combined with AND semantics.

**Use a raw IfcOpenShell selector:**

```graphql
query SelectorWalls {
  model(name: "example-model") {
    elements(where: { selector: "IfcWall" }) {
      guid
      name
      type
    }
  }
}
```

The selector is applied to the current candidate set, so it can be combined
with `type`, `search`, and `filters`.

**Query narrow topology relations:**

```graphql
query ElementTopology {
  model(name: "example-model") {
    elements(where: { type: "Wall" }) {
      guid
      name
      intersects(where: { type: "Door" }) {
        guid
        name
        type
      }
      adjacent(where: { type: "Slab" }) {
        guid
        name
        type
      }
    }
  }
}
```

Topology fields use cached axis-aligned bounding boxes generated from IFC
geometry. `intersects` returns elements whose boxes overlap with positive volume
on all axes. `adjacent` returns elements whose boxes do not intersect, but are
within 5 cm on one axis and overlap on the other two axes. This is an
approximate topology relation intended for lightweight querying and demos.

**Fetch one element by id and request inline OBJ:**

```graphql
query GetElement {
  model(name: "example-model") {
    elements(where: { id: "<ELEMENT-GUID-HERE>" }) {
      guid
      name
      type
      geometry(format: OBJ) {
        payload
        encoding
        extension
        contentType
      }
      partOf {
        guid
        name
      }
      contains {
        guid
        name
      }
      properties(pset: "Pset_WallCommon") {
        name
        value
        pset
      }
    }
  }
}
```

This returns a list containing the matching element when the id exists.

**Query extension data:**

```graphql
query WallDataSheets {
  model(name: "example-model") {
    elements(where: { type: "Wall" }) {
      guid
      name
      type
      dataSheetURL
    }
  }
}
```

The `dataSheetURL` field is provided by the demo extension, not the core schema.

**List available models:**

```graphql
query AvailableModels {
  models {
    name
    isDefault
  }
}
```

## Project layout (important files)

If you want to jump into the code, here are some pointers about the project structure:

- `api/app.py`: Flask + Ariadne GraphQL server and startup.
- `api/config.py`: local runtime configuration.
- `config.toml`: project-level runtime defaults.
- `api/gql/`: GraphQL schema and resolver bindings.
- `api/extensions/`: auto-loaded schema extensions and optional extension resolvers.
- `api/ifc/`: IFC model loading, relationship helpers, and geometry helpers.
- `api/static/models/<model>/`: canonical local model folder, containing `<model>.ifc` and generated geometry under `elements/<element guid>/`.
- `docs/architecture.md`: Mermaid diagrams for request flow, geometry resolution, providers, and static layout.
- `scripts/generate_geometry.py`: CLI helper that generates geometry and copies IFC into the static model folder.

## How to cite

If you use this repository in academic work, please cite the accompanying EC3 2026 paper:

```bibtex
@inproceedings{wolf2026extensiblegraphql,
  author    = {Nepomuk Wolf and Sebastian Esser and Andr{'e} Borrmann},
  title     = {An Extensible GraphQL API for Fine-Grained Access to Building Information Models},
  booktitle = {Proceedings of the 2026 European Conference on Computing in Construction (EC3 2026)},
  year      = {2026},
  address   = {Corfu, Greece},
  month     = jul,
  note      = {July 12--15, 2026}
}
```

The repository also includes `CITATION.cff` for citation-aware tools.

## License

This software is released under the MIT License. See `LICENSE` for details.

## Development & next steps

Currently at proof-of-concept level, not optimized and no security hardening yet.
