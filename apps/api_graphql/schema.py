"""Schéma GraphQL local — requêtes de lecture uniquement."""

import graphene

from apps.api_graphql.queries import Query

schema = graphene.Schema(query=Query)
