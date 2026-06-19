#!/usr/bin/env python3
"""
Palladio Scrap — synchronisation Airtable (idempotent).

Crée les champs typés [NEW] manquants dans la table Zones_PAG, puis upsert les
secteurs QE des communes (palladio_scrap/communes/*.json) sur la clé composite
(Commune, Code_zone, Regime). Confiance="auto" (relecture humaine ensuite).

Usage :
    AIRTABLE_API_KEY=pat... python3 palladio_scrap/airtable_sync.py --dry-run
    AIRTABLE_API_KEY=pat... python3 palladio_scrap/airtable_sync.py

Pourquoi un script et pas des writes MCP : dans la session Claude Code web les
écritures Airtable sont gated par approbation + l'egress est fermé. Ce script
tourne là où la clé API et le réseau existent (Railway/local). Source de vérité =
les JSON commités ; Airtable n'est qu'une projection plate consommée par n8n.
"""
import json, os, sys, glob, urllib.request, urllib.error

BASE_ID = "appFUtt83fMC6NwgU"
TABLE_ID = "tbll7YFXuR9ug1brF"   # Zones_PAG
API = "https://api.airtable.com/v0"
KEY_COMPOSITE = ["Commune", "Code_zone", "Regime"]

# Champs typés [NEW] à garantir (additifs ; on ne touche pas aux champs existants).
NEW_FIELDS = [
    {"name": "Regime", "type": "singleSelect",
     "options": {"choices": [{"name": "QE"}, {"name": "NQ"}]}},
    {"name": "Methode_recul_avant", "type": "singleSelect",
     "options": {"choices": [{"name": "fixe"}, {"name": "alignement_voisins"}, {"name": "lie_hauteur"}]}},
    {"name": "Recul_avant_fallback_m", "type": "number", "options": {"precision": 2}},
    {"name": "Bande_construction_max_m", "type": "number", "options": {"precision": 0}},
    {"name": "Hauteur_modele", "type": "singleSelect",
     "options": {"choices": [{"name": "fixe"}, {"name": "par_niveaux"}]}},
    {"name": "Hauteur_par_niveaux_json", "type": "multilineText"},
    {"name": "Logements_modele", "type": "singleSelect",
     "options": {"choices": [{"name": "fixe"}, {"name": "par_ha"}, {"name": "formule"}, {"name": "graphique"}]}},
    {"name": "Source_articles_json", "type": "multilineText"},
    {"name": "Confiance", "type": "singleSelect",
     "options": {"choices": [{"name": "auto"}, {"name": "valide"}]}},
]


def _req(method, url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {os.environ['AIRTABLE_API_KEY']}",
        "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} on {method} {url}\n{e.read().decode()}", file=sys.stderr)
        raise


def ensure_fields():
    meta = _req("GET", f"{API}/meta/bases/{BASE_ID}/tables")
    table = next(t for t in meta["tables"] if t["id"] == TABLE_ID)
    existing = {f["name"] for f in table["fields"]}
    for f in NEW_FIELDS:
        if f["name"] in existing:
            continue
        _req("POST", f"{API}/meta/bases/{BASE_ID}/tables/{TABLE_ID}/fields", f)
        print(f"  + champ créé : {f['name']}")


def sector_to_fields(commune, s):
    """Mappe un secteur (schéma typé) vers les colonnes plates de Zones_PAG."""
    ra = s.get("recul_avant", {}) or {}
    rl = s.get("recul_lateral", {}) or {}
    rr = s.get("recul_arriere", {}) or {}
    hp = s.get("hauteur_par_niveaux")
    f = {
        "Commune": commune,
        "Code_zone": (s.get("zone_pag") or [s.get("code_pap")])[0],
        "Nom_zone": s.get("libelle", ""),
        "Regime": s.get("regime", "QE"),
        "Article_PAP_QE": s.get("source_articles", {}).get("reculs") or ra.get("source_article", ""),
        "Methode_recul_avant": ra.get("type", "fixe"),
        "Recul_avant_fallback_m": ra.get("fallback_m"),
        "Recul_avant_max_m": ra.get("max_m"),
        "Recul_arriere_sous_sol_min_m": rr.get("min_sous_sol_m"),
        "Profondeur_sous_sol_max_m": s.get("profondeur_sous_sol_max_m"),
        "Bande_construction_max_m": s.get("bande_construction_max_m"),
        "Hauteur_modele": s.get("hauteur_modele", "fixe"),
        "Hauteur_corniche_max_m": s.get("hauteur_corniche_max_m"),
        "Hauteur_faite_max_m": s.get("hauteur_faite_max_m"),
        "Hauteur_acrotere_max_m": s.get("hauteur_acrotere_max_m"),
        "Hauteur_par_niveaux_json": json.dumps(hp, ensure_ascii=False) if hp else None,
        "COS_max": s.get("cos_max"),
        "CSS_max": s.get("css_max"),
        "DL_max_log_ha": s.get("dl_max_log_ha"),
        "Logements_modele": s.get("logements_modele"),
        "Nb_logements_max": (str(s.get("logements_max_par_construction")) + " /construction"
                             if s.get("logements_max_par_construction") is not None
                             else (s.get("logements_formule") or None)),
        "Min_SCB_logement_%_QE": s.get("part_min_scb_logement_qe_pct"),
        "Source_articles_json": json.dumps(s.get("source_articles", {}), ensure_ascii=False),
        "Notes_reculs": s.get("notes", ""),
        "Confiance": s.get("confiance", "auto"),
    }
    # reculs scalaires (singleSelect) : seulement si fixe ; sinon laissés vides
    if ra.get("type") == "fixe" and ra.get("min_m") is not None:
        f["Recul_avant_min_m"] = str(ra["min_m"])
    if rl.get("min_m") is not None:
        f["Recul_lateral_min_m"] = str(rl["min_m"])
    if rr.get("min_m") is not None:
        f["Recul_arriere_min_m"] = str(rr["min_m"])
    if s.get("profondeur_max_m") is not None:
        f["Profondeur_max_m"] = str(s["profondeur_max_m"])
    # régime voirie spécial -> champ texte existant
    rvs = s.get("regime_voirie_special")
    if rvs:
        f["Recul_avant_route_specifique"] = json.dumps(rvs, ensure_ascii=False)
    return {k: v for k, v in f.items() if v is not None}


def main():
    dry = "--dry-run" in sys.argv
    records = []
    for path in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "communes", "*.json"))):
        data = json.load(open(path))
        for s in data.get("secteurs", []):
            records.append({"fields": sector_to_fields(data["commune"], s)})
    print(f"{len(records)} secteurs à upsert (clé {KEY_COMPOSITE}).")
    if dry:
        print(json.dumps(records, ensure_ascii=False, indent=2))
        return
    ensure_fields()
    for i in range(0, len(records), 10):
        chunk = records[i:i + 10]
        _req("PATCH", f"{API}/{BASE_ID}/{TABLE_ID}", {
            "performUpsert": {"fieldsToMergeOn": KEY_COMPOSITE},
            "records": chunk, "typecast": True})
        print(f"  upsert {i + len(chunk)}/{len(records)}")
    print("OK.")


if __name__ == "__main__":
    if "AIRTABLE_API_KEY" not in os.environ and "--dry-run" not in sys.argv:
        sys.exit("AIRTABLE_API_KEY manquant (ou --dry-run).")
    main()
