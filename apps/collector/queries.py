"""Requêtes GraphQL envoyées à l'API AniList.

Les noms de champs proviennent de la référence officielle
(docs.anilist.co/reference/object/media) et ont été validés par un appel réel
contrôlé avant l'écriture de la couche de persistance.

Deux choix méritent une explication.

`startDate_greater` et `startDate_lesser` servent au filtre par année plutôt que
`seasonYear` : AniList impose normalement de fournir `season` en même temps que
`seasonYear`, ce qui rendrait un filtre annuel autonome inutilisable. Les bornes
sont des `FuzzyDateInt`, c'est-à-dire des entiers de la forme AAAAMMJJ.

`studios` est interrogé sans l'argument `isMain` : ce filtre écarterait
silencieusement les studios secondaires. Le drapeau est lu sur chaque arête.
"""

# Nombre de personnages récupérés par œuvre. AniList plafonne les
# sous-connexions à 25 éléments par page ; la valeur est répétée en littéral
# dans la requête ci-dessous, GraphQL n'acceptant pas d'interpolation.
MAX_CHARACTERS_PER_MEDIA = 25

FETCH_MEDIA_PAGE_QUERY = """
query (
  $page: Int!
  $perPage: Int!
  $type: MediaType!
  $yearGreater: FuzzyDateInt
  $yearLesser: FuzzyDateInt
  $genres: [String]
  $status: MediaStatus
  $sort: [MediaSort]
) {
  Page(page: $page, perPage: $perPage) {
    pageInfo {
      currentPage
      hasNextPage
      lastPage
      perPage
      total
    }
    media(
      type: $type
      startDate_greater: $yearGreater
      startDate_lesser: $yearLesser
      genre_in: $genres
      status: $status
      sort: $sort
    ) {
      id
      idMal
      title {
        romaji
        english
        native
      }
      type
      format
      status
      description(asHtml: false)
      startDate {
        year
        month
        day
      }
      endDate {
        year
        month
        day
      }
      season
      seasonYear
      episodes
      chapters
      volumes
      coverImage {
        large
      }
      bannerImage
      genres
      averageScore
      popularity
      studios {
        edges {
          isMain
          node {
            id
            name
            isAnimationStudio
          }
        }
      }
      characters(page: 1, perPage: 25, sort: [ROLE, RELEVANCE]) {
        edges {
          role
          node {
            id
            name {
              full
              native
            }
            image {
              large
            }
            description
            gender
            age
          }
        }
      }
    }
  }
}
"""
