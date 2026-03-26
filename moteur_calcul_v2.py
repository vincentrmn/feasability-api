"""
FEASIBILITY.LU — Moteur de calcul de faisabilité immobilière GÉNÉRIQUE
Fonctionne avec n'importe quelle commune via règles en input JSON.
Produit une trace détaillée de chaque étape de calcul.
"""

import math
import json

# ============================================================
# CONSTANTES RÉGLEMENTAIRES (RGD 8 mars 2017)
# ============================================================

ZONES_NON_CONSTRUCTIBLES = ["AGR", "FOR", "PARC", "VERD", "JAR"]

RATIO_SCB_SHN = 0.80
RATIO_CIRCULATIONS = 0.82  # 18% de la SCB part en circulations communes

MIX_STANDARD = {
    "T1_studio": {"pct": 0.20, "shn_m2": 35, "scb_m2": 44},
    "T2":        {"pct": 0.35, "shn_m2": 52, "scb_m2": 65},
    "T3":        {"pct": 0.30, "shn_m2": 70, "scb_m2": 88},
    "T4+":       {"pct": 0.15, "shn_m2": 90, "scb_m2": 113},
}

SCB_MOYENNE_PAR_LOGEMENT = sum(t["scb_m2"] * t["pct"] for t in MIX_STANDARD.values())


# ============================================================
# STATIONNEMENT (RGD)
# ============================================================

def calculer_parkings(nb_logements, mix_logements, scb_commerce=0, scb_bureaux=0):
    parkings_min = 0
    parkings_max = 0
    for type_log, data in mix_logements.items():
        nb = data["nb"]
        shn = data["shn_m2"]
        if shn < 60:
            parkings_min += nb * 1
            parkings_max += nb * 1
        elif shn <= 90:
            parkings_min += nb * 1
            parkings_max += nb * 2
        else:
            parkings_min += nb * 1
            parkings_max += nb * 3
    if scb_commerce > 0:
        parkings_min += math.ceil(scb_commerce / 20)
    if scb_bureaux > 0:
        parkings_min += math.ceil(scb_bureaux / 90)
        parkings_max += math.ceil(scb_bureaux / 60)
    return {"min": parkings_min, "max": parkings_max}


def calculer_parkings_velo(nb_logements, scb_commerce=0, scb_bureaux=0):
    velo = nb_logements
    if scb_commerce > 0:
        velo += math.ceil(scb_commerce / 50) if scb_commerce < 2000 else math.ceil(scb_commerce / 200)
    if scb_bureaux > 0:
        velo += math.ceil(scb_bureaux / 500)
    return velo


# ============================================================
# MOTEUR DE CALCUL PRINCIPAL — GÉNÉRIQUE
# ============================================================

