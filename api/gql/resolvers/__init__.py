from api.gql.resolvers.mutations.properties import property_mutations
from api.gql.resolvers.queries.models import model_queries
from api.gql.resolvers.types.elements import building_element
from api.gql.resolvers.types.geometry import geometry
from api.gql.resolvers.types.models import model, model_info
from api.gql.resolvers.types.zones import building, space, storey, zone

all_types = [
    model_queries,
    property_mutations,
    model,
    model_info,
    zone,
    building,
    storey,
    space,
    building_element,
    geometry,
]

__all__ = ["all_types"]
