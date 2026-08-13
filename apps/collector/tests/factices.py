"""Fabriques de réponses AniList simulées, partagées par les tests.

Aucun test ne dépend de la disponibilité réelle d'AniList : les réponses
sont construites ici à partir de la structure documentée de l'API.
"""

from unittest import mock

from apps.collector.anilist_client import RateLimitInfo


def noeud_personnage(anilist_id=10, nom="Edward Elric", **surcharges):
    noeud = {
        "id": anilist_id,
        "name": {"full": nom, "native": "エドワード・エルリック"},
        "image": {"large": f"https://img.anilist.co/perso{anilist_id}.jpg"},
        "description": "Description courte.",
        "gender": "Male",
        "age": "15",
    }
    noeud.update(surcharges)
    return noeud


def arete_personnage(anilist_id=10, role="MAIN", **surcharges):
    return {"role": role, "node": noeud_personnage(anilist_id, **surcharges)}


def arete_studio(anilist_id=100, nom="Bones", is_main=True, animation=True):
    return {
        "isMain": is_main,
        "node": {"id": anilist_id, "name": nom, "isAnimationStudio": animation},
    }


def noeud_media(anilist_id=1, **surcharges):
    """Construit un nœud Media complet et valide."""
    media = {
        "id": anilist_id,
        "idMal": 1000 + anilist_id,
        "title": {
            "romaji": "Hagane no Renkinjutsushi",
            "english": "Fullmetal Alchemist",
            "native": "鋼の錬金術師",
        },
        "type": "ANIME",
        "format": "TV",
        "status": "FINISHED",
        "description": "Deux freres cherchent la pierre philosophale.",
        "startDate": {"year": 2009, "month": 4, "day": 5},
        "endDate": {"year": 2010, "month": 7, "day": 4},
        "season": "SPRING",
        "seasonYear": 2009,
        "episodes": 64,
        "chapters": None,
        "volumes": None,
        "coverImage": {"large": f"https://img.anilist.co/cover{anilist_id}.jpg"},
        "bannerImage": f"https://img.anilist.co/banner{anilist_id}.jpg",
        "genres": ["Action", "Adventure", "Drama"],
        "averageScore": 90,
        "popularity": 500000,
        "studios": {"edges": [arete_studio()]},
        "characters": {"edges": [arete_personnage()]},
    }
    media.update(surcharges)
    return media


def page_media(medias, has_next_page=False, page_courante=1):
    """Enveloppe des œuvres dans la structure `Page` retournée par AniList."""
    return {
        "Page": {
            "pageInfo": {
                "currentPage": page_courante,
                "hasNextPage": has_next_page,
                "lastPage": 5000,
                "total": 5000,
            },
            "media": list(medias),
        }
    }


class ClientFactice:
    """Client AniList simulé, qui rejoue une file de réponses prédéfinies.

    Un élément de la file qui est une exception est levé au lieu d'être
    retourné, ce qui permet de simuler une panne réseau sur une page précise.
    """

    def __init__(self, reponses, limite=30, pause=2.1):
        self.reponses = list(reponses)
        self.appels = []
        self.rate_limit = RateLimitInfo(limit=limite)
        self._pause = pause

    def execute_query(self, query, variables=None):
        self.appels.append(variables)
        if not self.reponses:
            raise AssertionError("Appel AniList inattendu : la file est vide.")
        reponse = self.reponses.pop(0)
        if isinstance(reponse, Exception):
            raise reponse
        return reponse

    def recommended_page_delay(self):
        return self._pause


def reponse_http(status_code=200, corps=None, entetes=None, json_invalide=False):
    """Construit une réponse `requests` simulée."""
    reponse = mock.Mock()
    reponse.status_code = status_code
    reponse.headers = {} if entetes is None else entetes
    if json_invalide:
        reponse.json.side_effect = ValueError("JSON invalide")
    else:
        reponse.json.return_value = {} if corps is None else corps
    return reponse
