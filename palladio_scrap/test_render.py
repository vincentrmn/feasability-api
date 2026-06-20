"""
Test du renderer HTML sur une VRAIE reponse moteur (execution n8n 917, 5 rue de
Mamer, Bertrange MIX-v). Verifie le cablage des donnees (le bug d'affichage : le
recul avant doit etre 5.34 lu sur le moteur, pas 4 du payload) + non-plantage.
Genere aussi /tmp/palladio_sample.html. Lancer : python3 palladio_scrap/test_render.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from palladio_render import render_palladio_html

# Extrait reel de l'execution 917 (champs utiles au rendu)
RESP_917 = {
    "meta": {"engine": "palladio", "version": "0.3.1", "method": "full", "enveloppe_vide": False},
    "parcelle": {"id": "010A00477003433", "surface_cadastrale_m2": 216.5,
                 "geometry_luref": {"type": "Polygon", "coordinates": [[
                     [71384.38, 75197.75], [71384.88, 75188.61],
                     [71359.60, 75189.17], [71359.58, 75197.32], [71384.38, 75197.75]]]}},
    "voirie": {"idx": 0, "edge_label": "AB"},
    "fond": {"idx": 2, "edge_label": "CD"},
    "reculs_appliques": {"avant_m": 5.34187927253567, "lateral_m": 3, "arriere_m": 10, "profondeur_max_m": 15},
    "recul_avant_adaptatif": {"type": "alignement_voisins", "source_article": "Art. 6",
                              "n_voisins_utiles": 3, "fronts_m": [3.49, 5.34, 5.75],
                              "fallback_m": 4, "fallback_used": False, "recul_m": 5.34},
    "emprise": {"surface_m2": 84.7, "ratio_vs_cadastrale": 0.391,
                "geometry_luref": {"type": "Polygon", "coordinates": [[
                    [71369.598, 75188.95], [71369.593, 75191.951], [71369.584, 75197.493],
                    [71371.003, 75197.518], [71378.594, 75197.651], [71379.039, 75197.659],
                    [71379.527, 75188.731], [71369.598, 75188.95]]]}},
    "traces_reculs": [
        {"idx": 0, "cat": "AVANT", "distance_m": 5.34},
        {"idx": 2, "cat": "ARRIERE", "distance_m": 10},
        {"idx": 1, "cat": "LATERAL", "distance_m": 0, "mur_mitoyen_bati": True},
        {"idx": 3, "cat": "LATERAL", "distance_m": 0, "mur_mitoyen_bati": True}],
    "scb": {"scb_totale_m2": 304.9},
    "logements": {"nb_logements": 3},
    "parkings": {"auto_min": 7, "auto_max": 8, "velo": 5},
    "warnings": [{"code": "JUMELAGE_DETECTE_SANS_DROITE", "level": "info",
                  "message_fr": "Mitoyennete potentielle detectee : verifier le droit a batir en limite."}],
}


def test_recul_avant_lu_sur_moteur():
    h = render_palladio_html(RESP_917, "5 rue de Mamer, Bertrange")
    assert "5.34 m" in h, "le recul avant doit etre 5.34 (moteur), pas le fallback"
    assert "alignement" in h.lower() or "Aligne" in h
    assert "4 m —" not in h, "ne doit pas afficher le fallback 4 comme recul avant"
    print("OK recul avant = 5.34 (moteur), pas 4 (payload)")


def test_contenu_essentiel():
    h = render_palladio_html(RESP_917, "5 rue de Mamer, Bertrange")
    for needle in ["84.7 m²", "3", "7", "8", "304.9 m²", "mur mitoyen", "<svg", "polygon"]:
        assert needle in h, f"manque dans le HTML : {needle}"
    print("OK contenu essentiel present (KPIs, schema SVG, legende)")


def test_enveloppe_vide_ne_plante_pas():
    h = render_palladio_html({"meta": {"enveloppe_vide": True, "version": "0.3.1"},
                              "parcelle": {}}, "Parcelle test")
    assert "Non constructible" in h
    print("OK enveloppe vide -> page sans plantage")


if __name__ == "__main__":
    test_recul_avant_lu_sur_moteur()
    test_contenu_essentiel()
    test_enveloppe_vide_ne_plante_pas()
    out = "/tmp/palladio_sample.html"
    open(out, "w").write(render_palladio_html(RESP_917, "5 rue de Mamer, Bertrange"))
    print(f"\nTOUS LES TESTS PASSENT. Echantillon ecrit : {out}")
