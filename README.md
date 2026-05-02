# `main.py` — Feasibility.lu API (v2.3.0)

## 1. Mission du fichier

Une API HTTP qui calcule, pour une **parcelle au Luxembourg**, ce qui peut y être construit : emprise au sol, surface construite brute (SCB), nombre de logements, mix typologique, parkings, etc. Tout ça en appliquant la **réglementation luxembourgeoise** (RGD du 8 mars 2017, règlement du Plan d'Aménagement Général — *PAG*).

Le fichier contient **toute** l'application en monolithe : constantes réglementaires, géométrie, modèles, moteur de calcul, et endpoints HTTP.

## 2. Stack & exécution

- **Framework** : FastAPI + Pydantic v2, servi par uvicorn ([requirements.txt](requirements.txt))
- **Géo** : `pyproj` pour reprojeter WGS84 ↔ LUREF (EPSG:2169, le système de coordonnées luxembourgeois)
- **Déploiement** : Railway via Nixpacks ([railway.toml](railway.toml), [Procfile](Procfile))
- **CORS** : ouvert à `*` ([main.py:41-46](main.py#L41-L46)) — à durcir en prod
- **Tests** : un seul fichier, [test_emprise_polygon.py](test_emprise_polygon.py)

## 3. Plan du fichier (1388 lignes, 11 sections)

| Lignes | Section | Rôle |
|---|---|---|
| [1-46](main.py#L1-L46) | Imports & setup | FastAPI, CORS, import défensif de `pyproj` |
| [49-62](main.py#L49-L62) | **Constantes réglementaires** | Zones non-constructibles, ratio SCB→surface habitable (0.80), mix-type T1/T2/T3/T4+ |
| [65-260](main.py#L65-L260) | **Helpers géométriques** | Aire polygone (Shoelace), Oriented Bounding Box, calcul d'emprise rectangulaire |
| [263-495](main.py#L263-L495) | **v2.3 — Façade avant** | Détection du côté "rue" via point géocodé, emprise alignée OBB, conversion WGS84↔LUREF |
| [498-527](main.py#L498-L527) | **Modèles Pydantic** | `CalculRequestV2` (le bon) et `CalculRequestV1` (legacy) |
| [530-640](main.py#L530-L640) | **Mapping Airtable** | `map_airtable_to_regles()` + helpers `extract_airtable_value`, `parse_niveaux`, `parse_float` |
| [643-669](main.py#L643-L669) | Parkings | Calcul places voitures et vélos |
| [672-1284](main.py#L672-L1284) | **Moteur v2** `calculer_faisabilite_v2()` | Le gros morceau : 11 étapes de calcul |
| [1287-1342](main.py#L1287-L1342) | Moteur v1 | Rétrocompatibilité, données hardcodées pour Strassen |
| [1345-1388](main.py#L1345-L1388) | **Endpoints** | `GET /`, `GET /health`, `POST /calcul`, `POST /v2/calcul` |

## 4. Le moteur v2 en 11 étapes ([main.py:676-1284](main.py#L676-L1284))

C'est le cœur. Chaque étape ajoute du texte à `trace[]` (utile pour debug et UI).

0. **Constructibilité** — la zone est-elle bâtissable ? Sinon, court-circuit immédiat.
1. **Surface terrain net** — gère les cessions PAP NQ.
2. **Dimensions** — soit fournies, soit déduites du polygone via OBB, soit estimation carrée.
3. **Reculs** — avant / latéraux / arrière, avec règles spéciales "route Arlon" et formule `H_corniche/2`.
4. **Emprise au sol** — méthode 1 (par les reculs) vs méthode 2 (par le COS, *Coefficient d'Occupation au Sol*) → on prend le plus restrictif. Vérification CSS (*Coefficient de Scellement de Sol*).
5. **SCB** — Surface Construite Brute = emprise × niveaux + 60% des combles.
6. **Sous-sol** — emprise différenciée (reculs souvent plus permissifs).
7. **Programme logements** — selon zone résidentielle/mixte/activité, nombre de logements via SH ÷ moyenne.
8. **Mix** — T1 20% / T2 35% / T3 30% / T4+ 15% (ou T3 par défaut si ≤ 2 logements).
9. **Stationnement** — 1 à 3 places/logement selon SHN, +1 place/20m² commerce.
10. **Contraintes** — checklist optionnelle (zones inondables, etc.).
11. **Synthèse / Verdict** — Faible / Moyen / Fort.

## 5. Connexions externes

```
                 ┌─────────────┐
                 │  n8n (?)    │  workflow d'orchestration
                 └──────┬──────┘
                        │ POST /v2/calcul
                        ▼
   ┌──────────────────────────────────────┐
   │     Feasibility API (ce fichier)     │
   └──────────────────────────────────────┘
       ▲                              ▲
       │ règles PAG (champs)          │ point géocodé WGS84
       │                              │ + polygone parcelle
   ┌───┴────────┐              ┌─────┴────────────┐
   │  Airtable  │              │  Geoportail.lu   │
   │ Zones_PAG  │              │  (cadastre/géoc.)│
   └────────────┘              └──────────────────┘
```

- **Airtable** → format de la doctrine attendu via `regles_zone` dans le body. Le code [main.py:530-640](main.py#L530-L640) sait extraire les champs `singleSelect` Airtable (`{id, name, color}`) et tolère les valeurs textuelles ("2 par construction", "libre", "H corniche/2 (min 4m)", etc.). Les noms de champs côté Airtable sont en dur.
- **n8n** : mentionné en docstring ligne 3 mais **pas appelé depuis ce fichier** — c'est probablement n8n qui orchestre Airtable → API.
- **Geoportail Luxembourg** : pas appelé directement non plus. Le client (probablement le front Terravalu) fournit `parcelle_polygon_wgs84` et `point_geocode_wgs84` que l'API reprojette en LUREF avec `pyproj`.
- **Aucune base de données**, aucun cache, aucune auth. Stateless.

## 6. Endpoints exposés

| Méthode | Route | Usage |
|---|---|---|
| GET | `/` | Métadonnées |
| GET | `/health` | Healthcheck Railway, expose `pyproj_available` |
| POST | `/calcul` | **v1 legacy** — utilise les zones de Strassen hardcodées dans `ZONES_V1` |
| POST | `/v2/calcul` | **v2 actuel** — règles passées dans le body depuis Airtable |

## 7. Ce que tu dois savoir spécifiquement

### Architecture / dette technique
- **Tout est dans un fichier**. C'est le candidat n°1 au refactoring : séparer `routers/`, `services/calcul.py`, `geometry/`, `airtable/`, `models/`. La fonction `calculer_faisabilite_v2` fait à elle seule 600 lignes.
- **Aucune authentification**. CORS = `*`. Pour de la prod, il faudra a minima une clé API + un CORS restreint au domaine du front.
- **Pas de logging structuré** — uniquement des chaînes accumulées dans `trace[]` qui sont retournées dans la réponse JSON. Pas de monitoring, pas de tracking d'erreurs.
- **Tests quasi inexistants** : un seul fichier `test_emprise_polygon.py`. Le moteur métier (les 11 étapes) n'est pas couvert.
- **Versioning du fichier** : `version="2.3.0"` est dur dans 3 endroits différents. À centraliser.

### Conventions métier à connaître
- **LUREF (EPSG:2169)** = système de coordonnées projeté luxembourgeois, en mètres. C'est ce qui permet de calculer des distances réelles (alors que WGS84 est en degrés).
- **OBB (Oriented Bounding Box)** = boîte englobante alignée sur la parcelle, pas sur les axes Nord/Sud. Approche de l'algorithme : tester chaque arête comme axe candidat ([main.py:82-148](main.py#L82-L148)). C'est la base pour gérer des parcelles biscornues.
- **Acronymes du domaine** : SCB (Surface Construite Brute), SHN (Surface Habitable Nette), COS (Coeff. Occupation Sol), CSS (Coeff. Scellement Sol), CUS (Coeff. Utilisation Sol), DL (Densité Logements), PAP NQ (Plan d'Aménagement Particulier "Nouveau Quartier"), QE (Quartier Existant).
- Le `RATIO_SCB_TO_SH = 0.80` ([main.py:54](main.py#L54)) est une **hypothèse simplificatrice** — pas une règle juridique. À documenter pour les utilisateurs métier.

### Pièges techniques
- L'import de `pyproj` est entouré de try/except ([main.py:18-26](main.py#L18-L26)) : si `pyproj` n'est pas dispo, l'API démarre quand même mais les fonctionnalités géométriques v2.3 sont désactivées silencieusement. Vérifier `/health` pour voir l'état.
- Les fonctions `parse_float` / `parse_niveaux` ([main.py:549-582](main.py#L549-L582)) font des regex sur des chaînes textuelles fournies par Airtable. **Très fragile** : si un humain change un libellé dans Airtable, le calcul peut casser ou donner un résultat faux silencieusement.
- L'algorithme d'emprise en v2.3 documente lui-même ses **hypothèses** (parcelles en L mal gérées, orientation rue approximée) — voir docstring [main.py:151-186](main.py#L151-L186). C'est honnête mais ça veut dire que les résultats sont approximatifs sur certaines parcelles.
