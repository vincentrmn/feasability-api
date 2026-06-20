"""
PALLADIO RENDER — generation du HTML de resultat (sorti du node n8n de 39 Ko).

Objectif (roadmap point 8) : le rendu HTML vit desormais dans le repo, versionne et
testable, au lieu d'etre enterre dans un node n8n. Le node n8n n'aura plus qu'a
appeler un endpoint qui renvoie ce HTML.

`render_palladio_html(response, adresse)` prend la reponse de
/palladio/calcul/full (dict moteur) et renvoie une page HTML autonome.

IMPORTANT (corrige le bug d'affichage) : le recul avant affiche est lu sur la
reponse MOTEUR (`recul_avant_adaptatif.recul_m` / `reculs_appliques.avant_m`),
plus jamais sur le payload envoye. La methode de recul est explicitee.

Pur Python, aucune dependance reseau -> testable hors ligne (cf.
palladio_scrap/test_render.py).
"""
from typing import Dict, Any, List, Tuple, Optional
import html as _html


# ---------- helpers numeriques ----------

def _round(v, n=1):
    try:
        return round(float(v), n)
    except (TypeError, ValueError):
        return v


def _fmt(v, suffix="", dash="—"):
    if v is None or v == "":
        return dash
    return f"{v}{suffix}"


def _luref_ring(geom: Optional[Dict[str, Any]]) -> List[Tuple[float, float]]:
    if not geom or "coordinates" not in geom:
        return []
    ring = geom["coordinates"][0]
    pts = [(float(x), float(y)) for x, y in ring]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


# ---------- projection SVG (LUREF -> viewBox, y inverse) ----------

class _Proj:
    def __init__(self, all_pts: List[Tuple[float, float]], pad: float = 3.0, size: float = 100.0):
        xs = [p[0] for p in all_pts] or [0.0]
        ys = [p[1] for p in all_pts] or [0.0]
        self.minx, self.maxx = min(xs), max(xs)
        self.miny, self.maxy = min(ys), max(ys)
        w = max(self.maxx - self.minx, 1e-6)
        h = max(self.maxy - self.miny, 1e-6)
        self.scale = (size - 2 * pad) / max(w, h)
        self.pad = pad
        self.size = size
        self.w, self.h = w, h

    def x(self, x: float) -> float:
        return round(self.pad + (x - self.minx) * self.scale, 2)

    def y(self, y: float) -> float:
        # y cartographique vers le haut -> SVG vers le bas
        return round(self.pad + (self.maxy - y) * self.scale, 2)

    def pts(self, pts: List[Tuple[float, float]]) -> str:
        return " ".join(f"{self.x(px)},{self.y(py)}" for px, py in pts)


# ---------- SVG schema principal ----------

def _schema_svg(resp: Dict[str, Any]) -> str:
    parcelle = _luref_ring((resp.get("parcelle") or {}).get("geometry_luref"))
    emprise = _luref_ring((resp.get("emprise") or {}).get("geometry_luref"))
    if not parcelle:
        return '<p class="muted">Schema indisponible (geometrie manquante).</p>'

    voirie = resp.get("voirie") or {}
    fond = resp.get("fond") or {}
    idx_voirie = voirie.get("idx")
    idx_fond = fond.get("idx")
    traces = {t["idx"]: t for t in (resp.get("traces_reculs") or []) if "idx" in t}

    proj = _Proj(parcelle + emprise)
    n = len(parcelle)
    parts: List[str] = [f'<svg viewBox="0 0 {proj.size:.0f} {proj.size:.0f}" class="sch">']

    # parcelle
    parts.append(f'<polygon points="{proj.pts(parcelle)}" class="parcel"/>')

    # aretes colorees + cotes
    for i in range(n):
        a = parcelle[i]
        b = parcelle[(i + 1) % n]
        cls = "edge"
        if i == idx_voirie:
            cls = "edge-voirie"
        elif i == idx_fond:
            cls = "edge-fond"
        else:
            tr = traces.get(i)
            if tr and tr.get("mur_mitoyen_bati"):
                cls = "edge-mito"
        parts.append(
            f'<line x1="{proj.x(a[0])}" y1="{proj.y(a[1])}" '
            f'x2="{proj.x(b[0])}" y2="{proj.y(b[1])}" class="{cls}"/>')
        # label arete
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        parts.append(f'<text x="{proj.x(mx)}" y="{proj.y(my)}" class="lbl-edge">'
                     f'{_html.escape(chr(65 + i))}</text>')

    # enveloppe constructible
    if emprise:
        parts.append(f'<polygon points="{proj.pts(emprise)}" class="emprise"/>')

    parts.append('</svg>')
    return "".join(parts)


