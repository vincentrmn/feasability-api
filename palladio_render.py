"""
PALLADIO RENDER — generation du HTML de resultat (sorti du node n8n de 39 Ko).

Roadmap point 8/9 : le rendu HTML vit dans le repo, versionne et testable. Le node
n8n n'appelle plus qu'un endpoint (/palladio/calcul/full/html) qui renvoie ce HTML.

`render_palladio_html(response, adresse)` prend la reponse de /palladio/calcul/full
(dict moteur) et renvoie une page HTML autonome, pedagogique.

IMPORTANT : le recul avant affiche est lu sur la reponse MOTEUR
(`recul_avant_adaptatif.recul_m` / `reculs_appliques.avant_m`), jamais sur le
payload. La methode de recul est explicitee.

Pur Python, aucune dependance reseau -> testable hors ligne (palladio_scrap/test_render.py).
"""
from typing import Dict, Any, List, Tuple, Optional
import math
import html as _html


# ---------- helpers ----------

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


def _centroid(pts: List[Tuple[float, float]]) -> Tuple[float, float]:
    if not pts:
        return (0.0, 0.0)
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _inward_normal(a, b, centroid) -> Tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    if (centroid[0] - mx) * nx + (centroid[1] - my) * ny < 0:
        nx, ny = -nx, -ny
    return (nx, ny)


# ---------- projection SVG (LUREF -> viewBox, y inverse) ----------

class _Proj:
    def __init__(self, all_pts, pad=4.0, size=100.0):
        xs = [p[0] for p in all_pts] or [0.0]
        ys = [p[1] for p in all_pts] or [0.0]
        self.minx, self.maxx = min(xs), max(xs)
        self.miny, self.maxy = min(ys), max(ys)
        w = max(self.maxx - self.minx, 1e-6)
        h = max(self.maxy - self.miny, 1e-6)
        self.scale = (size - 2 * pad) / max(w, h)
        self.pad, self.size = pad, size

    def x(self, x):
        return round(self.pad + (x - self.minx) * self.scale, 2)

    def y(self, y):
        return round(self.pad + (self.maxy - y) * self.scale, 2)

    def pts(self, pts):
        return " ".join(f"{self.x(px)},{self.y(py)}" for px, py in pts)


def _cote(proj, a, b, nin, dist, cls, lbl):
    """Ligne de cote parallele a l'arete (a,b), decalee de `dist` vers l'interieur."""
    if not dist or dist <= 0:
        return ""
    ax, ay = a[0] + nin[0] * dist, a[1] + nin[1] * dist
    bx, by = b[0] + nin[0] * dist, b[1] + nin[1] * dist
    mx, my = (ax + bx) / 2, (ay + by) / 2
    return (f'<line x1="{proj.x(ax)}" y1="{proj.y(ay)}" x2="{proj.x(bx)}" y2="{proj.y(by)}" '
            f'class="{cls}"/>'
            f'<text x="{proj.x(mx)}" y="{proj.y(my)}" class="lbl-cote {cls}-t">{_html.escape(lbl)}</text>')


