from graphql_building_api.gql.resolvers.mutations.properties import property_mutations
from graphql_building_api.gql.resolvers.queries.building import building_queries
from graphql_building_api.gql.resolvers.types.elements import building_element
from graphql_building_api.gql.resolvers.types.geometry import geometry
from graphql_building_api.gql.resolvers.types.materials import (
    material,
    material_assignment,
    material_layer,
    material_layer_set,
)
from graphql_building_api.gql.resolvers.types.zones import building, space, storey, zone

all_types = [
    building_queries,
    property_mutations,
    zone,
    building,
    storey,
    space,
    building_element,
    geometry,
    material,
    material_layer,
    material_layer_set,
    material_assignment,
]

__all__ = ["all_types"]
