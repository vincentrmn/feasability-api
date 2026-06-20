"""
Test de contrat (roadmap point 11) — anti-regression de la classe de bug
"l'endpoint n'a pas transmis le parametre au moteur".

Verifie que CHAQUE parametre de calculer_palladio_full (hors self/geometrie de base)
est effectivement transmis dans main.py sous la forme `<param>=req.<...>`.
Si quelqu'un ajoute un parametre au moteur sans le cabler dans l'endpoint, ce test
casse. Lancer : python3 palladio_scrap/test_contract.py
"""
import os, sys, re, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from palladio_engine import calculer_palladio_full

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(ROOT, "main.py")

# Parametres toujours fournis par le modele de base (geometrie/reculs) — verifies
# implicitement, on se concentre sur ceux qui ont deja casse.
ALWAYS_OK = {"parcel_geometry_wgs84", "point_geocode_wgs84"}


def test_tous_les_params_moteur_sont_cables():
    params = [p for p in inspect.signature(calculer_palladio_full).parameters]
    src = open(MAIN, encoding="utf-8").read()
    manquants = []
    for p in params:
        if p in ALWAYS_OK:
            continue
        # le param doit etre transmis au moins une fois : "<param>=req."
        if not re.search(rf"\b{re.escape(p)}\s*=\s*req\.", src):
            manquants.append(p)
    assert not manquants, (
        "Parametres moteur non transmis par main.py (bug de contrat) : "
        + ", ".join(manquants))
    print(f"OK contrat : {len(params)} params moteur, tous cables dans main.py")


def test_routes_html_et_json_presentes():
    src = open(MAIN, encoding="utf-8").read()
    assert "/palladio/calcul/full\"" in src or "/palladio/calcul/full'" in src
    assert "/palladio/calcul/full/html" in src
    print("OK routes /full et /full/html presentes")


if __name__ == "__main__":
    test_tous_les_params_moteur_sont_cables()
    test_routes_html_et_json_presentes()
    print("\nTOUS LES TESTS DE CONTRAT PASSENT.")