def calculer_faisabilite(surface_terrain_m2, regles_zone, regles_communes=None,
                         largeur_facade_m=None, profondeur_parcelle_m=None,
                         forme_parcelle=None, est_route_specifique=False,
                         est_pap_nq=False, pap_nq_data=None,
                         checklist=None):
    """
    Moteur de calcul générique.
    
    Args:
        surface_terrain_m2: Surface du terrain en m²
        regles_zone: dict avec TOUTES les règles de la zone (depuis Airtable)
        regles_communes: dict avec les règles communes de la commune (Partie 3)
        largeur_facade_m: Largeur réelle de la façade (depuis polygone)
        profondeur_parcelle_m: Profondeur réelle (depuis polygone)
        forme_parcelle: "carrée", "rectangulaire", "allongée", "irrégulière"
        est_route_specifique: Si la parcelle est le long de la route spécifique (ex: Route d'Arlon)
        est_pap_nq: Si la parcelle est en zone PAP NQ
        pap_nq_data: Données PAP NQ de l'API (COS, CUS, CSS, densité)
        checklist: Résultats de la checklist contraintes
    
    Returns:
        dict avec données du rapport + trace détaillée
    """
    
    # Raccourcis
    r = regles_zone
    rc = regles_communes or {}
    trace = []  # Trace détaillée des calculs
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

    # ── ÉTAPE 0 : Vérification constructibilité ──
    trace.append("═══ ÉTAPE 0 — VÉRIFICATION CONSTRUCTIBILITÉ ═══")
    
    if code_zone in ZONES_NON_CONSTRUCTIBLES:
        trace.append(f"  Zone {code_zone} → NON CONSTRUCTIBLE (zone verte/agricole)")
        result["verdict"] = {
            "constructible": "Non",
            "potentiel": "Aucun",
            "raison": f"Zone {code_zone} non constructible",
        }
        result["trace"] = trace
        return result

    constructible = r.get("constructible", "Oui")
    if constructible != "Oui":
        trace.append(f"  Zone {code_zone} marquée non constructible dans la base")
        result["verdict"] = {
            "constructible": "Non",
            "potentiel": "Aucun",
            "raison": f"Zone {code_zone} non constructible",
        }
        result["trace"] = trace
        return result

    trace.append(f"  Zone: {code_zone} ({r.get('nom_zone', '')})")
    trace.append(f"  PAP QE: {pap_qe}")
    trace.append(f"  Type: {r.get('type_zone', 'N/A')}")
    trace.append(f"  → Constructible ✅")

    # ── Préparer les règles pour le rapport ──
    result["regles"] = {
        "nom_zone": r.get("nom_zone", ""),
        "pap_qe": pap_qe,
        "type_zone": r.get("type_zone", ""),
        "h_corniche_max": r.get("h_corniche_max"),
        "h_faite_max": r.get("h_faite_max"),
        "niveaux_pleins_max": r.get("niveaux_pleins_max"),
        "combles_retrait": r.get("combles_retrait", "Non") == "Oui",
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
        # En PAP NQ, cession possible jusqu'à 25%
        trace.append(f"  ⚠️ Parcelle en zone PAP NQ — cession terrain possible (jusqu'à 25%)")
        trace.append(f"  Pour l'estimation, on garde 100% (à préciser avec la commune)")
        contraintes.append("Zone PAP NQ: cession terrain possible jusqu'à 25% (voiries, espaces publics)")
    
    trace.append(f"  → Surface terrain net retenue: {surface_terrain_net} m²")

    # ── ÉTAPE 2 : Dimensions de la parcelle ──
    trace.append("")
    trace.append("═══ ÉTAPE 2 — DIMENSIONS DE LA PARCELLE ═══")
    
    if largeur_facade_m and profondeur_parcelle_m:
        trace.append(f"  Largeur façade (polygone réel): {largeur_facade_m} m")
        trace.append(f"  Profondeur parcelle (polygone réel): {profondeur_parcelle_m} m")
        trace.append(f"  Forme: {forme_parcelle or 'non déterminée'}")
    else:
        largeur_facade_m = math.sqrt(surface_terrain_m2)
        profondeur_parcelle_m = largeur_facade_m
        trace.append(f"  ⚠️ Dimensions réelles non disponibles — estimation parcelle carrée")
        trace.append(f"  Largeur estimée: {largeur_facade_m:.1f} m")
        trace.append(f"  Profondeur estimée: {profondeur_parcelle_m:.1f} m")
        contraintes.append("Dimensions parcelle estimées (carré) — vérifier avec le cadastre")

    # ── ÉTAPE 3 : Reculs applicables ──
    trace.append("")
    trace.append("═══ ÉTAPE 3 — RECULS APPLICABLES ═══")
    
    recul_avant = r.get("recul_avant_min") or 0
    recul_lateral = r.get("recul_lateral_min") or 0
    recul_arriere = r.get("recul_arriere_hors_sol_min") or 0
    recul_arriere_ss = r.get("recul_arriere_sous_sol_min")
    
    route_nom = r.get("route_specifique_nom", "")
    
    if est_route_specifique and route_nom:
        trace.append(f"  📍 Parcelle le long de {route_nom} — reculs spécifiques")
        
        recul_avant_route = r.get("recul_avant_route_specifique", "")
        if recul_avant_route:
            trace.append(f"  Recul avant: {recul_avant_route}")
            # Essayer d'extraire la valeur numérique
            try:
                recul_avant = float(''.join(c for c in recul_avant_route.split('m')[0] if c.isdigit() or c == '.'))
            except:
                recul_avant = 15  # fallback
            contraintes.append(f"Recul avant {route_nom}: {recul_avant_route}")
        
        recul_lat_route = r.get("recul_lateral_route_specifique", "")
        if recul_lat_route:
            trace.append(f"  Recul latéral: {recul_lat_route}")
            h_corniche = r.get("h_corniche_max") or 11
            recul_lateral = max(h_corniche / 2, 4.5)
            trace.append(f"    → Calculé: moitié h_corniche ({h_corniche}/2 = {h_corniche/2:.1f}), min 4.50 m → {recul_lateral:.1f} m")
            contraintes.append(f"Recul latéral {route_nom}: {recul_lat_route}")
    else:
        trace.append(f"  Recul avant: {recul_avant} m (min {recul_avant} m, max {r.get('recul_avant_max', '-')} m)")
        trace.append(f"  Recul latéral: {recul_lateral} m")
        trace.append(f"  Recul arrière hors-sol: {recul_arriere} m")
        if recul_arriere_ss:
            trace.append(f"  Recul arrière sous-sol: {recul_arriere_ss} m")

    # Formules de recul (QE5, QE6, QE7)
    recul_lat_formule = r.get("recul_lateral_formule")
    recul_arr_formule = r.get("recul_arriere_formule")
    if recul_lat_formule and not est_route_specifique:
        trace.append(f"  Recul latéral (formule): {recul_lat_formule}")
        h_corniche = r.get("h_corniche_max") or 10
        recul_lateral = max(h_corniche / 2, recul_lateral or 4)
        trace.append(f"    → Calculé: {recul_lateral:.1f} m")
    if recul_arr_formule:
        trace.append(f"  Recul arrière (formule): {recul_arr_formule}")
        h_corniche = r.get("h_corniche_max") or 10
        recul_arriere = max(h_corniche / 2, recul_arriere or 4)
        trace.append(f"    → Calculé: {recul_arriere:.1f} m")

    # ── ÉTAPE 4 : Emprise au sol ──
    trace.append("")
    trace.append("═══ ÉTAPE 4 — EMPRISE AU SOL ═══")
    
    # Méthode 1: Par les reculs
    profondeur_utile = profondeur_parcelle_m - recul_avant - recul_arriere
    largeur_utile = largeur_facade_m - 2 * recul_lateral
    
    trace.append(f"  Méthode 1 — Par les reculs:")
    trace.append(f"    Profondeur utile: {profondeur_parcelle_m:.1f} - {recul_avant} (avant) - {recul_arriere} (arrière) = {profondeur_utile:.1f} m")
    trace.append(f"    Largeur utile: {largeur_facade_m:.1f} - 2 × {recul_lateral} (latéral) = {largeur_utile:.1f} m")
    
    if profondeur_utile <= 0 or largeur_utile <= 0:
        trace.append(f"  ❌ Dimensions insuffisantes après reculs")
        result["verdict"] = {
            "constructible": "Non",
            "potentiel": "Aucun",
            "raison": "Parcelle trop étroite ou peu profonde pour respecter les reculs",
        }
        result["trace"] = trace
        return result
    
    # Limiter par la profondeur max
    prof_max = r.get("profondeur_max_hors_sol")
    if prof_max and profondeur_utile > prof_max:
        trace.append(f"    Profondeur limitée par profondeur max: {prof_max} m")
        profondeur_utile = prof_max
    
    emprise_reculs = largeur_utile * profondeur_utile
    trace.append(f"    Emprise par reculs: {largeur_utile:.1f} × {profondeur_utile:.1f} = {emprise_reculs:.1f} m²")
    
    # Méthode 2: Par le COS
    cos_max = r.get("cos_max")
    emprise_cos = None
    if cos_max:
        emprise_cos = surface_terrain_net * cos_max
        trace.append(f"  Méthode 2 — Par le COS:")
        trace.append(f"    COS max: {cos_max}")
        trace.append(f"    Emprise par COS: {surface_terrain_net} × {cos_max} = {emprise_cos:.1f} m²")
    
    # Override PAP NQ si dispo
    if est_pap_nq and pap_nq_data:
        cos_nq = pap_nq_data.get("cos_max")
        if cos_nq:
            emprise_cos_nq = surface_terrain_net * cos_nq
            trace.append(f"  Méthode 2b — Par le COS PAP NQ:")
            trace.append(f"    COS max PAP NQ: {cos_nq}")
            trace.append(f"    Emprise par COS NQ: {surface_terrain_net} × {cos_nq} = {emprise_cos_nq:.1f} m²")
            if emprise_cos is None or emprise_cos_nq < emprise_cos:
                emprise_cos = emprise_cos_nq
                trace.append(f"    → COS PAP NQ plus restrictif, retenu")
    
    # Facteur limitant
    if emprise_cos and emprise_cos < emprise_reculs:
        emprise_au_sol = emprise_cos
        trace.append(f"  → Facteur limitant: COS → Emprise retenue: {emprise_au_sol:.1f} m²")
    else:
        emprise_au_sol = emprise_reculs
        trace.append(f"  → Facteur limitant: Reculs → Emprise retenue: {emprise_au_sol:.1f} m²")

    # Vérifier CSS
    css_max = r.get("css_max")
    if css_max:
        surface_scellee_max = surface_terrain_net * css_max
        # Estimer surface scellée = emprise + accès (~15% terrain)
        surface_acces_estimee = surface_terrain_net * 0.10
        surface_scellee_estimee = emprise_au_sol + surface_acces_estimee
        trace.append(f"  Vérification CSS:")
        trace.append(f"    CSS max: {css_max} → Surface scellée max: {surface_scellee_max:.0f} m²")
        trace.append(f"    Surface scellée estimée (emprise + accès ~10%): {surface_scellee_estimee:.0f} m²")
        if surface_scellee_estimee > surface_scellee_max:
            emprise_au_sol = surface_scellee_max - surface_acces_estimee
            trace.append(f"    ⚠️ CSS limitant → Emprise réduite à: {emprise_au_sol:.1f} m²")
            contraintes.append(f"CSS {css_max} limitant: surface scellée max {surface_scellee_max:.0f} m²")
        else:
            trace.append(f"    ✅ CSS OK")

    # ── ÉTAPE 5 : SCB totale ──
    trace.append("")
    trace.append("═══ ÉTAPE 5 — SURFACE CONSTRUITE BRUTE (SCB) ═══")
    
    niveaux = r.get("niveaux_pleins_max") or 1
    combles_retrait = r.get("combles_retrait", "Non") == "Oui"
    
    scb_niveaux_pleins = emprise_au_sol * niveaux
    trace.append(f"  Niveaux pleins: {niveaux}")
    trace.append(f"  SCB niveaux pleins: {emprise_au_sol:.1f} × {niveaux} = {scb_niveaux_pleins:.1f} m²")
    
    scb_combles = 0
    if combles_retrait:
        gabarit_angle = rc.get("gabarit_combles_angle", 45)
        scb_combles = emprise_au_sol * 0.60
        trace.append(f"  Combles/retrait: gabarit {gabarit_angle}° → ~60% de l'emprise = {scb_combles:.1f} m²")
    else:
        trace.append(f"  Combles/retrait: non autorisé")
    
    scb_brute = scb_niveaux_pleins + scb_combles
    trace.append(f"  SCB brute totale: {scb_niveaux_pleins:.1f} + {scb_combles:.1f} = {scb_brute:.1f} m²")
    
    # Déduction circulations communes
    scb_totale = scb_brute * RATIO_CIRCULATIONS
    trace.append(f"  Déduction circulations ({(1-RATIO_CIRCULATIONS)*100:.0f}%): {scb_brute:.1f} × {RATIO_CIRCULATIONS} = {scb_totale:.1f} m²")

    # Vérifier CUS PAP NQ
    if est_pap_nq and pap_nq_data:
        cus_nq = pap_nq_data.get("cus_max")
        if cus_nq:
            scb_max_cus = surface_terrain_net * cus_nq
            trace.append(f"  Vérification CUS PAP NQ:")
            trace.append(f"    CUS max: {cus_nq} → SCB max: {surface_terrain_net} × {cus_nq} = {scb_max_cus:.1f} m²")
            if scb_totale > scb_max_cus:
                trace.append(f"    ⚠️ CUS limitant → SCB réduite de {scb_totale:.1f} à {scb_max_cus:.1f} m²")
                scb_totale = scb_max_cus
                contraintes.append(f"CUS PAP NQ {cus_nq} limitant: SCB max {scb_max_cus:.0f} m²")
            else:
                trace.append(f"    ✅ CUS OK")

    # ── ÉTAPE 6 : Sous-sol ──
    trace.append("")
    trace.append("═══ ÉTAPE 6 — SOUS-SOL ═══")
    
    recul_arr_ss = recul_arriere_ss if recul_arriere_ss else recul_arriere
    prof_ss_max = r.get("profondeur_max_sous_sol")
    
    prof_ss = profondeur_parcelle_m - recul_avant - recul_arr_ss
    if prof_ss_max and prof_ss > prof_ss_max:
        prof_ss = prof_ss_max
    
    emprise_sous_sol = largeur_utile * prof_ss if prof_ss > 0 else emprise_au_sol
    trace.append(f"  Recul arrière sous-sol: {recul_arr_ss} m")
    if prof_ss_max:
        trace.append(f"  Profondeur max sous-sol: {prof_ss_max} m")
    trace.append(f"  Profondeur sous-sol possible: {prof_ss:.1f} m")
    trace.append(f"  Emprise sous-sol estimée: {emprise_sous_sol:.1f} m²")

    # ── ÉTAPE 7 : Programme logements ──
    trace.append("")
    trace.append("═══ ÉTAPE 7 — PROGRAMME LOGEMENTS ═══")
    
    # Répartition logement / commerce
    type_zone = r.get("type_zone", "Habitation")
    min_scb_logement_pct = r.get("min_scb_logement_pct")
    logement_autorise = r.get("logement_autorise", "Oui") == "Oui"
    commerce_autorise = r.get("commerce_autorise", "Non") == "Oui"
    
    if type_zone == "Mixte" and commerce_autorise:
        pct_log = (min_scb_logement_pct or 50) / 100
        scb_commerce = emprise_au_sol * 0.80  # RDC commercial
        scb_logement = scb_totale - scb_commerce
        if scb_logement < scb_totale * pct_log:
            scb_logement = scb_totale * pct_log
            scb_commerce = scb_totale - scb_logement
        trace.append(f"  Zone mixte — part min logement: {min_scb_logement_pct or 50}%")
        trace.append(f"  SCB commerce (RDC ~80%): {scb_commerce:.1f} m²")
        trace.append(f"  SCB logement: {scb_logement:.1f} m²")
    elif not logement_autorise:
        scb_logement = 0
        scb_commerce = scb_totale
        trace.append(f"  Zone non résidentielle — pas de logement")
        trace.append(f"  SCB activités: {scb_commerce:.1f} m²")
    else:
        scb_logement = scb_totale
        scb_commerce = 0
        trace.append(f"  Zone résidentielle — 100% logement")
        trace.append(f"  SCB logement: {scb_logement:.1f} m²")

    # Nombre de logements
    nb_logements_brut = scb_logement / SCB_MOYENNE_PAR_LOGEMENT if scb_logement > 0 else 0
    trace.append(f"  SCB moyenne par logement (mix standard): {SCB_MOYENNE_PAR_LOGEMENT:.1f} m²")
    trace.append(f"  Nb logements brut: {scb_logement:.1f} / {SCB_MOYENNE_PAR_LOGEMENT:.1f} = {nb_logements_brut:.1f}")
    
    nb_logements = nb_logements_brut
    
    # Plafonner par DL max
    dl_max = r.get("dl_max")
    if dl_max:
        nb_log_max_dl = (surface_terrain_m2 / 10000) * dl_max
        trace.append(f"  Plafond densité: {dl_max} log/ha → max {nb_log_max_dl:.1f} logements")
        if nb_logements > nb_log_max_dl:
            nb_logements = nb_log_max_dl
            trace.append(f"    ⚠️ Densité limitante → réduit à {nb_logements:.1f}")
            contraintes.append(f"Densité max {dl_max} log/ha limitante")
    
    # Plafonner par nb max par construction
    nb_log_max_constr = r.get("nb_log_max_par_construction")
    if nb_log_max_constr:
        trace.append(f"  Plafond par construction: max {nb_log_max_constr} logements")
        if nb_logements > nb_log_max_constr:
            nb_logements = nb_log_max_constr
            trace.append(f"    ⚠️ Plafonné à {nb_log_max_constr}")
    
    # PAP NQ densité
    if est_pap_nq and pap_nq_data:
        dl_nq = pap_nq_data.get("dl_max")
        if dl_nq:
            nb_log_nq = (surface_terrain_m2 / 10000) * dl_nq
            trace.append(f"  Plafond PAP NQ: {dl_nq} log/ha → max {nb_log_nq:.1f}")
            if nb_logements > nb_log_nq:
                nb_logements = nb_log_nq
                trace.append(f"    ⚠️ Densité PAP NQ limitante")

    nb_logements = max(1, math.floor(nb_logements)) if logement_autorise else 0
    trace.append(f"  → Nombre de logements retenu: {nb_logements}")

    # ── ÉTAPE 8 : Mix logements ──
    trace.append("")
    trace.append("═══ ÉTAPE 8 — MIX LOGEMENTS ═══")
    
    mix_detail = {}
    if nb_logements > 0:
        if nb_logements <= 2:
            mix_detail = {"T3": {"nb": nb_logements, "shn_m2": 70, "scb_m2": 88}}
            trace.append(f"  ≤2 logements → T3 par défaut")
        else:
            for type_log, data in MIX_STANDARD.items():
                nb = max(1, round(nb_logements * data["pct"]))
                mix_detail[type_log] = {"nb": nb, "shn_m2": data["shn_m2"], "scb_m2": data["scb_m2"]}
            total_mix = sum(d["nb"] for d in mix_detail.values())
            if total_mix != nb_logements:
                diff = nb_logements - total_mix
                mix_detail["T2"]["nb"] += diff
            for t, d in mix_detail.items():
                trace.append(f"  {t}: {d['nb']} × {d['shn_m2']} m² SHN ({d['scb_m2']} m² SCB)")
    
    # Vérifier moyenne SHN ≥ 52m²
    total_log = sum(d["nb"] for d in mix_detail.values())
    avg_shn = sum(d["shn_m2"] * d["nb"] for d in mix_detail.values()) / total_log if total_log > 0 else 0
    trace.append(f"  Moyenne SHN: {avg_shn:.1f} m² {'✅ ≥ 52m²' if avg_shn >= 52 else '⚠️ < 52m²'}")
    if avg_shn < 52 and total_log > 0:
        contraintes.append(f"Moyenne SHN {avg_shn:.0f}m² < 52m² réglementaire — ajuster le mix")

    # ── ÉTAPE 9 : Stationnement ──
    trace.append("")
    trace.append("═══ ÉTAPE 9 — STATIONNEMENT ═══")
    
    parkings = calculer_parkings(nb_logements, mix_detail, scb_commerce)
    parkings_velo = calculer_parkings_velo(nb_logements, scb_commerce)
    surface_parking_ss = parkings["min"] * 25
    
    trace.append(f"  Parkings auto: {parkings['min']} à {parkings['max']} places")
    trace.append(f"  Parkings vélo: {parkings_velo} places")
    trace.append(f"  Surface parking sous-sol estimée (~25m²/place): {surface_parking_ss} m²")

    # ── ÉTAPE 10 : Contraintes supplémentaires ──
    trace.append("")
    trace.append("═══ ÉTAPE 10 — CONTRAINTES SUPPLÉMENTAIRES ═══")
    
    if css_max:
        trace.append(f"  CSS max: {css_max} → surface scellée max {surface_terrain_net * css_max:.0f} m²")
    
    csv_min = r.get("csv_min")
    if csv_min:
        surface_verdure = surface_terrain_net * csv_min
        trace.append(f"  Surface verdure min: {csv_min*100:.0f}% → {surface_verdure:.0f} m²")
        contraintes.append(f"Surface verdure min {csv_min*100:.0f}%: {surface_verdure:.0f} m²")
    
    construction_2e = r.get("construction_2e_position", "Non")
    if construction_2e == "Non":
        trace.append(f"  Construction en 2e position: interdite")
        contraintes.append("Construction en 2e position interdite")
    else:
        cond = r.get("construction_2e_position_condition", "")
        if cond:
            trace.append(f"  Construction en 2e position: autorisée ({cond})")
    
    distance_min = r.get("distance_entre_constructions_min")
    if distance_min:
        trace.append(f"  Distance min entre constructions: {distance_min} m")
        contraintes.append(f"Distance min entre constructions sur même parcelle: {distance_min} m")

    # Checklist géoportail
    if checklist:
        for item in checklist:
            statut = item.get("statut", "")
            if "OUI" in str(statut):
                trace.append(f"  ⚠️ {item.get('contrainte', '')}: CONCERNÉ")
                contraintes.append(f"{item.get('contrainte', '')}: concerné — vérifier impact")
            elif "Erreur" in str(statut):
                trace.append(f"  ❓ {item.get('contrainte', '')}: non vérifié")

    # ── ÉTAPE 11 : Programme niveaux ──
    trace.append("")
    trace.append("═══ ÉTAPE 11 — SYNTHÈSE PROGRAMME ═══")
    
    niveaux_programme = f"SS: parking ({surface_parking_ss} m²)"
    if type_zone == "Mixte" and scb_commerce > 0:
        niveaux_programme += f" | RDC: commerce ({scb_commerce:.0f} m²)"
        niveaux_programme += f" | R+1 à R+{niveaux-1}: logement"
    else:
        niveaux_programme += f" | RDC à R+{niveaux-1}: logement ({scb_logement:.0f} m²)"
    if combles_retrait:
        niveaux_programme += f" | Combles/retrait ({scb_combles:.0f} m²)"
    
    trace.append(f"  {niveaux_programme}")

    # ── VERDICT ──
    trace.append("")
    trace.append("═══ VERDICT ═══")
    
    if emprise_au_sol < 50:
        potentiel = "Faible"
    elif nb_logements <= 2:
        potentiel = "Faible"
    elif nb_logements <= 6:
        potentiel = "Moyen"
    else:
        potentiel = "Fort"
    
    trace.append(f"  Constructible: Oui")
    trace.append(f"  Potentiel: {potentiel}")
    trace.append(f"  Emprise: {emprise_au_sol:.1f} m² | SCB: {scb_totale:.1f} m² | Logements: {nb_logements}")

    # ── Résultat final ──
    result["programme"] = {
        "emprise_au_sol_m2": round(emprise_au_sol, 1),
        "scb_totale_m2": round(scb_totale, 1),
        "scb_niveaux_pleins_m2": round(scb_niveaux_pleins, 1),
        "scb_combles_retrait_m2": round(scb_combles, 1),
        "scb_logement_m2": round(scb_logement, 1),
        "scb_commerce_m2": round(scb_commerce, 1),
        "nb_logements": nb_logements,
        "mix_logements": mix_detail,
        "moyenne_shn_m2": round(avg_shn, 1),
        "respect_moyenne_52m2": avg_shn >= 52,
        "parkings_auto": parkings,
        "parkings_velo": parkings_velo,
        "surface_parking_ss_estimee_m2": surface_parking_ss,
        "emprise_sous_sol_m2": round(emprise_sous_sol, 1),
        "niveaux_programme": niveaux_programme,
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
# FORMATTAGE RAPPORT TEXTE
# ============================================================

def formater_rapport(data):
    r = data["regles"]
    p = data["programme"]
    v = data["verdict"]
    i = data["identification"]

    lines = []
    lines.append("=" * 60)
    lines.append("ANALYSE DE FAISABILITÉ IMMOBILIÈRE")
    lines.append(f"Commune: {i['commune']} | Zone: {i['zone_pag']}")
    lines.append(f"Surface terrain: {i['surface_terrain_m2']} m²")
    lines.append("=" * 60)

    if v["constructible"] == "Non":
        lines.append(f"\n❌ NON CONSTRUCTIBLE: {v.get('raison', '')}")
        return "\n".join(lines)

    lines.append(f"\n📍 ZONE: {r['nom_zone']} ({i['zone_pag']})")
    lines.append(f"   Type: {r['type_zone']} | PAP QE: {r['pap_qe']}")

    lines.append(f"\n📏 RÈGLES URBANISTIQUES:")
    lines.append(f"   Hauteur corniche max: {r['h_corniche_max']} m")
    lines.append(f"   Hauteur faîte max: {r['h_faite_max']} m")
    niv_txt = f"{r['niveaux_pleins_max']} pleins{' + combles/retrait' if r['combles_retrait'] else ''}"
    lines.append(f"   Niveaux: {niv_txt}")
    lines.append(f"   Reculs: avant {r['recul_avant_min']}m | latéral {r['recul_lateral_min']}m | arrière {r['recul_arriere_min']}m")
    if r['profondeur_max']:
        lines.append(f"   Profondeur max: {r['profondeur_max']} m")
    if r['cos_max']:
        lines.append(f"   COS max: {r['cos_max']} | CSS max: {r.get('css_max', '-')}")
    if r['dl_max']:
        lines.append(f"   Densité logements max: {r['dl_max']} log/ha")

    lines.append(f"\n🏗️ PROGRAMME ESTIMÉ:")
    lines.append(f"   Emprise au sol: {p['emprise_au_sol_m2']} m²")
    lines.append(f"   SCB totale: {p['scb_totale_m2']} m²")
    lines.append(f"     dont niveaux pleins: {p['scb_niveaux_pleins_m2']} m²")
    if p['scb_combles_retrait_m2'] > 0:
        lines.append(f"     dont combles/retrait: {p['scb_combles_retrait_m2']} m²")
    
    lines.append(f"\n   📦 Logements: {p['nb_logements']} unités")
    lines.append(f"   SCB logement: {p['scb_logement_m2']} m²")
    if p['scb_commerce_m2'] > 0:
        lines.append(f"   SCB commerce/activités: {p['scb_commerce_m2']} m²")
    
    lines.append(f"\n   Mix logements:")
    for type_log, detail in p['mix_logements'].items():
        if detail['nb'] > 0:
            lines.append(f"     {type_log}: {detail['nb']} × {detail['shn_m2']}m² SHN ({detail['scb_m2']}m² SCB)")
    lines.append(f"   Moyenne SHN: {p['moyenne_shn_m2']} m² {'✅' if p['moyenne_shn_m2'] >= 52 else '⚠️ < 52m²'}")

    lines.append(f"\n   🚗 Parkings auto: {p['parkings_auto']['min']}-{p['parkings_auto']['max']} places")
    lines.append(f"   🚲 Parkings vélo: {p['parkings_velo']} places")
    lines.append(f"   Surface parking sous-sol estimée: {p['surface_parking_ss_estimee_m2']} m²")

    if data["contraintes"]:
        lines.append(f"\n⚠️ POINTS D'ATTENTION:")
        for c in data["contraintes"]:
            lines.append(f"   • {c}")

    lines.append(f"\n{'='*60}")
    lines.append(f"VERDICT: {'✅' if v['constructible'] == 'Oui' else '❌'} {v['constructible']}")
    lines.append(f"POTENTIEL: {v['potentiel']}")
    lines.append(f"{'='*60}")

    # Trace détaillée
    lines.append(f"\n\n{'='*60}")
    lines.append("DÉTAIL DES CALCULS")
    lines.append(f"{'='*60}")
    for t in data.get("trace", []):
        lines.append(t)

    return "\n".join(lines)


# ============================================================
# API ENDPOINT (Flask)
# ============================================================

from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/calcul', methods=['POST'])
def api_calcul():
    data = request.json
    
    # Le workflow n8n envoie soit les règles directement, soit zone_pag + commune
    regles_zone = data.get("regles_zone")
    
    if not regles_zone:
        # Fallback: pas de règles → retourner une erreur claire
        return jsonify({
            "error": "Règles de zone manquantes. Le workflow doit envoyer regles_zone.",
            "regles": {},
            "programme": {},
            "contraintes": ["Aucune règle trouvée dans la base pour cette zone"],
            "verdict": {"constructible": "Indéterminé", "potentiel": "Indéterminé"},
            "trace": ["Erreur: aucune règle de zone fournie"]
        })
    
    result = calculer_faisabilite(
        surface_terrain_m2=data.get("surface_terrain_m2", 0),
        regles_zone=regles_zone,
        regles_communes=data.get("regles_communes"),
        largeur_facade_m=data.get("largeur_facade_m"),
        profondeur_parcelle_m=data.get("profondeur_parcelle_m"),
        forme_parcelle=data.get("forme_parcelle"),
        est_route_specifique=data.get("est_route_specifique", False),
        est_pap_nq=data.get("est_pap_nq", False),
        pap_nq_data=data.get("pap_nq_data"),
        checklist=data.get("checklist"),
    )
    
    return jsonify(result)


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "version": "2.0-generic"})


