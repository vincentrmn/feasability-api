"""
Test standalone Phase 2 — validation de compute_oriented_bbox et
compute_emprise_polygon sur les parcelles réelles de Strassen.

Usage :
  python test_emprise_polygon.py [chemin_vers_geojson]

Par défaut, lit strassen_11_rue_des_tilleuls_parcels.geojson à côté de ce script.

Exigences : uniquement la stdlib Python + le module main.py du projet feasibility-api
(placé dans le même dossier ou PYTHONPATH).
"""

import json
import math
import sys
from pathlib import Path

# ajout du dossier courant au path pour trouver main.py
sys.path.insert(0, str(Path(__file__).parent))
from main import (
    compute_oriented_bbox,
    compute_emprise_polygon,
    polygon_area_2d,
    calculer_faisabilite_v2,
)


# ────────────────────────────────────────────────────────────
# Règles Strassen HAB-1 (alignées sur ZONES_V1 de main.py)
# On simule une ligne Airtable pour tester le pipeline complet
# ────────────────────────────────────────────────────────────
REGLES_HAB_1 = {
    "commune": "Strassen",
    "code_zone": "HAB-1",
    "nom_zone": "Zone d'habitation 1",
    "pap_qe": "QE1",
    "type_zone": "Habitation",
    "constructible": "Oui",
    "logement_autorise": "Oui",
    "commerce_autorise": "Non",
    "h_corniche_max": 8.0,
    "h_faite_max": 12.0,
    "niveaux_pleins_max": 2,
    "combles_retrait": True,
    "recul_avant_min": 3.0,
    "recul_avant_max": 6.0,
    "recul_lateral_min": 3.0,
    "recul_arriere_hors_sol_min": 10.0,
    "profondeur_max_hors_sol": 14.0,
    "cos_max": 0.35,
    "css_max": 0.60,
    "nb_log_max_par_construction": 2,
    "dl_max": None,
    "notes_reculs": "",
}


def extract_polygon(feature):
    """Extrait le premier ring d'un feature GeoJSON (Polygon ou MultiPolygon)."""
    geom = feature["geometry"]
    if geom["type"] == "Polygon":
        return geom["coordinates"][0]
    elif geom["type"] == "MultiPolygon":
        return geom["coordinates"][0][0]
    else:
        return None


def normalize_ring(ring):
    """Retire le dernier point si identique au premier (fermeture GeoJSON)."""
    if len(ring) >= 2 and ring[0] == ring[-1]:
        return ring[:-1]
    return ring


def test_obb_sanity():
    """Test 1 : OBB d'un rectangle axis-aligned connu — vérité terrain parfaite."""
    print("─" * 70)
    print("TEST 1 — OBB d'un rectangle axis-aligned 20×40")
    print("─" * 70)

    # rectangle de (100, 200) à (120, 240) — 20m façade × 40m profondeur
    rect = [[100, 200], [120, 200], [120, 240], [100, 240]]
    obb = compute_oriented_bbox(rect)
    print(f"  Input     : coin SO (100,200) à coin NE (120,240)")
    print(f"  Résultat  : centre=({obb['center_x']:.2f}, {obb['center_y']:.2f})")
    print(f"              width={obb['width']:.2f}  depth={obb['depth']:.2f}  angle={math.degrees(obb['angle_rad']):.1f}°")
    # attendu : center=(110, 220), width=20, depth=40, angle=0 ou 90
    ok = (
        abs(obb["center_x"] - 110) < 0.01
        and abs(obb["center_y"] - 220) < 0.01
        and abs(obb["width"] - 20) < 0.01
        and abs(obb["depth"] - 40) < 0.01
    )
    print(f"  {'✅ PASS' if ok else '❌ FAIL'}")
    print()
    return ok