def _schema_svg(resp: Dict[str, Any]) -> str:
    parcelle = _luref_ring((resp.get("parcelle") or {}).get("geometry_luref"))
    emprise = _luref_ring((resp.get("emprise") or {}).get("geometry_luref"))
    if not parcelle:
        return '<p class="muted">Schema indisponible (geometrie manquante).</p>'

    voirie = resp.get("voirie") or {}
    fond = resp.get("fond") or {}
    appliq = resp.get("reculs_appliques") or {}
    idx_voirie, idx_fond = voirie.get("idx"), fond.get("idx")
    traces = {t["idx"]: t for t in (resp.get("traces_reculs") or []) if "idx" in t}
    cen = _centroid(parcelle)
    proj = _Proj(parcelle + emprise)
    n = len(parcelle)
    out = [f'<svg viewBox="0 0 {proj.size:.0f} {proj.size:.0f}" class="sch">']
    out.append(f'<polygon points="{proj.pts(parcelle)}" class="parcel"/>')

    for i in range(n):
        a, b = parcelle[i], parcelle[(i + 1) % n]
        cls = "edge"
        if i == idx_voirie:
            cls = "edge-voirie"
        elif i == idx_fond:
            cls = "edge-fond"
        elif (traces.get(i) or {}).get("mur_mitoyen_bati"):
            cls = "edge-mito"
        out.append(f'<line x1="{proj.x(a[0])}" y1="{proj.y(a[1])}" '
                   f'x2="{proj.x(b[0])}" y2="{proj.y(b[1])}" class="{cls}"/>')
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        out.append(f'<text x="{proj.x(mx)}" y="{proj.y(my)}" class="lbl-edge">{chr(65 + i)}</text>')

    # cotes de recul avant / arriere (lignes paralleles a l'interieur)
    if idx_voirie is not None and idx_voirie < n:
        a, b = parcelle[idx_voirie], parcelle[(idx_voirie + 1) % n]
        ra = (resp.get("recul_avant_adaptatif") or {}).get("recul_m") or appliq.get("avant_m")
        out.append(_cote(proj, a, b, _inward_normal(a, b, cen), _round(ra, 1),
                         "cote-avant", f"avant {_round(ra,1)} m"))
    if idx_fond is not None and idx_fond < n:
        a, b = parcelle[idx_fond], parcelle[(idx_fond + 1) % n]
        rr = appliq.get("arriere_m")
        out.append(_cote(proj, a, b, _inward_normal(a, b, cen), _round(rr, 1),
                         "cote-arriere", f"arriere {_round(rr,1)} m"))

    if emprise:
        out.append(f'<polygon points="{proj.pts(emprise)}" class="emprise"/>')
    out.append('</svg>')
    return "".join(out)


def _recul_avant_label(resp: Dict[str, Any]) -> Tuple[str, str]:
    adapt = resp.get("recul_avant_adaptatif") or {}
    appliq = resp.get("reculs_appliques") or {}
    val = adapt.get("recul_m")
    if val is None:
        val = appliq.get("avant_m")
    t = adapt.get("type", "fixe")
    art = adapt.get("source_article")
    art_txt = f" (art. {art})" if art else ""
    if t == "alignement_voisins":
        if adapt.get("fallback_used"):
            expl = f"Alignement voisins : aucun voisin bâti exploitable, repli sur le minimum réglementaire{art_txt}."
        else:
            expl = f"Aligné sur la façade des {adapt.get('n_voisins_utiles')} voisin(s) (médiane des reculs){art_txt}."
    elif t == "lie_hauteur":
        expl = f"Recul lié à la hauteur : {adapt.get('coef_hauteur')} × corniche, planché au minimum{art_txt}."
    else:
        expl = f"Recul fixe réglementaire{art_txt}."
    return (f"{_round(val, 2)} m", expl)


def _section(title, inner):
    return f'<section class="card"><h2>{_html.escape(title)}</h2>{inner}</section>'


def _row(k, v):
    return f'<div class="row"><span class="k">{_html.escape(k)}</span><span class="v">{v}</span></div>'


