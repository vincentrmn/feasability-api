"""
Routes Palladio — extraites de main.py (roadmap point 12, archi propre).

Expose le moteur Palladio (palladio_engine) et le rendu HTML (palladio_render)
via un APIRouter monte par main.py. Aucune logique metier ici : uniquement le
contrat HTTP (modeles d'entree + routes), tout le calcul est dans palladio_engine.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any

from palladio_engine import (
    calculer_emprise_palladio, calculer_palladio_full, geocode_search, PalladioError,
)
from palladio_render import render_palladio_html
from cockpit_render import compute_communes_status, render_landing_html
from airtable_landing import fetch_landing_data

router = APIRouter()


class PalladioRequest(BaseModel):
    """Input pour POST /palladio/calcul - Sprint 1 enveloppe seule."""

    parcel_geometry_wgs84: Dict[str, Any] = Field(
        ...,
        description="GeoJSON Polygon en WGS84. Ex: {'type': 'Polygon', 'coordinates': [[[lon, lat], ...]]}",
    )
    point_geocode_wgs84: List[float] = Field(
        ...,
        description="[lon, lat] WGS84 du point geocode, sert a identifier la voirie",
        min_length=2,
        max_length=2,
    )
    recul_avant_m: float = Field(..., ge=0, description="Recul avant en metres")
    recul_lateral_m: float = Field(..., ge=0, description="Recul lateral en metres")
    recul_arriere_m: float = Field(..., ge=0, description="Recul arriere en metres")
    profondeur_max_m: Optional[float] = Field(
        default=None, ge=0,
        description="Profondeur max totale depuis voirie (recul_avant + prof_max)",
    )
    parcelle_id: Optional[str] = Field(
        default=None,
        description="ID cadastral Geoportail (ex: 114B00133002970). Active la detection "
                    "voirie par adjacence cadastrale (Sprint 1.5). Si absent : geocode_proximity.",
    )


class PalladioFullRequest(PalladioRequest):
    """Input pour POST /palladio/calcul/full - Sprint 2 (enveloppe + metier)."""

    zone_pag: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Regles PAG mappees depuis Airtable : niveaux_pleins_max, "
                    "combles_retrait, type_zone, logement_autorise, commerce_autorise, "
                    "cus_max, min_scb_logement_pct, dl_max, nb_log_max_par_construction.",
    )
    corriger_hab1: bool = Field(
        default=True,
        description="Si True (defaut), corrige le bug HAB-1 (comptage logements base SCB coherente).",
    )
    recul_avant_methode: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Methode de recul avant typee (Palladio Scrap) : "
                    "{type: fixe|alignement_voisins|lie_hauteur, fallback_m, coef_hauteur, plancher_m}. "
                    "Absent -> recul avant scalaire (comportement historique).",
    )
    corniche_effective_m: Optional[float] = Field(
        default=None, description="Hauteur a la corniche, pour le recul avant lie_hauteur.",
    )
    adresse: Optional[str] = Field(
        default="", description="Adresse affichee dans la page HTML (route /full/html).",
    )
    contexte: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Contexte d'affichage non porte par le moteur (route /full/html) : "
                    "parcel_label, code_zone, nom_zone, regles (champs Airtable).",
    )


@router.post("/palladio/calcul")
def calcul_palladio(req: PalladioRequest):
    """Sprint 1 - enveloppe constructible 2D pure. 400 si parcelle/reculs invalides."""
    try:
        return calculer_emprise_palladio(
            parcel_geometry_wgs84=req.parcel_geometry_wgs84,
            point_geocode_wgs84=req.point_geocode_wgs84,
            recul_avant_m=req.recul_avant_m,
            recul_lateral_m=req.recul_lateral_m,
            recul_arriere_m=req.recul_arriere_m,
            profondeur_max_m=req.profondeur_max_m,
            parcelle_id=req.parcelle_id,
        )
    except PalladioError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _full(req: PalladioFullRequest):
    """Appel moteur complet, partage par /full et /full/html (contrat unique)."""
    return calculer_palladio_full(
        parcel_geometry_wgs84=req.parcel_geometry_wgs84,
        point_geocode_wgs84=req.point_geocode_wgs84,
        recul_avant_m=req.recul_avant_m,
        recul_lateral_m=req.recul_lateral_m,
        recul_arriere_m=req.recul_arriere_m,
        zone_pag=req.zone_pag,
        profondeur_max_m=req.profondeur_max_m,
        parcelle_id=req.parcelle_id,
        corriger_hab1=req.corriger_hab1,
        recul_avant_methode=req.recul_avant_methode,
        corniche_effective_m=req.corniche_effective_m,
    )


@router.post("/palladio/calcul/full")
def calcul_palladio_full_route(req: PalladioFullRequest):
    """Sprint 2 - enveloppe + SCB + logements + parkings + type + warnings (JSON)."""
    try:
        return _full(req)
    except PalladioError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/palladio/calcul/full/html", response_class=HTMLResponse)
def calcul_palladio_full_html(req: PalladioFullRequest):
    """Idem /full mais renvoie la page HTML (renderer palladio_render)."""
    resp = _full(req)
    return HTMLResponse(content=render_palladio_html(resp, req.adresse or "", req.contexte))


@router.get("/palladio/search")
def palladio_search(q: str = ""):
    """Autocomplete d'adresse officielle (geocodeur Geoportail).

    Renvoie les candidats avec leur cle cadastrale pour que la page d'accueil
    laisse l'utilisateur CHOISIR la bonne adresse/parcelle, au lieu de prendre
    aveuglement le 1er resultat (cause des erreurs de parcelle en drapeau).
    Jamais de 500 : requete vide ou geoportail injoignable -> results vide."""
    return {"query": q, "results": geocode_search(q)}


@router.get("/palladio/landing/html", response_class=HTMLResponse)
def palladio_landing_html():
    """Page d'accueil = formulaire d'adresse + cockpit de couverture des communes.
    Servie sur l'interface principale (webhook n8n /webhook/palladio).

    Les donnees de couverture sont lues cote serveur depuis Airtable, en cache
    (airtable_landing) : un seul refetch toutes les 5 min, pas d'appel Airtable
    par visite. Si la cle Airtable manque -> formulaire seul, sans erreur."""
    d = fetch_landing_data()
    status = compute_communes_status(
        zones=d["zones"], stationnement=d["stationnement"], velo=d["velo"],
        servitudes=d["servitudes"], pap_nq=d["pap_nq"], communes_meta=d["communes"],
    )
    return HTMLResponse(content=render_landing_html(status))