def test_obb_rotated():
    """Test 2 : OBB d'un rectangle tourné de 30° — vérifie la robustesse angulaire."""
    print("─" * 70)
    print("TEST 2 — OBB d'un rectangle 20×40 tourné de 30°")
    print("─" * 70)

    angle_deg = 30
    a = math.radians(angle_deg)
    cos_a, sin_a = math.cos(a), math.sin(a)
    # rectangle centré sur (500, 300), width=20, depth=40, tourné de 30°
    local_corners = [(-10, -20), (10, -20), (10, 20), (-10, 20)]
    rect = []
    for lx, ly in local_corners:
        x = cos_a * lx - sin_a * ly + 500
        y = sin_a * lx + cos_a * ly + 300
        rect.append([x, y])

    obb = compute_oriented_bbox(rect)
    print(f"  Résultat  : centre=({obb['center_x']:.2f}, {obb['center_y']:.2f})")
    print(f"              width={obb['width']:.2f}  depth={obb['depth']:.2f}  angle={math.degrees(obb['angle_rad']):.1f}°")
    ok = (
        abs(obb["center_x"] - 500) < 0.1
        and abs(obb["center_y"] - 300) < 0.1
        and abs(obb["width"] - 20) < 0.1
        and abs(obb["depth"] - 40) < 0.1
    )
    # l'angle peut être 30° ou 30°+180° selon quelle arête a gagné
    print(f"  {'✅ PASS' if ok else '❌ FAIL'}")
    print()
    return ok


def test_emprise_simple():
    """Test 3 : emprise d'un rectangle simple avec reculs HAB-1."""
    print("─" * 70)
    print("TEST 3 — Emprise sur rectangle 20×40, reculs HAB-1 (3/3/10)")
    print("─" * 70)

    rect = [[0, 0], [20, 0], [20, 40], [0, 40]]
    emp = compute_emprise_polygon(rect, recul_avant=3, recul_lateral=3,
                                   recul_arriere=10, prof_max=14)
    print(f"  OBB parcelle : {emp['obb_width']}×{emp['obb_depth']} m")
    print(f"  Emprise      : {emp['emprise_width']}×{emp['emprise_depth']} m = {emp['area_m2']} m²")
    print(f"  Coins LUREF  :")
    for i, c in enumerate(emp["corners"]):
        print(f"    [{i}] ({c[0]:.2f}, {c[1]:.2f})")
    # vérifications :
    # - largeur utile = 20 - 2*3 = 14 (OK)
    # - profondeur utile = 40 - 3 - 10 = 27, limitée par prof_max=14 → 14
    # - surface = 14*14 = 196 m²
    ok = (
        abs(emp["emprise_width"] - 14) < 0.01
        and abs(emp["emprise_depth"] - 14) < 0.01
        and abs(emp["area_m2"] - 196) < 1
    )
    print(f"  Attendu: 14×14 = 196 m²  |  {'✅ PASS' if ok else '❌ FAIL'}")
    print()
    return ok


def test_emprise_trop_petit():
    """Test 4 : reculs plus grands que la parcelle → warning."""
    print("─" * 70)
    print("TEST 4 — Parcelle trop petite (10×12) pour reculs HAB-1")
    print("─" * 70)

    rect = [[0, 0], [10, 0], [10, 12], [0, 12]]
    emp = compute_emprise_polygon(rect, recul_avant=3, recul_lateral=3, recul_arriere=10)
    print(f"  Warning : {emp.get('warning', 'aucun')}")
    print(f"  Corners : {emp.get('corners')}")
    ok = emp.get("corners") is None and emp.get("warning") is not None
    print(f"  {'✅ PASS' if ok else '❌ FAIL'}")
    print()
    return ok


def test_parcelles_reelles(geojson_path):
    """Test 5 : applique compute_emprise_polygon sur les 20 parcelles Strassen."""
    print("─" * 70)
    print(f"TEST 5 — {geojson_path.name} : 20 parcelles réelles de Strassen")
    print("─" * 70)
    with open(geojson_path) as f:
        gj = json.load(f)

    print(f"{'sourceId':<14}{'sommets':>8}{'surface':>10}{'OBB w×d':>16}{'emprise':>16}{'area':>10}")
    print(f"{'─'*14}{'─'*8}{'─'*10}{'─'*16}{'─'*16}{'─'*10}")
    all_ok = True
    for feat in gj["features"]:
        ring = extract_polygon(feat)
        if not ring:
            continue
        ring = normalize_ring(ring)
        src = feat["properties"].get("sourceId", "?")
        n = len(ring)
        area_parcel = polygon_area_2d(ring)
        emp = compute_emprise_polygon(ring, recul_avant=3, recul_lateral=3, recul_arriere=10)
        if emp and emp.get("corners"):
            obb_str = f"{emp['obb_width']:.1f}×{emp['obb_depth']:.1f}"
            emp_str = f"{emp['emprise_width']:.1f}×{emp['emprise_depth']:.1f}"
            area_str = f"{emp['area_m2']:.0f}"
        else:
            obb_str = f"{emp['obb_width']:.1f}×{emp['obb_depth']:.1f}" if emp else "?"
            emp_str = "TROP PETIT"
            area_str = "0"
        print(f"{src:<14}{n:>8}{area_parcel:>9.0f}m²{obb_str:>16}{emp_str:>16}{area_str:>9}m²")
    print()


