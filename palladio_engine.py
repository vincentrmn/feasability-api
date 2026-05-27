"""
PALLADIO ENGINE v0.1
====================

Moteur d'enveloppe constructible 2D. Sprint 1 de la nouvelle generation Terravalu.

Strategie : remplacer a terme le moteur v2.3 (OBB + reculs alignes) qui deborde
sur parcelles obliques. Palladio s'aligne sur la geometrie cadastrale reelle
(buffer Shapely + half-planes), garanti zero debordement.

Hors perimetre Sprint 1 :
  - SCB, hauteurs, niveaux, logements, parkings (Sprint 2, recycle depuis main.py)
  - 3D, GLB, TopoExport (mis de cote)
  - Servitudes, biotopes, zones inondables (Sprint 3)

Input principal : polygone parcelle WGS84 + point geocode + reculs depuis Airtable.
Output principal : polygone enveloppe N-coins en LUREF + WGS84 + surface m2.

Portage depuis :
  - algo_v4.py (compute_enveloppe_v4, half_plane_interior, find_limite_voirie, scoring fond)
  - algo_v5.py (idem v4 avec profondeur max + traces)

Valide sur 3 parcelles reelles (briefing v5 24/04/2026) :
  - 5 Tilleuls Strassen (133/2970) : 366 m2 attendu
  - 7 Tilleuls Strassen (133/2971) : 327 m2 attendu
  - 11 Tilleuls Strassen (133/2973) : 259 m2 attendu
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


# ============================================================
# HELPERS GEOMETRIQUES (porte tel quel de algo_v4)
# ============================================================

def find_limite_voirie(pts: List[List[float]], voirie_point: List[float]) -> int:
    """
    Identifie l'arete de la parcelle la plus proche du point geocode.
    Heuristique simple, sous-optimale sur parcelles allongees (cf. 11 Tilleuls),
    mais l'enveloppe reste legale meme si l'orientation est sous-optimale.
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
# CALCUL ENVELOPPE (porte de algo_v4.compute_enveloppe_v4)
# ============================================================

def _compute_enveloppe_unique(pts: List[List[float]], idx_voirie: int, idx_fond: int,
                               ra: float, rl: float, rr: float,
                               prof_max: Optional[float] = None) -> Tuple[Polygon, List[Dict]]:
    """
    Calcule l'enveloppe pour une combinaison (voirie, fond) donnee.
    Pipeline :
      1. buffer(-rl) latera uniforme (mitre, gere les coins)
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
        # Prendre le polygone le plus grand
        geom = max(geom.geoms, key=lambda g: g.area)
    if not hasattr(geom, 'exterior'):
        return None
    coords = list(geom.exterior.coords)
    if len(coords) < 4:
        return None
    # Drop closing point (GeoJSON-like, on retourne ouvert puis on fermera au serialize)
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
) -> Dict[str, Any]:
    """
    Calcule l'enveloppe constructible 2D d'une parcelle cadastrale.

    Args:
        parcel_geometry_wgs84 : GeoJSON Polygon en WGS84 (lon, lat).
            Ex : {"type": "Polygon", "coordinates": [[[lon, lat], ...]]}
        point_geocode_wgs84 : [lon, lat] WGS84, identifie la voirie.
        recul_avant_m : distance min depuis l'arete voirie (en metres).
        recul_lateral_m : distance min depuis les aretes laterales.
        recul_arriere_m : distance min depuis l'arete fond.
        profondeur_max_m : optionnel, profondeur max totale depuis voirie
            (NB : recul_avant + profondeur_max_m mesures depuis la voirie).
        top_k_fond : nombre de candidats arete-fond a tester.

    Returns:
        dict prêt a JSONifier avec :
        - meta : version, methode
        - parcelle : geometrie en LUREF + WGS84, surface cadastrale, nb sommets
        - voirie : idx arete + label + methode detection
        - fond : idx + label + score + candidats top-k (avec surface chacune)
        - reculs_appliques : ce qui a ete utilise
        - emprise : geometry GeoJSON LUREF + WGS84, surface m2, nb sommets,
                    ratio vs COS theorique si fourni
        - traces_reculs : liste des reculs par arete pour debug Jour 3

    Raises:
        PalladioError : input invalide (polygone < 3 sommets, reculs negatifs,
                        enveloppe degeneree).
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

    # ---- Detection voirie ----
    idx_voirie = find_limite_voirie(pts_luref, pt_geo_luref)

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
    if ratio_vs_cadastrale < 0.10:
        # Pas une erreur : on previent juste, on n'echoue pas (briefing : "complexe / archi" Sprint 4+)
        pass

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
            "version": "0.1",
            "method": "shapely_buffer_halfplanes_v5",
        },
        "parcelle": {
            "geometry_luref": {
                "type": "Polygon",
                "coordinates": [_close_ring([list(p) for p in pts_luref])],
            },
            "geometry_wgs84": parcel_geometry_wgs84,
            "surface_cadastrale_m2": round(surface_cadastrale_m2, 1),
            "nb_sommets": n_sommets,
        },
        "voirie": {
            "idx": idx_voirie,
            "edge_label": idx_voirie_label,
            "method": "geocode_proximity",
            "point_luref": [round(pt_geo_luref[0], 2), round(pt_geo_luref[1], 2)],
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
