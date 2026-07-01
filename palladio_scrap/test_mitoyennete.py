"""
Test unitaire de l'application du recul 0 sur murs mitoyens (party_wall_idxs),
en particulier sur une LANIERE ETROITE ou le buffer lateral uniforme s'effondre.
Regression du 113 rue du Kiem. Geometrie pure, aucun appel reseau.
Lancer : python3 palladio_scrap/test_mitoyennete.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from palladio_engine import _compute_enveloppe_unique

# Laniere 7 m de large x 30 m de profond (maison de ville).
# Sommets CCW : edges 0=bas(voirie), 1=droite, 2=haut(fond), 3=gauche.
PTS = [[0.0, 0.0], [7.0, 0.0], [7.0, 30.0], [0.0, 30.0]]


def test_laniere_sans_party_effondre():
    # Lateral 4.5 des deux cotes sur 7 m de large -> buffer(-4.5) vide -> emprise nulle.
    env, _ = _compute_enveloppe_unique(PTS, 0, 2, ra=6.0, rl=4.5, rr=8.0, prof_max=14.0)
    assert env.is_empty or env.area < 1.0, env.area
    print("OK laniere sans mitoyennete -> emprise vide (attendu)")


def test_laniere_avec_party_reconstruit():
    # Memes reculs MAIS les deux longs cotes (idx 1 et 3) sont mitoyens -> recul 0.
    # Le buffer uniforme s'effondre quand meme, mais les bandes mitoyennes doivent
    # reconstruire l'enveloppe sur toute la largeur (bug 113 rue du Kiem).
    env, _ = _compute_enveloppe_unique(PTS, 0, 2, ra=6.0, rl=4.5, rr=8.0,
                                       prof_max=14.0, party_wall_idxs={1, 3})
    assert env.area > 1.0, env.area
    # Largeur ~7 m, profondeur bornee par prof_max (6..20) -> ~14 m => ~98 m2.
    assert 80.0 < env.area < 110.0, env.area
    print("OK laniere mitoyenne 2 cotes -> emprise reconstruite", round(env.area, 1), "m2")


def test_party_un_seul_cote():
    # Un seul cote mitoyen : latéral 0 a droite, 4.5 a gauche -> largeur 7-4.5=2.5 m.
    env, _ = _compute_enveloppe_unique(PTS, 0, 2, ra=6.0, rl=4.5, rr=8.0,
                                       prof_max=14.0, party_wall_idxs={1})
    assert env.area > 1.0, env.area
    print("OK laniere mitoyenne 1 cote -> emprise", round(env.area, 1), "m2")


if __name__ == "__main__":
    test_laniere_sans_party_effondre()
    test_laniere_avec_party_reconstruit()
    test_party_un_seul_cote()
    print("\nTOUS LES TESTS PASSENT.")
