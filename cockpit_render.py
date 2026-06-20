"""
COCKPIT RENDER — page d'accueil Palladio (formulaire de recherche + tableau de bord
de couverture des communes), rendue cote serveur et versionnee/testable dans le repo.

C'est la page servie sur l'interface principale actuelle (webhook n8n GET
/webhook/palladio). Elle remplace l'ancien formulaire « nu » : meme formulaire
d'adresse + un cockpit qui montre, par commune, ce qui est pris en charge
(PAG / PAP QE / stationnement / velo / servitudes / PAP NQ), la qualite des
donnees (valide vs auto) et les trous restants. Pour que Jules et Jamie voient
l'avancement en un coup d'oeil.

Deux fonctions pures (aucun reseau, testables hors ligne) :
  compute_communes_status(zones, stationnement, velo, servitudes, pap_nq, communes_meta)
      -> liste ordonnee de dicts (un par commune) avec compteurs + couverture + statut.
  render_landing_html(communes_status, ...) -> HTML complet de la page d'accueil.

Les enregistrements attendus sont des dicts {nom_champ: valeur}, valeur pouvant etre
une string ou un objet singleSelect Airtable {"name": ...}. Le noeud n8n Airtable
renvoie les champs par nom ; on normalise les deux formes par securite. Tout est
optionnel : une table absente => couverture "—", jamais d'erreur.
"""
from typing import Dict, Any, List, Optional
import html as _h

CALCUL_URL = "https://n8n-production-8929d.up.railway.app/webhook/palladio/calcul"

# Nombre total de communes au Luxembourg (depuis les fusions de 2024). Sert au
# compteur "couvertes / total". A ajuster si une nouvelle fusion intervient.
TOTAL_COMMUNES_LU = 100


# ---------------- helpers ----------------

def _esc(s):
    return _h.escape(str(s)) if s is not None else ""


def _val(rec: Dict[str, Any], *keys):
    """Valeur d'un champ par nom, en gerant les objets singleSelect {name:..}
    et les listes d'objets. Renvoie une string nettoyee ('' si vide)."""
    for k in keys:
        if k in rec and rec[k] not in (None, ""):
            v = rec[k]
            if isinstance(v, dict):
                return str(v.get("name", "")).strip()
            if isinstance(v, list):
                names = [x.get("name", x) if isinstance(x, dict) else x for x in v]
                return ", ".join(str(n) for n in names if n).strip()
            return str(v).strip()
    return ""


def _commune_of(rec: Dict[str, Any]) -> str:
    # "Nom" : table Communes (meta) ; "Commune"/"commune" : toutes les autres tables.
    return _val(rec, "Commune", "commune", "Nom")


