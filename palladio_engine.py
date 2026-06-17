"""
PALLADIO ENGINE v0.2
====================

Moteur d'enveloppe constructible 2D. Sprint 1.5 livre la detection voirie par
adjacence cadastrale (collection 359 Geoportail).

Strategie : remplacer a terme le moteur v2.3 (OBB + reculs alignes) qui deborde
sur parcelles obliques. Palladio s'aligne sur la geometrie cadastrale reelle
(buffer Shapely + half-planes), garanti zero debordement.

Hors perimetre Sprint 1.5 :
  - SCB, hauteurs, niveaux, logements, parkings (Sprint 2, recycle depuis main.py)
  - 3D, GLB, TopoExport (mis de cote)
  - Servitudes, biotopes, zones inondables (Sprint 3)

Input principal : polygone parcelle WGS84 + point geocode + reculs + (NEW) parcelle_id.
Output principal : polygone enveloppe N-coins LUREF + WGS84 + surface m2
                   + classification des aretes (voirie/interne).

Portage depuis :
  - algo_v4.py (compute_enveloppe_v4, half_plane_interior, scoring fond)
  - algo_v5.py (idem v4 avec profondeur max + traces)
  - Prototype Sprint 1.5 (detect_voirie_by_adjacency, validation 4 cas reels)

Valide sur 4 parcelles reelles (Sprint 1.5, 01/06/2026) :
  - 5 Tilleuls Strassen (133/2970) : voirie BC (~5m, via vide cadastral)
  - 7 Tilleuls Strassen (133/2971) : voirie AB (~10m, via vide cadastral)
  - Parcelle d'angle 100/2949 Strassen : 9 aretes voirie (cas multi-faces)
  - 29/2523 Rue P. Federspiel Strassen : voirie CD (~14.7m, via voisin public 5038)

Regle de detection voirie :
    Une arete est VOIRIE si :
      - pas de parcelle voisine au sondage perpendiculaire a 3m, OU
      - le voisin sonde a k_code_nature dans PUBLIC_NATURES = {5038, 5043}
        (5038 = espace public cadastre, 5043 = vide cadastral domaine public)
"""

import math
from typing import List, Tuple, Optional, Dict, Any
from shapely.geometry import Polygon, Point, LineString
from shapely.validation import make_valid

try:
    from pyproj import Transformer
    _T_WGS84_TO_LUREF = Transformer.from_crs("EPSG:4326", "EPSG:2169", always_xy=True)
    _T_LUREF_TO_WGS84 = Transformer.from_crs("EPSG:2169", "EPSG:4326", always_xy=True)
    _PYPROJ_OK = True
except Exception as _e:
    _T_WGS84_TO_LUREF = None
    _T_LUREF_TO_WGS84 = None
    _PYPROJ_OK = False
    _PYPROJ_ERROR = str(_e)

try:
    import requests
    _REQUESTS_OK = True
except Exception as _e:
    _REQUESTS_OK = False
    _REQUESTS_ERROR = str(_e)


# ============================================================
# CONSTANTES SPRINT 1.5 - DETECTION VOIRIE CADASTRALE
# ============================================================

# Codes cadastraux Luxembourg consideres comme espace public
# 5038 = espace public cadastre (placette, trottoir, esplanade)
# 5043 = vide cadastral domaine public (chaussee cadastree comme parcelle)
PUBLIC_NATURES = {5038, 5043}

# Distance de sondage perpendiculaire a chaque arete (metres LUREF)
PROBE_DISTANCE_M = 3.0

# Marge bbox pour la requete Geoportail collection 359 (en degres WGS84)
# ~ 0.001 deg = environ 75 m a 49 deg N en longitude, 110 m en latitude
BBOX_MARGIN_DEG = 0.001

# Endpoint OGC Features Geoportail collection 359 (parcelles cadastrales)
GEOPORTAIL_359_URL = "https://features.geoportail.lu/collections/359/items"

# Timeout HTTP pour la requete voisines (secondes)
NEIGHBORS_HTTP_TIMEOUT_S = 8


# ============================================================
# CONSTANTES SPRINT 2 - SCB / LOGEMENTS / PARKINGS / TYPE / WARNINGS
# ============================================================
# Portees telles quelles depuis main.py v2.3 (non-regression visee < 5%).

# Surface habitable nette ~ 80% de la SCB (murs, gaines, circulations)
RATIO_SCB_TO_SH = 0.80

# Part de l'emprise au sol comptee en combles/retrait amenageable
COMBLES_RATIO = 0.60

# Mix logements standard (memes valeurs que main.py v2.3)
MIX_STANDARD = {
    "T1_studio": {"pct": 0.20, "shn_m2": 35, "scb_m2": 44},
    "T2":        {"pct": 0.35, "shn_m2": 52, "scb_m2": 65},
    "T3":        {"pct": 0.30, "shn_m2": 70, "scb_m2": 88},
    "T4+":       {"pct": 0.15, "shn_m2": 90, "scb_m2": 113},
}
# Moyenne SCB ponderee par logement (~74.9 m2 SCB)
SCB_MOYENNE_PAR_LOGEMENT = sum(t["scb_m2"] * t["pct"] for t in MIX_STANDARD.values())
# Moyenne SHN ponderee (~59.7 m2 SHN) - utile pour la variante HAB-1 corrigee
SHN_MOYENNE_PAR_LOGEMENT = sum(t["shn_m2"] * t["pct"] for t in MIX_STANDARD.values())

# Codes cadastraux residentiels prives (mitoyennete potentielle laterale)
RESIDENTIAL_NATURES = {5024, 5025}

# Seuils warnings (metres)
FACADE_RUE_COURTE_SEUIL_M = 8.0
PARCELLE_QUASI_ENCLAVEE_SEUIL_M = 5.0
PROFONDEUR_MARGE_M = 6.0  # marge mini au-dela de recul_avant + recul_arriere


# ============================================================
# REPROJECTION HELPERS (WGS84 <-> LUREF)
# ============================================================

def wgs84_ring_to_luref(ring: List[List[float]]) -> List[List[float]]:
    """Convertit un ring GeoJSON WGS84 [[lon, lat], ...] en LUREF [[x, y], ...]."""
    if not _PYPROJ_OK:
        raise RuntimeError(f"pyproj indisponible : {_PYPROJ_ERROR}")
    return [list(_T_WGS84_TO_LUREF.transform(lon, lat)) for lon, lat in ring]


def luref_ring_to_wgs84(ring: List[List[float]]) -> List[List[float]]:
    """Convertit un ring LUREF [[x, y], ...] en WGS84 [[lon, lat], ...]."""
    if not _PYPROJ_OK:
        raise RuntimeError(f"pyproj indisponible : {_PYPROJ_ERROR}")
    return [list(_T_LUREF_TO_WGS84.transform(x, y)) for x, y in ring]


def wgs84_point_to_luref(pt: List[float]) -> List[float]:
    """Convertit un point WGS84 [lon, lat] en LUREF [x, y]."""
    if not _PYPROJ_OK:
        raise RuntimeError(f"pyproj indisponible : {_PYPROJ_ERROR}")
    return list(_T_WGS84_TO_LUREF.transform(pt[0], pt[1]))


def _normalize_ring(ring: List[List[float]]) -> List[List[float]]:
    """Retire le dernier point s'il est egal au premier (convention GeoJSON closed)."""
    if not ring:
        return ring
    if len(ring) >= 2 and ring[0][0] == ring[-1][0] and ring[0][1] == ring[-1][1]:
        return ring[:-1]
    return ring