def render_palladio_html(response: Dict[str, Any], adresse: str = "") -> str:
    resp = response or {}
    meta = resp.get("meta") or {}
    parcelle = resp.get("parcelle") or {}
    emprise = resp.get("emprise") or {}
    scb = resp.get("scb") or {}
    logements = resp.get("logements") or {}
    parkings = resp.get("parkings") or {}
    tc = resp.get("type_construction") or {}
    warnings = resp.get("warnings") or []
    appliq = resp.get("reculs_appliques") or {}
    adresse_h = _html.escape(adresse or "")

    # KPIs
    if meta.get("enveloppe_vide"):
        kpis = ('<div class="kpi kpi-dark"><div class="lab">Résultat</div>'
                '<div class="big">Non constructible</div><div class="sub">enveloppe nulle après reculs</div></div>')
    else:
        kpis = (
            f'<div class="kpi kpi-dark"><div class="lab">Emprise au sol</div>'
            f'<div class="big">{_fmt(_round(emprise.get("surface_m2")), " m²")}</div>'
            f'<div class="sub">{_fmt(_round((emprise.get("ratio_vs_cadastrale") or 0)*100,0), " % du terrain")}</div></div>'
            f'<div class="kpi"><div class="lab">SCB totale</div>'
            f'<div class="big">{_fmt(_round(scb.get("scb_totale_m2")), " m²")}</div></div>'
            f'<div class="kpi"><div class="lab">Logements</div>'
            f'<div class="big">{_fmt(logements.get("nb_logements"))}</div></div>'
            f'<div class="kpi"><div class="lab">Parkings</div>'
            f'<div class="big">{_fmt(parkings.get("auto_min"))}–{_fmt(parkings.get("auto_max"))}</div>'
            f'<div class="sub">+ {_fmt(parkings.get("velo"))} vélos</div></div>')

    # schema
    schema = (f'<div class="schema">{_schema_svg(resp)}</div>'
              '<div class="legend">'
              '<span class="lg lg-voirie">rue</span><span class="lg lg-fond">fond</span>'
              '<span class="lg lg-mito">mur mitoyen</span><span class="lg lg-emp">constructible</span></div>')

    # reculs
    ra_val, ra_expl = _recul_avant_label(resp)
    reculs = (_row("Recul avant", f'<strong>{_html.escape(ra_val)}</strong> — {_html.escape(ra_expl)}')
              + _row("Recul latéral", f'{_fmt(_round(appliq.get("lateral_m")), " m")} '
                     f'<span class="muted">(0 sur les murs mitoyens)</span>')
              + _row("Recul arrière", _fmt(_round(appliq.get("arriere_m")), " m"))
              + _row("Type d'implantation",
                     _html.escape(str(tc.get("type", "—")).replace("_", " "))))

    # constructibilite (ventilation SCB)
    vent = scb.get("ventilation_par_niveau") or []
    constr = ""
    if vent:
        rows = "".join(f'<tr><td>{_html.escape(str(v.get("niveau","")))}</td>'
                       f'<td>{_fmt(_round(v.get("scb_m2")), " m²")}</td></tr>' for v in vent)
        constr = (f'<table class="tbl"><thead><tr><th>Niveau</th><th>SCB</th></tr></thead>'
                  f'<tbody>{rows}</tbody></table>'
                  f'<div class="muted" style="margin-top:8px">Surface habitable estimée : '
                  f'{_fmt(_round(scb.get("surface_habitable_m2")), " m²")} · '
                  f'{_fmt(scb.get("niveaux_pleins"))} niveaux pleins'
                  f'{" + combles/retrait" if scb.get("combles") else ""}.</div>')

    # logements
    log_html = ""
    if logements.get("nb_logements"):
        mix = logements.get("mix_detail") or {}
        chips = "".join(f'<span class="chip">{_html.escape(k)} × {v.get("nb")}</span>'
                        for k, v in mix.items() if v.get("nb"))
        log_html = (_row("Nombre de logements", f'<strong>{logements.get("nb_logements")}</strong>')
                    + (_row("Répartition", chips) if chips else "")
                    + _row("Facteur limitant",
                           _html.escape(str((logements.get("plafonds") or {}).get("facteur_limitant", "—")))))

    # parkings
    park_html = (_row("Voitures", f'{_fmt(parkings.get("auto_min"))} à {_fmt(parkings.get("auto_max"))}')
                 + _row("Vélos", _fmt(parkings.get("velo")))
                 + _row("Surface sous-sol estimée", _fmt(_round(parkings.get("surface_sous_sol_estimee_m2")), " m²")))

    # warnings
    warn_html = ""
    if warnings:
        items = "".join(
            f'<div class="warn warn-{_html.escape(w.get("level","info"))}">'
            f'<span class="wl">{_html.escape(w.get("level","info"))}</span>'
            f'<span class="wm">{_html.escape(w.get("message_fr",""))}</span></div>' for w in warnings)
        warn_html = _section("Points d'attention", items)

    sections = _section("Enveloppe constructible", schema + reculs)
    if not meta.get("enveloppe_vide"):
        sections += _section("Surface construite brute (SCB)", constr)
        if log_html:
            sections += _section("Logements", log_html)
        sections += _section("Stationnement", park_html)
    sections += warn_html

    zone = _html.escape(str(parcelle.get("id", "")))
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Palladio — {adresse_h}</title><style>{_css()}</style></head>
<body><div class="wrap">
<header><h1>Étude de faisabilité</h1><div class="addr">{adresse_h}</div>
<div class="muted mono">parcelle {zone} · {_fmt(_round(parcelle.get("surface_cadastrale_m2")), " m²")}</div></header>
<div class="kpis">{kpis}</div>
{sections}
<footer class="mono muted">Palladio {_html.escape(str(meta.get("version","")))} · estimation indicative — consulter un architecte</footer>
</div></body></html>"""


def _css() -> str:
    return (
        "*{box-sizing:border-box;margin:0;padding:0}"
        "body{font-family:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:#111;background:#fff;font-size:15px;line-height:1.5}"
        ".mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px}.muted{color:#888}"
        ".wrap{max-width:760px;margin:0 auto;padding:20px 16px 64px}"
        "header{padding-bottom:16px;border-bottom:1px solid #eee;margin-bottom:18px}"
        "h1{font-size:21px;font-weight:600;letter-spacing:-.01em}.addr{color:#555;font-size:14px;margin-top:2px}"
        ".kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:18px}"
        ".kpi{background:#f7f7f5;border-radius:12px;padding:14px 16px}"
        ".kpi-dark{background:#111;color:#fff}.kpi-dark .lab,.kpi-dark .sub{color:#bbb}"
        ".kpi .lab{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#888;margin-bottom:6px}"
        ".kpi .big{font-size:22px;font-weight:700;letter-spacing:-.02em}.kpi .sub{font-size:12px;color:#888;margin-top:3px}"
        ".card{border:1px solid #eee;border-radius:14px;padding:18px;margin-bottom:16px}"
        ".card h2{font-size:16px;font-weight:600;margin-bottom:12px}"
        ".sch{width:100%;height:auto;max-height:440px;display:block}"
        ".parcel{fill:#fafafa;stroke:#ccc;stroke-width:.4}"
        ".emprise{fill:#111;fill-opacity:.82;stroke:#000;stroke-width:.3}"
        ".edge{stroke:#ccc;stroke-width:.4;fill:none}.edge-voirie{stroke:#c00;stroke-width:1;fill:none}"
        ".edge-fond{stroke:#2a7;stroke-width:1;fill:none}.edge-mito{stroke:#e08a2e;stroke-width:1.5;fill:none}"
        ".lbl-edge{font-size:2.4px;fill:#999;text-anchor:middle;dominant-baseline:middle}"
        ".cote-avant{stroke:#c00;stroke-width:.35;stroke-dasharray:1.2,1.2;fill:none}"
        ".cote-arriere{stroke:#2a7;stroke-width:.35;stroke-dasharray:1.2,1.2;fill:none}"
        ".lbl-cote{font-size:2.2px;font-weight:600;text-anchor:middle;dominant-baseline:middle}"
        ".cote-avant-t{fill:#c00}.cote-arriere-t{fill:#2a7}"
        ".legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:10px;font-size:12px;color:#555}"
        ".lg{display:inline-flex;align-items:center;gap:5px}.lg::before{content:'';width:14px;height:3px;border-radius:2px}"
        ".lg-voirie::before{background:#c00}.lg-fond::before{background:#2a7}.lg-mito::before{background:#e08a2e}"
        ".lg-emp::before{background:#111;height:10px;width:10px;border-radius:2px}"
        ".row{display:grid;grid-template-columns:140px 1fr;gap:12px;padding:9px 0;border-bottom:1px solid #f2f2f2}"
        ".row:last-child{border-bottom:0}.row .k{font-size:12px;text-transform:uppercase;letter-spacing:.03em;color:#888}.row .v{font-size:14px}"
        ".tbl{width:100%;border-collapse:collapse;font-size:14px}.tbl th{text-align:left;font-size:11px;text-transform:uppercase;color:#888;padding:6px 0;border-bottom:1px solid #eee}"
        ".tbl td{padding:7px 0;border-bottom:1px solid #f2f2f2}"
        ".chip{display:inline-block;background:#f0f0ee;border-radius:6px;padding:2px 8px;margin:2px 4px 2px 0;font-size:13px}"
        ".warn{display:flex;gap:10px;align-items:baseline;padding:8px 0;border-bottom:1px solid #f2f2f2}.warn:last-child{border-bottom:0}"
        ".wl{font-family:ui-monospace,monospace;font-size:10px;text-transform:uppercase;color:#fff;background:#888;padding:2px 6px;border-radius:3px}"
        ".warn-warning .wl{background:#e08a2e}.warn-critique .wl{background:#c00}.warn-info .wl{background:#789}.wm{font-size:13px;flex:1}"
        "footer{margin-top:32px;padding-top:16px;border-top:1px solid #eee;text-align:center}"
    )
