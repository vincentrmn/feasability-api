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
