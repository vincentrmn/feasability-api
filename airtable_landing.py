"""
AIRTABLE LANDING — recuperation cote serveur des tables de couverture pour le cockpit
de la page d'accueil, avec cache TTL en memoire.

Pourquoi cote serveur : faire 6 appels Airtable depuis n8n a CHAQUE visite de la page
d'accueil sature la limite Airtable (5 req/s/base) et fait ramer/planter la page.
Ici on lit une fois toutes les `_CACHE_TTL_S` secondes et on sert depuis le cache.

Degradation gracieuse : si `AIRTABLE_API_KEY` est absente ou si Airtable est
injoignable, on renvoie des listes vides (la page d'accueil affiche le formulaire
sans cockpit) — jamais d'erreur, jamais de page qui rame.
"""
import os
import time
from typing import Dict, List, Any

import requests

_BASE = "appFUtt83fMC6NwgU"
_TABLES = {
    "zones": "tbll7YFXuR9ug1brF",
    "stationnement": "tblR2DFZdSJKSQ2JW",
    "velo": "tbl87Z0liDcIzgPnd",
    "servitudes": "tbl0yLbARCP1SpUho",
    "pap_nq": "tblaa3HSpGvStwJWG",
    "communes": "tblol1ZHPJTiho4fz",
}
_CACHE_TTL_S = 300
_HTTP_TIMEOUT_S = 8

_cache: Dict[str, Any] = {"t": 0.0, "data": None}


def _empty() -> Dict[str, List[dict]]:
    return {k: [] for k in _TABLES}


def _fetch_table(table_id: str, key: str) -> List[dict]:
    """Liste tous les records (fields uniquement) d'une table, paginee."""
    out: List[dict] = []
    url = f"https://api.airtable.com/v0/{_BASE}/{table_id}"
    headers = {"Authorization": f"Bearer {key}"}
    params = {"pageSize": 100}
    for _ in range(20):  # garde-fou pagination
        r = requests.get(url, headers=headers, params=params, timeout=_HTTP_TIMEOUT_S)
        r.raise_for_status()
        j = r.json()
        out.extend(rec.get("fields", {}) for rec in j.get("records", []))
        offset = j.get("offset")
        if not offset:
            break
        params["offset"] = offset
    return out


def fetch_landing_data(force: bool = False) -> Dict[str, List[dict]]:
    """Renvoie {zones, stationnement, velo, servitudes, pap_nq, communes}.
    Sert depuis le cache si frais ; sinon refetch. Toujours safe (jamais d'exception)."""
    key = os.environ.get("AIRTABLE_API_KEY")
    if not key:
        return _empty()
    now = time.time()
    if not force and _cache["data"] is not None and (now - _cache["t"]) < _CACHE_TTL_S:
        return _cache["data"]
    try:
        data = {name: _fetch_table(tid, key) for name, tid in _TABLES.items()}
        _cache["data"] = data
        _cache["t"] = now
        return data
    except Exception:
        # Airtable down / rate-limit : on sert le dernier cache connu, sinon vide.
        return _cache["data"] or _empty()
