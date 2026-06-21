"""
PALLADIO RENDER — page HTML pedagogique (portee depuis l'ancien node n8n de 39 Ko,
desormais versionnee et testable dans le repo). Roadmap point 8/9.

`render_palladio_html(response, adresse, contexte)` reproduit fidelement la page en
9 etapes + 8 schemas SVG de l'ancienne version :
  1 parcelle, 2 regles, 3 rue+fond (distances + candidats), 4 mitoyennete bati,
  5 placement (lateraux + cotes avant/arriere + emprise), 6 SCB, 7 logements+parking,
  8 vigilance, 9 resume.

CORRECTIF vs ancien node : le recul avant est lu sur la REPONSE MOTEUR
(recul_avant_adaptatif.recul_m / reculs_appliques.avant_m), plus sur le payload.

response = sortie /palladio/calcul/full. contexte = infos n8n non portees par le
moteur : { adresse, parcel_label, code_zone, nom_zone, regles{COS_max, CSS_max,
Hauteur_corniche_max_m, Hauteur_faite_max_m, DL_max_log_ha} }. Tout est optionnel
(degradation gracieuse). Pur Python, testable hors ligne.
"""
from typing import Dict, Any, List, Tuple, Optional
import math
import re
import html as _h
from datetime import datetime

# Génération PDF côté navigateur : capture le rendu écran (après le JS de mise en
# page des schémas) et télécharge un vrai fichier .pdf, sans boîte d'impression.
_HTML2PDF_CDN = "https://cdn.jsdelivr.net/npm/html2pdf.js@0.10.2/dist/html2pdf.bundle.min.js"


def _now_stamp() -> str:
    """Horodatage de generation (heure du Luxembourg si dispo, sinon locale).
    Sert le tampon "etude figee a l'instant t" affiche + exporte en PDF."""
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Europe/Luxembourg"))
    except Exception:
        now = datetime.now()
    return now.strftime("%d/%m/%Y à %H:%M")


def _pdf_js(filename: str) -> str:
    """Bouton "Télécharger en PDF" : html2pdf capture .wrap (le contenu, hors barre
    d'actions) APRES le rendu/JS des schemas et telecharge un vrai .pdf. Fallback
    sur l'impression navigateur si la lib CDN n'a pas charge."""
    fn = filename.replace("'", "")
    return (
        "<script>function palladioPdf(){"
        "var el=document.querySelector('.wrap');"
        "if(!el||typeof html2pdf==='undefined'){window.print();return;}"
        "var b=document.querySelector('.btn-pdf');"
        "if(b){b.disabled=true;b.dataset.t=b.textContent;b.textContent='Génération…';}"
        "function done(){if(b){b.disabled=false;b.textContent=b.dataset.t||'Télécharger en PDF';}}"
        "var opt={margin:[8,8,10,8],filename:'" + fn + "',"
        "image:{type:'jpeg',quality:0.96},"
        "html2canvas:{scale:2,useCORS:true,backgroundColor:'#ffffff',windowWidth:el.scrollWidth},"
        "jsPDF:{unit:'mm',format:'a4',orientation:'portrait'},"
        "pagebreak:{mode:['css','legacy'],avoid:['.section','.schema','.hero']}};"
        "html2pdf().set(opt).from(el).save().then(done).catch(function(){done();window.print();});"
        "}</script>"
    )


FORM_URL = "https://n8n-production-8929d.up.railway.app/webhook/palladio"

# Passe de de-collision des labels (cote navigateur) : mesure les vraies boites
# (getBBox) et ecarte verticalement les <text> qui se chevauchent, en restant dans
# le viewBox. Garantit qu'aucun nombre ne se superpose, sur tous les schemas.
_DECLUTTER_JS = """<script>
(function(){
 function dc(svg){
  var vb=svg.viewBox.baseVal, T=[].slice.call(svg.querySelectorAll('text'));
  if(T.length<2) return;
  var B=T.map(function(t){var k;try{k=t.getBBox();}catch(e){return null;}
    return {t:t,x:k.x,y:k.y,w:k.width,h:k.height,dy:0};}).filter(Boolean);
  var pad=0.5;
  function ov(a,b){var ay=a.y+a.dy,by=b.y+b.dy;
    return (Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x))>-pad
        && (Math.min(ay+a.h,by+b.h)-Math.max(ay,by))>-pad;}
  for(var it=0;it<120;it++){var moved=false;
   for(var i=0;i<B.length;i++)for(var j=i+1;j<B.length;j++){
     var a=B[i],b=B[j]; if(!ov(a,b))continue;
     var ay=a.y+a.dy,by=b.y+b.dy;
     var oy=Math.min(ay+a.h,by+b.h)-Math.max(ay,by);
     var p=(oy+pad)/2+0.05;
     if(ay+a.h/2<=by+b.h/2){a.dy-=p;b.dy+=p;}else{a.dy+=p;b.dy-=p;}
     moved=true;}
   if(!moved)break;}
  B.forEach(function(o){
    var y=o.y+o.dy;
    if(y<vb.y+0.3)o.dy=vb.y+0.3-o.y;
    if(y+o.h>vb.y+vb.height-0.3)o.dy=vb.y+vb.height-0.3-o.h-o.y;
    if(o.dy)o.t.setAttribute('transform','translate(0,'+o.dy.toFixed(2)+')');});
 }
 function run(){var s=document.querySelectorAll('svg.schema-svg');
   for(var i=0;i<s.length;i++){try{dc(s[i]);}catch(e){}}}
 if(document.readyState!=='loading')run();
 else document.addEventListener('DOMContentLoaded',run);
})();
</script>"""


# ---------------- helpers ----------------

def _f(v, dash="?"):
    """Entier formate (style fmt() de l'ancien node)."""
    try:
        return f"{round(float(v)):,}".replace(",", " ")
    except (TypeError, ValueError):
        return dash


def _n(v, nd=1, dash="?"):
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return dash


def _ring(geom):
    if not geom or "coordinates" not in geom:
        return []
    r = [(float(x), float(y)) for x, y in geom["coordinates"][0]]
    if len(r) > 1 and r[0] == r[-1]:
        r = r[:-1]
    return r


def _poly_area(pts):
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s / 2)


def _esc(s):
    return _h.escape(str(s)) if s is not None else ""


def _art_ref(arts, *keys):
    """Petite annotation d'article reglementaire ' (Art. X)' si dispo, sinon ''.
    Plusieurs cles possibles : la premiere renseignee gagne."""
    if not arts:
        return ""
    for k in keys:
        v = arts.get(k)
        if v:
            return f' <span class="art">({_esc(v)})</span>'
    return ""


# ---------------- rendu principal ----------------