if __name__ == "__main__":
    # Test local avec règles Strassen MIX-u
    test_regles = {
        "commune": "Strassen",
        "code_commune": "C006",
        "code_zone": "MIX-u",
        "pap_qe": "QE2",
        "nom_zone": "Zone mixte urbaine",
        "type_zone": "Mixte",
        "constructible": "Oui",
        "logement_autorise": "Oui",
        "commerce_autorise": "Oui",
        "recul_avant_min": 3,
        "recul_avant_max": 7,
        "recul_lateral_min": 4.5,
        "recul_arriere_hors_sol_min": 12,
        "recul_arriere_sous_sol_min": 4.5,
        "profondeur_max_hors_sol": 14,
        "profondeur_max_sous_sol": 18,
        "profondeur_rdc_non_logement": 20,
        "profondeur_rdc_non_logement_route_specifique": 30,
        "cos_max": 0.35,
        "css_max": 0.50,
        "niveaux_pleins_max": 3,
        "combles_retrait": "Oui",
        "h_corniche_max": 11,
        "h_faite_max": 15,
        "dl_max": 105,
        "min_scb_logement_pct": 50,
        "construction_2e_position": "Oui",
        "construction_2e_position_condition": "accès carrossable indépendant",
        "distance_entre_constructions_min": 9,
        "route_specifique_nom": "Route d'Arlon",
        "recul_avant_route_specifique": "15 m depuis axe voie",
        "recul_lateral_route_specifique": "moitié h_corniche, min 4.50 m",
    }
    
    print("\n" + "=" * 60)
    print("TEST 1: 779 m² en MIX-u (sans Route d'Arlon)")
    print("=" * 60)
    result1 = calculer_faisabilite(779, test_regles, largeur_facade_m=33, profondeur_parcelle_m=34.8)
    print(formater_rapport(result1))

    print("\n\n" + "=" * 60)
    print("TEST 2: 779 m² en MIX-u (Route d'Arlon)")
    print("=" * 60)
    result2 = calculer_faisabilite(779, test_regles, largeur_facade_m=33, profondeur_parcelle_m=34.8, est_route_specifique=True)
    print(formater_rapport(result2))
    
    # Lancer le serveur
    # app.run(host='0.0.0.0', port=5000)