# ---------- recul avant : libelle lisible depuis la reponse MOTEUR ----------

def _recul_avant_label(resp: Dict[str, Any]) -> Tuple[str, str]:
    """Retourne (valeur_m, explication) en lisant la reponse moteur (jamais le payload)."""
    adapt = resp.get("recul_avant_adaptatif") or {}
    appliq = resp.get("reculs_appliques") or {}
    val = adapt.get("recul_m")
    if val is None:
        val = appliq.get("avant_m")
    val_r = _round(val, 2)
    t = adapt.get("type", "fixe")
    art = adapt.get("source_article")
    art_txt = f" (art. {art})" if art else ""
    if t == "alignement_voisins":
        if adapt.get("fallback_used"):
            expl = (f"Alignement sur les voisins : aucun voisin bati exploitable, "
                    f"repli sur le minimum reglementaire{art_txt}.")
        else:
            nb = adapt.get("n_voisins_utiles")
            expl = (f"Aligne sur la facade des {nb} construction(s) voisine(s) "
                    f"(mediane des reculs observes){art_txt}.")
    elif t == "lie_hauteur":
        coef = adapt.get("coef_hauteur")
        expl = f"Recul lie a la hauteur : {coef} x corniche, planche au minimum{art_txt}."
    else:
        expl = f"Recul fixe reglementaire{art_txt}."
    return (f"{val_r} m", expl)


# ---------- page complete ----------

