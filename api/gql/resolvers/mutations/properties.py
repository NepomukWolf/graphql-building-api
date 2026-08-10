from ariadne import MutationType
from graphql.type.definition import GraphQLResolveInfo


property_mutations = MutationType()


@property_mutations.field("updateProperty")
def resolve_update_property(_obj, info: GraphQLResolveInfo, input: dict):
    pass