def test_pipeline_complet(geojson_path):
    """Test 6 : pipeline complet calculer_faisabilite_v2 avec parcelle_polygon_luref."""
    print("─" * 70)
    print("TEST 6 — calculer_faisabilite_v2 bout en bout avec polygone")
    print("─" * 70)
    with open(geojson_path) as f:
        gj = json.load(f)

    # On prend la première parcelle
    feat = gj["features"][0]
    ring = normalize_ring(extract_polygon(feat))
    src = feat["properties"].get("sourceId")
    surface = polygon_area_2d(ring)

    print(f"  Parcelle cible : {src}")
    print(f"  Surface        : {surface:.0f} m²")
    print()

    result = calculer_faisabilite_v2(
        surface_terrain_m2=surface,
        regles=REGLES_HAB_1,
        parcelle_polygon_luref=ring,
    )

    prog = result["programme"]
    print(f"  Emprise au sol : {prog['emprise_au_sol_m2']} m²")
    print(f"  SCB totale     : {prog['scb_totale_m2']} m²")
    print(f"  Logements      : {prog['nb_logements']}")
    print()

    emp_poly = prog.get("emprise_polygon_luref")
    if emp_poly:
        print(f"  emprise_polygon_luref :")
        print(f"    method          : {emp_poly['method']}")
        print(f"    OBB parcelle    : {emp_poly['obb_width']}×{emp_poly['obb_depth']} m")
        print(f"    Emprise bâti    : {emp_poly['emprise_width']}×{emp_poly['emprise_depth']} m")
        print(f"    Surface bâti    : {emp_poly['area_m2']} m²")
        print(f"    Orientation     : {math.degrees(emp_poly['orientation_rad']):.1f}°")
        if emp_poly.get("corners"):
            print(f"    Coins LUREF     :")
            for i, c in enumerate(emp_poly["corners"]):
                print(f"      [{i}] ({c[0]:.2f}, {c[1]:.2f})")
    else:
        print("  ⚠️  emprise_polygon_luref absent (pas calculé)")
    print()

    return emp_poly is not None and emp_poly.get("corners") is not None


def main():
    path_arg = sys.argv[1] if len(sys.argv) > 1 else None
    if path_arg:
        geojson_path = Path(path_arg)
    else:
        geojson_path = Path(__file__).parent / "strassen_11_rue_des_tilleuls_parcels.geojson"

    if not geojson_path.exists():
        print(f"❌ Fichier GeoJSON introuvable : {geojson_path}")
        print("   Usage : python test_emprise_polygon.py [chemin/vers/parcels.geojson]")
        sys.exit(1)

    results = []
    results.append(("Test 1 — OBB axis-aligned",    test_obb_sanity()))
    results.append(("Test 2 — OBB rotated 30°",     test_obb_rotated()))
    results.append(("Test 3 — Emprise simple",      test_emprise_simple()))
    results.append(("Test 4 — Parcelle trop petite", test_emprise_trop_petit()))
    test_parcelles_reelles(geojson_path)
    results.append(("Test 6 — Pipeline complet",    test_pipeline_complet(geojson_path)))

    print("=" * 70)
    print("RÉCAPITULATIF")
    print("=" * 70)
    for name, ok in results:
        print(f"  {'✅' if ok else '❌'} {name}")
    all_ok = all(ok for _, ok in results)
    print()
    print("✅ TOUS LES TESTS PASSENT" if all_ok else "❌ AU MOINS UN TEST ÉCHOUE")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
