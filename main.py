"""
FEASIBILITY.LU — API de calcul de faisabilité immobilière V2
Moteur GÉNÉRIQUE — les règles viennent d'Airtable via n8n
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
import math
import json

app = FastAPI(
    title="Feasibility.lu API",
    description="Moteur de calcul de faisabilité immobilière — Luxembourg — V2 Générique",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# CONSTANTES RÉGLEMENTAIRES (RGD 8 mars 2017)
# ============================================================

ZONES_NON_CONSTRUCTIBLES = ["AGR", "FOR", "PARC", "VERD", "JAR"]
RATIO_CIRCULATIONS = 0.82  # 18% de SCB part en circulations communes

MIX_STANDARD = {
    "T1_studio": {"pct": 0.20, "shn_m2": 35, "scb_m2": 44},
    "T2":        {"pct": 0.35, "shn_m2": 52, "scb_m2": 65},
    "T3":        {"pct": 0.30, "shn_m2": 70, "scb_m2": 88},
    "T4+":       {"pct": 0.15, "shn_m2": 90, "scb_m2": 113},
}
SCB_MOYENNE_PAR_LOGEMENT = sum(t["scb_m2"] * t["pct"] for t in MIX_STANDARD.values())


# ============================================================
# DATA MODELS
# ============================================================

class CalculRequestV2(BaseModel):
    surface_terrain_m2: float = Field(..., gt=0)
    regles_zone: Dict[str, Any] = Field(..., description="Règles depuis Airtable Zones_PAG")
    regles_communes: Optional[Dict[str, Any]] = Field(default=None)
    largeur_facade_m: Optional[float] = None
    profondeur_parcelle_m: Optional[float] = None
    forme_parcelle: Optional[str] = None
    est_route_specifique: bool = False
    est_pap_nq: bool = False
    pap_nq_data: Optional[Dict[str, Any]] = None
    checklist: Optional[List[Dict[str, Any]]] = None

# Ancien format pour rétrocompatibilité
class CalculRequestV1(BaseModel):
    surface_terrain_m2: float = Field(..., gt=0)
    zone_pag: str
    commune: str = "Strassen"
    largeur_facade_m: Optional[float] = None
    route_arlon: bool = False
    adresse: Optional[str] = None
    num_cadastral: Optional[str] = None


# ============================================================
# MAPPING AIRTABLE → MOTEUR
# Tes colonnes Airtable → noms internes du moteur
# ============================================================

def parse_niveaux(val):
    """Parse '3 + combles/retrait' → (3, True) ou '2' → (2, False)"""
    if not val:
        return 1, False
    s = str(val).lower()
    combles = "comble" in s or "retrait" in s
    # Extraire le premier nombre
    import re
    nums = re.findall(r'\d+', s)
    niveaux = int(nums[0]) if nums else 1
    return niveaux, combles


def parse_float(val):
    """Parse une valeur en float, retourne None si impossible"""
    if val is None or val == "" or val == "libre":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def map_airtable_to_regles(r):
    """Convertit une ligne Airtable (Zones_PAG) en dict pour le moteur"""
    niveaux, combles = parse_niveaux(r.get("Niveaux_hors_sol_max"))
    
    return {
        "commune": r.get("Commune", ""),
        "code_zone": r.get("Code_zone", ""),
        "nom_zone": r.get("Nom_zone", ""),
        "pap_qe": r.get("PAP_QE", ""),
        "type_zone": r.get("Type_zone", ""),
        "constructible": r.get("Constructible", "Non"),
        "logement_autorise": r.get("Logement_autorise", "Non"),
        "commerce_autorise": r.get("Commerce_autorise", "Non"),
        "h_corniche_max": parse_float(r.get("Hauteur_corniche_max_m")),
        "h_faite_max": parse_float(r.get("Hauteur_faite_max_m")),
        "h_acrotere_max": parse_float(r.get("Hauteur_acrotere_max_m")),
        "niveaux_pleins_max": niveaux,
        "combles_retrait": combles,
        "niveaux_sous_sol_max": r.get("Niveaux_sous_sol_max"),
        "recul_avant_min": parse_float(r.get("Recul_avant_min_m")),
        "recul_avant_max": parse_float(r.get("Recul_avant_max_m")),
        "recul_lateral_min": parse_float(r.get("Recul_lateral_min_m")),
        "recul_arriere_hors_sol_min": parse_float(r.get("Recul_arriere_min_m")),
        "profondeur_max_hors_sol": parse_float(r.get("Profondeur_max_m")),
        "cos_max": parse_float(r.get("COS_max")),
        "css_max": parse_float(r.get("CSS_max")),
        "nb_log_max_par_construction": parse_float(r.get("Nb_logements_max")),
        "dl_max": parse_float(r.get("DL_max_log_ha")),
        "min_scb_logement_pct": parse_float(r.get("Min_SCB_logement_%_QE")),
        "notes_reculs": r.get("Notes_reculs", ""),
        "notes_affectation": r.get("Notes_affectation", ""),
        # Colonnes spécifiques route (nouvelles)
        "recul_avant_route_specifique": r.get("Recul_avant_route_specifique"),
        "recul_lateral_route_specifique": r.get("Recul_lateral_route_specifique"),
        "profondeur_sous_sol_max": parse_float(r.get("Profondeur_sous_sol_max_m")),
        "recul_arriere_sous_sol_min": parse_float(r.get("Recul_arriere_sous_sol_min_m")),
    }


# ============================================================
# PARKINGS
# ============================================================

def calculer_parkings(nb_logements, mix_logements, scb_commerce=0):
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
    return {"min": p_min, "max": p_max}


def calculer_parkings_velo(nb_logements, scb_commerce=0):
    v = nb_logements
    if scb_commerce > 0:
        v += math.ceil(scb_commerce / 50) if scb_commerce < 2000 else math.ceil(scb_commerce / 200)
    return v


# ============================================================
# MOTEUR DE CALCUL V2 — GÉNÉRIQUE
# ============================================================

def calculer_faisabilite_v2(surface_terrain_m2, regles, regles_communes=None,
                            largeur_facade_m=None, profondeur_parcelle_m=None,
                            forme_parcelle=None, est_route_specifique=False,
                            est_pap_nq=False, pap_nq_data=None, checklist=None):
    
    r = regles
    rc = regles_communes or {}
    trace = []
    contraintes = []
    
    commune = r.get("commune", "Inconnue")
    code_zone = r.get("code_zone", "Inconnue")
    pap_qe = r.get("pap_qe", "")
    
    result = {
        "identification": {
            "commune": commune,
            "zone_pag": code_zone,
            "surface_terrain_m2": surface_terrain_m2,
            "largeur_facade_m": largeur_facade_m,
            "profondeur_parcelle_m": profondeur_parcelle_m,
            "forme_parcelle": forme_parcelle,
        },
        "regles": {},
        "programme": {},
        "contraintes": [],
        "verdict": {},
        "trace": [],
    }

    # ── ÉTAPE 0 : Constructibilité ──
    trace.append("═══ ÉTAPE 0 — VÉRIFICATION CONSTRUCTIBILITÉ ═══")
    
    if code_zone in ZONES_NON_CONSTRUCTIBLES:
        trace.append(f"  Zone {code_zone} → NON CONSTRUCTIBLE (zone verte/agricole)")
        result["verdict"] = {"constructible": "Non", "potentiel": "Aucun",
                             "raison": f"Zone {code_zone} non constructible"}
        result["trace"] = trace
        return result

    constructible = str(r.get("constructible", "Non"))
    if "Non" in constructible and "limité" not in constructible.lower() and "faible" not in constructible.lower():
        trace.append(f"  Zone {code_zone} marquée non constructible")
        result["verdict"] = {"constructible": "Non", "potentiel": "Aucun",
                             "raison": f"Zone {code_zone} non constructible"}
        result["trace"] = trace
        return result

    trace.append(f"  Zone: {code_zone} ({r.get('nom_zone', '')})")
    trace.append(f"  PAP QE: {pap_qe}")
    trace.append(f"  Type: {r.get('type_zone', 'N/A')}")
    trace.append(f"  → Constructible ✅")

    # Règles pour le rapport
    result["regles"] = {
        "nom_zone": r.get("nom_zone", ""),
        "pap_qe": pap_qe,
        "type_zone": r.get("type_zone", ""),
        "h_corniche_max": r.get("h_corniche_max"),
        "h_faite_max": r.get("h_faite_max"),
        "niveaux_pleins_max": r.get("niveaux_pleins_max"),
        "combles_retrait": r.get("combles_retrait", False),
        "recul_avant_min": r.get("recul_avant_min"),
        "recul_lateral_min": r.get("recul_lateral_min"),
        "recul_arriere_min": r.get("recul_arriere_hors_sol_min"),
        "profondeur_max": r.get("profondeur_max_hors_sol"),
        "cos_max": r.get("cos_max"),
        "css_max": r.get("css_max"),
        "dl_max": r.get("dl_max"),
    }

    # ── ÉTAPE 1 : Surface terrain net ──
    trace.append("")
    trace.append("═══ ÉTAPE 1 — SURFACE TERRAIN NET ═══")
    trace.append(f"  Surface terrain brute: {surface_terrain_m2} m²")
    
    surface_terrain_net = surface_terrain_m2
    if est_pap_nq:
        trace.append(f"  ⚠️ Zone PAP NQ — cession terrain possible (jusqu'à 25%)")
        trace.append(f"  Estimation conservatrice: 100% retenu (à vérifier)")
        contraintes.append("Zone PAP NQ: cession terrain possible jusqu'à 25%")
    trace.append(f"  → Surface terrain net: {surface_terrain_net} m²")

    # ── ÉTAPE 2 : Dimensions ──
    trace.append("")
    trace.append("═══ ÉTAPE 2 — DIMENSIONS DE LA PARCELLE ═══")
    
    if largeur_facade_m and profondeur_parcelle_m:
        trace.append(f"  Largeur façade (polygone réel): {largeur_facade_m} m")
        trace.append(f"  Profondeur parcelle (polygone réel): {profondeur_parcelle_m} m")
        trace.append(f"  Forme: {forme_parcelle or 'non déterminée'}")
    else:
        largeur_facade_m = math.sqrt(surface_terrain_m2)
        profondeur_parcelle_m = largeur_facade_m
        trace.append(f"  ⚠️ Dimensions non disponibles — estimation carrée")
        trace.append(f"  Largeur estimée: {largeur_facade_m:.1f} m")
        trace.append(f"  Profondeur estimée: {profondeur_parcelle_m:.1f} m")
        contraintes.append("Dimensions parcelle estimées (carré) — vérifier cadastre")

    # ── ÉTAPE 3 : Reculs ──
    trace.append("")
    trace.append("═══ ÉTAPE 3 — RECULS APPLICABLES ═══")
    
    recul_avant = r.get("recul_avant_min") or 0
    recul_lateral = r.get("recul_lateral_min") or 0
    recul_arriere = r.get("recul_arriere_hors_sol_min") or 0
    recul_arriere_ss = r.get("recul_arriere_sous_sol_min")
    
    # Route spécifique (Route d'Arlon pour Strassen, etc.)
    if est_route_specifique:
        recul_avant_route = r.get("recul_avant_route_specifique")
        recul_lateral_route = r.get("recul_lateral_route_specifique")
        
        if recul_avant_route:
            trace.append(f"  📍 Route spécifique détectée")
            trace.append(f"  Recul avant: {recul_avant_route}")
            # Extraire valeur numérique
            import re
            nums = re.findall(r'[\d.]+', str(recul_avant_route))
            if nums:
                recul_avant = float(nums[0])
            contraintes.append(f"Recul avant route spécifique: {recul_avant_route}")
        
        if recul_lateral_route:
            trace.append(f"  Recul latéral: {recul_lateral_route}")
            h_corniche = r.get("h_corniche_max") or 11
            recul_lateral = max(h_corniche / 2, 4.5)
            trace.append(f"    → Calculé: H corniche/2 = {h_corniche}/2 = {h_corniche/2:.1f}, min 4.5 → {recul_lateral:.1f} m")
            contraintes.append(f"Recul latéral route spécifique: {recul_lateral_route}")
    else:
        trace.append(f"  Recul avant: {recul_avant} m (min {recul_avant}, max {r.get('recul_avant_max', '-')} m)")
        trace.append(f"  Recul latéral: {recul_lateral} m")
        trace.append(f"  Recul arrière hors-sol: {recul_arriere} m")
    
    # Reculs formule (QE5, QE6, QE7 — "H corniche/2 min 4m")
    notes_reculs = str(r.get("notes_reculs", "")).lower()
    if "corniche/2" in notes_reculs and not est_route_specifique:
        h_corniche = r.get("h_corniche_max") or 10
        recul_calc = h_corniche / 2
        if recul_lateral and recul_calc > recul_lateral:
            recul_lateral = recul_calc
            trace.append(f"  Recul latéral (formule H/2): {recul_calc:.1f} m")
        if recul_arriere and recul_calc > recul_arriere:
            recul_arriere = recul_calc
            trace.append(f"  Recul arrière (formule H/2): {recul_calc:.1f} m")
    
    if recul_arriere_ss:
        trace.append(f"  Recul arrière sous-sol: {recul_arriere_ss} m")

    # ── ÉTAPE 4 : Emprise au sol ──
    trace.append("")
    trace.append("═══ ÉTAPE 4 — EMPRISE AU SOL ═══")
    
    profondeur_utile = profondeur_parcelle_m - recul_avant - recul_arriere
    largeur_utile = largeur_facade_m - 2 * recul_lateral
    
    trace.append(f"  Méthode 1 — Par les reculs:")
    trace.append(f"    Profondeur utile: {profondeur_parcelle_m:.1f} - {recul_avant} (avant) - {recul_arriere} (arrière) = {profondeur_utile:.1f} m")
    trace.append(f"    Largeur utile: {largeur_facade_m:.1f} - 2×{recul_lateral} (latéral) = {largeur_utile:.1f} m")
    
    if profondeur_utile <= 0 or largeur_utile <= 0:
        trace.append(f"  ❌ Dimensions insuffisantes après reculs")
        result["verdict"] = {"constructible": "Non", "potentiel": "Aucun",
                             "raison": "Parcelle trop étroite/peu profonde pour les reculs"}
        result["trace"] = trace
        return result
    
    prof_max = r.get("profondeur_max_hors_sol")
    if prof_max and profondeur_utile > prof_max:
        trace.append(f"    Profondeur limitée par max: {prof_max} m")
        profondeur_utile = prof_max
    
    emprise_reculs = largeur_utile * profondeur_utile
    trace.append(f"    Emprise par reculs: {largeur_utile:.1f} × {profondeur_utile:.1f} = {emprise_reculs:.1f} m²")
    
    cos_max = r.get("cos_max")
    emprise_cos = None
    if cos_max:
        emprise_cos = surface_terrain_net * cos_max
        trace.append(f"  Méthode 2 — Par le COS:")
        trace.append(f"    COS max: {cos_max}")
        trace.append(f"    Emprise par COS: {surface_terrain_net} × {cos_max} = {emprise_cos:.1f} m²")
    
    # Override PAP NQ
    if est_pap_nq and pap_nq_data:
        cos_nq = pap_nq_data.get("cos_max")
        if cos_nq:
            emprise_cos_nq = surface_terrain_net * cos_nq
            trace.append(f"  Méthode 2b — COS PAP NQ: {cos_nq}")
            trace.append(f"    Emprise: {surface_terrain_net} × {cos_nq} = {emprise_cos_nq:.1f} m²")
            if emprise_cos is None or emprise_cos_nq < emprise_cos:
                emprise_cos = emprise_cos_nq
                trace.append(f"    → COS PAP NQ plus restrictif, retenu")
    
    if emprise_cos and emprise_cos < emprise_reculs:
        emprise_au_sol = emprise_cos
        trace.append(f"  → Facteur limitant: COS → Emprise: {emprise_au_sol:.1f} m²")
    else:
        emprise_au_sol = emprise_reculs
        trace.append(f"  → Facteur limitant: Reculs → Emprise: {emprise_au_sol:.1f} m²")

    # Vérification CSS
    css_max = r.get("css_max")
    if css_max:
        surface_scellee_max = surface_terrain_net * css_max
        surface_acces = surface_terrain_net * 0.10
        surface_scellee = emprise_au_sol + surface_acces
        trace.append(f"  Vérification CSS ({css_max}):")
        trace.append(f"    Surface scellée max: {surface_scellee_max:.0f} m²")
        trace.append(f"    Surface scellée estimée: {surface_scellee:.0f} m²")
        if surface_scellee > surface_scellee_max:
            emprise_au_sol = surface_scellee_max - surface_acces
            trace.append(f"    ⚠️ CSS limitant → Emprise réduite: {emprise_au_sol:.1f} m²")
            contraintes.append(f"CSS {css_max} limitant")
        else:
            trace.append(f"    ✅ CSS OK")

    # ── ÉTAPE 5 : SCB ──
    trace.append("")
    trace.append("═══ ÉTAPE 5 — SURFACE CONSTRUITE BRUTE (SCB) ═══")
    
    niveaux = r.get("niveaux_pleins_max") or 1
    combles = r.get("combles_retrait", False)
    
    scb_niveaux = emprise_au_sol * niveaux
    trace.append(f"  Niveaux pleins: {niveaux}")
    trace.append(f"  SCB niveaux pleins: {emprise_au_sol:.1f} × {niveaux} = {scb_niveaux:.1f} m²")
    
    scb_combles = emprise_au_sol * 0.60 if combles else 0
    if combles:
        trace.append(f"  Combles/retrait: ~60% emprise = {scb_combles:.1f} m²")
    
    scb_brute = scb_niveaux + scb_combles
    scb_totale = scb_brute * RATIO_CIRCULATIONS
    trace.append(f"  SCB brute: {scb_brute:.1f} m²")
    trace.append(f"  Déduction circulations ({int((1-RATIO_CIRCULATIONS)*100)}%): {scb_brute:.1f} × {RATIO_CIRCULATIONS} = {scb_totale:.1f} m²")

    # CUS PAP NQ
    if est_pap_nq and pap_nq_data:
        cus_nq = pap_nq_data.get("cus_max") or pap_nq_data.get("CUS_max")
        if cus_nq:
            scb_max_cus = surface_terrain_net * float(cus_nq)
            trace.append(f"  Vérification CUS PAP NQ ({cus_nq}):")
            trace.append(f"    SCB max: {scb_max_cus:.1f} m²")
            if scb_totale > scb_max_cus:
                trace.append(f"    ⚠️ CUS limitant → SCB réduite à {scb_max_cus:.1f} m²")
                scb_totale = scb_max_cus
                contraintes.append(f"CUS PAP NQ {cus_nq} limitant")
            else:
                trace.append(f"    ✅ CUS OK")

    # ── ÉTAPE 6 : Sous-sol ──
    trace.append("")
    trace.append("═══ ÉTAPE 6 — SOUS-SOL ═══")
    
    rec_arr_ss = recul_arriere_ss if recul_arriere_ss else recul_arriere
    prof_ss_max = r.get("profondeur_sous_sol_max")
    prof_ss = profondeur_parcelle_m - recul_avant - rec_arr_ss
    if prof_ss_max and prof_ss > prof_ss_max:
        prof_ss = prof_ss_max
    emprise_ss = largeur_utile * prof_ss if prof_ss > 0 else emprise_au_sol
    
    trace.append(f"  Recul arrière SS: {rec_arr_ss} m")
    if prof_ss_max:
        trace.append(f"  Profondeur max SS: {prof_ss_max} m")
    trace.append(f"  Profondeur SS possible: {prof_ss:.1f} m")
    trace.append(f"  Emprise SS estimée: {emprise_ss:.1f} m²")

    # ── ÉTAPE 7 : Programme ──
    trace.append("")
    trace.append("═══ ÉTAPE 7 — PROGRAMME LOGEMENTS ═══")
    
    type_zone = r.get("type_zone", "Habitation")
    logement_ok = "oui" in str(r.get("logement_autorise", "Non")).lower()
    commerce_ok = "oui" in str(r.get("commerce_autorise", "Non")).lower()
    min_scb_log_pct = r.get("min_scb_logement_pct")
    
    scb_commerce = 0
    scb_logement = scb_totale
    
    if type_zone == "Mixte" and commerce_ok:
        pct_log = (min_scb_log_pct or 50) / 100
        scb_commerce = emprise_au_sol * 0.80
        scb_logement = scb_totale - scb_commerce
        if scb_logement < scb_totale * pct_log:
            scb_logement = scb_totale * pct_log
            scb_commerce = scb_totale - scb_logement
        trace.append(f"  Zone mixte — part min logement: {min_scb_log_pct or 50}%")
        trace.append(f"  SCB commerce (RDC ~80%): {scb_commerce:.1f} m²")
        trace.append(f"  SCB logement: {scb_logement:.1f} m²")
    elif not logement_ok:
        scb_logement = 0
        scb_commerce = scb_totale
        trace.append(f"  Zone non résidentielle — SCB activités: {scb_commerce:.1f} m²")
    else:
        trace.append(f"  Zone résidentielle — SCB logement: {scb_logement:.1f} m²")

    # Nb logements
    nb_logements = 0
    if logement_ok and scb_logement > 0:
        nb_log_brut = scb_logement / SCB_MOYENNE_PAR_LOGEMENT
        trace.append(f"  SCB moy/logement: {SCB_MOYENNE_PAR_LOGEMENT:.1f} m²")
        trace.append(f"  Nb logements brut: {scb_logement:.1f} / {SCB_MOYENNE_PAR_LOGEMENT:.1f} = {nb_log_brut:.1f}")
        
        nb_log = nb_log_brut
        
        dl_max = r.get("dl_max")
        if dl_max:
            nb_dl = (surface_terrain_m2 / 10000) * dl_max
            trace.append(f"  Plafond densité: {dl_max} log/ha → max {nb_dl:.1f}")
            if nb_log > nb_dl:
                nb_log = nb_dl
                trace.append(f"    ⚠️ Densité limitante")
                contraintes.append(f"Densité max {dl_max} log/ha limitante")
        
        nb_max = r.get("nb_log_max_par_construction")
        if nb_max:
            # Gérer "2 par construction" etc.
            try:
                nb_max_val = float(str(nb_max).split()[0]) if isinstance(nb_max, str) else float(nb_max)
                trace.append(f"  Plafond par construction: max {nb_max_val:.0f}")
                if nb_log > nb_max_val:
                    nb_log = nb_max_val
                    trace.append(f"    ⚠️ Plafonné")
            except:
                pass
        
        # PAP NQ densité
        if est_pap_nq and pap_nq_data:
            dl_nq = pap_nq_data.get("dl_max") or pap_nq_data.get("DL_max_log_ha")
            if dl_nq:
                nb_nq = (surface_terrain_m2 / 10000) * float(dl_nq)
                trace.append(f"  Plafond PAP NQ: {dl_nq} log/ha → max {nb_nq:.1f}")
                if nb_log > nb_nq:
                    nb_log = nb_nq
                    trace.append(f"    ⚠️ PAP NQ limitant")
        
        nb_logements = max(1, math.floor(nb_log))
    
    trace.append(f"  → Nombre de logements retenu: {nb_logements}")

    # ── ÉTAPE 8 : Mix ──
    trace.append("")
    trace.append("═══ ÉTAPE 8 — MIX LOGEMENTS ═══")
    
    mix_detail = {}
    if nb_logements <= 0:
        trace.append(f"  Pas de logement")
    elif nb_logements <= 2:
        mix_detail = {"T3": {"nb": nb_logements, "shn_m2": 70, "scb_m2": 88}}
        trace.append(f"  ≤2 logements → T3 par défaut")
    else:
        for t, d in MIX_STANDARD.items():
            mix_detail[t] = {"nb": max(1, round(nb_logements * d["pct"])), "shn_m2": d["shn_m2"], "scb_m2": d["scb_m2"]}
        total_mix = sum(dd["nb"] for dd in mix_detail.values())
        if total_mix != nb_logements:
            mix_detail["T2"]["nb"] += nb_logements - total_mix
        for t, d in mix_detail.items():
            trace.append(f"  {t}: {d['nb']} × {d['shn_m2']} m² SHN ({d['scb_m2']} m² SCB)")
    
    total_log = sum(d["nb"] for d in mix_detail.values())
    avg_shn = sum(d["shn_m2"] * d["nb"] for d in mix_detail.values()) / total_log if total_log > 0 else 0
    trace.append(f"  Moyenne SHN: {avg_shn:.1f} m² {'✅ ≥ 52m²' if avg_shn >= 52 else '⚠️ < 52m²'}")
    if avg_shn < 52 and total_log > 0:
        contraintes.append(f"Moyenne SHN {avg_shn:.0f}m² < 52m² réglementaire")

    # ── ÉTAPE 9 : Stationnement ──
    trace.append("")
    trace.append("═══ ÉTAPE 9 — STATIONNEMENT ═══")
    
    parkings = calculer_parkings(nb_logements, mix_detail, scb_commerce) if total_log > 0 else {"min": 0, "max": 0}
    if scb_commerce > 0 and total_log == 0:
        parkings = {"min": math.ceil(scb_commerce / 20), "max": math.ceil(scb_commerce / 20)}
    parkings_velo = calculer_parkings_velo(nb_logements, scb_commerce)
    surface_parking_ss = parkings["min"] * 25
    
    trace.append(f"  Parkings auto: {parkings['min']} à {parkings['max']} places")
    trace.append(f"  Parkings vélo: {parkings_velo} places")
    trace.append(f"  Surface parking SS (~25m²/place): {surface_parking_ss} m²")

    # ── ÉTAPE 10 : Contraintes ──
    trace.append("")
    trace.append("═══ ÉTAPE 10 — CONTRAINTES ═══")
    
    if css_max:
        trace.append(f"  CSS max: {css_max}")
    
    notes = r.get("notes_reculs", "")
    if notes:
        trace.append(f"  Notes reculs: {notes[:100]}...")
    
    if checklist:
        for item in checklist:
            statut = str(item.get("statut", ""))
            if "OUI" in statut:
                trace.append(f"  ⚠️ {item.get('contrainte', '')}: CONCERNÉ")
                contraintes.append(f"{item.get('contrainte', '')}: concerné")

    # ── ÉTAPE 11 : Synthèse ──
    trace.append("")
    trace.append("═══ ÉTAPE 11 — SYNTHÈSE ═══")
    
    niveaux_prog = f"R+{niveaux - 1}{'+C' if combles else ''}"
    if type_zone == "Mixte" and scb_commerce > 0:
        niveaux_prog = f"SS parking | RDC commerce | R+1 à R+{niveaux-1} logement"
        if combles:
            niveaux_prog += " | Combles"
    else:
        niveaux_prog = f"SS parking | RDC à R+{niveaux-1}"
        if combles:
            niveaux_prog += " + Combles"
    
    trace.append(f"  {niveaux_prog}")

    # Verdict
    if nb_logements == 0 and type_zone in ["Activités", "Commercial", "Spéciale", "Loisirs"]:
        potentiel = "Moyen" if scb_totale > 500 else "Faible"
    elif nb_logements <= 2:
        potentiel = "Faible"
    elif nb_logements <= 6:
        potentiel = "Moyen"
    else:
        potentiel = "Fort"
    
    trace.append("")
    trace.append("═══ VERDICT ═══")
    trace.append(f"  Constructible: Oui | Potentiel: {potentiel}")
    trace.append(f"  Emprise: {emprise_au_sol:.1f} m² | SCB: {scb_totale:.1f} m² | Logements: {nb_logements}")

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
        "surface_parking_ss_estimee_m2": surface_parking_ss,
        "emprise_sous_sol_m2": round(emprise_ss, 1),
        "niveaux_programme": niveaux_prog,
    }
    result["verdict"] = {
        "constructible": "Oui",
        "potentiel": potentiel,
        "points_attention": contraintes,
    }
    result["contraintes"] = contraintes
    result["trace"] = trace
    return result


# ============================================================
# ANCIEN MOTEUR V1 (rétrocompatibilité)
# ============================================================

# Garder les anciennes zones en dur pour ne pas casser le workflow actuel
ZONES_V1 = {
    "Strassen": {
        "HAB-1": {"nom": "Zone d'habitation 1", "pap_qe": "QE1", "type": "Habitation", "constructible": True, "logement": True, "commerce": False, "h_corniche_max": 8.0, "h_faite_max": 12.0, "niveaux_pleins_max": 2, "combles_retrait": True, "niveaux_sous_sol_max": 1, "recul_avant_min": 3.0, "recul_avant_max": 6.0, "recul_lateral_min": 3.0, "recul_arriere_min": 10.0, "profondeur_max": 14.0, "cos_max": 0.35, "css_max": 0.60, "nb_log_max_par_construction": 2, "dl_max": None, "min_scb_logement_pct_qe": None, "construction_2e_position": False},
        "HAB-2": {"nom": "Zone d'habitation 2", "pap_qe": "QE2", "type": "Habitation", "constructible": True, "logement": True, "commerce": False, "h_corniche_max": 11.0, "h_faite_max": 15.0, "niveaux_pleins_max": 3, "combles_retrait": True, "niveaux_sous_sol_max": None, "recul_avant_min": 3.0, "recul_avant_max": 7.0, "recul_lateral_min": 4.5, "recul_arriere_min": 12.0, "profondeur_max": 14.0, "cos_max": 0.35, "css_max": 0.50, "nb_log_max_par_construction": None, "dl_max": 105, "min_scb_logement_pct_qe": 70, "construction_2e_position": True},
        "MIX-u": {"nom": "Zone mixte urbaine", "pap_qe": "QE2", "type": "Mixte", "constructible": True, "logement": True, "commerce": True, "h_corniche_max": 11.0, "h_faite_max": 15.0, "niveaux_pleins_max": 3, "combles_retrait": True, "niveaux_sous_sol_max": None, "recul_avant_min": 3.0, "recul_avant_max": 7.0, "recul_lateral_min": 4.5, "recul_arriere_min": 12.0, "profondeur_max": 14.0, "cos_max": 0.35, "css_max": 0.50, "nb_log_max_par_construction": None, "dl_max": 105, "min_scb_logement_pct_qe": 50, "construction_2e_position": True},
        "MIX-v": {"nom": "Zone mixte villageoise", "pap_qe": "QE2", "type": "Mixte", "constructible": True, "logement": True, "commerce": True, "h_corniche_max": 11.0, "h_faite_max": 15.0, "niveaux_pleins_max": 3, "combles_retrait": True, "niveaux_sous_sol_max": None, "recul_avant_min": 3.0, "recul_avant_max": 7.0, "recul_lateral_min": 4.5, "recul_arriere_min": 12.0, "profondeur_max": 14.0, "cos_max": 0.35, "css_max": 0.50, "nb_log_max_par_construction": None, "dl_max": 105, "min_scb_logement_pct_qe": 70, "construction_2e_position": True},
        "BEP": {"nom": "Zone bâtiments et équipements publics", "pap_qe": "QE3", "type": "Equipement public", "constructible": True, "logement": False, "commerce": False, "h_corniche_max": 14.0, "h_faite_max": 18.0, "niveaux_pleins_max": 4, "combles_retrait": False, "niveaux_sous_sol_max": None, "recul_avant_min": 0, "recul_lateral_min": 3.0, "recul_arriere_min": 5.0, "profondeur_max": None, "cos_max": None, "css_max": None, "nb_log_max_par_construction": None, "dl_max": 105, "construction_2e_position": True},
        "ECO-c1": {"nom": "Zone d'activités économiques", "pap_qe": "QE6", "type": "Activités", "constructible": True, "logement": False, "commerce": True, "h_corniche_max": 10.0, "h_faite_max": 13.0, "niveaux_pleins_max": 3, "combles_retrait": False, "niveaux_sous_sol_max": None, "recul_avant_min": 7.0, "recul_lateral_min": 4.0, "recul_arriere_min": 4.0, "profondeur_max": None, "cos_max": 0.50, "css_max": 0.80, "nb_log_max_par_construction": None, "dl_max": None, "construction_2e_position": True},
        "COM": {"nom": "Zone commerciale", "pap_qe": "QE7", "type": "Commercial", "constructible": True, "logement": False, "commerce": True, "h_corniche_max": 13.0, "h_faite_max": 18.0, "niveaux_pleins_max": 3, "combles_retrait": True, "niveaux_sous_sol_max": None, "recul_avant_min": 7.0, "recul_lateral_min": 4.0, "recul_arriere_min": 4.0, "profondeur_max": None, "cos_max": None, "css_max": None, "nb_log_max_par_construction": 2, "dl_max": None, "construction_2e_position": True},
    }
}


def calculer_v1(req: CalculRequestV1) -> dict:
    """Ancien moteur pour rétrocompatibilité"""
    commune_zones = ZONES_V1.get(req.commune)
    if not commune_zones or req.zone_pag not in commune_zones:
        if req.zone_pag in ZONES_NON_CONSTRUCTIBLES:
            return {"regles": {}, "programme": {}, "contraintes": [],
                    "verdict": {"constructible": "Non", "potentiel": "Aucun",
                                "raison": f"Zone {req.zone_pag} non constructible"}, "trace": []}
        return {"regles": {}, "programme": {}, "contraintes": [],
                "verdict": {"constructible": "Indéterminé", "potentiel": "Indéterminé",
                            "raison": f"Zone non référencée"}, "trace": []}
    
    zone = commune_zones[req.zone_pag]
    regles = {
        "commune": req.commune, "code_zone": req.zone_pag,
        "nom_zone": zone["nom"], "pap_qe": zone["pap_qe"], "type_zone": zone["type"],
        "constructible": "Oui" if zone["constructible"] else "Non",
        "logement_autorise": "Oui" if zone["logement"] else "Non",
        "commerce_autorise": "Oui" if zone["commerce"] else "Non",
        "h_corniche_max": zone["h_corniche_max"], "h_faite_max": zone["h_faite_max"],
        "niveaux_pleins_max": zone["niveaux_pleins_max"],
        "combles_retrait": zone["combles_retrait"],
        "recul_avant_min": zone["recul_avant_min"],
        "recul_avant_max": zone.get("recul_avant_max"),
        "recul_lateral_min": zone["recul_lateral_min"],
        "recul_arriere_hors_sol_min": zone["recul_arriere_min"],
        "profondeur_max_hors_sol": zone["profondeur_max"],
        "cos_max": zone["cos_max"], "css_max": zone["css_max"],
        "dl_max": zone["dl_max"],
        "nb_log_max_par_construction": zone.get("nb_log_max_par_construction"),
        "min_scb_logement_pct": zone.get("min_scb_logement_pct_qe"),
    }
    
    return calculer_faisabilite_v2(
        surface_terrain_m2=req.surface_terrain_m2,
        regles=regles,
        largeur_facade_m=req.largeur_facade_m,
        est_route_specifique=req.route_arlon,
    )


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/")
def root():
    return {"service": "Feasibility.lu API", "version": "2.0.0",
            "endpoints": ["POST /calcul (v1 rétrocompat)", "POST /v2/calcul (v2 générique)"]}


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0-generic"}


@app.post("/calcul")
def calcul_v1(req: CalculRequestV1):
    """Endpoint V1 — rétrocompatible avec le workflow actuel"""
    return calculer_v1(req)


@app.post("/v2/calcul")
def calcul_v2(req: CalculRequestV2):
    """Endpoint V2 — générique, reçoit les règles depuis Airtable"""
    regles = map_airtable_to_regles(req.regles_zone)
    return calculer_faisabilite_v2(
        surface_terrain_m2=req.surface_terrain_m2,
        regles=regles,
        regles_communes=req.regles_communes,
        largeur_facade_m=req.largeur_facade_m,
        profondeur_parcelle_m=req.profondeur_parcelle_m,
        forme_parcelle=req.forme_parcelle,
        est_route_specifique=req.est_route_specifique,
        est_pap_nq=req.est_pap_nq,
        pap_nq_data=req.pap_nq_data,
        checklist=req.checklist,
    )
