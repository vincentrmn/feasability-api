"""
Test du renderer HTML sur une VRAIE reponse moteur (execution 917, 5 rue de Mamer,
Bertrange MIX-v). Verifie : recul avant lu sur le moteur (5.34, pas 4), parite des
9 etapes + schemas, non-plantage. Genere /tmp/palladio_sample.html.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from palladio_render import render_palladio_html

RESP_917 = {
    "meta": {"engine": "palladio", "version": "0.3.1", "method": "full", "enveloppe_vide": False},
    "parcelle": {"id": "010A00477003433", "surface_cadastrale_m2": 216.5,
                 "geometry_luref": {"type": "Polygon", "coordinates": [[
                     [71384.38, 75197.75], [71384.88, 75188.61],
                     [71359.60, 75189.17], [71359.58, 75197.32], [71384.38, 75197.75]]]}},
    "voirie": {"idx": 0, "edge_label": "AB", "point_luref": [71376.84, 75192.35],
               "detection": {"edges_classified": [
                   {"p1": [71384.38, 75197.75], "p2": [71384.88, 75188.61], "is_voirie": True, "length_m": 9.15},
                   {"p1": [71384.88, 75188.61], "p2": [71359.60, 75189.17], "is_voirie": False, "length_m": 25.29},
                   {"p1": [71359.60, 75189.17], "p2": [71359.58, 75197.32], "is_voirie": False, "length_m": 8.15},
                   {"p1": [71359.58, 75197.32], "p2": [71384.38, 75197.75], "is_voirie": False, "length_m": 24.8}]}},
    "fond": {"idx": 2, "edge_label": "CD", "candidats": [
        {"idx_fond": 2, "fond_label": "CD", "score_fond": 24.93, "surface_emprise_m2": 84.7},
        {"idx_fond": 1, "fond_label": "BC", "score_fond": 0.07, "surface_emprise_m2": 0},
        {"idx_fond": 3, "fond_label": "DA", "score_fond": 0.02, "surface_emprise_m2": 0}]},
    "reculs_appliques": {"avant_m": 5.34187927253567, "lateral_m": 3, "arriere_m": 10, "profondeur_max_m": 15},
    "recul_avant_adaptatif": {"type": "alignement_voisins", "source_article": "Art. 6",
                              "n_voisins_utiles": 3, "fronts_m": [3.49, 5.34, 5.75],
                              "fallback_m": 4, "fallback_used": False, "recul_m": 5.34},
    "emprise": {"surface_m2": 84.7, "ratio_vs_cadastrale": 0.391, "mitoyennete_batie_appliquee": [1, 3],
                "geometry_luref": {"type": "Polygon", "coordinates": [[
                    [71369.598, 75188.95], [71369.593, 75191.951], [71369.584, 75197.493],
                    [71371.003, 75197.518], [71378.594, 75197.651], [71379.039, 75197.659],
                    [71379.527, 75188.731], [71369.598, 75188.95]]]}},
    "traces_reculs": [
        {"idx": 0, "cat": "AVANT", "distance_m": 5.34},
        {"idx": 2, "cat": "ARRIERE", "distance_m": 10},
        {"idx": 1, "cat": "LATERAL", "distance_m": 0, "mur_mitoyen_bati": True},
        {"idx": 3, "cat": "LATERAL", "distance_m": 0, "mur_mitoyen_bati": True}],
    "scb": {"scb_totale_m2": 304.9, "surface_habitable_m2": 243.9, "niveaux_pleins": 3, "combles": True,
            "ventilation_par_niveau": [{"niveau": "RDC", "scb_m2": 84.7}, {"niveau": "R+1", "scb_m2": 84.7},
                                       {"niveau": "R+2", "scb_m2": 84.7}, {"niveau": "Combles/retrait", "scb_m2": 50.8}]},
    "logements": {"nb_logements": 3, "surface_moyenne_shn_m2": 52.3, "scb_commerce_m2": 67.8, "type_zone": "Mixte",
                  "mix_detail": {"T1_studio": {"nb": 1, "shn_m2": 35}, "T2": {"nb": 1, "shn_m2": 52}, "T3": {"nb": 1, "shn_m2": 70}},
                  "plafonds": {"facteur_limitant": "surface"}},
    "parkings": {"auto_min": 7, "auto_max": 8, "velo": 5},
    "type_construction": {"type": "maison_mitoyenne_2_facades"},
    "mitoyennete_batie": {"n_batiments": 51, "n_murs_mitoyens_batis": 2, "edges": [
        {"label": "BC", "mur_mitoyen_bati": True, "overlap_bati_m": 16.4},
        {"label": "DA", "mur_mitoyen_bati": True, "overlap_bati_m": 10.7}]},
    "warnings": [{"code": "JUMELAGE_DETECTE_SANS_DROITE", "level": "info",
                  "message_fr": "Mitoyennete potentielle detectee : verifier le droit a batir en limite."}],
}
CTX = {"adresse": "5 rue de Mamer, Bertrange", "parcel_label": "Bertrange, Bertrange(A), 477 / 3433",
       "code_zone": "MIX-v", "nom_zone": "Quartier du centre villageois (QCV)",
       "regles": {"COS_max": None, "CSS_max": None, "Hauteur_corniche_max_m": 11, "Hauteur_faite_max_m": 16}}


def test_recul_avant_moteur():
    h = render_palladio_html(RESP_917, CTX["adresse"], CTX)
    assert "5.34" in h and "voisin" in h.lower()
    assert "avant 4m" not in h, "ne doit pas afficher le fallback 4 comme recul avant"
    print("OK recul avant moteur 5.34 (pas le fallback 4)")


def test_parite_9_etapes():
    h = render_palladio_html(RESP_917, CTX["adresse"], CTX)
    for t in ["On retrouve votre parcelle", "urbanisme de votre zone", "rue et le fond",
              "Mitoyenn", "poser le b", "surface de plancher",
              "Logements et stationnement", "Points de vigilance", "En r"]:
        assert t in h, f"section manquante : {t}"
    # schemas matplotlib (img) multiples + candidats + cotes
    assert h.count("schema-img") >= 6, "il manque des schemas (img matplotlib)"
    assert "score 24.93" in h and "retenu" in h, "candidats fond absents"
    assert "mitoyen" in h, "mitoyennete non rendue"
    assert "Gabarit au sol" in h, "cotes emprise absentes"
    print(f"OK parite : 9 etapes, {h.count('schema-img')} schemas img, candidats fond, cotes, mitoyennete")


def test_enveloppe_vide():
    h = render_palladio_html({"meta": {"enveloppe_vide": True}}, "X")
    assert "n'a pas abouti" in h
    print("OK enveloppe vide -> page erreur sans plantage")


if __name__ == "__main__":
    test_recul_avant_moteur()
    test_parite_9_etapes()
    test_enveloppe_vide()
    open("/tmp/palladio_sample.html", "w").write(render_palladio_html(RESP_917, CTX["adresse"], CTX))
    print("\nTOUS LES TESTS PASSENT. Echantillon : /tmp/palladio_sample.html")