def _close_ring(ring: List[List[float]]) -> List[List[float]]:
    """Ajoute le premier point a la fin (convention GeoJSON Polygon)."""
    if not ring:
        return ring
    if ring[0][0] != ring[-1][0] or ring[0][1] != ring[-1][1]:
        return ring + [ring[0]]
    return ring


def _bbox_from_ring_wgs84(ring: List[List[float]]) -> Tuple[float, float, float, float]:
    """Retourne (min_lon, min_lat, max_lon, max_lat) en WGS84."""
    lons = [c[0] for c in ring]
    lats = [c[1] for c in ring]
    return (min(lons), min(lats), max(lons), max(lats))


def _pad_bbox(bbox: Tuple[float, float, float, float], margin_deg: float
              ) -> Tuple[float, float, float, float]:
    """Elargit la bbox de margin_deg dans les quatre directions."""
    return (
        bbox[0] - margin_deg, bbox[1] - margin_deg,
        bbox[2] + margin_deg, bbox[3] + margin_deg,
    )


# ============================================================
# HELPERS GEOMETRIQUES (porte tel quel de algo_v4)
# ============================================================

def find_limite_voirie(pts: List[List[float]], voirie_point: List[float]) -> int:
    """
    Identifie l'arete de la parcelle la plus proche du point geocode.
    Heuristique simple, sous-optimale sur parcelles allongees (cf. 11 Tilleuls),
    mais l'enveloppe reste legale meme si l'orientation est sous-optimale.
    Conserve comme fallback Sprint 1.5 si la detection cadastrale echoue.
    Retourne l'index de l'arete [pts[i], pts[i+1]].
    """
    n = len(pts)
    voirie = Point(voirie_point)
    best = (float('inf'), -1)
    for i in range(n):
        seg = LineString([pts[i], pts[(i + 1) % n]])
        d = seg.distance(voirie)
        if d < best[0]:
            best = (d, i)
    return best[1]


def edge_inward_normal(pts: List[List[float]], idx: int, centroid: Tuple[float, float]) -> Tuple[float, float]:
    """Normale unitaire pointant vers l'interieur de la parcelle pour l'arete idx."""
    n = len(pts)
    a, b = pts[idx], pts[(idx + 1) % n]
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    nx, ny = -dy / L, dx / L
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    if nx * (centroid[0] - mid[0]) + ny * (centroid[1] - mid[1]) < 0:
        nx, ny = -nx, -ny
    return nx, ny


def edge_outward_normal_from_polygon(p1: List[float], p2: List[float],
                                       polygon: Polygon) -> Tuple[float, float]:
    """
    Normale unitaire pointant vers l'EXTERIEUR de la parcelle pour l'arete [p1, p2].
    Utilise pour le sondage des voisines.
    """
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    L = math.hypot(dx, dy)
    if L < 1e-9:
        return (0.0, 0.0)
    n1 = (-dy / L, dx / L)
    n2 = (dy / L, -dx / L)
    mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
    c = polygon.centroid
    d1 = math.hypot(mid[0] + n1[0] - c.x, mid[1] + n1[1] - c.y)
    d2 = math.hypot(mid[0] + n2[0] - c.x, mid[1] + n2[1] - c.y)
    return n1 if d1 > d2 else n2


def edge_direction(pts: List[List[float]], idx: int) -> Tuple[float, float]:
    """Vecteur unitaire tangent a l'arete idx."""
    n = len(pts)
    a, b = pts[idx], pts[(idx + 1) % n]
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    return dx / L, dy / L


def score_fond(pts: List[List[float]], idx_voirie: int, idx_cand: int) -> float:
    """
    Score d'un candidat arete-fond : profondeur perpendiculaire a la voirie * cos^2(angle).
    Privilegie les aretes paralleles a la voirie et eloignees.
    """
    poly = Polygon(pts)
    centroid = (poly.centroid.x, poly.centroid.y)
    n = len(pts)
    a_v, b_v = pts[idx_voirie], pts[(idx_voirie + 1) % n]
    mid_v = ((a_v[0] + b_v[0]) / 2, (a_v[1] + b_v[1]) / 2)
    n_v = edge_inward_normal(pts, idx_voirie, centroid)
    d_v = edge_direction(pts, idx_voirie)
    a, b = pts[idx_cand], pts[(idx_cand + 1) % n]
    L_edge = math.hypot(b[0] - a[0], b[1] - a[1])
    if L_edge < 0.5:
        return -1.0
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    prof = n_v[0] * (mid[0] - mid_v[0]) + n_v[1] * (mid[1] - mid_v[1])
    d_e = edge_direction(pts, idx_cand)
    cos_a = abs(d_e[0] * d_v[0] + d_e[1] * d_v[1])
    return prof * (cos_a ** 2)


def candidates_fond(pts: List[List[float]], idx_voirie: int, top_k: int = 3) -> List[Tuple[float, int]]:
    """Retourne les top_k aretes-fond candidates triees par score decroissant."""
    n = len(pts)
    scores = []
    for i in range(n):
        if i == idx_voirie:
            continue
        s = score_fond(pts, idx_voirie, i)
        if s > 0:
            scores.append((s, i))
    scores.sort(reverse=True)
    return scores[:top_k]


def half_plane_interior(a: List[float], b: List[float], distance: float,
                         centroid: Tuple[float, float]) -> Optional[Polygon]:
    """
    Construit un demi-plan (sous forme de polygone borne BIG) a distance >= d
    du segment [a, b], cote interieur (vers le centroide).
    Utilise pour les reculs avant/arriere.
    """
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy)
    if L < 1e-9:
        return None
    nx, ny = -dy / L, dx / L
    mid = ((ax + bx) / 2, (ay + by) / 2)
    v = (centroid[0] - mid[0], centroid[1] - mid[1])
    if nx * v[0] + ny * v[1] < 0:
        nx, ny = -nx, -ny
    BIG = 10000
    p1 = (ax + nx * distance - dx / L * BIG, ay + ny * distance - dy / L * BIG)
    p2 = (bx + nx * distance + dx / L * BIG, by + ny * distance + dy / L * BIG)
    p3 = (p2[0] + nx * BIG, p2[1] + ny * BIG)
    p4 = (p1[0] + nx * BIG, p1[1] + ny * BIG)
    return Polygon([p1, p2, p3, p4])


# ============================================================
# SPRINT 1.5 - DETECTION VOIRIE PAR ADJACENCE CADASTRALE
# ============================================================