def _bucket_by_commune(records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for r in records or []:
        c = _commune_of(r)
        if not c:
            continue
        out.setdefault(c, []).append(r)
    return out


# ---------------- calcul du statut ----------------

def compute_communes_status(
    zones: Optional[List[Dict[str, Any]]] = None,
    stationnement: Optional[List[Dict[str, Any]]] = None,
    velo: Optional[List[Dict[str, Any]]] = None,
    servitudes: Optional[List[Dict[str, Any]]] = None,
    pap_nq: Optional[List[Dict[str, Any]]] = None,
    communes_meta: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Agrege l'etat de chaque commune a partir des tables Airtable."""
    zones_by = _bucket_by_commune(zones or [])
    stat_by = _bucket_by_commune(stationnement or [])
    velo_by = _bucket_by_commune(velo or [])
    serv_by = _bucket_by_commune(servitudes or [])
    nq_by = _bucket_by_commune(pap_nq or [])
    meta_by = {_commune_of(m): m for m in (communes_meta or [])}

    communes = set(zones_by) | set(stat_by) | set(velo_by) | set(serv_by) | set(nq_by) | set(meta_by)
    out = []
    for c in communes:
        if not c:
            continue
        zs = zones_by.get(c, [])
        n_zones = len(zs)
        # zones constructibles « dimensionnees » : recul lateral + arriere renseignes
        dimensionnees = [z for z in zs if _val(z, "Recul_lateral_min_m") and _val(z, "Recul_arriere_min_m")]
        n_dim = len(dimensionnees)
        n_valide = sum(1 for z in zs if _val(z, "Confiance").lower() == "valide")
        n_auto = sum(1 for z in zs if _val(z, "Confiance").lower() == "auto")
        methodes = sorted({_val(z, "Methode_recul_avant") for z in zs if _val(z, "Methode_recul_avant")})

        coverage = {
            "pag": n_zones > 0,
            "pap_qe": n_dim > 0,
            "stationnement": len(stat_by.get(c, [])) > 0,
            "velo": len(velo_by.get(c, [])) > 0,
            "servitudes": len(serv_by.get(c, [])) > 0,
            "pap_nq": len(nq_by.get(c, [])) > 0,
        }
        n_layers = sum(1 for v in coverage.values() if v)

        meta = meta_by.get(c, {})
        statut_extraction = _val(meta, "Statut_extraction")
        version_pag = _val(meta, "Version_PAG")
        date_pag = _val(meta, "Date_reglement_PAG")

        # statut global : valide (relu humain + couverture large) / auto (extrait) / partiel
        if n_valide > 0 and n_layers >= 4:
            statut = "valide"
        elif n_dim > 0:
            statut = "auto"
        else:
            statut = "partiel"

        out.append({
            "commune": c,
            "n_zones": n_zones,
            "n_dimensionnees": n_dim,
            "n_valide": n_valide,
            "n_auto": n_auto,
            "methodes": methodes,
            "coverage": coverage,
            "n_layers": n_layers,
            "statut": statut,
            "statut_extraction": statut_extraction,
            "version_pag": version_pag,
            "date_pag": date_pag,
        })

    # ordre : valide d'abord, puis par nb de zones decroissant, puis alpha
    rank = {"valide": 0, "auto": 1, "partiel": 2}
    out.sort(key=lambda s: (rank.get(s["statut"], 3), -s["n_zones"], s["commune"]))
    return out


# ---------------- rendu HTML ----------------

_LAYERS = [
    ("pag", "PAG", "Zonage (affectation des sols)"),
    ("pap_qe", "PAP QE", "Reculs, hauteurs, profondeur — quartier existant"),
    ("stationnement", "Stationnement", "Ratios de parking voiture (RBVS / Art. 10)"),
    ("velo", "Vélo", "Emplacements vélo réglementaires"),
    ("servitudes", "Servitudes", "Servitudes d'urbanisation et couloirs"),
    ("pap_nq", "PAP NQ", "Coefficients des nouveaux quartiers"),
]

_STATUT_LABEL = {
    "valide": ("Validé", "var(--green)"),
    "auto": ("Auto", "var(--amber)"),
    "partiel": ("Partiel", "var(--muted)"),
}


def _badge(ok: bool) -> str:
    if ok:
        return '<span class="cov cov-ok" title="Pris en charge">✓</span>'
    return '<span class="cov cov-no" title="Non couvert">—</span>'


def _commune_row(s: Dict[str, Any]) -> str:
    cov = s["coverage"]
    cells = "".join(
        f'<td class="cov-cell" data-label="{_esc(short)}">{_badge(cov[k])}</td>'
        for k, short, _ in _LAYERS)
    label, color = _STATUT_LABEL.get(s["statut"], (s["statut"], "var(--muted)"))
    conf_bits = []
    if s["n_valide"]:
        conf_bits.append(f'{s["n_valide"]} validé' + ("s" if s["n_valide"] > 1 else ""))
    if s["n_auto"]:
        conf_bits.append(f'{s["n_auto"]} auto')
    conf = " · ".join(conf_bits) if conf_bits else "—"
    methodes = ", ".join(s["methodes"]) if s["methodes"] else "—"
    return (
        '<tr>'
        f'<td class="c-name"><span class="c-dot" style="background:{color}"></span>{_esc(s["commune"])}'
        f'<div class="c-sub">{s["n_zones"]} zone(s) · recul avant : {_esc(methodes)}</div></td>'
        f'{cells}'
        f'<td class="c-conf" data-label="Confiance">{_esc(conf)}</td>'
        f'<td class="c-statut" data-label="Statut"><span class="pill" style="--pc:{color}">{_esc(label)}</span></td>'
        '</tr>'
    )


def render_landing_html(
    communes_status: List[Dict[str, Any]],
    calcul_url: str = CALCUL_URL,
    placeholder: str = "5 rue des Tilleuls, Strassen",
) -> str:
    cs = communes_status or []
    n_communes = len(cs)
    n_zones = sum(s["n_zones"] for s in cs)
    n_valide_communes = sum(1 for s in cs if s["statut"] == "valide")

    rows = "".join(_commune_row(s) for s in cs) or (
        '<tr><td colspan="9" class="empty">Aucune commune chargée.</td></tr>')

    head_cells = "".join(
        f'<th class="cov-cell" title="{_esc(desc)}">{_esc(short)}</th>'
        for _, short, desc in _LAYERS)

    legend = (
        '<div class="legend">'
        '<span><span class="cov cov-ok">✓</span> pris en charge</span>'
        '<span><span class="cov cov-no">—</span> non couvert</span>'
        '<span><span class="c-dot" style="background:var(--green)"></span> validé (relu)</span>'
        '<span><span class="c-dot" style="background:var(--amber)"></span> auto (extrait, à relire)</span>'
        '</div>')

    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Palladio — Étude de faisabilité</title>'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">'
        f'<style>{_styles()}</style></head><body>'
        '<div class="topbar"><div class="brand">Palladio</div>'
        '<div class="tag">moteur · interne</div></div>'
        '<main>'
        # --- formulaire (outil interne, pas de marketing) ---
        '<section class="hero">'
        '<label class="search-label" for="addr">Adresse au Luxembourg</label>'
        f'<form class="search" action="{_esc(calcul_url)}" method="get">'
        f'<input id="addr" type="text" name="address" placeholder="{_esc(placeholder)}" autocomplete="off" required>'
        '<button type="submit">Analyser</button>'
        '</form>'
        '</section>'
        # --- cockpit ---
        '<section class="cockpit">'
        '<div class="cock-head"><h2>Couverture réglementaire</h2>'
        '<div class="kpis">'
        f'<div class="kpi"><div class="kn">{n_communes}<span class="kn-tot"> / {TOTAL_COMMUNES_LU}</span></div><div class="kl">communes couvertes</div></div>'
        f'<div class="kpi"><div class="kn">{n_zones}</div><div class="kl">zones PAG</div></div>'
        f'<div class="kpi"><div class="kn">{n_valide_communes}</div><div class="kl">validées</div></div>'
        '</div></div>'
        '<div class="table-wrap"><table class="cock">'
        '<thead><tr><th class="c-name">Commune</th>'
        f'{head_cells}'
        '<th class="c-conf">Confiance</th><th class="c-statut">Statut</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div>'
        f'{legend}'
        '<p class="note">« Validé » = règlement relu par un humain, utilisable en production. '
        '« Auto » = extrait automatiquement du PAG/PAP, en attente de relecture. '
        'Le stationnement, les servitudes et les nouveaux quartiers (PAP NQ) sont '
        'progressivement ajoutés commune par commune.</p>'
        '</section>'
        '</main>'
        '<footer>Palladio · Terravalu · données cadastrales geoportail.lu · règles Airtable</footer>'
        '</body></html>'
    )


def _styles() -> str:
    return (
        ":root{--ink:#111;--muted:#777;--line:#e6e6e6;--soft:#f7f7f5;--amber:#e08a2e;--blue:#2962ff;--green:#2a7;--red:#c00}"
        "*{box-sizing:border-box;font-family:'Inter',sans-serif}"
        "body{margin:0;font-size:15px;line-height:1.55;color:var(--ink);background:#fff;-webkit-font-smoothing:antialiased}"
        ".topbar{position:sticky;top:0;z-index:10;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 20px;background:rgba(255,255,255,.92);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}"
        ".brand{font-weight:700;letter-spacing:-.01em}"
        ".tag{font-size:12px;color:var(--muted)}"
        "main{max-width:880px;margin:0 auto;padding:0 20px}"
        ".hero{padding:28px 0 24px;border-bottom:1px solid var(--line)}"
        ".search-label{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:8px}"
        ".search{display:flex;gap:10px;max-width:620px}"
        ".search input{flex:1;font-size:15px;padding:13px 15px;border:1px solid #ccc;border-radius:11px;outline:none}"
        ".search input:focus{border-color:var(--ink);box-shadow:0 0 0 3px rgba(17,17,17,.08)}"
        ".search button{font-size:15px;font-weight:600;color:#fff;background:var(--ink);border:0;border-radius:11px;padding:13px 22px;cursor:pointer}"
        ".search button:hover{background:#000}"
        ".cockpit{padding:26px 0 10px}"
        ".cock-head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:16px}"
        ".cock-head h2{font-size:18px;font-weight:600;margin:0}"
        ".kpis{display:flex;gap:10px;flex-wrap:wrap}"
        ".kpi{background:var(--soft);border-radius:11px;padding:10px 16px;text-align:center;min-width:78px}"
        ".kpi .kn{font-size:22px;font-weight:700;line-height:1.1}.kpi .kn-tot{font-size:15px;font-weight:600;color:var(--muted)}"
        ".kpi .kl{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}"
        ".table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:14px}"
        "table.cock{border-collapse:collapse;width:100%;font-size:14px}"
        "table.cock th,table.cock td{padding:11px 12px;text-align:center;border-bottom:1px solid #f0f0f0}"
        "table.cock thead th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:600;background:#fafafa}"
        "table.cock tbody tr:last-child td{border-bottom:0}"
        ".c-name{text-align:left!important;font-weight:600;min-width:170px}"
        ".c-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;vertical-align:middle}"
        ".c-sub{font-weight:400;font-size:12px;color:var(--muted);margin-top:2px}"
        ".cov{display:inline-block;font-weight:700;font-size:14px}.cov-ok{color:var(--green)}.cov-no{color:#ccc}"
        ".c-conf{font-size:12px;color:var(--muted);white-space:nowrap}"
        ".pill{display:inline-block;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--pc);border:1px solid var(--pc);border-radius:999px;padding:3px 10px}"
        ".empty{color:var(--muted);padding:24px!important}"
        ".legend{display:flex;flex-wrap:wrap;gap:16px;font-size:12px;color:var(--muted);margin:14px 2px 0}"
        ".legend span{display:inline-flex;align-items:center;gap:6px}"
        ".note{font-size:12px;color:var(--muted);line-height:1.5;margin:18px 0 0}"
        "footer{max-width:880px;margin:40px auto 0;padding:18px 20px 32px;border-top:1px solid var(--line);color:#999;font-size:12px}"
        # --- responsive : sur mobile, chaque ligne devient une carte (pas de scroll horizontal) ---
        "@media(max-width:640px){"
        ".table-wrap{overflow-x:visible;border:0;border-radius:0}"
        "table.cock thead{display:none}"
        "table.cock,table.cock tbody,table.cock tr,table.cock td{display:block;width:100%}"
        "table.cock tr{border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:12px}"
        "table.cock td{border:0;padding:6px 0;text-align:right;display:flex;align-items:center;justify-content:space-between;gap:12px}"
        "table.cock td.c-name{text-align:left;display:block;font-size:16px;padding:0 0 8px;margin-bottom:6px;border-bottom:1px solid #f0f0f0}"
        "table.cock td[data-label]::before{content:attr(data-label);color:var(--muted);font-size:13px;font-weight:500;text-align:left}"
        "}"
    )
