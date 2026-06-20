"""
PALLADIO SCHEMAS — rendu des schémas géométriques en matplotlib (PNG base64 inline).

Remplace les SVG faits main (illisibles sur parcelles atypiques : drapeau, angle).
matplotlib gère l'échelle (aspect égal), et on place les cotes dans les espaces
vides → aucun chevauchement. Chaque fonction renvoie une balise <img> data-URI.

Backend Agg (pas d'affichage). Pur calcul, testable hors ligne (on peut relire le PNG).
"""
import io
import base64
import math
from typing import List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPoly

INK = "#111"
MUTED = "#777"
AMBER = "#e08a2e"
RED = "#c00"
GREEN = "#2a7"
BLUE = "#2962ff"

_FS = 12  # taille de police de base (points)


def _img(fig, tight=True) -> str:
    buf = io.BytesIO()
    kw = dict(format="png", dpi=140, facecolor="white")
    if tight:
        kw.update(bbox_inches="tight", pad_inches=0.06)
    fig.savefig(buf, **kw)
    plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f'<img class="schema-img" alt="schéma" src="data:image/png;base64,{b64}"/>'


def _new(w=6.4, h=4.2):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_aspect("equal")
    ax.axis("off")
    return fig, ax


def _centroid(P):
    return (sum(p[0] for p in P) / len(P), sum(p[1] for p in P) / len(P))


def _draw_parcel(ax, P, fc="#fafafa", ec=INK, lw=1.6, z=1):
    ax.add_patch(MplPoly(P, closed=True, facecolor=fc, edgecolor=ec, lw=lw, zorder=z))


def _vertex_labels(ax, P, span):
    cx, cy = _centroid(P)
    off = span * 0.045 + 0.8
    for i, p in enumerate(P):
        ox, oy = p[0] - cx, p[1] - cy
        L = math.hypot(ox, oy) or 1
        ax.text(p[0] + ox / L * off, p[1] + oy / L * off, chr(65 + i),
                fontsize=_FS, fontweight="bold", color=INK,
                ha="center", va="center", zorder=8)
        ax.plot([p[0]], [p[1]], "o", ms=3, color=INK, zorder=7)


def _span(P, extra=None):
    xs = [p[0] for p in P] + ([q[0] for q in extra] if extra else [])
    ys = [p[1] for p in P] + ([q[1] for q in extra] if extra else [])
    return max(max(xs) - min(xs), max(ys) - min(ys)) or 1


def _fit(ax, P, extra=None, frac=0.08):
    xs = [p[0] for p in P] + ([q[0] for q in extra] if extra else [])
    ys = [p[1] for p in P] + ([q[1] for q in extra] if extra else [])
    m = max(max(xs) - min(xs), max(ys) - min(ys)) * frac + 1.0
    ax.set_xlim(min(xs) - m, max(xs) + m)
    ax.set_ylim(min(ys) - m, max(ys) + m)


def _edge(P, i):
    return P[i], P[(i + 1) % len(P)]


def _emid(P, i):
    a, b = _edge(P, i)
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _inward_normal(P, i):
    """Normale unitaire de l'arête i pointant vers l'intérieur du polygone."""
    a, b = _edge(P, i)
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1
    nx, ny = -dy / L, dx / L
    cx, cy = _centroid(P)
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    if nx * (cx - mx) + ny * (cy - my) < 0:
        nx, ny = -nx, -ny
    return nx, ny


# ---------------- figures ----------------

def fig_parcelle(P, pt=None) -> str:
    fig, ax = _new()
    _draw_parcel(ax, P)
    if pt:
        ax.plot([pt[0]], [pt[1]], "o", ms=7, color=BLUE, zorder=9)
    _vertex_labels(ax, P, _span(P, [pt] if pt else None))
    _fit(ax, P, [pt] if pt else None)
    return _img(fig)