def render_palladio_html(response: Dict[str, Any], adresse: str = "",
                         contexte: Optional[Dict[str, Any]] = None) -> str:
    resp = response or {}
    ctx = contexte or {}
    regles = ctx.get("regles") or {}
    meta = resp.get("meta") or {}

    if meta.get("enveloppe_vide") or not resp.get("emprise"):
        return _error_page(adresse, resp.get("meta", {}).get("error") or
                           "Enveloppe constructible nulle après application des reculs.")

    parcelle = resp.get("parcelle") or {}
    voirie = resp.get("voirie") or {}
    fond = resp.get("fond") or {}
    emprise = resp.get("emprise") or {}
    appliq = resp.get("reculs_appliques") or {}
    adapt = resp.get("recul_avant_adaptatif") or {}
    scb = resp.get("scb")
    lg = resp.get("logements")
    pk = resp.get("parkings")
    tc = resp.get("type_construction") or {}
    mito = resp.get("mitoyennete_batie")
    wn = resp.get("warnings") or []

    P = _ring(parcelle.get("geometry_luref"))
    E = _ring(emprise.get("geometry_luref"))
    pt = voirie.get("point_luref") or (P[0] if P else [0, 0])
    if not P:
        return _error_page(adresse, "Géométrie parcelle manquante.")

    # bbox + projection. On normalise vers un canvas fixe (~100 unites sur le grand
    # cote) avec marge proportionnelle : traits et textes restent nets et lisibles
    # quelle que soit la taille de la parcelle (correctif lisibilite schemas).
    xs = [p[0] for p in P] + [p[0] for p in E] + [pt[0]]
    ys = [p[1] for p in P] + [p[1] for p in E] + [pt[1]]
    rW, rH = (max(xs) - min(xs)), (max(ys) - min(ys))
    span = max(rW, rH) or 1
    margin = span * 0.10 + 1.5
    loff = span * 0.05 + 1.2  # deport des labels sommets (metres)
    doff = span * 0.045 + 1.0  # deport des cotes d'emprise (metres)
    xmin, xmax = min(xs) - margin, max(xs) + margin
    ymin, ymax = min(ys) - margin, max(ys) + margin
    W, H = xmax - xmin, ymax - ymin
    S = max(W, H) or 1
    F = 100.0 / S  # facteur metres -> unites canvas
    vb = f"0 0 {W * F:.2f} {H * F:.2f}"

    def px(x): return f"{(x - xmin) * F:.2f}"
    def py(y): return f"{(H - (y - ymin)) * F:.2f}"
    def p2svg(pts): return " ".join(f"{(x - xmin) * F:.2f},{(H - (y - ymin)) * F:.2f}" for x, y in pts)

    cx = sum(p[0] for p in P) / len(P)
    cy = sum(p[1] for p in P) / len(P)
    n = len(P)
    idxV = voirie.get("idx", 0)
    idxF = fond.get("idx", 0)

    # recul avant : LU SUR LE MOTEUR (correctif)
    ra = adapt.get("recul_m")
    if ra is None:
        ra = appliq.get("avant_m")
    ra = round(float(ra or 0), 2)
    raS = f"{ra:g}"
    rl = appliq.get("lateral_m") or 0
    rr = appliq.get("arriere_m") or 0
    profMax = appliq.get("profondeur_max_m")
    party = emprise.get("mitoyennete_batie_appliquee") or []

    def edge_off(idx, dist):
        a, b = P[idx], P[(idx + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1
        dx, dy = dx / L, dy / L
        nx, ny = -dy, dx
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        if nx * (cx - mx) + ny * (cy - my) < 0:
            nx, ny = -nx, -ny
        return ([a[0] + nx * dist, a[1] + ny * dist], [b[0] + nx * dist, b[1] + ny * dist])

    def edge_mid(idx):
        a, b = P[idx], P[(idx + 1) % n]
        return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]

    def edge_out(idx, dist):
        """Point au milieu de l'arete, deporte vers l'EXTERIEUR (loin du centroide)."""
        a, b = P[idx], P[(idx + 1) % n]
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L, dx / L
        if nx * (cx - mx) + ny * (cy - my) > 0:
            nx, ny = -nx, -ny
        return [mx + nx * dist, my + ny * dist]

    def dist_pt_seg(p0, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        if L2 < 1e-9:
            return math.hypot(p0[0] - a[0], p0[1] - a[1])
        t = max(0, min(1, ((p0[0] - a[0]) * dx + (p0[1] - a[1]) * dy) / L2))
        qx, qy = a[0] + t * dx, a[1] + t * dy
        return math.hypot(p0[0] - qx, p0[1] - qy)

    # labels sommets
    vlabels = ""
    for i, p in enumerate(P):
        ox, oy = p[0] - cx, p[1] - cy
        L = math.hypot(ox, oy) or 1
        lx, ly = p[0] + ox / L * loff, p[1] + oy / L * loff
        vlabels += f'<text x="{px(lx)}" y="{py(ly)}" class="lbl-vertex">{chr(65 + i)}</text>'
    vdots = "".join(f'<circle cx="{px(p[0])}" cy="{py(p[1])}" r="0.9" class="dot-vertex"/>' for p in P)
    ptgeo = f'<circle cx="{px(pt[0])}" cy="{py(pt[1])}" r="1.4" class="dot-geocode"/>'

    # --- schema 1 : parcelle ---
    schParcelle = (f'<svg viewBox="{vb}" class="schema-svg"><polygon points="{p2svg(P)}" class="parcel-fill"/>'
                   f'{vdots}{vlabels}{ptgeo}</svg>'
                   f'<div class="schema-caption">Polygone cadastral (LUREF), {n} sommets. Surface '
                   f'<strong>{_n(_poly_area(P))} m²</strong>. Le point bleu est l\'adresse géocodée.</div>')

    # --- schema 3a : voirie (distances + overlay cadastral) ---
    # On ne cote QUE la facade rue retenue (deportee a l'exterieur) : sur les parcelles
    # etroites/en drapeau, coter chaque arete rendait le schema illisible.
    ev = ""
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        cls = "edge-voirie-winner" if i == idxV else "edge-voirie-other"
        ev += f'<line x1="{px(a[0])}" y1="{py(a[1])}" x2="{px(b[0])}" y2="{py(b[1])}" class="{cls}"/>'
    ddw = dist_pt_seg(pt, P[idxV], P[(idxV + 1) % n])
    wlab = edge_out(idxV, loff)
    ev += f'<text x="{px(wlab[0])}" y="{py(wlab[1])}" class="lbl-edge-winner">rue {_n(ddw)}m</text>'
    overlay, cad_cap = "", ""
    det = voirie.get("detection") or {}
    ecs = det.get("edges_classified") or []
    if ecs:
        for ec in ecs:
            color = "#c9a961" if ec.get("is_voirie") else "#bbb"
            wdt = "1.4" if ec.get("is_voirie") else "0.5"
            overlay += (f'<line x1="{px(ec["p1"][0])}" y1="{py(ec["p1"][1])}" x2="{px(ec["p2"][0])}" '
                        f'y2="{py(ec["p2"][1])}" stroke="{color}" stroke-width="{wdt}" fill="none"/>')
        nbv = sum(1 for e in ecs if e.get("is_voirie"))
        tot = sum(e.get("length_m", 0) for e in ecs if e.get("is_voirie"))
        cad_cap = (f' Les arêtes en ambre touchent le domaine public : <strong>{nbv}</strong> sur '
                   f'{len(ecs)} ({_n(tot)} m de façade rue).')
    wmid = edge_mid(idxV)
    schVoirie = (f'<svg viewBox="{vb}" class="schema-svg"><polygon points="{p2svg(P)}" class="parcel-fill-light"/>'
                 f'{ev}{overlay}{vlabels}<line x1="{px(pt[0])}" y1="{py(pt[1])}" x2="{px(wmid[0])}" '
                 f'y2="{py(wmid[1])}" class="line-perp"/>{ptgeo}</svg>'
                 f'<div class="schema-caption">On repère la façade sur rue (la <em>voirie</em>) : '
                 f'arête <strong>{_esc(voirie.get("edge_label"))}</strong>, à {_n(ddw)} m de l\'adresse '
                 f'(trait bleu).{cad_cap}</div>')

    # --- schema 3b : candidats fond ---
    cands = fond.get("candidats") or []
    ccol = ["#222", "#555", "#888"]
    csvg = ""
    for k, c in enumerate(cands):
        a, b = P[c["idx_fond"]], P[(c["idx_fond"] + 1) % n]
        chosen = (c["idx_fond"] == idxF)
        stroke = "#000" if chosen else ccol[k % 3]
        wdt = "1.3" if chosen else "0.7"
        dash = "" if chosen else "1.6,1.6"
        csvg += (f'<line x1="{px(a[0])}" y1="{py(a[1])}" x2="{px(b[0])}" y2="{py(b[1])}" stroke="{stroke}" '
                 f'stroke-width="{wdt}" stroke-dasharray="{dash}" fill="none"/>')
    aW, bW = P[idxV], P[(idxV + 1) % n]
    vline = f'<line x1="{px(aW[0])}" y1="{py(aW[1])}" x2="{px(bW[0])}" y2="{py(bW[1])}" stroke="#c00" stroke-width="1.4" fill="none"/>'
    clegend = ""
    for c in cands:
        chosen = c["idx_fond"] == idxF
        rowcls = "cand-row cand-chosen" if chosen else "cand-row"
        pick = '<span class="cand-pick">retenu</span>' if chosen else ""
        clegend += (f'<div class="{rowcls}"><span class="cand-label">{_esc(c["fond_label"])}</span>'
                    f'<span class="cand-score">score {c.get("score_fond")}</span>'
                    f'<span class="cand-surf">{_n(c.get("surface_emprise_m2"))} m²</span>{pick}</div>')
    schFond = (f'<svg viewBox="{vb}" class="schema-svg"><polygon points="{p2svg(P)}" class="parcel-fill-light"/>'
               f'{csvg}{vline}{vlabels}</svg><div class="schema-caption">On teste les côtés candidats pour '
               f'le fond. <strong>{_esc(fond.get("edge_label"))}</strong> est retenu. La façade rue '
               f'{_esc(voirie.get("edge_label"))} est en rouge.</div><div class="cand-list">{clegend}</div>')

    # --- schema 4 : mitoyennete ---
    if mito and mito.get("edges"):
        me = ""
        for i in range(n):
            a, b = P[i], P[(i + 1) % n]
            isp = i in party
            isv = (i == idxV)
            color = "#e08a2e" if isp else ("#2962ff" if isv else "#ccc")
            wdt = "1.6" if isp else ("0.9" if isv else "0.45")
            lbl = ""
            if isp:
                m = edge_mid(i)
                lbl = f'<text x="{px(m[0])}" y="{py(m[1])}" class="lbl-mito">mur mitoyen</text>'
            me += f'<line x1="{px(a[0])}" y1="{py(a[1])}" x2="{px(b[0])}" y2="{py(b[1])}" stroke="{color}" stroke-width="{wdt}" fill="none"/>{lbl}'
        nmurs = mito.get("n_murs_mitoyens_batis", 0)
        det_m = ", ".join(f'{x.get("label")} ({x.get("overlap_bati_m")} m de mur)'
                          for x in mito["edges"] if x.get("mur_mitoyen_bati"))
        schMito = (f'<svg viewBox="{vb}" class="schema-svg"><polygon points="{p2svg(P)}" class="parcel-fill-light"/>'
                   f'{me}{vlabels}</svg><div class="schema-caption">{mito.get("n_batiments")} bâtiment(s) '
                   f'voisin(s) analysé(s). <strong>{nmurs}</strong> mur(s) mitoyen(s) bâti(s) détecté(s)'
                   f'{(" : " + det_m) if det_m else ""}. Les côtés en orange passent en recul 0.</div>')
    else:
        schMito = '<div class="schema-content"><div class="schema-caption">Détection de mitoyenneté bâtie indisponible pour cette parcelle.</div></div>'

    # --- schema 4bis : alignement sur les facades voisines (recul avant adaptatif) ---
    # Cadrage LOCAL (les batiments voisins debordent de la parcelle) : on ne touche
    # pas au viewBox partage des autres schemas.
    schAlign = ""
    if adapt.get("type") == "alignement_voisins":
        vz = adapt.get("voisins") or []
        axs = [p[0] for p in P]
        ays = [p[1] for p in P]
        for v in vz:
            for q in v.get("coords", []):
                axs.append(q[0]); ays.append(q[1])
        aspan = max(max(axs) - min(axs), max(ays) - min(ays)) or 1
        amg = aspan * 0.08 + 1.5
        axmin, aymin = min(axs) - amg, min(ays) - amg
        aWl = (max(axs) + amg) - axmin
        aHl = (max(ays) + amg) - aymin
        aF = 100.0 / (max(aWl, aHl) or 1)
        avb = f"0 0 {aWl * aF:.2f} {aHl * aF:.2f}"
        def apx(x): return f"{(x - axmin) * aF:.2f}"
        def apy(y): return f"{(aHl - (y - aymin)) * aF:.2f}"
        def ap2(pts): return " ".join(f"{(x - axmin) * aF:.2f},{(aHl - (y - aymin)) * aF:.2f}" for x, y in pts)
        nb = ""
        for v in vz:
            ret = v.get("retenu")
            col = "#e08a2e" if ret else "#cfcfcf"
            op = "0.5" if ret else "0.22"
            cd = v.get("coords") or []
            nb += f'<polygon points="{ap2(cd)}" fill="{col}" fill-opacity="{op}" stroke="{col}" stroke-width="0.5"/>'
            if ret and cd:
                cxv = sum(c[0] for c in cd) / len(cd)
                cyv = sum(c[1] for c in cd) / len(cd)
                nb += f'<text x="{apx(cxv)}" y="{apy(cyv)}" class="lbl-mito">{_esc(v.get("cote"))} {v.get("front_m")}m</text>'
        aWv, bWv = P[idxV], P[(idxV + 1) % n]
        al = edge_off(idxV, ra)
        alm = [(al[0][0] + al[1][0]) / 2, (al[0][1] + al[1][1]) / 2]
        nb += (f'<line x1="{apx(aWv[0])}" y1="{apy(aWv[1])}" x2="{apx(bWv[0])}" y2="{apy(bWv[1])}" class="edge-voirie-thick"/>'
               f'<line x1="{apx(al[0][0])}" y1="{apy(al[0][1])}" x2="{apx(al[1][0])}" y2="{apy(al[1][1])}" class="line-recul-avant"/>'
               f'<text x="{apx(alm[0])}" y="{apy(alm[1])}" class="lbl-recul-avant">aligné {raS}m</text>')
        g, d = adapt.get("cote_gauche_m"), adapt.get("cote_droite_m")
        if adapt.get("fallback_used"):
            cap = ("Aucun voisin bâti exploitable de part et d'autre : on retombe sur le "
                   f"<strong>minimum réglementaire {raS} m</strong>.")
        else:
            parts = []
            if g is not None: parts.append(f"gauche {g:g} m")
            if d is not None: parts.append(f"droite {d:g} m")
            cap = (f"Recul avant <em>aligné sur les voisins immédiats</em> ({', '.join(parts)}) → "
                   f"<strong>{raS} m</strong>. En orange : les façades voisines retenues ; en gris : les autres "
                   f"bâtiments vus mais écartés (2ᵉ rang, garages, angle).")
        schAlign = (f'<svg viewBox="{avb}" class="schema-svg"><polygon points="{ap2(P)}" class="parcel-fill-light"/>'
                    f'{nb}</svg><div class="schema-caption">{cap}</div>')

    # --- schema 5a : reculs lateraux ---
    lat = ""
    for i in range(n):
        if i == idxV or i == idxF:
            continue
        m = edge_mid(i)
        if i in party:
            a, b = P[i], P[(i + 1) % n]
            lat += f'<line x1="{px(a[0])}" y1="{py(a[1])}" x2="{px(b[0])}" y2="{py(b[1])}" class="edge-mitoyen"/>'
            lat += f'<text x="{px(m[0])}" y="{py(m[1])}" class="lbl-mito">mitoyen 0m</text>'
        else:
            o = edge_off(i, rl)
            om = [(o[0][0] + o[1][0]) / 2, (o[0][1] + o[1][1]) / 2]
            lat += f'<line x1="{px(o[0][0])}" y1="{py(o[0][1])}" x2="{px(o[1][0])}" y2="{py(o[1][1])}" class="line-recul-lateral"/>'
            lat += f'<text x="{px(om[0])}" y="{py(om[1])}" class="lbl-recul">{rl}m</text>'
    schLateral = (f'<svg viewBox="{vb}" class="schema-svg"><polygon points="{p2svg(P)}" class="parcel-fill-light"/>'
                  f'{lat}{vlabels}</svg><div class="schema-caption">Reculs latéraux : <strong>{rl} m</strong> '
                  f'de chaque côté{", sauf sur le(s) côté(s) mitoyen(s) en orange où le recul tombe à <strong>0</strong>" if party else ""}.</div>')

    # --- schema 5b : cotes avant / arriere / profondeur ---
    cA = edge_off(idxV, ra)
    cAr = edge_off(idxF, rr)
    mA = [(cA[0][0] + cA[1][0]) / 2, (cA[0][1] + cA[1][1]) / 2]
    mAr = [(cAr[0][0] + cAr[1][0]) / 2, (cAr[0][1] + cAr[1][1]) / 2]
    cProf = ""
    if profMax:
        cp = edge_off(idxV, ra + profMax)
        pm = [(cp[0][0] + cp[1][0]) / 2, (cp[0][1] + cp[1][1]) / 2]
        cProf = (f'<line x1="{px(cp[0][0])}" y1="{py(cp[0][1])}" x2="{px(cp[1][0])}" y2="{py(cp[1][1])}" class="line-recul-prof"/>'
                 f'<text x="{px(pm[0])}" y="{py(pm[1])}" class="lbl-recul-prof">prof max {raS}+{profMax}={round(ra+profMax,1)}m</text>')
    aF, bF = P[idxF], P[(idxF + 1) % n]
    schAvAr = (f'<svg viewBox="{vb}" class="schema-svg"><polygon points="{p2svg(P)}" class="parcel-fill-light"/>'
               f'<line x1="{px(aW[0])}" y1="{py(aW[1])}" x2="{px(bW[0])}" y2="{py(bW[1])}" class="edge-voirie-thick"/>'
               f'<line x1="{px(aF[0])}" y1="{py(aF[1])}" x2="{px(bF[0])}" y2="{py(bF[1])}" class="edge-fond-thick"/>'
               f'<line x1="{px(cA[0][0])}" y1="{py(cA[0][1])}" x2="{px(cA[1][0])}" y2="{py(cA[1][1])}" class="line-recul-avant"/>'
               f'<text x="{px(mA[0])}" y="{py(mA[1])}" class="lbl-recul-avant">avant {raS}m</text>'
               f'<line x1="{px(cAr[0][0])}" y1="{py(cAr[0][1])}" x2="{px(cAr[1][0])}" y2="{py(cAr[1][1])}" class="line-recul-arriere"/>'
               f'<text x="{px(mAr[0])}" y="{py(mAr[1])}" class="lbl-recul-arriere">arriere {rr}m</text>{cProf}{vlabels}</svg>'
               f'<div class="schema-caption">Recul avant de <strong>{raS} m</strong> depuis la rue '
               f'({_esc(voirie.get("edge_label"))}), recul arrière de <strong>{rr} m</strong> depuis le fond '
               f'({_esc(fond.get("edge_label"))})'
               f'{(", et profondeur bâtie limitée à " + str(round(ra+profMax,1)) + " m depuis la rue") if profMax else ""}.</div>')

    # --- schema 5c : emprise ---
    edims = ""
    ne = len(E)
    ecx = sum(q[0] for q in E) / ne if ne else 0
    ecy = sum(q[1] for q in E) / ne if ne else 0
    elens = []
    for i in range(ne):
        a, b = E[i], E[(i + 1) % ne]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1.5:
            continue
        elens.append(L)
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        dx, dy = b[0] - a[0], b[1] - a[1]
        Ln = math.hypot(dx, dy) or 1
        nx, ny = dy / Ln, -dx / Ln
        if nx * (mx - ecx) + ny * (my - ecy) < 0:
            nx, ny = -nx, -ny
        mx += nx * doff
        my += ny * doff
        edims += f'<text x="{px(mx)}" y="{py(my)}" class="lbl-dim">{_n(L)}m</text>'
    elens.sort(reverse=True)
    dimres = (f' Gabarit au sol : environ <strong>{_n(elens[0])} m × {_n(elens[1])} m</strong>.'
              if len(elens) >= 2 else "")
    schEmprise = (f'<svg viewBox="{vb}" class="schema-svg"><polygon points="{p2svg(P)}" class="parcel-fill-final"/>'
                  f'<polygon points="{p2svg(E)}" class="emprise-fill"/>{edims}{vlabels}</svg>'
                  f'<div class="schema-caption">La zone noire est l\'emprise constructible : '
                  f'<strong>{emprise.get("surface_m2")} m²</strong> sur un terrain de '
                  f'<strong>{_n(_poly_area(P))} m²</strong>, soit '
                  f'<strong>{_n((emprise.get("ratio_vs_cadastrale") or 0) * 100)}%</strong>.{dimres} '
                  f'Les cotes sont en mètres.</div>')

    # --- schema 6 : SCB ---
    schScb = ""
    if scb:
        rows = "".join(f'<div class="text-row"><span class="k">{_esc(v.get("niveau"))}</span>'
                       f'<span class="v mono">{v.get("scb_m2")} m²</span></div>'
                       for v in (scb.get("ventilation_par_niveau") or []))
        cus = scb.get("cus_applique")
        cusrow = (f'<div class="text-row"><span class="k">Plafond densité (CUS)</span>'
                  f'<span class="v">{cus.get("scb_max_cus_m2")} m² {"⚠ limitant" if cus.get("limitant") else "OK"}</span></div>'
                  if cus else "")
        schScb = (f'<div class="schema-content">{rows}'
                  f'<div class="text-row"><span class="k">SCB totale</span><span class="v"><strong>{scb.get("scb_totale_m2")} m²</strong></span></div>'
                  f'<div class="text-row"><span class="k">Surface habitable</span><span class="v">{scb.get("surface_habitable_m2")} m² (SCB × 0,80)</span></div>{cusrow}</div>')

    # --- schema 7 : logements + parkings ---
    schLog = ""
    if lg:
        mix = "".join(f'<div class="text-row"><span class="k">{_esc(t)}</span><span class="v">{m.get("nb")} × {m.get("shn_m2")} m² SHN</span></div>'
                      for t, m in (lg.get("mix_detail") or {}).items())
        pkrows = ""
        if pk:
            pkrows = (f'<div class="text-row"><span class="k">Parkings voiture</span><span class="v">{pk.get("auto_min")} à {pk.get("auto_max")}</span></div>'
                      f'<div class="text-row"><span class="k">Parkings vélo</span><span class="v">{pk.get("velo")}</span></div>')
        schLog = (f'<div class="schema-content"><div class="text-row"><span class="k">Logements</span>'
                  f'<span class="v"><strong>{lg.get("nb_logements")}</strong></span></div>{mix}'
                  f'<div class="text-row"><span class="k">Moyenne par logement</span><span class="v">{lg.get("surface_moyenne_shn_m2")} m² habitables</span></div>{pkrows}</div>')

    # --- schema 8 : warnings ---
    lvl = {"info": "#2962ff", "warning": "#c9a961", "critique": "#c00"}
    if wn:
        schWarn = '<div class="schema-content">' + "".join(
            f'<div class="warn-row"><span class="warn-lvl" style="background:{lvl.get(w.get("level"), "#888")}">{_esc(w.get("level"))}</span>'
            f'<span class="warn-code">{_esc(w.get("code"))}{(" (" + _esc(w.get("edge")) + ")") if w.get("edge") else ""}</span>'
            f'<span class="warn-msg">{_esc(w.get("message_fr"))}</span></div>' for w in wn) + '</div>'
    else:
        schWarn = '<div class="schema-content"><div class="schema-caption">Aucun point de vigilance.</div></div>'

    # ---------- textes ----------
    terrain = parcelle.get("surface_cadastrale_m2") or _poly_area(P)
    empM2 = emprise.get("surface_m2")
    ratioPct = _n((emprise.get("ratio_vs_cadastrale") or 0) * 100, 0)
    code_zone = ctx.get("code_zone") or (lg or {}).get("type_zone") or "?"
    nomZone = ctx.get("nom_zone") or ""
    parcel_label = ctx.get("parcel_label") or parcelle.get("id") or "?"
    cos = regles.get("COS_max") or regles.get("cos_max") or "?"
    css = regles.get("CSS_max") or regles.get("cus_max") or "?"
    hC = regles.get("Hauteur_corniche_max_m") or "?"
    hF = regles.get("Hauteur_faite_max_m") or "?"

    # references d'articles PAG/PAP (contexte n8n) : map granulaire + generaux
    arts = ctx.get("articles") or {}
    art_pag = ctx.get("article_pag")
    art_pap = ctx.get("article_pap_qe")
    # le recul avant adaptatif porte deja sa propre source d'article (moteur)
    if adapt.get("source_article") and not arts.get("reculs"):
        arts = dict(arts); arts["reculs"] = adapt.get("source_article")

    adapt_expl = ""
    if adapt.get("type") == "alignement_voisins":
        adapt_expl = (" Ce recul est <em>aligné sur les façades des voisins</em>"
                      if not adapt.get("fallback_used") else " (minimum réglementaire, faute de voisin bâti exploitable)")

    txtParcelle = (f"À partir de l'adresse <strong>{_esc(adresse)}</strong>, on identifie le terrain au "
                   f"cadastre : parcelle <strong>{_esc(parcel_label)}</strong>, d'une surface de "
                   f"<strong>{_f(terrain)} m²</strong>.")

    art_reculs = _art_ref(arts, "reculs")
    regLi = (f"<li>Recul avant (rue → maison) : <strong>{raS} m</strong>{adapt_expl}{art_reculs}</li>"
             f"<li>Reculs latéraux : <strong>{rl} m</strong>{art_reculs}</li>"
             f"<li>Recul arrière : <strong>{rr} m</strong>{_art_ref(arts, 'profondeur', 'reculs')}</li>")
    if scb:
        regLi += (f'<li>Hauteur : <strong>{scb.get("niveaux_pleins")} niveaux{" + combles" if scb.get("combles") else ""}</strong>'
                  f'{_art_ref(arts, "hauteurs")}</li>')
    if cos != "?":
        regLi += f"<li>COS (emprise au sol max) : <strong>{cos}</strong></li>"
    if css != "?":
        regLi += f"<li>CUS/CSS : <strong>{css}</strong></li>"
    # ligne sources : articles generaux PAG / PAP QE
    src_bits = []
    if art_pag:
        src_bits.append(f"PAG {_esc(art_pag)}")
    if art_pap:
        src_bits.append(f"PAP QE {_esc(art_pap)}")
    src_line = (f'<p class="sources">Sources réglementaires : {" · ".join(src_bits)}.</p>'
                if src_bits else "")
    txtRegles = (f"Votre terrain est classé en zone <strong>{_esc(code_zone)}</strong>"
                 f"{(' (' + _esc(nomZone) + ')') if nomZone else ''} au PAG (Plan d'Aménagement Général), "
                 f"le règlement communal. Voici ce qu'il impose ici :<ul>{regLi}</ul>{src_line}")

    txtRueFond = (f"On repère le côté sur rue (la <em>voirie</em>) et le fond. La façade sur rue est l'arête "
                  f"<strong>{_esc(voirie.get('edge_label'))}</strong>, détectée par adjacence cadastrale "
                  f"(quelles limites touchent le domaine public). Le fond retenu est "
                  f"<strong>{_esc(fond.get('edge_label'))}</strong>.")

    if mito and mito.get("edges"):
        txtMito = ("On regarde les bâtiments voisins. Quand une maison voisine est déjà collée à votre limite "
                   "(<em>mur mitoyen</em>), on peut bâtir contre cette limite sans recul.")
        if party:
            txtMito += (f" Ici, <strong>{len(party)} côté{'s' if len(party) > 1 else ''}</strong> concerné(s) : "
                        f"le recul latéral y passe à <strong>0</strong>, ce qui agrandit la surface constructible.")
        else:
            txtMito += " Ici, <strong>aucun mur mitoyen bâti</strong> : les reculs latéraux normaux s'appliquent."
        if tc.get("type"):
            txtMito += f' Type estimé : <strong>{_esc(str(tc["type"]).replace("_", " "))}</strong>.'
    else:
        txtMito = "Détection des murs mitoyens indisponible ; les reculs latéraux standards s'appliquent."

    txtAlign = ""
    if schAlign:
        if adapt.get("fallback_used"):
            txtAlign = ("Dans cette commune, le recul avant n'est pas un chiffre fixe : il doit "
                        "s'<em>aligner sur les constructions voisines</em>. Faute de voisin bâti exploitable ici, "
                        "on applique le minimum réglementaire.")
        else:
            txtAlign = ("Dans cette commune, le recul avant s'<em>aligne sur les façades des maisons voisines</em> "
                        "plutôt que sur un chiffre fixe. On mesure la façade du voisin immédiat de chaque côté de "
                        "la rue et on en retient la moyenne.")

    txtPlacement = (f"On part des <strong>{_f(terrain)} m²</strong> du terrain et on retire les bandes "
                    f"inconstructibles : {raS} m le long de la rue, {rl} m de chaque côté (sauf mitoyens), "
                    f"{rr} m au fond. L'emprise au sol constructible est de <strong>{_f(empM2)} m²</strong>, "
                    f"soit <strong>{ratioPct} %</strong> du terrain.")

    txtScb = ""
    if scb:
        txtScb = (f"On empile les niveaux autorisés. La somme des planchers est la <strong>SCB</strong> "
                  f"(Surface Construite Brute) : <strong>{scb.get('scb_totale_m2')} m²</strong> sur "
                  f"{scb.get('niveaux_pleins')} niveaux{' + combles' if scb.get('combles') else ''}."
                  f"{_art_ref(arts, 'bande', 'hauteurs')}")
        cus = scb.get("cus_applique")
        if cus and cus.get("limitant"):
            txtScb += f" Le plafond de densité (CUS) limite à <strong>{cus.get('scb_max_cus_m2')} m²</strong>."

    txtLog = ""
    if lg:
        if lg.get("nb_logements", 0) > 0:
            fl = {"surface": "la surface de plancher disponible", "densite": "la densité réglementaire",
                  "construction": "le plafond par construction"}.get((lg.get("plafonds") or {}).get("facteur_limitant"),
                                                                       "la limite la plus stricte")
            txtLog = (f"On retient la limite la plus stricte ({fl}), d'où "
                      f"<strong>{lg.get('nb_logements')} logement{'s' if lg.get('nb_logements') > 1 else ''}</strong>")
            if (lg.get("scb_commerce_m2") or 0) > 0:
                txtLog += " + un commerce en rez-de-chaussée (zone mixte)"
            txtLog += "." + _art_ref(arts, "logements")
        else:
            txtLog = "Cette zone n'autorise pas le logement (ou surface insuffisante) : <strong>aucun logement</strong>."
        if pk:
            txtLog += (f" Stationnement imposé : <strong>{pk.get('auto_min')} à {pk.get('auto_max')} places voiture</strong> "
                       f"et <strong>{pk.get('velo')} vélo(s)</strong>.")

    synth = f"Sur ce terrain de <strong>{_f(terrain)} m²</strong>, on peut bâtir une emprise au sol de <strong>{_f(empM2)} m²</strong>"
    if scb:
        synth += f", soit environ <strong>{_f(scb.get('scb_totale_m2'))} m²</strong> de plancher"
    if lg:
        synth += f", soit <strong>{lg.get('nb_logements')} logement{'s' if (lg.get('nb_logements') or 0) > 1 else ''}</strong>"
    if lg and (lg.get("scb_commerce_m2") or 0) > 0:
        synth += " + un commerce"
    if pk:
        synth += f", avec <strong>{pk.get('auto_min')}-{pk.get('auto_max')} places de parking</strong>"
    synth += "."

    # ---------- assemblage ----------
    def section(num, title, text, schema):
        text_html = f'<div class="section-text">{text}</div>' if text else ""
        schema_html = f'<div class="schema">{schema}</div>' if schema else ""
        return (f'<section class="section"><div class="section-head"><span class="section-num">{num}</span>'
                f'<span class="section-title">{_esc(title)}</span></div>{text_html}{schema_html}</section>')

    s = ""
    nn = 0
    nn += 1; s += section(nn, "On retrouve votre parcelle", txtParcelle, schParcelle)
    nn += 1; s += section(nn, "Les règles d'urbanisme de votre zone", txtRegles, "")
    nn += 1; s += section(nn, "On identifie la rue et le fond", txtRueFond, schVoirie + schFond)
    nn += 1; s += section(nn, "Mitoyenneté : les murs déjà accolés", txtMito, schMito)
    if schAlign:
        nn += 1; s += section(nn, "Alignement sur les façades voisines", txtAlign, schAlign)
    nn += 1; s += section(nn, "Où peut-on poser le bâtiment ?", txtPlacement, schLateral + schAvAr + schEmprise)
    if scb:
        nn += 1; s += section(nn, "Combien de surface de plancher ?", txtScb, schScb)
    if lg:
        nn += 1; s += section(nn, "Logements et stationnement", txtLog, schLog)
    if wn:
        nn += 1; s += section(nn, "Points de vigilance", "", schWarn)
    nn += 1; s += section(nn, "En résumé", synth, "")

    kpi_log = (f'<div class="kpi"><div class="label">Logements estimés</div><div class="value">{lg.get("nb_logements")}</div></div>'
               if lg else "")
    stamp = _now_stamp()
    ver = _esc(meta.get("version") or "")
    _slug = re.sub(r"[^a-zA-Z0-9]+", "_", (adresse or parcel_label or "etude")).strip("_").lower()[:50] or "etude"
    pdf_name = f"palladio_{_slug}.pdf"
    hero = (f'<div class="hero"><h1>{_esc(adresse)}</h1>'
            f'<div class="addr">Parcelle {_esc(parcel_label)} · zone {_esc(code_zone)}{(" · " + _esc(nomZone)) if nomZone else ""}</div>'
            f'<div class="gen">Étude générée le {stamp} · Palladio {ver}</div>'
            f'<div class="hero-grid">'
            f'<div class="kpi"><div class="label">Terrain</div><div class="value">{_f(terrain)} m²</div></div>'
            f'<div class="kpi"><div class="label">Règles (COS / CUS)</div><div class="value">{cos} / {css}</div>'
            f'<div class="sub">h. {hC}m / {hF}m</div></div>'
            f'<div class="kpi kpi-result"><div class="label">Emprise constructible</div>'
            f'<div class="value-big">{empM2} m²</div><div class="sub">{ratioPct}% du terrain</div></div>'
            f'{kpi_log}</div></div>')
    topbar = (f'<div class="topbar"><span class="brand">Palladio</span>'
              f'<span class="topbar-actions">'
              f'<button type="button" class="btn-pdf" onclick="palladioPdf()">Télécharger en PDF</button>'
              f'<a class="btn-home" href="{FORM_URL}">← Nouvelle recherche</a></span></div>')
    return (f'<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Palladio · {_esc(adresse)}</title>'
            f'<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">'
            f'<style>{_styles()}</style></head><body>{topbar}<div class="wrap">{hero}{s}'
            f'<a class="btn-home btn-home-bottom" href="{FORM_URL}">← Nouvelle recherche</a>'
            f'<footer class="footer"><span>Palladio engine {ver}</span>'
            f'<span>Étude générée le {stamp}</span></footer></div>'
            f'<script src="{_HTML2PDF_CDN}"></script>'
            f'{_pdf_js(pdf_name)}'
            f'{_DECLUTTER_JS}</body></html>')


def _error_page(adresse, msg):
    return (f'<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Palladio · erreur</title>'
            f'<style>body{{font-family:system-ui,sans-serif;max-width:760px;margin:0 auto;padding:32px 20px;color:#111}}'
            f'.err{{background:#fff5f5;border:1px solid #fcc;border-radius:10px;padding:20px;line-height:1.5}}</style></head>'
            f'<body><h1>Le calcul n\'a pas abouti</h1><div class="err"><strong>{_esc(msg)}</strong></div>'
            f'<p style="margin-top:20px"><a href="{FORM_URL}">← Nouvelle recherche</a></p></body></html>')


def _styles():
    return ("*{box-sizing:border-box;margin:0;padding:0}"
            ":root{--ink:#111;--muted:#777;--line:#e6e6e6;--soft:#f7f7f5;--amber:#e08a2e;--blue:#2962ff;--green:#2a7;--red:#c00}"
            "body{font-family:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;font-size:15px;line-height:1.55;color:var(--ink);background:#fff;-webkit-font-smoothing:antialiased}"
            ".mono{font-family:ui-monospace,'SF Mono',Menlo,Consolas,monospace;font-size:12px}"
            ".topbar{position:sticky;top:0;z-index:10;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 20px;background:rgba(255,255,255,.92);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}"
            ".topbar .brand{font-weight:700;font-size:17px;letter-spacing:-.01em}"
            ".btn-home{display:inline-flex;align-items:center;gap:6px;font-size:13px;font-weight:500;color:#fff;background:var(--ink);padding:9px 15px;border-radius:9px;text-decoration:none}"
            ".btn-home-bottom{margin:8px 0 0}.wrap{max-width:880px;margin:0 auto;padding:24px 20px 72px}"
            ".hero{padding:4px 0 22px;border-bottom:1px solid var(--line);margin-bottom:26px}"
            ".hero h1{font-size:22px;font-weight:600;letter-spacing:-.01em;margin-bottom:4px}.hero .addr{color:var(--muted);font-size:14px}"
            ".hero-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:14px;margin-top:20px}"
            ".kpi{background:var(--soft);border-radius:11px;padding:14px 16px}"
            ".kpi .label{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:6px}"
            ".kpi .value{font-size:16px;font-weight:600}.kpi .value-big{font-size:26px;font-weight:700;letter-spacing:-.02em}"
            ".kpi .sub{font-size:12px;color:var(--muted);margin-top:3px}.kpi-result{background:#111;color:#fff}.kpi-result .label,.kpi-result .sub{color:#bbb}"
            ".section{margin-bottom:20px;padding:20px;border:1px solid var(--line);border-radius:14px}"
            ".section-head{display:flex;gap:12px;align-items:center;margin-bottom:10px}"
            ".section-num{flex:0 0 26px;width:26px;height:26px;border-radius:50%;background:var(--ink);color:#fff;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:600}"
            ".section-title{font-size:16px;font-weight:600;letter-spacing:-.01em}"
            ".section-text{font-size:14px;color:#333;line-height:1.65}.section-text ul{margin:10px 0 2px 18px}.section-text li{margin:4px 0}"
            ".art{color:var(--muted);font-size:.85em;font-weight:400}.sources{font-size:12px;color:var(--muted);margin:10px 0 0}"
            ".schema{margin-top:16px}.schema-svg{width:100%;height:auto;max-height:440px;display:block;background:#fff;border:1px solid #f0f0f0;border-radius:8px}"
            ".schema-caption{font-size:13px;color:#555;margin-top:10px;line-height:1.55}.schema-content{padding:4px 0}"
            ".text-row{display:grid;grid-template-columns:minmax(120px,210px) 1fr;gap:12px;padding:9px 0;border-bottom:1px solid #f0f0f0}.text-row:last-child{border-bottom:0}"
            ".k{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}.v{font-size:14px}"
            ".cand-list{margin-top:12px;padding-top:12px;border-top:1px solid #f0f0f0;display:flex;flex-direction:column;gap:4px}"
            ".cand-row{display:grid;grid-template-columns:60px 90px 90px 1fr;gap:10px;padding:4px 0;font-size:13px}.cand-row.cand-chosen{font-weight:600}"
            ".cand-label{font-family:ui-monospace,monospace}.cand-score{color:#888;font-size:12px}.cand-pick{color:var(--green);font-size:12px;text-transform:uppercase}"
            ".warn-row{display:flex;gap:10px;align-items:baseline;padding:8px 0;border-bottom:1px solid #f0f0f0;flex-wrap:wrap}"
            ".warn-lvl{font-family:ui-monospace,monospace;font-size:11px;text-transform:uppercase;color:#fff;padding:2px 6px;border-radius:3px}"
            ".warn-code{font-family:ui-monospace,monospace;font-size:12px;color:#888}.warn-msg{font-size:13px;color:#111;flex:1;min-width:200px}"
            ".parcel-fill{fill:#fafafa;stroke:#111;stroke-width:0.5}.parcel-fill-light{fill:#fafafa;stroke:#bbb;stroke-width:0.45}.parcel-fill-final{fill:#f3f3f3;stroke:#888;stroke-width:0.45}"
            ".emprise-fill{fill:#111;fill-opacity:0.85;stroke:#000;stroke-width:0.5}.dot-vertex{fill:#111}.dot-geocode{fill:#2962ff}"
            ".lbl-vertex{font-size:4.2px;font-weight:700;fill:#111;text-anchor:middle;dominant-baseline:middle;paint-order:stroke;stroke:#fff;stroke-width:1;stroke-linejoin:round}"
            ".edge-voirie-other{stroke:#ccc;stroke-width:0.5;fill:none}.edge-voirie-winner{stroke:#c00;stroke-width:1.2;fill:none}"
            ".lbl-edge{font-size:3.4px;fill:#777;text-anchor:middle;dominant-baseline:middle;paint-order:stroke;stroke:#fff;stroke-width:0.9;stroke-linejoin:round}.lbl-edge-winner{font-size:3.9px;fill:#c00;font-weight:700;text-anchor:middle;dominant-baseline:middle;paint-order:stroke;stroke:#fff;stroke-width:1;stroke-linejoin:round}"
            ".line-perp{stroke:#2962ff;stroke-width:0.5;stroke-dasharray:1.6,1.6;fill:none}.line-recul-lateral{stroke:#555;stroke-width:0.6;stroke-dasharray:1.8,1.8;fill:none}"
            ".edge-mitoyen{stroke:#e08a2e;stroke-width:1.7;fill:none}.lbl-mito{font-size:3.4px;fill:#e08a2e;font-weight:700;text-anchor:middle;dominant-baseline:middle;paint-order:stroke;stroke:#fff;stroke-width:1;stroke-linejoin:round}"
            ".lbl-recul{font-size:3.2px;fill:#555;text-anchor:middle;dominant-baseline:middle;paint-order:stroke;stroke:#fff;stroke-width:0.9;stroke-linejoin:round}"
            ".lbl-dim{font-size:3.7px;font-weight:700;fill:#fff;paint-order:stroke;stroke:#111;stroke-width:1.1px;text-anchor:middle;dominant-baseline:middle}"
            ".edge-voirie-thick{stroke:#c00;stroke-width:1.2;fill:none}.edge-fond-thick{stroke:#2a7;stroke-width:1.2;fill:none}"
            ".line-recul-avant{stroke:#c00;stroke-width:0.6;stroke-dasharray:1.8,1.8;fill:none}.line-recul-arriere{stroke:#2a7;stroke-width:0.6;stroke-dasharray:1.8,1.8;fill:none}.line-recul-prof{stroke:#84c;stroke-width:0.55;stroke-dasharray:1,1;fill:none}"
            ".lbl-recul-avant{font-size:3.3px;fill:#c00;font-weight:700;text-anchor:middle;dominant-baseline:middle;paint-order:stroke;stroke:#fff;stroke-width:1;stroke-linejoin:round}.lbl-recul-arriere{font-size:3.3px;fill:#2a7;font-weight:700;text-anchor:middle;dominant-baseline:middle;paint-order:stroke;stroke:#fff;stroke-width:1;stroke-linejoin:round}.lbl-recul-prof{font-size:3px;fill:#84c;font-weight:700;text-anchor:middle;dominant-baseline:middle;paint-order:stroke;stroke:#fff;stroke-width:0.9;stroke-linejoin:round}"
            ".footer{margin-top:48px;padding-top:20px;border-top:1px solid var(--line);display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;color:#999;font-size:12px;font-family:ui-monospace,monospace}"
            ".gen{font-size:12px;color:var(--muted);margin-top:4px}"
            ".topbar-actions{display:flex;align-items:center;gap:10px}"
            ".btn-pdf{display:inline-flex;align-items:center;gap:6px;font-size:13px;font-weight:600;color:var(--ink);background:#fff;border:1px solid var(--ink);padding:8px 14px;border-radius:9px;cursor:pointer;font-family:inherit}"
            ".btn-pdf:hover{background:var(--soft)}"
            "@media(max-width:600px){.wrap{padding:18px 14px 60px}.section{padding:16px 14px}.text-row{grid-template-columns:1fr;gap:2px}.hero h1{font-size:20px}.kpi .value-big{font-size:23px}}"
            # --- impression / export PDF : on cache la barre d'actions et les boutons,
            # on neutralise le sticky, et on evite de couper schemas/sections en deux ---
            "@media print{"
            ".topbar{position:static;border-bottom:1px solid var(--line)}"
            ".topbar-actions,.btn-home,.btn-home-bottom{display:none!important}"
            ".wrap{max-width:none;padding:0 6mm}"
            ".section{break-inside:avoid;page-break-inside:avoid;border-color:#ddd}"
            ".schema-svg{break-inside:avoid;max-height:none}"
            ".hero{break-inside:avoid}"
            "a[href]:after{content:''}"
            "body{-webkit-print-color-adjust:exact;print-color-adjust:exact}"
            "}")
