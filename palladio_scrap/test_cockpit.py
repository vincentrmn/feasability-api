"""
Test du cockpit (page d'accueil + couverture communes), sur un echantillon fidele
des donnees Airtable reelles (snapshot 2026-06-20). Hors reseau.

Lancer : python3 palladio_scrap/test_cockpit.py
Genere aussi /tmp/palladio_landing.html pour relecture visuelle.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cockpit_render import compute_communes_status, render_landing_html


def _zone(commune, code, regime="", conf="", methode="", lat="", arr=""):
    return {"Commune": commune, "Code_zone": code, "Regime": regime,
            "Confiance": conf, "Methode_recul_avant": methode,
            "Recul_lateral_min_m": lat, "Recul_arriere_min_m": arr}


# --- snapshot Zones_PAG (26 lignes) ---
ZONES = [
    # Strassen : 4 zones QE validees + zones vertes/speciales sans dimensions
    _zone("Strassen", "HAB-1", "QE", "valide", "fixe", "3", "10"),
    _zone("Strassen", "HAB-2", "QE", "valide", "fixe", "4.5", "12"),
    _zone("Strassen", "MIX-v", "QE", "valide", "fixe", "4.5", "12"),
    _zone("Strassen", "MIX-u", "QE", "valide", "fixe", "4.5", "12"),
    _zone("Strassen", "BEP", "", "", "", "3", ""),
    _zone("Strassen", "COM", "", "", "", "H corniche/2 (min 4m)", ""),
    _zone("Strassen", "SPEC-AD", "", "", "", "H corniche/2 (min 4m)", ""),
    _zone("Strassen", "ECO-c1", "", "", "", "H corniche/2 (min 4m)", ""),
    _zone("Strassen", "REC-tr", "", "", "", "H corniche/2", ""),
    _zone("Strassen", "REC-eq", "", "", "", "H corniche/2", ""),
    _zone("Strassen", "BEP-ep", "", "", "", "libre", ""),
    _zone("Strassen", "AGR"), _zone("Strassen", "PARC"), _zone("Strassen", "VERD"),
    _zone("Strassen", "FOR"), _zone("Strassen", "SPEC-H"), _zone("Strassen", "SPEC-B"),
    _zone("Strassen", "SPEC-COG"),
    # Bertrange : 4 zones auto
    _zone("Bertrange", "MIX-v", "QE", "auto", "alignement_voisins", "3", "10"),
    _zone("Bertrange", "HAB-1", "QE", "auto", "alignement_voisins", "3", "10"),
    _zone("Bertrange", "HAB-2", "QE", "auto", "alignement_voisins", "4.5", "10"),
    _zone("Bertrange", "MIX-u", "QE", "auto", "fixe", "4.5", "10"),
    # Mamer : 2 zones auto
    _zone("Mamer", "HAB-1", "QE", "auto", "alignement_voisins", "3", "10"),
    _zone("Mamer", "HAB-2", "QE", "auto", "alignement_voisins", "3", "10"),
    # Junglinster : 2 zones auto
    _zone("Junglinster", "MIX-v", "QE", "auto", "fixe", "3", "6"),
    _zone("Junglinster", "HAB-1", "QE", "auto", "fixe", "3", "9"),
]
STAT = [{"Commune": "Strassen"} for _ in range(9)]
VELO = [{"Commune": "Strassen"} for _ in range(9)]
SERV = [{"Commune": "Strassen"} for _ in range(12)]
NQ = [{"Commune": "Strassen"} for _ in range(7)]
META = [{"Commune": "Strassen", "Statut_extraction": "Complète",
         "Version_PAG": "Version coordonnée 30/01/2025", "Date_reglement_PAG": "2021-03-23"}]


def test_status():
    st = compute_communes_status(ZONES, STAT, VELO, SERV, NQ, META)
    by = {s["commune"]: s for s in st}
    assert set(by) == {"Strassen", "Bertrange", "Mamer", "Junglinster"}
    s = by["Strassen"]
    assert s["n_zones"] == 18
    assert s["n_valide"] == 4
    assert s["statut"] == "valide"
    assert all(s["coverage"].values()), s["coverage"]
    b = by["Bertrange"]
    assert b["n_zones"] == 4 and b["n_auto"] == 4 and b["statut"] == "auto"
    assert b["coverage"]["pag"] and b["coverage"]["pap_qe"]
    assert not b["coverage"]["stationnement"] and not b["coverage"]["pap_nq"]
    # ordre : Strassen (valide) en premier
    assert st[0]["commune"] == "Strassen"
    print("OK status :", ", ".join(f'{s["commune"]}({s["statut"]},{s["n_zones"]}z,{s["n_layers"]}/6)' for s in st))


def test_render_and_dump():
    st = compute_communes_status(ZONES, STAT, VELO, SERV, NQ, META)
    html = render_landing_html(st)
    assert "<form" in html and "address" in html
    assert "Strassen" in html and "Bertrange" in html
    assert "Couverture réglementaire" in html
    assert html.count("<tr>") >= 5
    open("/tmp/palladio_landing.html", "w", encoding="utf-8").write(html)
    print(f"OK render : {len(html)} caracteres -> /tmp/palladio_landing.html")


if __name__ == "__main__":
    test_status()
    test_render_and_dump()
    print("\nTOUS LES TESTS COCKPIT PASSENT.")
