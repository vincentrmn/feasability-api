"""
FEASIBILITY.LU — API

Moteur Palladio (palladio_engine) exposé via palladio_api, rendu HTML par
palladio_render. Les règles d'urbanisme viennent d'Airtable via n8n.

Le moteur legacy OBB v2.3 (routes /calcul et /v2/calcul) a été retiré le
2026-06-20 : remplacé partout par Palladio, plus aucun consommateur actif
(workflows n8n legacy désactivés). Historique dans git si besoin.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from palladio_api import router as palladio_router

# Smoke test de la dispo pyproj (le moteur en a besoin) ; l'API démarre quand même.
try:
    from pyproj import Transformer  # noqa: F401
    _PYPROJ_OK = True
    _PYPROJ_ERROR = None
except Exception as _e:  # pragma: no cover
    _PYPROJ_OK = False
    _PYPROJ_ERROR = str(_e)

app = FastAPI(
    title="Feasibility.lu API",
    description="Moteur Palladio — faisabilité immobilière — Luxembourg",
    version="3.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(palladio_router)


@app.get("/")
def root():
    return {
        "service": "Feasibility.lu API",
        "version": "3.0.0",
        "palladio_version": "0.3.1",
        "endpoints": [
            "POST /palladio/calcul          (enveloppe + voirie cadastrale)",
            "POST /palladio/calcul/full     (enveloppe + SCB + logements + parkings + warnings, JSON)",
            "POST /palladio/calcul/full/html(idem, rendu HTML pédagogique)",
        ],
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "3.0.0",
        "pyproj_available": _PYPROJ_OK,
        "pyproj_error": _PYPROJ_ERROR,
    }