def fetch_neighbors_359(bbox_wgs84: Tuple[float, float, float, float],
                         exclude_id: Optional[str] = None,
                         timeout: int = NEIGHBORS_HTTP_TIMEOUT_S
                         ) -> List[Dict[str, Any]]:
    """
    Recupere les parcelles voisines via Geoportail OGC Features collection 359.

    Args:
        bbox_wgs84 : (min_lon, min_lat, max_lon, max_lat) en WGS84
        exclude_id : ID de la parcelle cible a exclure du retour
        timeout : timeout HTTP en secondes

    Returns:
        Liste de dicts avec id, k_code_nature, poly_luref (Shapely Polygon en LUREF).
        Retour vide en cas d'echec (fallback safe : on bascule sur geocode_proximity).
    """
    if not _REQUESTS_OK:
        print(f"[palladio voirie] WARN requests indisponible : {_REQUESTS_ERROR}")
        return []

    params = {
        "bbox": f"{bbox_wgs84[0]},{bbox_wgs84[1]},{bbox_wgs84[2]},{bbox_wgs84[3]}",
        "bbox-crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
        "f": "json",
        "limit": 400,
    }
    try:
        r = requests.get(GEOPORTAIL_359_URL, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[palladio voirie] WARN fetch 359 a echoue : {e}")
        return []

    voisines = []
    for feat in data.get("features", []):
        if exclude_id and feat.get("id") == exclude_id:
            continue
        try:
            coords_wgs = feat["geometry"]["coordinates"][0]
            coords_lu = wgs84_ring_to_luref(coords_wgs)
            poly = Polygon(coords_lu)
            if not poly.is_valid:
                poly = poly.buffer(0)
                if poly.is_empty or not hasattr(poly, 'exterior'):
                    continue
            voisines.append({
                "id": feat["id"],
                "k_code_nature": feat["properties"].get("k_code_nature"),
                "poly_luref": poly,
            })
        except Exception:
            continue
    return voisines


def detect_voirie_by_adjacency(parcelle_poly_luref: Polygon,
                                voisines: List[Dict[str, Any]],
                                probe_dist: float = PROBE_DISTANCE_M
                                ) -> List[Dict[str, Any]]:
    """
    Classifie chaque arete de la parcelle : voirie ou interne, par sondage cadastral.

    Pour chaque arete :
      1. Calculer la normale sortante (perpendiculaire vers l'exterieur)
      2. Sonder un point a `probe_dist` metres dans la direction normale sortante
      3. Tester si ce point tombe dans une parcelle voisine

    Regle :
      Arete VOIRIE si :
        - aucune voisine ne contient le point sonde, OU
        - la voisine qui contient le point sonde a k_code_nature dans PUBLIC_NATURES
      Arete INTERNE sinon (mitoyennete privee)

    Args:
        parcelle_poly_luref : Polygon Shapely de la parcelle cible en LUREF
        voisines : liste issue de fetch_neighbors_359
        probe_dist : distance de sondage en metres (defaut 3.0)

    Returns:
        Liste de dicts (une entree par arete) avec :
            idx, label, p1, p2, length_m, mid, normal, probe_point,
            voisin_id, voisin_nature, is_voirie, motif
    """
    coords = list(parcelle_poly_luref.exterior.coords)[:-1]
    n = len(coords)
    edges = []

    for i in range(n):
        p1, p2 = list(coords[i]), list(coords[(i + 1) % n])
        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        mid = [(p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2]
        normal = edge_outward_normal_from_polygon(p1, p2, parcelle_poly_luref)
        probe = [mid[0] + normal[0] * probe_dist, mid[1] + normal[1] * probe_dist]
        probe_pt = Point(probe)

        voisin_match = None
        for v in voisines:
            if v["poly_luref"].contains(probe_pt):
                voisin_match = v
                break

        if voisin_match is None:
            is_voirie = True
            motif = "voirie via vide cadastral (aucune voisine au sondage)"
            voisin_id, voisin_nature = None, None
        else:
            voisin_id = voisin_match["id"]
            voisin_nature = voisin_match["k_code_nature"]
            if voisin_nature in PUBLIC_NATURES:
                is_voirie = True
                motif = f"voirie via voisin public (k_nature={voisin_nature})"
            else:
                is_voirie = False
                motif = f"interne via voisin prive (k_nature={voisin_nature})"

        edges.append({
            "idx": i,
            "label": f"{chr(65 + i)}{chr(65 + (i + 1) % n)}",
            "p1": [round(p1[0], 2), round(p1[1], 2)],
            "p2": [round(p2[0], 2), round(p2[1], 2)],
            "length_m": round(length, 2),
            "mid": [round(mid[0], 2), round(mid[1], 2)],
            "normal": [round(normal[0], 4), round(normal[1], 4)],
            "probe_point": [round(probe[0], 2), round(probe[1], 2)],
            "voisin_id": voisin_id,
            "voisin_nature": voisin_nature,
            "is_voirie": is_voirie,
            "motif": motif,
        })

    return edges


def select_voirie_edge_from_classification(edges_classified: List[Dict[str, Any]],
                                             point_geocode_luref: Optional[List[float]] = None
                                             ) -> Dict[str, Any]:
    """
    Selectionne l'arete voirie principale parmi les aretes classifiees.

    Strategie :
      1. Filtrer les aretes is_voirie=True
      2. Si 0 arete voirie : fallback "arete la plus proche du geocode"
      3. Si 1 arete : retourner directement
      4. Si N aretes (parcelle d'angle ou multi-segments) :
         - Si point_geocode_luref fourni : prendre la plus proche du geocode
         - Sinon : prendre la plus longue

    Returns:
        dict avec selected_idx, all_voirie_edges (liste idx), fallback_used (str|None)
    """
    voirie_edges = [e for e in edges_classified if e["is_voirie"]]
    fallback_used = None

    if len(voirie_edges) == 0:
        fallback_used = "no_voirie_found_geocode_proximity"
        if point_geocode_luref is None:
            return {"selected_idx": 0, "all_voirie_edges": [], "fallback_used": fallback_used}
        best_idx, best_d = 0, float("inf")
        for e in edges_classified:
            d = math.hypot(e["mid"][0] - point_geocode_luref[0],
                           e["mid"][1] - point_geocode_luref[1])
            if d < best_d:
                best_d, best_idx = d, e["idx"]
        return {"selected_idx": best_idx, "all_voirie_edges": [], "fallback_used": fallback_used}

    if len(voirie_edges) == 1:
        return {
            "selected_idx": voirie_edges[0]["idx"],
            "all_voirie_edges": [e["idx"] for e in voirie_edges],
            "fallback_used": None,
        }

    if point_geocode_luref is not None:
        best = min(voirie_edges, key=lambda e: math.hypot(
            e["mid"][0] - point_geocode_luref[0],
            e["mid"][1] - point_geocode_luref[1]))
    else:
        best = max(voirie_edges, key=lambda e: e["length_m"])

    return {
        "selected_idx": best["idx"],
        "all_voirie_edges": [e["idx"] for e in voirie_edges],
        "fallback_used": None,
    }


# ============================================================
# CALCUL ENVELOPPE (porte de algo_v4.compute_enveloppe_v4)
# ============================================================

def _compute_enveloppe_unique(pts: List[List[float]], idx_voirie: int, idx_fond: int,
                               ra: float, rl: float, rr: float,
                               prof_max: Optional[float] = None) -> Tuple[Polygon, List[Dict]]:
    """
    Calcule l'enveloppe pour une combinaison (voirie, fond) donnee.
    Pipeline :
      1. buffer(-rl) lateral uniforme (mitre, gere les coins)
      2. intersection demi-plan recul avant
      3. intersection demi-plan recul arriere
      4. (option) clip a distance <= ra + prof_max de la voirie
    """
    poly = Polygon(pts)
    centroid = (poly.centroid.x, poly.centroid.y)
    n = len(pts)
    traces = []

    # 1. Buffer lateral uniforme
    env = poly.buffer(-rl, join_style=2, mitre_limit=10)
    if env.is_empty:
        return env, traces

    # 2. Recul avant additionnel si ra > rl
    a_v, b_v = pts[idx_voirie], pts[(idx_voirie + 1) % n]
    if ra > rl:
        hp_av = half_plane_interior(a_v, b_v, ra, centroid)
        if hp_av is not None:
            env = env.intersection(hp_av)
    traces.append({
        "idx": idx_voirie,
        "from": chr(65 + idx_voirie),
        "to": chr(65 + (idx_voirie + 1) % n),
        "cat": "AVANT",
        "distance_m": ra,
    })

    # 3. Recul arriere
    if not env.is_empty:
        a_f, b_f = pts[idx_fond], pts[(idx_fond + 1) % n]
        if rr > rl:
            hp_ar = half_plane_interior(a_f, b_f, rr, centroid)
            if hp_ar is not None:
                env = env.intersection(hp_ar)
        traces.append({
            "idx": idx_fond,
            "from": chr(65 + idx_fond),
            "to": chr(65 + (idx_fond + 1) % n),
            "cat": "ARRIERE",
            "distance_m": rr,
        })

    # Traces laterales (info uniquement, buffer les gere deja)
    for i in range(n):
        if i == idx_voirie or i == idx_fond:
            continue
        traces.append({
            "idx": i,
            "from": chr(65 + i),
            "to": chr(65 + (i + 1) % n),
            "cat": "LATERAL",
            "distance_m": rl,
        })

    # 4. Profondeur max (clip arriere-de-la-voirie)
    if prof_max and not env.is_empty:
        hp_deep = half_plane_interior(a_v, b_v, ra + prof_max, centroid)
        if hp_deep is not None:
            env = env.difference(hp_deep)

    return env, traces


def _polygon_to_corners(geom) -> Optional[List[List[float]]]:
    """
    Extrait les coins du polygone resultant, en gardant le plus gros polygone
    si MultiPolygon (cas rare apres clip). Drop closing point. Retourne None si vide.
    """
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type == 'MultiPolygon':
        geom = max(geom.geoms, key=lambda g: g.area)
    if not hasattr(geom, 'exterior'):
        return None
    coords = list(geom.exterior.coords)
    if len(coords) < 4:
        return None
    if coords[0] == coords[-1]:
        coords = coords[:-1]
    return [[round(p[0], 3), round(p[1], 3)] for p in coords]


# ============================================================
# API PUBLIQUE
# ============================================================

class PalladioError(Exception):
    """Erreur metier Palladio (parcelle invalide, reculs incompatibles, etc.)"""
    pass


def calculer_emprise_palladio(
    parcel_geometry_wgs84: Dict[str, Any],
    point_geocode_wgs84: List[float],
    recul_avant_m: float,
    recul_lateral_m: float,
    recul_arriere_m: float,
    profondeur_max_m: Optional[float] = None,
    top_k_fond: int = 3,
    parcelle_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calcule l'enveloppe constructible 2D d'une parcelle cadastrale.

    Args:
        parcel_geometry_wgs84 : GeoJSON Polygon en WGS84 (lon, lat).
            Ex : {"type": "Polygon", "coordinates": [[[lon, lat], ...]]}
        point_geocode_wgs84 : [lon, lat] WGS84, identifie la voirie (fallback).
        recul_avant_m : distance min depuis l'arete voirie (en metres).
        recul_lateral_m : distance min depuis les aretes laterales.
        recul_arriere_m : distance min depuis l'arete fond.
        profondeur_max_m : optionnel, profondeur max totale depuis voirie
            (NB : recul_avant + profondeur_max_m mesures depuis la voirie).
        top_k_fond : nombre de candidats arete-fond a tester.
        parcelle_id : (NEW Sprint 1.5) ID cadastral pour activer la detection
            voirie par adjacence cadastrale. Si None, fallback sur geocode_proximity.

    Returns:
        dict pret a JSONifier avec :
        - meta : version, methode
        - parcelle : geometrie LUREF + WGS84, surface cadastrale, nb sommets
        - voirie : idx + label + methode detection + (Sprint 1.5) detection complete
        - fond : idx + label + score + candidats top-k
        - reculs_appliques : ce qui a ete utilise
        - emprise : geometry GeoJSON LUREF + WGS84, surface m2, nb sommets, ratio
        - traces_reculs : liste des reculs par arete pour debug

    Raises:
        PalladioError : input invalide ou enveloppe degeneree
    """
    # ---- Validation inputs ----
    if not _PYPROJ_OK:
        raise PalladioError(f"pyproj indisponible : {_PYPROJ_ERROR}")
    if not parcel_geometry_wgs84 or parcel_geometry_wgs84.get("type") != "Polygon":
        raise PalladioError("parcel_geometry_wgs84 doit etre un GeoJSON Polygon")
    coords = parcel_geometry_wgs84.get("coordinates")
    if not coords or len(coords) == 0 or len(coords[0]) < 4:
        raise PalladioError("Parcelle invalide : polygone doit avoir >= 3 sommets distincts")
    if not point_geocode_wgs84 or len(point_geocode_wgs84) != 2:
        raise PalladioError("point_geocode_wgs84 doit etre [lon, lat]")
    if recul_avant_m < 0 or recul_lateral_m < 0 or recul_arriere_m < 0:
        raise PalladioError("Tous les reculs doivent etre >= 0")

    # ---- Reprojection en LUREF (tous les calculs metrique se font la) ----
    ring_wgs = _normalize_ring(coords[0])
    pts_luref = wgs84_ring_to_luref(ring_wgs)
    pt_geo_luref = wgs84_point_to_luref(point_geocode_wgs84)

    parcel_poly_luref = Polygon(pts_luref)
    if not parcel_poly_luref.is_valid:
        parcel_poly_luref = make_valid(parcel_poly_luref)
        if parcel_poly_luref.geom_type != 'Polygon':
            raise PalladioError(f"Parcelle invalide apres make_valid : {parcel_poly_luref.geom_type}")
        pts_luref = _normalize_ring(list(parcel_poly_luref.exterior.coords))

    surface_cadastrale_m2 = parcel_poly_luref.area
    n_sommets = len(pts_luref)

    # ---- Detection voirie : Sprint 1.5 (cadastral) + fallback geocode ----
    voirie_detection = _detect_voirie_with_fallback(
        parcel_poly_luref=parcel_poly_luref,
        pts_luref=pts_luref,
        ring_wgs=ring_wgs,
        pt_geo_luref=pt_geo_luref,
        parcelle_id=parcelle_id,
    )
    idx_voirie = voirie_detection["selected_idx"]
    voirie_method = voirie_detection["method"]

    # ---- Calcul enveloppe pour les top-k candidats fond ----
    cands = candidates_fond(pts_luref, idx_voirie, top_k=top_k_fond)
    if not cands:
        raise PalladioError("Aucun candidat arete-fond trouve (parcelle degeneree ?)")

    results_by_fond = []
    best = None  # (area, idx_fond, env_geom, traces)

    for score, idx_f in cands:
        env_geom, traces = _compute_enveloppe_unique(
            pts_luref, idx_voirie, idx_f,
            ra=recul_avant_m, rl=recul_lateral_m, rr=recul_arriere_m,
            prof_max=profondeur_max_m,
        )
        area = env_geom.area if not env_geom.is_empty else 0.0
        fond_label = chr(65 + idx_f) + chr(65 + (idx_f + 1) % n_sommets)
        results_by_fond.append({
            "idx_fond": idx_f,
            "fond_label": fond_label,
            "score_fond": round(score, 2),
            "surface_emprise_m2": round(area, 1),
        })
        if best is None or area > best[0]:
            best = (area, idx_f, env_geom, traces)

    best_area, best_idx_fond, best_env, best_traces = best

    if best_area < 1.0:
        raise PalladioError(
            f"Enveloppe degeneree : surface {best_area:.1f} m2 sur parcelle de "
            f"{surface_cadastrale_m2:.0f} m2. Reculs trop restrictifs ? "
            f"(avant={recul_avant_m}, lateral={recul_lateral_m}, arriere={recul_arriere_m})"
        )

    ratio_vs_cadastrale = best_area / surface_cadastrale_m2 if surface_cadastrale_m2 > 0 else 0

    # ---- Extraction coins emprise + reprojection WGS84 ----
    corners_luref = _polygon_to_corners(best_env)
    if corners_luref is None:
        raise PalladioError("Polygone enveloppe extractible vide apres calcul")
    corners_wgs84 = luref_ring_to_wgs84(corners_luref)

    # ---- Labels aretes ----
    idx_voirie_label = chr(65 + idx_voirie) + chr(65 + (idx_voirie + 1) % n_sommets)
    idx_fond_label = chr(65 + best_idx_fond) + chr(65 + (best_idx_fond + 1) % n_sommets)

    return {
        "meta": {
            "engine": "palladio",
            "version": "0.2",
            "method": "shapely_buffer_halfplanes_v5_with_cadastral_voirie",
        },
        "parcelle": {
            "geometry_luref": {
                "type": "Polygon",
                "coordinates": [_close_ring([list(p) for p in pts_luref])],
            },
            "geometry_wgs84": parcel_geometry_wgs84,
            "surface_cadastrale_m2": round(surface_cadastrale_m2, 1),
            "nb_sommets": n_sommets,
            "id": parcelle_id,
        },
        "voirie": {
            "idx": idx_voirie,
            "edge_label": idx_voirie_label,
            "method": voirie_method,
            "point_luref": [round(pt_geo_luref[0], 2), round(pt_geo_luref[1], 2)],
            "detection": voirie_detection,
        },
        "fond": {
            "idx": best_idx_fond,
            "edge_label": idx_fond_label,
            "candidats": results_by_fond,
        },
        "reculs_appliques": {
            "avant_m": recul_avant_m,
            "lateral_m": recul_lateral_m,
            "arriere_m": recul_arriere_m,
            "profondeur_max_m": profondeur_max_m,
        },
        "emprise": {
            "geometry_luref": {
                "type": "Polygon",
                "coordinates": [_close_ring([list(p) for p in corners_luref])],
            },
            "geometry_wgs84": {
                "type": "Polygon",
                "coordinates": [_close_ring([list(p) for p in corners_wgs84])],
            },
            "surface_m2": round(best_area, 1),
            "nb_sommets": len(corners_luref),
            "ratio_vs_cadastrale": round(ratio_vs_cadastrale, 3),
        },
        "traces_reculs": best_traces,
    }


def _detect_voirie_with_fallback(parcel_poly_luref: Polygon,
                                   pts_luref: List[List[float]],
                                   ring_wgs: List[List[float]],
                                   pt_geo_luref: List[float],
                                   parcelle_id: Optional[str]) -> Dict[str, Any]:
    """
    Wrapper de detection voirie avec fallback gracieux.

    Hierarchie :
      1. Si parcelle_id fourni : tenter detection cadastrale (Sprint 1.5)
         - Si succes (voisines fetched et au moins une classification reussie) : OK
         - Sinon : fallback geocode_proximity
      2. Si parcelle_id absent : geocode_proximity direct (mode legacy)

    Returns:
        dict avec selected_idx, method, edges_classified, all_voirie_edges,
        fallback_used, n_neighbors_fetched, n_neighbors_public
    """
    # Mode legacy : pas de parcelle_id
    if not parcelle_id:
        idx = find_limite_voirie(pts_luref, pt_geo_luref)
        return {
            "selected_idx": idx,
            "method": "geocode_proximity",
            "edges_classified": [],
            "all_voirie_edges": [],
            "fallback_used": "no_parcelle_id_provided",
            "n_neighbors_fetched": 0,
            "n_neighbors_public": 0,
        }

    # Mode Sprint 1.5 : detection cadastrale
    try:
        bbox_wgs = _bbox_from_ring_wgs84(ring_wgs)
        bbox_padded = _pad_bbox(bbox_wgs, BBOX_MARGIN_DEG)
        voisines = fetch_neighbors_359(bbox_padded, exclude_id=parcelle_id)

        if not voisines:
            # API indisponible ou bbox vide : fallback geocode
            idx = find_limite_voirie(pts_luref, pt_geo_luref)
            return {
                "selected_idx": idx,
                "method": "geocode_proximity_fallback",
                "edges_classified": [],
                "all_voirie_edges": [],
                "fallback_used": "no_neighbors_fetched",
                "n_neighbors_fetched": 0,
                "n_neighbors_public": 0,
            }

        edges_classified = detect_voirie_by_adjacency(parcel_poly_luref, voisines)
        selection = select_voirie_edge_from_classification(
            edges_classified, point_geocode_luref=pt_geo_luref
        )
        n_public = sum(1 for v in voisines if v["k_code_nature"] in PUBLIC_NATURES)

        return {
            "selected_idx": selection["selected_idx"],
            "method": "cadastral_adjacency_v0.2"
                if selection["fallback_used"] is None else "cadastral_adjacency_with_fallback",
            "edges_classified": edges_classified,
            "all_voirie_edges": selection["all_voirie_edges"],
            "fallback_used": selection["fallback_used"],
            "n_neighbors_fetched": len(voisines),
            "n_neighbors_public": n_public,
        }

    except Exception as e:
        # Toute exception dans la detection cadastrale : fallback robuste
        print(f"[palladio voirie] WARN detection cadastrale a echoue, fallback geocode : {e}")
        idx = find_limite_voirie(pts_luref, pt_geo_luref)
        return {
            "selected_idx": idx,
            "method": "geocode_proximity_fallback",
            "edges_classified": [],
            "all_voirie_edges": [],
            "fallback_used": f"detection_error: {type(e).__name__}",
            "n_neighbors_fetched": 0,
            "n_neighbors_public": 0,
        }


# ============================================================
# SPRINT 2 - SCB (Surface Construite Brute)
# ============================================================

def calculate_scb(emprise_au_sol_m2: float,
                  zone_pag: Dict[str, Any],
                  surface_terrain_net_m2: Optional[float] = None) -> Dict[str, Any]:
    """
    Calcule la Surface Construite Brute a partir de l'emprise au sol Palladio.

    Porte de main.py v2.3 (etape 5). L'emprise au sol = surface de l'enveloppe
    constructible calculee par calculer_emprise_palladio (et non un rectangle OBB).

    Args:
        emprise_au_sol_m2 : surface de l'enveloppe 2D (m2)
        zone_pag : regles PAG mappees (niveaux_pleins_max, combles_retrait,
            cus_max/CUS_max optionnel)
        surface_terrain_net_m2 : pour le plafond CUS (defaut = None, pas de cap)

    Returns:
        dict avec scb_totale_m2, surface_habitable_m2, ventilation par niveau,
        cus_applique. surface_habitable est calculee AVANT le cap CUS (fidele
        a main.py : la SH sert au comptage logements et n'est pas re-rognee).
    """
    niveaux = int(zone_pag.get("niveaux_pleins_max") or 1)
    combles = bool(zone_pag.get("combles_retrait", False))

    scb_niveaux = emprise_au_sol_m2 * niveaux
    scb_combles = emprise_au_sol_m2 * COMBLES_RATIO if combles else 0.0
    scb_totale = scb_niveaux + scb_combles

    # SH calculee avant cap CUS (fidele main.py)
    surface_habitable = scb_totale * RATIO_SCB_TO_SH

    # Ventilation par niveau
    ventilation = [{"niveau": "RDC", "scb_m2": round(emprise_au_sol_m2, 1)}]
    for k in range(1, niveaux):
        ventilation.append({"niveau": f"R+{k}", "scb_m2": round(emprise_au_sol_m2, 1)})
    if combles:
        ventilation.append({"niveau": "Combles/retrait", "scb_m2": round(scb_combles, 1)})

    # Plafond CUS (PAP NQ ou zone)
    cus_applique = None
    cus_max = zone_pag.get("cus_max") or zone_pag.get("CUS_max")
    if cus_max and surface_terrain_net_m2:
        try:
            scb_max_cus = surface_terrain_net_m2 * float(cus_max)
            limitant = scb_totale > scb_max_cus
            if limitant:
                scb_totale = scb_max_cus
            cus_applique = {
                "cus_max": float(cus_max),
                "scb_max_cus_m2": round(scb_max_cus, 1),
                "limitant": limitant,
            }
        except (ValueError, TypeError):
            cus_applique = None

    return {
        "emprise_au_sol_m2": round(emprise_au_sol_m2, 1),
        "niveaux_pleins": niveaux,
        "combles": combles,
        "scb_niveaux_m2": round(scb_niveaux, 1),
        "scb_combles_m2": round(scb_combles, 1),
        "scb_totale_m2": round(scb_totale, 1),
        "surface_habitable_m2": round(surface_habitable, 1),
        "ventilation_par_niveau": ventilation,
        "cus_applique": cus_applique,
    }


# ============================================================
# SPRINT 2 - LOGEMENTS THEORIQUES
# ============================================================

def calculate_logements(scb_totale_m2: float,
                        surface_habitable_m2: float,
                        emprise_au_sol_m2: float,
                        zone_pag: Dict[str, Any],
                        surface_terrain_m2: float,
                        corriger_hab1: bool = False) -> Dict[str, Any]:
    """
    Estime le nombre de logements theoriques et le mix typologique.

    Porte de main.py v2.3 (etapes 7-8).

    BUG HAB-1 (connu, documente) :
        main.py ligne 1150 fait `nb_log_brut = sh_logement / SCB_MOYENNE_PAR_LOGEMENT`,
        soit une surface HABITABLE divisee par une moyenne SCB (~74.9). Mismatch
        d'unite : sous-compte d'environ 20% par rapport a une base SCB coherente.
        - corriger_hab1=False (defaut) : reproduit main.py a l'identique (parite).
        - corriger_hab1=True : `nb = scb_logement / SCB_MOYENNE_PAR_LOGEMENT`
          (tout en base SCB, coherent). A activer apres validation Vincent.

    Returns:
        dict avec nb_logements, mix_detail, surface_moyenne_shn_m2,
        scb_logement_m2, scb_commerce_m2, contraintes, hab1.
    """
    type_zone = zone_pag.get("type_zone", "Habitation")
    logement_ok = "oui" in str(zone_pag.get("logement_autorise", "Non")).lower()
    commerce_ok = "oui" in str(zone_pag.get("commerce_autorise", "Non")).lower()
    min_scb_log_pct = zone_pag.get("min_scb_logement_pct")

    contraintes: List[str] = []
    scb_commerce = 0.0
    scb_logement = scb_totale_m2
    sh_logement = surface_habitable_m2

    if type_zone == "Mixte" and commerce_ok:
        pct_log = (min_scb_log_pct or 50) / 100
        scb_commerce = emprise_au_sol_m2 * 0.80
        scb_logement = scb_totale_m2 - scb_commerce
        if scb_logement < scb_totale_m2 * pct_log:
            scb_logement = scb_totale_m2 * pct_log
            scb_commerce = scb_totale_m2 - scb_logement
        sh_logement = scb_logement * RATIO_SCB_TO_SH
    elif not logement_ok:
        scb_logement = 0.0
        scb_commerce = scb_totale_m2
        sh_logement = 0.0

    nb_logements = 0
    if logement_ok and sh_logement > 0:
        if corriger_hab1:
            nb_log = scb_logement / SCB_MOYENNE_PAR_LOGEMENT
        else:
            # Fidele main.py v2.3 (HAB-1)
            nb_log = sh_logement / SCB_MOYENNE_PAR_LOGEMENT

        # Plafond densite (log/ha)
        dl_max = zone_pag.get("dl_max")
        if dl_max:
            try:
                nb_dl = (surface_terrain_m2 / 10000) * float(dl_max)
                if nb_log > nb_dl:
                    nb_log = nb_dl
                    contraintes.append(f"Densite max {dl_max} log/ha limitante")
            except (ValueError, TypeError):
                pass

        # Plafond par construction
        nb_max = zone_pag.get("nb_log_max_par_construction")
        if nb_max:
            try:
                nb_max_val = float(str(nb_max).split()[0]) if isinstance(nb_max, str) else float(nb_max)
                if nb_log > nb_max_val:
                    nb_log = nb_max_val
                    contraintes.append(f"Plafond {nb_max_val:.0f} log/construction limitant")
            except (ValueError, TypeError):
                pass

        nb_logements = max(1, math.floor(nb_log))

    # Mix typologique
    mix_detail: Dict[str, Dict[str, Any]] = {}
    if nb_logements <= 0:
        pass
    elif nb_logements <= 2:
        mix_detail = {"T3": {"nb": nb_logements, "shn_m2": 70, "scb_m2": 88}}
    else:
        for t, d in MIX_STANDARD.items():
            mix_detail[t] = {
                "nb": max(1, round(nb_logements * d["pct"])),
                "shn_m2": d["shn_m2"],
                "scb_m2": d["scb_m2"],
            }
        total_mix = sum(dd["nb"] for dd in mix_detail.values())
        if total_mix != nb_logements:
            mix_detail["T2"]["nb"] += nb_logements - total_mix

    total_log = sum(d["nb"] for d in mix_detail.values())
    avg_shn = (sum(d["shn_m2"] * d["nb"] for d in mix_detail.values()) / total_log
               if total_log > 0 else 0.0)
    if avg_shn < 52 and total_log > 0:
        contraintes.append(f"Moyenne SHN {avg_shn:.0f}m2 < 52m2 reglementaire")

    return {
        "nb_logements": nb_logements,
        "mix_detail": mix_detail,
        "surface_moyenne_shn_m2": round(avg_shn, 1),
        "scb_logement_m2": round(scb_logement, 1),
        "scb_commerce_m2": round(scb_commerce, 1),
        "type_zone": type_zone,
        "logement_autorise": logement_ok,
        "contraintes": contraintes,
        "hab1": {
            "corrige": corriger_hab1,
            "scb_moyenne_par_logement_m2": round(SCB_MOYENNE_PAR_LOGEMENT, 1),
            "shn_moyenne_par_logement_m2": round(SHN_MOYENNE_PAR_LOGEMENT, 1),
        },
    }


# ============================================================
# SPRINT 2 - PARKINGS REGLEMENTAIRES
# ============================================================

def calculate_parkings(mix_detail: Dict[str, Dict[str, Any]],
                       scb_commerce_m2: float = 0.0) -> Dict[str, Any]:
    """
    Calcule les places de parking reglementaires (auto + velo + surface SS).

    Porte de main.py v2.3 (calculer_parkings / calculer_parkings_velo, etape 9).
    Bareme auto par logement selon SHN : <60m2 -> 1/1, 60-90 -> 1/2, >90 -> 1/3.
    Commerce : 1 place / 20 m2 SCB. Velo : 1/logement + commerce.
    """
    p_min = 0
    p_max = 0
    nb_logements = sum(d["nb"] for d in mix_detail.values())

    for _, data in mix_detail.items():
        nb = data["nb"]
        shn = data["shn_m2"]
        if shn < 60:
            p_min += nb * 1
            p_max += nb * 1
        elif shn <= 90:
            p_min += nb * 1
            p_max += nb * 2
        else:
            p_min += nb * 1
            p_max += nb * 3

    if scb_commerce_m2 > 0:
        p_com = math.ceil(scb_commerce_m2 / 20)
        p_min += p_com
        p_max += p_com

    # Velo
    velo = nb_logements
    if scb_commerce_m2 > 0:
        velo += (math.ceil(scb_commerce_m2 / 50) if scb_commerce_m2 < 2000
                 else math.ceil(scb_commerce_m2 / 200))

    surface_parking_ss_m2 = p_min * 25  # ~25 m2/place en sous-sol

    return {
        "auto_min": p_min,
        "auto_max": p_max,
        "velo": velo,
        "surface_sous_sol_estimee_m2": surface_parking_ss_m2,
    }


# ============================================================
# SPRINT 2 - TYPE DE CONSTRUCTION (proxy adjacence cadastrale)
# ============================================================

def detect_construction_type(edges_classified: List[Dict[str, Any]],
                             idx_voirie: int,
                             idx_fond: int,
                             min_edge_m: float = 2.0) -> Dict[str, Any]:
    """
    Deduit le type de construction depuis l'adjacence cadastrale (Sprint 1.5).

    PROXY v0.3 : on n'a pas (encore) de source batie. On approxime par les
    mitoyennetes LATERALES potentielles = aretes non-voirie, non-fond, adjacentes
    a une parcelle privee (voisin present, k_nature non public). C'est de
    l'adjacence FONCIERE, pas de la mitoyennete batie reelle -> confiance "proxy".

    Regle :
        n_lateraux_mitoyens = nb aretes laterales avec voisin prive
          0 -> maison_isolee_4_facades
          1 -> maison_jumelee
          2 -> maison_mitoyenne_2_facades
          >=3 -> bande

    Args:
        edges_classified : sortie detect_voirie_by_adjacency (vide si fallback)
        idx_voirie, idx_fond : index des aretes voirie et fond a exclure
        min_edge_m : ignore les micro-aretes (coins)

    Returns:
        dict avec type, n_lateraux, n_mitoyens, method, confiance, details.
    """
    if not edges_classified:
        return {
            "type": "indetermine",
            "n_lateraux": 0,
            "n_mitoyens": 0,
            "method": "indisponible_sans_classification_cadastrale",
            "confiance": "nulle",
            "details": [],
        }

    lateraux = []
    n_mitoyens = 0
    for e in edges_classified:
        if e["idx"] in (idx_voirie, idx_fond):
            continue
        if e.get("length_m", 0) < min_edge_m:
            continue
        mitoyen = (not e["is_voirie"]) and (e.get("voisin_id") is not None)
        lateraux.append({
            "idx": e["idx"],
            "label": e.get("label"),
            "length_m": e.get("length_m"),
            "mitoyen": mitoyen,
            "voisin_nature": e.get("voisin_nature"),
        })
        if mitoyen:
            n_mitoyens += 1

    if n_mitoyens == 0:
        type_constr = "maison_isolee_4_facades"
    elif n_mitoyens == 1:
        type_constr = "maison_jumelee"
    elif n_mitoyens == 2:
        type_constr = "maison_mitoyenne_2_facades"
    else:
        type_constr = "bande"

    return {
        "type": type_constr,
        "n_lateraux": len(lateraux),
        "n_mitoyens": n_mitoyens,
        "method": "cadastral_adjacency_proxy_v0.3",
        "confiance": "proxy_foncier",
        "details": lateraux,
    }


# ============================================================
# SPRINT 2 - WARNINGS SYSTEME
# ============================================================

def _mk_warning(code: str, level: str, fr: str, en: str,
                edge: Optional[str] = None) -> Dict[str, Any]:
    return {"code": code, "level": level, "message_fr": fr, "message_en": en, "edge": edge}


def generate_warnings(edges_classified: List[Dict[str, Any]],
                      idx_voirie: int,
                      all_voirie_edges: List[int],
                      parcelle_nb_sommets: int,
                      type_construction: Dict[str, Any],
                      zone_pag: Dict[str, Any],
                      enveloppe_vide: bool = False,
                      profondeur_insuffisante: bool = False,
                      voirie_edge_label: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Genere la liste des warnings systeme (codes + niveau + FR/EN + arete).

    Codes : FACADE_RUE_COURTE, PARCELLE_QUASI_ENCLAVEE, PARCELLE_NON_RECTANGULAIRE,
            PROFONDEUR_INSUFFISANTE, JUMELAGE_DETECTE_SANS_DROITE, ENVELOPPE_VIDE.
    """
    warnings: List[Dict[str, Any]] = []

    if enveloppe_vide:
        warnings.append(_mk_warning(
            "ENVELOPPE_VIDE", "critique",
            "Enveloppe constructible nulle ou degeneree : reculs trop restrictifs "
            "ou parcelle trop petite.",
            "Constructible envelope is empty or degenerate: setbacks too restrictive "
            "or parcel too small."))

    # Longueurs voirie
    voirie_total_m = 0.0
    selected_len = None
    if edges_classified:
        for e in edges_classified:
            if e["idx"] in all_voirie_edges:
                voirie_total_m += e.get("length_m", 0)
            if e["idx"] == idx_voirie:
                selected_len = e.get("length_m")

    if selected_len is not None and selected_len < FACADE_RUE_COURTE_SEUIL_M:
        warnings.append(_mk_warning(
            "FACADE_RUE_COURTE", "warning",
            f"Facade sur rue courte ({selected_len:.1f} m < {FACADE_RUE_COURTE_SEUIL_M:.0f} m) : "
            "implantation et acces a verifier.",
            f"Short street frontage ({selected_len:.1f} m < {FACADE_RUE_COURTE_SEUIL_M:.0f} m): "
            "layout and access to be checked.",
            edge=voirie_edge_label))

    if edges_classified and 0 < voirie_total_m < PARCELLE_QUASI_ENCLAVEE_SEUIL_M:
        warnings.append(_mk_warning(
            "PARCELLE_QUASI_ENCLAVEE", "critique",
            f"Parcelle quasi-enclavee : contact voirie total {voirie_total_m:.1f} m "
            f"< {PARCELLE_QUASI_ENCLAVEE_SEUIL_M:.0f} m.",
            f"Near-landlocked parcel: total street contact {voirie_total_m:.1f} m "
            f"< {PARCELLE_QUASI_ENCLAVEE_SEUIL_M:.0f} m."))

    if parcelle_nb_sommets > 5:
        warnings.append(_mk_warning(
            "PARCELLE_NON_RECTANGULAIRE", "info",
            f"Parcelle non rectangulaire ({parcelle_nb_sommets} sommets) : "
            "estimation d'enveloppe indicative.",
            f"Non-rectangular parcel ({parcelle_nb_sommets} vertices): "
            "envelope estimate is indicative."))

    if profondeur_insuffisante and not enveloppe_vide:
        warnings.append(_mk_warning(
            "PROFONDEUR_INSUFFISANTE", "warning",
            "Profondeur de parcelle limite vis-a-vis des reculs avant + arriere.",
            "Parcel depth is tight given front + rear setbacks."))

    tc = type_construction.get("type")
    if tc in ("maison_jumelee", "maison_mitoyenne_2_facades", "bande"):
        warnings.append(_mk_warning(
            "JUMELAGE_DETECTE_SANS_DROITE", "info",
            f"Mitoyennete potentielle detectee ({tc}) par adjacence cadastrale : "
            "verifier le droit a batir en limite (PAG/PAP).",
            f"Potential party-wall situation detected ({tc}) via cadastral adjacency: "
            "check the right to build on the boundary (PAG/PAP)."))

    return warnings


# ============================================================
# SPRINT 2 - ORCHESTRATEUR /palladio/calcul/full
# ============================================================

def _profondeur_disponible(pts_luref: List[List[float]], idx_voirie: int) -> float:
    """Profondeur perpendiculaire max de la parcelle depuis l'arete voirie."""
    poly = Polygon(pts_luref)
    centroid = (poly.centroid.x, poly.centroid.y)
    n = len(pts_luref)
    a, b = pts_luref[idx_voirie], pts_luref[(idx_voirie + 1) % n]
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    nx, ny = edge_inward_normal(pts_luref, idx_voirie, centroid)
    return max((nx * (p[0] - mid[0]) + ny * (p[1] - mid[1])) for p in pts_luref)


def calculer_palladio_full(
    parcel_geometry_wgs84: Dict[str, Any],
    point_geocode_wgs84: List[float],
    recul_avant_m: float,
    recul_lateral_m: float,
    recul_arriere_m: float,
    zone_pag: Optional[Dict[str, Any]] = None,
    profondeur_max_m: Optional[float] = None,
    parcelle_id: Optional[str] = None,
    corriger_hab1: bool = False,
) -> Dict[str, Any]:
    """
    Endpoint metier complet Sprint 2 : enveloppe + voirie + SCB + logements
    + parkings + type construction + warnings. Palladio v0.3.

    Ne leve PAS d'erreur sur enveloppe degeneree : retourne une reponse
    structuree avec warning ENVELOPPE_VIDE (cas test 8). Tolere zone_pag
    absente (commune sans PAG, cas test 9) via defauts surs.

    Returns:
        dict JSONifiable : meta + tout l'output /calcul + scb + logements
        + parkings + type_construction + warnings.
    """
    zone_pag = zone_pag or {}

    # ---- 1. Enveloppe + voirie (reutilise tout le Sprint 1/1.5) ----
    enveloppe_vide = False
    base = None
    try:
        base = calculer_emprise_palladio(
            parcel_geometry_wgs84=parcel_geometry_wgs84,
            point_geocode_wgs84=point_geocode_wgs84,
            recul_avant_m=recul_avant_m,
            recul_lateral_m=recul_lateral_m,
            recul_arriere_m=recul_arriere_m,
            profondeur_max_m=profondeur_max_m,
            parcelle_id=parcelle_id,
        )
    except PalladioError as e:
        enveloppe_vide = True
        base_error = str(e)

    # Cas enveloppe degeneree : reponse structuree, pas de 500
    if enveloppe_vide:
        # On tente quand meme de reconstruire la parcelle pour les warnings geometrie
        try:
            ring_wgs = _normalize_ring(parcel_geometry_wgs84["coordinates"][0])
            nb_sommets = len(ring_wgs)
        except Exception:
            nb_sommets = 0
        warnings = generate_warnings(
            edges_classified=[], idx_voirie=0, all_voirie_edges=[],
            parcelle_nb_sommets=nb_sommets, type_construction={"type": "indetermine"},
            zone_pag=zone_pag, enveloppe_vide=True)
        return {
            "meta": {"engine": "palladio", "version": "0.3", "method": "full",
                     "enveloppe_vide": True, "error": base_error},
            "parcelle": {"nb_sommets": nb_sommets, "id": parcelle_id},
            "scb": None, "logements": None, "parkings": None,
            "type_construction": {"type": "indetermine", "method": "enveloppe_vide"},
            "warnings": warnings,
            "enveloppe": base,
        }

    # ---- 2. SCB ----
    emprise_au_sol = base["emprise"]["surface_m2"]
    surface_terrain = base["parcelle"]["surface_cadastrale_m2"]
    scb = calculate_scb(emprise_au_sol, zone_pag, surface_terrain_net_m2=surface_terrain)

    # ---- 3. Logements ----
    logements = calculate_logements(
        scb_totale_m2=scb["scb_totale_m2"],
        surface_habitable_m2=scb["surface_habitable_m2"],
        emprise_au_sol_m2=emprise_au_sol,
        zone_pag=zone_pag,
        surface_terrain_m2=surface_terrain,
        corriger_hab1=corriger_hab1,
    )

    # ---- 4. Parkings ----
    parkings = calculate_parkings(
        logements["mix_detail"],
        scb_commerce_m2=logements["scb_commerce_m2"],
    )

    # ---- 5. Type de construction (proxy cadastral) ----
    edges_classified = base["voirie"]["detection"].get("edges_classified", [])
    all_voirie_edges = base["voirie"]["detection"].get("all_voirie_edges", [])
    idx_voirie = base["voirie"]["idx"]
    idx_fond = base["fond"]["idx"]
    type_construction = detect_construction_type(edges_classified, idx_voirie, idx_fond)

    # ---- 6. Warnings ----
    pts_luref = base["parcelle"]["geometry_luref"]["coordinates"][0]
    pts_luref = _normalize_ring(pts_luref)
    prof_dispo = _profondeur_disponible(pts_luref, idx_voirie)
    prof_insuffisante = prof_dispo < (recul_avant_m + recul_arriere_m + PROFONDEUR_MARGE_M)
    warnings = generate_warnings(
        edges_classified=edges_classified,
        idx_voirie=idx_voirie,
        all_voirie_edges=all_voirie_edges,
        parcelle_nb_sommets=base["parcelle"]["nb_sommets"],
        type_construction=type_construction,
        zone_pag=zone_pag,
        enveloppe_vide=False,
        profondeur_insuffisante=prof_insuffisante,
        voirie_edge_label=base["voirie"]["edge_label"],
    )

    # ---- 7. Assemblage ----
    return {
        "meta": {
            "engine": "palladio",
            "version": "0.3",
            "method": "full",
            "enveloppe_vide": False,
            "hab1_corrige": corriger_hab1,
        },
        "parcelle": base["parcelle"],
        "voirie": base["voirie"],
        "fond": base["fond"],
        "reculs_appliques": base["reculs_appliques"],
        "emprise": base["emprise"],
        "traces_reculs": base["traces_reculs"],
        "scb": scb,
        "logements": logements,
        "parkings": parkings,
        "type_construction": type_construction,
        "profondeur_disponible_m": round(prof_dispo, 1),
        "warnings": warnings,
    }
