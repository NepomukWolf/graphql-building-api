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

## Quickstart

Once the python environment is setup and activated, you can proceed with the following steps:

1. **Add your models:** Place each IFC model in `api/static/models/<model name>/<model name>.ifc`, or use one of the sample models already provided there.

   Model files and generated geometry under `api/static/models/` are intentionally ignored by git because IFC files can be large and may have unclear redistribution rights. To use a different startup model, set `DEFAULT_MODEL` to the folder/model name:

   ```shell
   DEFAULT_MODEL=my_model uv run api/app.py
   ```

2. **Pre-generate geometry model:** There is a small CLI to extract and save element-wise geometry for an IFC model. Example usage:

   ```shell
   uv run python -m scripts.generate_geometry api/static/models/2026-SampleModel/2026-SampleModel.ifc --formats OBJ GLB STL
   ```

   The generated geometry files will be located at `api/static/models/<model name>/elements/<element guid>/`.

3. **Start the GraphQL server:** The repository provides a small Flask + Ariadne server in `api/app.py` that serves a GraphQL endpoint (by default `/graphql`). Start it like:

   ```shell
   uv run api/app.py
   ```

   The server exposes the IFC model in the GraphQL context and can return geometry URLs for pre-generated files or embedded payloads from files or dynamic exporters.

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
- `properties(pset: String)`: common PSet values as `{ name, value, pset }`
- `partOf` / `contains`: relationships to parent/children elements

Supported geometry formats are `OBJ`, `GLB`, `STL`, `STL_ASCII`, `PLY`,
`PLY_ASCII`, `OFF`, and `BREP`. `BREP` is exposed for future exact-geometry
support and currently resolves from existing `.brep` files only.

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

**Fetch one element by id and request inline OBJ:**

```graphql
query GetElement {
  model(name: "2026-SampleModel") {
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

## Development & next steps

Currently at proof-of-concept level, not optimized and no security hardening yet.