def fig_overview(P, E, pt=None, idxV=None) -> str:
    """Plan d'ensemble épuré : parcelle + zone constructible (emprise) + façade rue.
    Pas de lettres de sommets : lisible même sur parcelle en lanière/drapeau."""
    fig, ax = _new(6.0, 4.4)
    _draw_parcel(ax, P, fc="#f4f4f2", ec="#999", lw=1.2)
    if E:
        ax.add_patch(MplPoly(E, closed=True, facecolor=INK, edgecolor="#000",
                             lw=1.0, alpha=0.85, zorder=3))
    if idxV is not None:
        a, b = _edge(P, idxV)
        ax.plot([a[0], b[0]], [a[1], b[1]], color=RED, lw=4, zorder=4, solid_capstyle="round")
    if pt:
        ax.plot([pt[0]], [pt[1]], "o", ms=7, color=BLUE, zorder=9)
    _fit(ax, P, [pt] if pt else None)
    return _img(fig)


def fig_voirie(P, pt, idxV, edges_classified=None) -> str:
    fig, ax = _new()
    _draw_parcel(ax, P, fc="#fafafa", ec="#bbb", lw=1.0)
    # arêtes classées (ambre = touche le domaine public)
    if edges_classified:
        for ec in edges_classified:
            p1, p2 = ec.get("p1"), ec.get("p2")
            if not p1 or not p2:
                continue
            col = AMBER if ec.get("is_voirie") else "#ccc"
            w = 4 if ec.get("is_voirie") else 1.2
            ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color=col, lw=w, zorder=3,
                    solid_capstyle="round")
    # façade rue retenue en rouge épais
    a, b = _edge(P, idxV)
    ax.plot([a[0], b[0]], [a[1], b[1]], color=RED, lw=4, zorder=4, solid_capstyle="round")
    extra = [pt]
    if pt:
        m = _emid(P, idxV)
        ax.plot([pt[0], m[0]], [pt[1], m[1]], color=BLUE, lw=1.3, ls=(0, (3, 3)), zorder=5)
        ax.plot([pt[0]], [pt[1]], "o", ms=7, color=BLUE, zorder=9)
    _vertex_labels(ax, P, _span(P, extra))
    _fit(ax, P, extra)
    return _img(fig)


def fig_fond(P, idxV, idxF, candidats=None) -> str:
    fig, ax = _new()
    _draw_parcel(ax, P, fc="#fafafa", ec="#bbb", lw=1.0)
    for c in (candidats or []):
        i = c.get("idx_fond")
        if i is None:
            continue
        a, b = _edge(P, i)
        chosen = (i == idxF)
        ax.plot([a[0], b[0]], [a[1], b[1]], color=(GREEN if chosen else "#999"),
                lw=(4 if chosen else 1.6), ls=("solid" if chosen else (0, (4, 3))),
                zorder=4, solid_capstyle="round")
    av, bv = _edge(P, idxV)
    ax.plot([av[0], bv[0]], [av[1], bv[1]], color=RED, lw=3.5, zorder=3, solid_capstyle="round")
    _vertex_labels(ax, P, _span(P))
    _fit(ax, P)
    return _img(fig)


def fig_mitoyennete(P, idxV, party) -> str:
    fig, ax = _new()
    _draw_parcel(ax, P, fc="#fafafa", ec="#bbb", lw=1.0)
    party = set(party or [])
    for i in range(len(P)):
        a, b = _edge(P, i)
        if i in party:
            ax.plot([a[0], b[0]], [a[1], b[1]], color=AMBER, lw=5, zorder=4, solid_capstyle="round")
            m = _emid(P, i)
            ax.text(m[0], m[1], "mitoyen", fontsize=_FS - 2, color=AMBER,
                    fontweight="bold", ha="center", va="center", zorder=9,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))
        elif i == idxV:
            ax.plot([a[0], b[0]], [a[1], b[1]], color=RED, lw=3, zorder=3, solid_capstyle="round")
    _vertex_labels(ax, P, _span(P))
    _fit(ax, P)
    return _img(fig)


def _cote(ax, x0, y0, x1, y1, txt, color, side=1.0):
    """Cote fléchée double + texte décalé perpendiculairement."""
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle="<->", color=color, lw=1.5), zorder=10)
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy) or 1
    px, py = -dy / L, dx / L
    off = 0.9 * side
    ax.text(mx + px * off, my + py * off, txt, fontsize=_FS - 2, color=color,
            fontweight="bold", ha="center", va="center", zorder=11,
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.9))


