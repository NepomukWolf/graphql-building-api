# API Package

FastAPI + Ariadne GraphQL server and IFC resolver implementation. The
simplified schema is reusable independently or through the multi-level host and
selects its IFC model from the endpoint rather than the GraphQL document.

Local IFC files are not stored in this package. Add user-owned models under
`graphql_building_api/static/models/<model>/<model>.ifc` before running model-specific queries.
