"""
Tests unitaires du recul avant adaptatif (Palladio Scrap).
Geometrie pure LUREF, aucun appel reseau. Lancer : python3 palladio_scrap/test_alignment.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shapely.geometry import Polygon
from palladio_engine import compute_recul_avant_effectif, alignment_band_ra

# Arete voirie le long de l'axe x ; parcelle au-dessus (centroid y>0).
P1, P2 = [0.0, 0.0], [10.0, 0.0]
CENTROID = (5.0, 5.0)

def approx(a, b, tol=1e-6): return abs(a - b) <= tol

def test_fixe():
    ra, j = compute_recul_avant_effectif({"type": "fixe", "min_m": 6, "max_m": 8,
                                          "source_article": "Art. X"}, P1, P2, CENTROID)
    assert approx(ra, 6.0), ra
    assert j["type"] == "fixe" and j["source_article"] == "Art. X"
    print("OK fixe -> 6.0")

def test_lie_hauteur():
    ra, j = compute_recul_avant_effectif({"type": "lie_hauteur", "coef_hauteur": 0.5,
                                          "plancher_m": 4.5}, P1, P2, CENTROID,
                                         corniche_effective_m=11.0)
    assert approx(ra, 5.5), ra          # max(0.5*11, 4.5) = 5.5
    ra2, _ = compute_recul_avant_effectif({"type": "lie_hauteur", "coef_hauteur": 0.5,
                                           "plancher_m": 4.5}, P1, P2, CENTROID,
                                          corniche_effective_m=8.0)
    assert approx(ra2, 4.5), ra2        # max(4.0, 4.5) = 4.5 (plancher)
    print("OK lie_hauteur -> 5.5 / plancher 4.5")

def test_alignement_deux_voisins():
    # Deux batiments voisins, facades avant a y=4 et y=6 -> moyenne 5.0
    g = Polygon([(11, 6), (20, 6), (20, 12), (11, 12)])   # front a y=6
    d = Polygon([(-9, 4), (-1, 4), (-1, 10), (-9, 10)])   # front a y=4
    ra, info = alignment_band_ra(P1, P2, [g, d], CENTROID, fallback_m=6.0)
    assert approx(ra, 5.0), (ra, info)
    assert info["n_voisins_utiles"] == 2 and not info["fallback_used"]
    print("OK alignement 2 voisins -> 5.0", info["fronts_m"])

def test_alignement_fallback():
    ra, info = alignment_band_ra(P1, P2, [], CENTROID, fallback_m=6.0)
    assert approx(ra, 6.0) and info["fallback_used"]
    # Via dispatch complet (aucun voisin fourni)
    ra2, j = compute_recul_avant_effectif({"type": "alignement_voisins", "fallback_m": 4,
                                           "source_article": "Art. 6.1.1"}, P1, P2, CENTROID,
                                          neighbor_polys_luref=[])
    assert approx(ra2, 4.0) and j["fallback_used"]
    print("OK alignement fallback -> 6.0 / 4.0")

def test_alignement_ignore_voisin_arriere():
    # Un batiment du mauvais cote (y negatif) doit etre ignore (cote rue)
    arriere = Polygon([(2, -8), (8, -8), (8, -2), (2, -2)])
    bon = Polygon([(11, 5), (20, 5), (20, 12), (11, 12)])  # front y=5
    ra, info = alignment_band_ra(P1, P2, [arriere, bon], CENTROID, fallback_m=6.0)
    assert approx(ra, 5.0), (ra, info)
    assert info["n_voisins_utiles"] == 1
    assert info["cote_droite_m"] == 5.0 and info["cote_gauche_m"] is None
    print("OK alignement ignore voisin cote rue -> 5.0")

def test_alignement_voisin_immediat_pas_mediane():
    # Cote droit : un voisin IMMEDIAT (front 5, proche du bord L=10) + un batiment
    # plus loin dans la rue mais dans la fenetre (front 9). L'ancienne mediane
    # aurait donne 7 ; on doit retenir le voisin immediat -> 5.0.
    adj = Polygon([(11, 5), (16, 5), (16, 10), (11, 10)])   # pc~13.5, front 5
    loin = Polygon([(17, 9), (21, 9), (21, 14), (17, 14)])  # pc~19, front 9
    ra, info = alignment_band_ra(P1, P2, [loin, adj], CENTROID, fallback_m=6.0)
    assert approx(ra, 5.0), (ra, info)
    assert info["n_voisins_utiles"] == 1 and info["cote_droite_m"] == 5.0
    assert info["fronts_m"] == [5.0, 9.0]          # les deux sont bien "vus"
    assert info["fronts_adjacent_m"] == [5.0]      # mais un seul retenu
    print("OK alignement voisin immediat (pas mediane) -> 5.0", info["fronts_m"])

def test_alignement_mitoyennete_prioritaire():
    # Voisin gauche ACCOLE (mur mitoyen sur le bord gauche de la parcelle, x=0),
    # front 8. Voisin droite DETACHE (maison d'angle), front 3. Sans regle on
    # moyennerait a 5.5 ; avec le mur mitoyen a gauche on s'aligne sur le gauche -> 8.0.
    g = Polygon([(-6, 8), (-0.1, 8), (-0.1, 16), (-6, 16)])   # accole au bord x=0, front 8
    d = Polygon([(11, 3), (18, 3), (18, 11), (11, 11)])       # detache a droite, front 3
    party = [((0.0, 0.0), (0.0, 30.0))]                        # mur mitoyen le long de x=0
    ra, info = alignment_band_ra(P1, P2, [g, d], CENTROID, fallback_m=6.0,
                                 party_wall_segments=party)
    assert approx(ra, 8.0), (ra, info)
    assert info["regle"] == "mitoyen_gauche"
    assert info["n_voisins_utiles"] == 1
    ecarte = [v for v in info["voisins"] if not v["retenu"]]
    assert any(v["motif"] == "ecarte_au_profit_du_voisin_mitoyen" for v in ecarte), info["voisins"]
    print("OK mitoyennete prioritaire -> 8.0 (gauche accole, droite ecarte)")

def test_alignement_deux_mitoyens_moyenne():
    # Les DEUX cotes accoles -> pas de priorite, on garde la moyenne (ordre contigu).
    g = Polygon([(-6, 6), (-0.1, 6), (-0.1, 14), (-6, 14)])
    d = Polygon([(10.1, 4), (16, 4), (16, 12), (10.1, 12)])
    party = [((0.0, 0.0), (0.0, 30.0)), ((10.0, 0.0), (10.0, 30.0))]
    ra, info = alignment_band_ra(P1, P2, [g, d], CENTROID, fallback_m=6.0,
                                 party_wall_segments=party)
    assert approx(ra, 5.0), (ra, info)          # (6+4)/2
    assert info["regle"] == "moyenne_voisins_immediats" and info["n_voisins_utiles"] == 2
    print("OK deux mitoyens -> moyenne 5.0")

def test_alignement_ecarte_maison_angle_autre_rue():
    # Cote droit : PAS de vrai voisin de rue, seulement une maison d'angle de l'autre
    # cote d'une rue perpendiculaire (separee lateralement du front par >5 m).
    # Cote gauche : un vrai voisin, front 6.
    # Sans la regle "hors rue" on moyennerait 6 et la facade laterale de l'angle (4)
    # -> 5.0. Avec la regle, l'angle est ecarte -> on ne garde que gauche -> 6.0.
    gauche = Polygon([(-6, 6), (-0.1, 6), (-0.1, 14), (-6, 14)])   # front 6, contigu
    angle = Polygon([(16, 4), (23, 4), (23, 12), (16, 12)])        # proj>=16, gap=6 -> hors rue
    ra, info = alignment_band_ra(P1, P2, [gauche, angle], CENTROID, fallback_m=6.0)
    assert approx(ra, 6.0), (ra, info)
    assert info["n_voisins_utiles"] == 1 and info["n_ecartes_hors_rue"] == 1
    hr = [v for v in info["voisins"] if v["hors_rue"]]
    assert hr and hr[0]["motif"] == "hors_alignement_rue", info["voisins"]
    print("OK maison d'angle autre rue ecartee -> 6.0 (gap", hr[0]["gap_lateral_m"], "m)")

if __name__ == "__main__":
    test_fixe(); test_lie_hauteur(); test_alignement_deux_voisins()
    test_alignement_fallback(); test_alignement_ignore_voisin_arriere()
    test_alignement_voisin_immediat_pas_mediane()
    test_alignement_mitoyennete_prioritaire()
    test_alignement_deux_mitoyens_moyenne()
    test_alignement_ecarte_maison_angle_autre_rue()
    print("\nTOUS LES TESTS PASSENT.")