def _emprise_edge_normals(E):
    """Pour chaque arête de l'emprise : (milieu, normale unitaire vers l'extérieur)."""
    ecx, ecy = _centroid(E)
    out = []
    ne = len(E)
    for i in range(ne):
        a, b = E[i], E[(i + 1) % ne]
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L, dx / L
        if nx * (mx - ecx) + ny * (my - ecy) < 0:
            nx, ny = -nx, -ny
        out.append(((mx, my), (nx, ny), L))
    return out


def fig_implantation(P, E, idxV, idxF, ra, rl, rr) -> str:
    """Vue zoomée sur la zone bâtissable : parcelle + emprise + cotes des reculs.
    Les cotes partent des arêtes de l'EMPRISE vers l'extérieur (toujours dans le
    cadre, même sur parcelle en drapeau)."""
    fig, ax = _new(6.0, 4.6)
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    _draw_parcel(ax, P, fc="#fafafa", ec="#ccc", lw=1.0)  # clip auto au cadre
    if not E:
        ax.text(0.5, 0.5, "Enveloppe nulle", transform=ax.transAxes,
                ha="center", va="center", color=MUTED, fontsize=_FS)
        return _img(fig, tight=False)
    ax.add_patch(MplPoly(E, closed=True, facecolor=INK, edgecolor="#000",
                         lw=1.0, alpha=0.85, zorder=3))
    pad = max(ra or 0, rl or 0, rr or 0, 2) + 2.0
    xs = [q[0] for q in E]
    ys = [q[1] for q in E]
    ax.set_xlim(min(xs) - pad, max(xs) + pad)
    ax.set_ylim(min(ys) - pad, max(ys) + pad)

    # directions de reference (vers l'exterieur, cote rue / cote fond)
    svx, svy = _inward_normal(P, idxV)
    svx, svy = -svx, -svy
    sfx, sfy = _inward_normal(P, idxF)
    sfx, sfy = -sfx, -sfy
    edges = _emprise_edge_normals(E)

    def best(dirx, diry, used):
        bi, bs = -1, -2
        for i, (_, (nx, ny), _L) in enumerate(edges):
            if i in used:
                continue
            sc = nx * dirx + ny * diry
            if sc > bs:
                bs, bi = sc, i
        return bi

    used = set()
    fi = best(svx, svy, used)            # façade rue (avant)
    if fi >= 0:
        used.add(fi)
    bi = best(sfx, sfy, used)            # fond (arrière)
    if bi >= 0:
        used.add(bi)
    li = best(-svy, svx, used)           # latéral (perpendiculaire à la rue)
    if li >= 0:
        used.add(li)

    def cote_edge(i, val, color, label):
        if i < 0 or not val or val <= 0:
            return
        (mx, my), (nx, ny), _L = edges[i]
        _cote(ax, mx, my, mx + nx * val, my + ny * val, label, color)

    cote_edge(fi, ra, RED, f"avant {ra:g} m")
    cote_edge(bi, rr, GREEN, f"arrière {rr:g} m")
    cote_edge(li, rl, MUTED, f"latéral {rl:g} m")
    return _img(fig, tight=False)


def fig_emprise(P, E) -> str:
    """Emprise cotée (largeur × profondeur) dans la parcelle."""
    fig, ax = _new()
    _draw_parcel(ax, P, fc="#f3f3f3", ec="#888", lw=1.0)
    if E:
        ax.add_patch(MplPoly(E, closed=True, facecolor=INK, edgecolor="#000",
                             lw=1.0, alpha=0.85, zorder=3))
        ecx, ecy = _centroid(E)
        ne = len(E)
        for i in range(ne):
            a, b = E[i], E[(i + 1) % ne]
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L < 1.5:
                continue
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            dx, dy = b[0] - a[0], b[1] - a[1]
            Ln = math.hypot(dx, dy) or 1
            nx, ny = dy / Ln, -dx / Ln
            if nx * (mx - ecx) + ny * (my - ecy) < 0:
                nx, ny = -nx, -ny
            ax.text(mx + nx * 1.1, my + ny * 1.1, f"{L:.0f} m", fontsize=_FS - 2,
                    fontweight="bold", color="white", ha="center", va="center", zorder=11,
                    bbox=dict(boxstyle="round,pad=0.12", fc=INK, ec="none", alpha=0.92))
    _fit(ax, P)
    return _img(fig)
