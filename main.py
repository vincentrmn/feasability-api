"""
FEASIBILITY.LU — API de calcul de faisabilité immobilière
Deploy on Railway: https://railway.app
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import math
import json

app = FastAPI(
    title="Feasibility.lu API",
    description="Moteur de calcul de faisabilité immobilière — Luxembourg",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# DATA MODELS
# ============================================================

class CalculRequest(BaseModel):
    surface_terrain_m2: float = Field(..., gt=0, description="Surface du terrain en m²")
    zone_pag: str = Field(..., description="Code zone PAG (ex: HAB-1, MIX-u)")
    commune: str = Field(default="Strassen", description="Nom de la commune")
    largeur_facade_m: Optional[float] = Field(default=None, description="Largeur façade estimée (m)")
    route_arlon: bool = Field(default=False, description="Parcelle le long de la Route d'Arlon")
    adresse: Optional[str] = Field(default=None, description="Adresse de la parcelle")
    num_cadastral: Optional[str] = Field(default=None, description="Numéro cadastral")


# ============================================================
# BASE DE DONNÉES ZONES (Strassen)
# ============================================================

ZONES = {
    "Strassen": {
        "HAB-1": {
            "nom": "Zone d'habitation 1",
            "pap_qe": "QE1",
            "type": "Habitation",
            "constructible": True,
            "logement": True,
            "commerce": False,
            "h_corniche_max": 8.0,
            "h_faite_max": 12.0,
            "niveaux_pleins_max": 2,
            "combles_retrait": True,
            "niveaux_sous_sol_max": 1,
            "recul_avant_min": 3.0,
            "recul_avant_max": 6.0,
            "recul_lateral_min": 3.0,
            "recul_arriere_min": 10.0,
            "profondeur_max": 14.0,
            "cos_max": 0.35,
            "css_max": 0.60,
            "nb_log_max_par_construction": 2,
            "dl_max": None,
            "min_scb_logement_pct_qe": None,
            "min_scb_logement_pct_nq": 90,
            "surface_vente_max": None,
            "construction_2e_position": False,
        },
        "HAB-2": {
            "nom": "Zone d'habitation 2",
            "pap_qe": "QE2",
            "type": "Habitation",
            "constructible": True,
            "logement": True,
            "commerce": False,
            "h_corniche_max": 11.0,
            "h_faite_max": 15.0,
            "niveaux_pleins_max": 3,
            "combles_retrait": True,
            "niveaux_sous_sol_max": None,
            "recul_avant_min": 3.0,
            "recul_avant_max": 7.0,
            "recul_lateral_min": 4.5,
            "recul_arriere_min": 12.0,
            "profondeur_max": 14.0,
            "cos_max": 0.35,
            "css_max": 0.50,
            "nb_log_max_par_construction": None,
            "dl_max": 105,
            "min_scb_logement_pct_qe": 70,
            "min_scb_logement_pct_nq": 80,
            "surface_vente_max": None,
            "construction_2e_position": True,
        },
        "MIX-u": {
            "nom": "Zone mixte urbaine",
            "pap_qe": "QE2",
            "type": "Mixte",
            "constructible": True,
            "logement": True,
            "commerce": True,
            "h_corniche_max": 11.0,
            "h_faite_max": 15.0,
            "niveaux_pleins_max": 3,
            "combles_retrait": True,
            "niveaux_sous_sol_max": None,
            "recul_avant_min": 3.0,
            "recul_avant_max": 7.0,
            "recul_lateral_min": 4.5,
            "recul_arriere_min": 12.0,
            "profondeur_max": 14.0,
            "cos_max": 0.35,
            "css_max": 0.50,
            "nb_log_max_par_construction": None,
            "dl_max": 105,
            "min_scb_logement_pct_qe": 50,
            "min_scb_logement_pct_nq": 25,
            "min_scb_autre_pct_nq": 10,
            "surface_vente_max": 10000,
            "construction_2e_position": True,
        },
        "MIX-v": {
            "nom": "Zone mixte villageoise",
            "pap_qe": "QE2",
            "type": "Mixte",
            "constructible": True,
            "logement": True,
            "commerce": True,
            "h_corniche_max": 11.0,
            "h_faite_max": 15.0,
            "niveaux_pleins_max": 3,
            "combles_retrait": True,
            "niveaux_sous_sol_max": None,
            "recul_avant_min": 3.0,
            "recul_avant_max": 7.0,
            "recul_lateral_min": 4.5,
            "recul_arriere_min": 12.0,
            "profondeur_max": 14.0,
            "cos_max": 0.35,
            "css_max": 0.50,
            "nb_log_max_par_construction": None,
            "dl_max": 105,
            "min_scb_logement_pct_qe": 70,
            "min_scb_logement_pct_nq": 50,
            "min_scb_autre_pct_nq": 10,
            "surface_vente_max": 2000,
            "construction_2e_position": True,
        },
        "BEP": {
            "nom": "Zone bâtiments et équipements publics",
            "pap_qe": "QE3",
            "type": "Equipement public",
            "constructible": True,
            "logement": False,
            "commerce": False,
            "h_corniche_max": 14.0,
            "h_faite_max": 18.0,
            "niveaux_pleins_max": 4,
            "combles_retrait": False,
            "niveaux_sous_sol_max": None,
            "recul_avant_min": 0,
            "recul_avant_max": None,
            "recul_lateral_min": 3.0,
            "recul_arriere_min": 5.0,
            "profondeur_max": None,
            "cos_max": None,
            "css_max": None,
            "nb_log_max_par_construction": None,
            "dl_max": 105,
            "surface_vente_max": None,
            "construction_2e_position": True,
        },
        "BEP-ep": {
            "nom": "Zone d'espaces publics",
            "pap_qe": "QE4",
            "type": "Equipement public",
            "constructible": False,
            "logement": False,
            "commerce": False,
            "h_corniche_max": 5.0,
            "h_faite_max": None,
            "niveaux_pleins_max": 1,
            "combles_retrait": False,
            "niveaux_sous_sol_max": None,
            "recul_avant_min": 0,
            "recul_avant_max": None,
            "recul_lateral_min": 0,
            "recul_arriere_min": 0,
            "profondeur_max": None,
            "cos_max": 0.20,
            "css_max": 0.20,
            "nb_log_max_par_construction": None,
            "dl_max": None,
            "surface_vente_max": None,
            "construction_2e_position": False,
        },
        "ECO-c1": {
            "nom": "Zone d'activités économiques communale type 1",
            "pap_qe": "QE6",
            "type": "Activités",
            "constructible": True,
            "logement": False,
            "commerce": True,
            "h_corniche_max": 10.0,
            "h_faite_max": 13.0,
            "niveaux_pleins_max": 3,
            "combles_retrait": False,
            "niveaux_sous_sol_max": None,
            "recul_avant_min": 7.0,
            "recul_avant_max": None,
            "recul_lateral_min": 4.0,
            "recul_arriere_min": 4.0,
            "profondeur_max": None,
            "cos_max": 0.50,
            "css_max": 0.80,
            "nb_log_max_par_construction": None,
            "dl_max": None,
            "surface_vente_max": 2000,
            "construction_2e_position": True,
        },
        "SPEC-AD": {
            "nom": "Zone spéciale Administration",
            "pap_qe": "QE6",
            "type": "Spéciale",
            "constructible": True,
            "logement": False,
            "commerce": True,
            "h_corniche_max": 10.0,
            "h_faite_max": 13.0,
            "niveaux_pleins_max": 3,
            "combles_retrait": False,
            "niveaux_sous_sol_max": None,
            "recul_avant_min": 7.0,
            "recul_avant_max": None,
            "recul_lateral_min": 4.0,
            "recul_arriere_min": 4.0,
            "profondeur_max": None,
            "cos_max": 0.50,
            "css_max": 0.80,
            "nb_log_max_par_construction": None,
            "dl_max": None,
            "surface_vente_max": 10000,
            "construction_2e_position": True,
        },
        "COM": {
            "nom": "Zone commerciale",
            "pap_qe": "QE7",
            "type": "Commercial",
            "constructible": True,
            "logement": False,
            "commerce": True,
            "h_corniche_max": 13.0,
            "h_faite_max": 18.0,
            "niveaux_pleins_max": 3,
            "combles_retrait": True,
            "niveaux_sous_sol_max": None,
            "recul_avant_min": 7.0,
            "recul_avant_max": None,
            "recul_lateral_min": 4.0,
            "recul_arriere_min": 4.0,
            "profondeur_max": None,
            "cos_max": None,
            "css_max": None,
            "nb_log_max_par_construction": 2,
            "dl_max": None,
            "surface_vente_max": None,
            "construction_2e_position": True,
        },
        "REC-tr": {
            "nom": "Zone sports et loisirs - tourisme rural",
            "pap_qe": "QE5",
            "type": "Loisirs",
            "constructible": True,
            "logement": False,
            "commerce": False,
            "h_corniche_max": 10.0,
            "h_faite_max": 15.0,
            "niveaux_pleins_max": 2,
            "combles_retrait": True,
            "niveaux_sous_sol_max": 1,
            "recul_avant_min": 5.0,
            "recul_avant_max": None,
            "recul_lateral_min": 5.0,
            "recul_arriere_min": 5.0,
            "profondeur_max": 30.0,
            "cos_max": 0.30,
            "css_max": 0.50,
            "nb_log_max_par_construction": None,
            "dl_max": None,
            "surface_vente_max": None,
            "construction_2e_position": True,
        },
        "REC-eq": {
            "nom": "Zone sports et loisirs - centre équestre",
            "pap_qe": "QE5",
            "type": "Loisirs",
            "constructible": True,
            "logement": False,
            "commerce": False,
            "h_corniche_max": 10.0,
            "h_faite_max": 15.0,
            "niveaux_pleins_max": 2,
            "combles_retrait": True,
            "niveaux_sous_sol_max": 1,
            "recul_avant_min": 5.0,
            "recul_avant_max": None,
            "recul_lateral_min": 5.0,
            "recul_arriere_min": 5.0,
            "profondeur_max": 30.0,
            "cos_max": 0.30,
            "css_max": 0.50,
            "nb_log_max_par_construction": None,
            "dl_max": None,
            "surface_vente_max": None,
            "construction_2e_position": True,
        },
    }
}

ZONES_NON_CONSTRUCTIBLES = ["AGR", "FOR", "PARC", "VERD"]

# Mix standard Luxembourg — moyenne SHN ≥ 52m²
MIX_STANDARD = {
    "T1_studio": {"pct": 0.20, "shn_m2": 35, "scb_m2": 44},
    "T2":        {"pct": 0.35, "shn_m2": 52, "scb_m2": 65},
    "T3":        {"pct": 0.30, "shn_m2": 70, "scb_m2": 88},
    "T4+":       {"pct": 0.15, "shn_m2": 90, "scb_m2": 113},
}
SCB_MOYENNE_PAR_LOGEMENT = sum(t["scb_m2"] * t["pct"] for t in MIX_STANDARD.values())


# ============================================================
# PARKINGS
# ============================================================

def calculer_parkings(nb_logements, mix_logements, scb_commerce=0, scb_bureaux=0):
    p_min = 0
    p_max = 0
    for _, data in mix_logements.items():
        nb = data["nb"]
        shn = data["shn_m2"]
        if shn < 60:
            p_min += nb * 1; p_max += nb * 1
        elif shn <= 90:
            p_min += nb * 1; p_max += nb * 2
        else:
            p_min += nb * 1; p_max += nb * 3
    if scb_commerce > 0:
        p_com = math.ceil(scb_commerce / 20)
        p_min += p_com; p_max += p_com
    if scb_bureaux > 0:
        p_min += math.ceil(scb_bureaux / 90)
        p_max += math.ceil(scb_bureaux / 60)
    return {"min": p_min, "max": p_max}


def calculer_parkings_velo(nb_logements, scb_commerce=0, scb_bureaux=0):
    v = nb_logements
    if scb_commerce > 0:
        v += math.ceil(scb_commerce / 50) if scb_commerce < 2000 else math.ceil(scb_commerce / 200)
    if scb_bureaux > 0:
        v += math.ceil(scb_bureaux / 500)
    return v


# ============================================================
# MOTEUR DE CALCUL
# ============================================================

def calculer_faisabilite(req: CalculRequest) -> dict:
    result = {
        "identification": {
            "commune": req.commune,
            "zone_pag": req.zone_pag,
            "surface_terrain_m2": req.surface_terrain_m2,
            "adresse": req.adresse,
            "num_cadastral": req.num_cadastral,
        },
        "regles": {},
        "programme": {},
        "contraintes": [],
        "verdict": {},
    }

    # Zone non constructible
    if req.zone_pag in ZONES_NON_CONSTRUCTIBLES:
        result["verdict"] = {
            "constructible": "Non",
            "potentiel": "Aucun",
            "raison": f"Zone {req.zone_pag} — zone verte, non constructible",
        }
        return result

    # Commune non référencée
    commune_zones = ZONES.get(req.commune)
    if not commune_zones:
        result["verdict"] = {
            "constructible": "Indéterminé",
            "potentiel": "Indéterminé",
            "raison": f"Commune '{req.commune}' non encore référencée dans la base de données",
        }
        return result

    # Zone non référencée
    zone = commune_zones.get(req.zone_pag)
    if not zone:
        result["verdict"] = {
            "constructible": "Indéterminé",
            "potentiel": "Indéterminé",
            "raison": f"Zone '{req.zone_pag}' non référencée pour {req.commune}",
        }
        return result

    result["regles"] = {
        "nom_zone": zone["nom"],
        "pap_qe": zone["pap_qe"],
        "type_zone": zone["type"],
        "h_corniche_max": zone["h_corniche_max"],
        "h_faite_max": zone["h_faite_max"],
        "niveaux_pleins_max": zone["niveaux_pleins_max"],
        "combles_retrait": zone["combles_retrait"],
        "recul_avant_min": zone["recul_avant_min"],
        "recul_lateral_min": zone["recul_lateral_min"],
        "recul_arriere_min": zone["recul_arriere_min"],
        "profondeur_max": zone["profondeur_max"],
        "cos_max": zone["cos_max"],
        "css_max": zone["css_max"],
        "dl_max": zone["dl_max"],
    }

    if not zone["constructible"]:
        result["verdict"] = {
            "constructible": "Non",
            "potentiel": "Aucun",
            "raison": f"Zone {req.zone_pag} ({zone['nom']}) — constructions très limitées",
        }
        return result

    # --- GÉOMÉTRIE ---
    surface = req.surface_terrain_m2
    largeur = req.largeur_facade_m or math.sqrt(surface)
    profondeur_terrain = surface / largeur

    recul_avant = zone["recul_avant_min"]
    recul_lateral = zone["recul_lateral_min"]
    recul_arriere = zone["recul_arriere_min"]

    # Route d'Arlon — reculs majorés QE2
    if req.route_arlon and zone["pap_qe"] == "QE2":
        recul_avant = 15
        recul_lateral = max(zone["h_corniche_max"] / 2, 4.5)
        result["contraintes"].append("Parcelle le long de la Route d'Arlon — reculs majorés appliqués")

    profondeur_utile = profondeur_terrain - recul_avant - recul_arriere
    largeur_utile = largeur - 2 * recul_lateral

    if profondeur_utile <= 0 or largeur_utile <= 0:
        result["verdict"] = {
            "constructible": "Sous conditions",
            "potentiel": "Très faible",
            "raison": "Parcelle trop étroite/peu profonde pour respecter les reculs réglementaires",
        }
        return result

    # Profondeur max
    prof_max = zone["profondeur_max"]
    if prof_max and profondeur_utile > prof_max:
        profondeur_utile = prof_max

    # Emprise au sol
    emprise_reculs = largeur_utile * profondeur_utile
    cos_max = zone["cos_max"]
    emprise_au_sol = min(emprise_reculs, surface * cos_max) if cos_max else emprise_reculs

    # --- SCB ---
    niveaux = zone["niveaux_pleins_max"]
    scb_niveaux = emprise_au_sol * niveaux
    scb_combles = emprise_au_sol * 0.60 if zone["combles_retrait"] else 0
    scb_totale = scb_niveaux + scb_combles

    # Sous-sol
    emprise_ss = emprise_au_sol
    if zone["pap_qe"] == "QE2":
        prof_ss = min(profondeur_terrain - recul_avant - 4.5, 18)
        if prof_ss > profondeur_utile:
            emprise_ss = largeur_utile * prof_ss

    # --- PROGRAMME ---
    scb_commerce = 0
    if zone["type"] == "Mixte":
        min_log_pct = zone.get("min_scb_logement_pct_qe", 50) or 50
        scb_commerce = emprise_au_sol * 0.80
        scb_logement = scb_totale - scb_commerce
        if scb_logement < scb_totale * (min_log_pct / 100):
            scb_logement = scb_totale * (min_log_pct / 100)
            scb_commerce = scb_totale - scb_logement
    else:
        scb_logement = scb_totale

    # Nombre logements
    if zone["logement"]:
        nb_log = scb_logement / SCB_MOYENNE_PAR_LOGEMENT
        dl_max = zone["dl_max"]
        if dl_max:
            nb_log = min(nb_log, (surface / 10000) * dl_max)
        nb_log_max = zone.get("nb_log_max_par_construction")
        if nb_log_max:
            nb_log = min(nb_log, nb_log_max)
        nb_logements = max(1, math.floor(nb_log))
    else:
        nb_logements = 0
        scb_logement = 0
        scb_commerce = scb_totale

    # Mix logements
    mix_detail = {}
    if nb_logements <= 2:
        mix_detail = {"T3": {"nb": nb_logements, "shn_m2": 70, "scb_m2": 88}}
    elif nb_logements > 0:
        for type_log, data in MIX_STANDARD.items():
            mix_detail[type_log] = {
                "nb": max(1, round(nb_logements * data["pct"])),
                "shn_m2": data["shn_m2"],
                "scb_m2": data["scb_m2"],
            }
        total_mix = sum(d["nb"] for d in mix_detail.values())
        if total_mix != nb_logements:
            mix_detail["T2"]["nb"] += nb_logements - total_mix

    # Moyenne SHN
    total_log = sum(d["nb"] for d in mix_detail.values())
    avg_shn = sum(d["shn_m2"] * d["nb"] for d in mix_detail.values()) / total_log if total_log > 0 else 0

    # Parkings
    parkings = calculer_parkings(nb_logements, mix_detail, scb_commerce) if nb_logements > 0 else {"min": 0, "max": 0}
    if scb_commerce > 0 and nb_logements == 0:
        parkings = {"min": math.ceil(scb_commerce / 20), "max": math.ceil(scb_commerce / 20)}
    parkings_velo = calculer_parkings_velo(nb_logements, scb_commerce)

    # Contraintes
    if zone.get("css_max"):
        result["contraintes"].append(f"Surface scellée max: {surface * zone['css_max']:.0f} m² (CSS {zone['css_max']})")
    if req.zone_pag == "HAB-1":
        result["contraintes"].append("Max 2 logements par construction (y compris logement intégré)")
        result["contraintes"].append("Construction en 2e position interdite (sauf habitations légères)")
    if avg_shn < 52 and total_log > 0:
        result["contraintes"].append(f"⚠️ Moyenne SHN {avg_shn:.0f}m² < 52m² réglementaire — ajuster le mix")

    # Verdict
    if nb_logements == 0 and zone["type"] in ["Activités", "Commercial", "Spéciale", "Loisirs"]:
        potentiel = "Moyen" if scb_totale > 500 else "Faible"
    elif nb_logements <= 2:
        potentiel = "Faible"
    elif nb_logements <= 6:
        potentiel = "Moyen"
    else:
        potentiel = "Fort"

    result["programme"] = {
        "emprise_au_sol_m2": round(emprise_au_sol, 1),
        "scb_totale_m2": round(scb_totale, 1),
        "scb_niveaux_pleins_m2": round(scb_niveaux, 1),
        "scb_combles_retrait_m2": round(scb_combles, 1),
        "scb_logement_m2": round(scb_logement, 1),
        "scb_commerce_m2": round(scb_commerce, 1),
        "nb_logements": nb_logements,
        "mix_logements": mix_detail,
        "moyenne_shn_m2": round(avg_shn, 1),
        "respect_moyenne_52m2": avg_shn >= 52 or total_log == 0,
        "parkings_auto": parkings,
        "parkings_velo": parkings_velo,
        "surface_parking_ss_estimee_m2": parkings["min"] * 25,
        "emprise_sous_sol_m2": round(emprise_ss, 1),
        "niveaux_programme": f"R+{niveaux - 1}{'+C' if zone['combles_retrait'] else ''}",
    }

    result["verdict"] = {
        "constructible": "Oui",
        "potentiel": potentiel,
        "points_attention": result["contraintes"],
    }

    return result


# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/")
def root():
    return {
        "service": "Feasibility.lu API",
        "version": "1.0.0",
        "communes_disponibles": list(ZONES.keys()),
        "endpoint": "POST /calcul",
    }


@app.get("/communes")
def get_communes():
    return {
        "communes": [
            {"nom": commune, "zones": list(zones.keys())}
            for commune, zones in ZONES.items()
        ]
    }


@app.get("/zones/{commune}")
def get_zones(commune: str):
    commune_zones = ZONES.get(commune)
    if not commune_zones:
        raise HTTPException(status_code=404, detail=f"Commune '{commune}' non référencée")
    return {
        "commune": commune,
        "zones": {
            code: {"nom": z["nom"], "type": z["type"], "constructible": z["constructible"]}
            for code, z in commune_zones.items()
        }
    }


@app.post("/calcul")
def calcul(req: CalculRequest):
    return calculer_faisabilite(req)


@app.get("/health")
def health():
    return {"status": "ok"}