def render_palladio_html(response: Dict[str, Any], adresse: str = "") -> str:
    resp = response or {}
    meta = resp.get("meta") or {}
    parcelle = resp.get("parcelle") or {}
    emprise = resp.get("emprise") or {}
    scb = resp.get("scb") or {}
    logements = resp.get("logements") or {}
    parkings = resp.get("parkings") or {}
    warnings = resp.get("warnings") or []
    appliq = resp.get("reculs_appliques") or {}

    if meta.get("enveloppe_vide"):
        body_kpi = ('<div class="kpi kpi-dark"><div class="lab">Resultat</div>'
                    '<div class="big">Non constructible</div>'
                    '<div class="sub">enveloppe nulle apres reculs</div></div>')
    else:
        body_kpi = (
            f'<div class="kpi kpi-dark"><div class="lab">Emprise constructible</div>'
            f'<div class="big">{_fmt(_round(emprise.get("surface_m2")), " m²")}</div>'
            f'<div class="sub">{_fmt(_round((emprise.get("ratio_vs_cadastrale") or 0)*100,0), " % du terrain")}</div></div>'
            f'<div class="kpi"><div class="lab">Logements</div>'
            f'<div class="big">{_fmt(logements.get("nb_logements"))}</div></div>'
            f'<div class="kpi"><div class="lab">Parkings</div>'
            f'<div class="big">{_fmt(parkings.get("auto_min"))}–{_fmt(parkings.get("auto_max"))}</div>'
            f'<div class="sub">+ {_fmt(parkings.get("velo"))} vélos</div></div>'
            f'<div class="kpi"><div class="lab">SCB totale</div>'
            f'<div class="big">{_fmt(_round(scb.get("scb_totale_m2")), " m²")}</div></div>')

    ra_val, ra_expl = _recul_avant_label(resp)
    lat = appliq.get("lateral_m")
    rr = appliq.get("arriere_m")

    reculs_html = (
        f'<div class="row"><span class="k">Recul avant</span>'
        f'<span class="v"><strong>{_html.escape(ra_val)}</strong> — {_html.escape(ra_expl)}</span></div>'
        f'<div class="row"><span class="k">Recul latéral</span>'
        f'<span class="v">{_fmt(_round(lat), " m")} '
        f'<span class="muted">(0 sur les murs mitoyens)</span></span></div>'
        f'<div class="row"><span class="k">Recul arrière</span>'
        f'<span class="v">{_fmt(_round(rr), " m")}</span></div>')

    warn_html = ""
    if warnings:
        items = "".join(
            f'<div class="warn warn-{_html.escape(w.get("level","info"))}">'
            f'<span class="wl">{_html.escape(w.get("level","info"))}</span>'
            f'<span class="wm">{_html.escape(w.get("message_fr",""))}</span></div>'
            for w in warnings)
        warn_html = f'<section class="card"><h2>Points d\'attention</h2>{items}</section>'

    zone = parcelle.get("id", "")
    adresse_h = _html.escape(adresse or "")
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Palladio — {adresse_h}</title><style>{_css()}</style></head>
<body><div class="wrap">
<header><h1>Étude de faisabilité</h1><div class="addr">{adresse_h}</div>
<div class="muted mono">parcelle {_html.escape(str(zone))} · {_fmt(_round(parcelle.get("surface_cadastrale_m2")), " m²")}</div></header>
<div class="kpis">{body_kpi}</div>
<section class="card"><h2>Enveloppe constructible</h2>
<div class="schema">{_schema_svg(resp)}</div>
<div class="legend"><span class="lg lg-voirie">rue</span><span class="lg lg-fond">fond</span>
<span class="lg lg-mito">mur mitoyen</span><span class="lg lg-emp">constructible</span></div>
</section>
<section class="card"><h2>Reculs appliqués</h2>{reculs_html}</section>
{warn_html}
<footer class="mono muted">Palladio {_html.escape(str(meta.get("version","")))} · estimation indicative — consulter un architecte</footer>
</div></body></html>"""


def _css() -> str:
    return (
        "*{box-sizing:border-box;margin:0;padding:0}"
        "body{font-family:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;"
        "color:#111;background:#fff;font-size:15px;line-height:1.5}"
        ".mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px}"
        ".muted{color:#888}"
        ".wrap{max-width:760px;margin:0 auto;padding:20px 16px 64px}"
        "header{padding-bottom:16px;border-bottom:1px solid #eee;margin-bottom:18px}"
        "h1{font-size:21px;font-weight:600;letter-spacing:-.01em}"
        ".addr{color:#555;font-size:14px;margin-top:2px}"
        ".kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px}"
        ".kpi{background:#f7f7f5;border-radius:12px;padding:14px 16px}"
        ".kpi-dark{background:#111;color:#fff}.kpi-dark .lab,.kpi-dark .sub{color:#bbb}"
        ".kpi .lab{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#888;margin-bottom:6px}"
        ".kpi .big{font-size:23px;font-weight:700;letter-spacing:-.02em}"
        ".kpi .sub{font-size:12px;color:#888;margin-top:3px}"
        ".card{border:1px solid #eee;border-radius:14px;padding:18px;margin-bottom:16px}"
        ".card h2{font-size:16px;font-weight:600;margin-bottom:12px}"
        ".schema{background:#fff}"
        ".sch{width:100%;height:auto;max-height:420px;display:block}"
        ".parcel{fill:#fafafa;stroke:#ccc;stroke-width:.4}"
        ".emprise{fill:#111;fill-opacity:.85;stroke:#000;stroke-width:.3}"
        ".edge{stroke:#ccc;stroke-width:.4;fill:none}"
        ".edge-voirie{stroke:#c00;stroke-width:.9;fill:none}"
        ".edge-fond{stroke:#2a7;stroke-width:.9;fill:none}"
        ".edge-mito{stroke:#e08a2e;stroke-width:1.4;fill:none}"
        ".lbl-edge{font-size:2.4px;fill:#999;text-anchor:middle;dominant-baseline:middle}"
        ".legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:10px;font-size:12px;color:#555}"
        ".lg{display:inline-flex;align-items:center;gap:5px}"
        ".lg::before{content:'';width:14px;height:3px;border-radius:2px;display:inline-block}"
        ".lg-voirie::before{background:#c00}.lg-fond::before{background:#2a7}"
        ".lg-mito::before{background:#e08a2e}.lg-emp::before{background:#111;height:10px;width:10px;border-radius:2px}"
        ".row{display:grid;grid-template-columns:130px 1fr;gap:12px;padding:9px 0;border-bottom:1px solid #f2f2f2}"
        ".row:last-child{border-bottom:0}.row .k{font-size:12px;text-transform:uppercase;letter-spacing:.03em;color:#888}"
        ".row .v{font-size:14px}"
        ".warn{display:flex;gap:10px;align-items:baseline;padding:8px 0;border-bottom:1px solid #f2f2f2}"
        ".warn:last-child{border-bottom:0}"
        ".wl{font-family:ui-monospace,monospace;font-size:10px;text-transform:uppercase;color:#fff;background:#888;padding:2px 6px;border-radius:3px}"
        ".warn-warning .wl{background:#e08a2e}.warn-critique .wl{background:#c00}.warn-info .wl{background:#789}"
        ".wm{font-size:13px;flex:1}"
        "footer{margin-top:32px;padding-top:16px;border-top:1px solid #eee;text-align:center}"
    )
