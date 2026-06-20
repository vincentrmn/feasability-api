# Architecture — Feasibility.lu / Palladio

> État au 2026-06-20, après retrait du legacy OBB v2.3. Document de référence du flux.

## Vue d'ensemble

Une étude de faisabilité = un parcours : **adresse → géométrie cadastrale → règles
d'urbanisme → enveloppe constructible → SCB / logements / parkings → page HTML**.
L'orchestration est dans n8n ; le calcul dans une API FastAPI (Railway) ; les règles
dans Airtable ; les géodonnées chez geoportail.lu.

```
Utilisateur (navigateur)
   │  GET /webhook/palladio/calcul?address=...
   ▼
n8n  «Palladio»  (XFOhmez4MtTnmtnL, Railway n8n-production-8929d)
   │  Webhook Calcul
   ├─ Geocodage v4 ............ apiv4.geoportail.lu  → parcel_key, lon/lat
   ├─ Parcelle 359 ............ features.geoportail.lu/collections/359
   ├─ Zone PAG 698/28 ......... features.geoportail.lu/collections/698/28  → code_zone
   ├─ Lookup Rules Airtable ... base appFUtt83fMC6NwgU / table Zones_PAG
   ├─ Build Palladio Payload .. (Code) mappe Airtable → payload + contexte + methode recul
   ├─ Calcul Palladio ......... POST web-production-afd8d/palladio/calcul/full/html
   ├─ Assemble Palladio Page .. (Code) passe-plat : récupère le HTML renvoyé
   └─ Respond JSON ............ renvoie le HTML (text/html)
```

## API FastAPI (`web-production-afd8d.up.railway.app`)

Déployée depuis ce repo (branche `main`, auto-deploy Railway, healthcheck `/health`).

| Fichier | Rôle |
|---|---|
| `main.py` | App FastAPI minimale : CORS, `GET /`, `GET /health`, `include_router(palladio_api)`. ~60 lignes. |
| `palladio_api.py` | Contrat HTTP : modèles `PalladioRequest`/`PalladioFullRequest` + 3 routes. Aucune logique métier. |
| `palladio_engine.py` | **Le moteur** : enveloppe (reculs + voirie cadastrale + mitoyenneté bâtie + recul avant adaptatif), SCB, logements, parkings, type construction, warnings. |
| `palladio_render.py` | Génère la page HTML pédagogique (9 étapes + schémas SVG) depuis la réponse moteur. |

### Routes
- `POST /palladio/calcul` — enveloppe + voirie (Sprint 1/1.5), JSON.
- `POST /palladio/calcul/full` — enveloppe + SCB + logements + parkings + warnings, JSON.
- `POST /palladio/calcul/full/html` — idem + **rendu HTML** (consommé par n8n).
- `GET /` , `GET /health` — smoke test / statut.

Legacy retiré le 2026-06-20 : moteur OBB v2.3, routes `/calcul` et `/v2/calcul`,
workflows n8n `MVP Feasibility Luxembourg` + `Terravalu draft` (désactivés). Historique git.

## Le recul avant adaptatif (cœur Palladio Scrap)

Chaque commune encode le recul avant différemment. Le moteur dispatche selon
`recul_avant_methode.type` (fourni par Airtable via n8n) :
- `fixe` → scalaire réglementaire.
- `lie_hauteur` → `coef × corniche`, planché.
- `alignement_voisins` → **médiane des façades des bâtiments voisins en vis-à-vis**
  (collection bâtiments 2214), fallback chiffré si aucun voisin. `recul_avant_adaptatif`
  est renvoyé dans la réponse (méthode + valeur + source article) pour l'affichage.

## Données

- **Airtable** base `appFUtt83fMC6NwgU`, table `Zones_PAG` (`tbll7YFXuR9ug1brF`) :
  une ligne par (Commune, Code_zone, Regime). Champs typés Palladio Scrap :
  `Methode_recul_avant`, `Recul_avant_fallback_m`, `Bande_construction_max_m`,
  `Hauteur_modele`, `Logements_modele`, `Source_articles_json`, `Confiance`…
  Source de vérité versionnée : `palladio_scrap/communes/*.json` ; schéma : `palladio_scrap/SCHEMA.md`.
- **geoportail.lu** : géocodage (apiv4), parcelles (359), PAG (698/28), bâtiments (2214).

## Palladio Scrap (alimentation des règles)

Pipeline d'acquisition/normalisation des règlements communaux (PAG / PAP QE / RBVS,
en PDF) vers Airtable. Voir `PALLADIO_SCRAP_BRIEFING.md`. Extraction texte fidèle
(`pdftotext`/`pdf→md` → LLM) ; vision réservée aux parties graphiques (casier NQ).
Prompts : `palladio_scrap/prompts/`. Script de sync : `palladio_scrap/airtable_sync.py`.

## Tests (hors réseau)

- `palladio_scrap/test_alignment.py` — dispatch recul avant + alignement (géométrie pure).
- `palladio_scrap/test_render.py` — parité du rendu HTML sur une réponse moteur réelle.
- `palladio_scrap/test_contract.py` — **garde-fou** : tout param moteur est câblé dans l'endpoint.

## Vérifier un déploiement

1. `GET /` doit lister les routes Palladio (`palladio_version`).
2. Via n8n : exécuter le workflow sur une adresse → la page HTML doit contenir
   `recul_avant_adaptatif` cohérent. Le conteneur de dev ne joint pas Railway
   (egress fermé) : la validation live passe par n8n ou le navigateur.
