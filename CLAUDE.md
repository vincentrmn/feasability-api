# CLAUDE.md — Palladio (Terravalu)

> Document destiné à Claude Code (et tout autre instance de Claude qui prend le relais sur Palladio).
> À lire **en entier** avant d'écrire la moindre ligne de code.
> Dernière mise à jour : 2026-06-17 — fin de Sprint 1.5.

---

## 1. Qui je suis et où je suis

Tu es Claude Code, en mission sur le repo `vincentrmn/feasability-api` (déployé sur Railway à `web-production-afd8d.up.railway.app`). Tu travailles pour **Vincent**, co-fondateur et CEO de **Terravalu** (Luxembourg). Tu n'es pas seul : Jules est co-fondateur dev, il possède la prod legacy (`main.py`). **Tu ne touches pas à `main.py`.** Tu travailles uniquement sur `palladio_engine.py`.

Vincent communique en **français informel et direct**. Il n'a pas de terminal local, tout passe par GitHub web UI et le HTML debug servi par n8n. **Aucun output terminal verbeux**, aucun étalage d'outils. Réponses courtes, dense quand il le demande, sans bla.

---

## 2. Le produit (ce que tu construis)

### 2.1. Vision long terme — Terravalu Intelligence
La vraie ambition c'est **Terravalu Intelligence** : une plateforme B2B/institutionnelle (banques, asset managers, promoteurs, public) — *le "Palantir du foncier et de la construction"*. International : Grande Région d'abord (LU, FR Lorraine, BE Wallonie, DE Sarre), puis Europe.

### 2.2. Le B2C est un vecteur de données, pas une fin
En 2026 le **B2C est gratuit** (étude de faisabilité offerte aux particuliers). Plus de tiers 79€/199€/799€ — c'est terminé. La monétisation passe par les **professionnels** (constructeurs, architectes, courtiers, agences) qui paient pour des leads qualifiés et des prises de RDV.

Le B2C sert à **collecter de la donnée comportementale** (qui cherche quoi, où, avec quels critères) qui alimentera Intelligence.

### 2.3. Sources de données pour Intelligence (priorité)
1. **Imagerie satellite** (Sentinel-1/2 gratuit, Planet/Maxar payant) — détection ML de l'activité de construction et des changements. **Plus prioritaire que le B2C** parce qu'exportable hors Luxembourg.
2. **B2C funnel gratuit** — données comportementales (low quality vs transactionnel, mais volume).
3. **Open data Luxembourg** — cadastre, PAG, permis de construire, AED, LISER.
4. **Scraping marché** — athome, immotop, presse.
5. **Données partenaires pros** — vrais devis, taux de conversion.

### 2.4. Première persona Intelligence
**Banques retail luxembourgeoises** — modélisation risque hypothécaire. C'est le persona à valider avant expansion.

### 2.5. Ne pas surinvestir
- **Pas dans le 3D engine** : strategic value zéro pour Intelligence. Reste 2D autant que possible.
- **Pas dans la précision OBB** : la précision absolue n'aide pas la modélisation B2B.

---

## 3. Stack technique

| Composant | Stack | Localisation |
|---|---|---|
| Moteur calcul | Python FastAPI | `vincentrmn/feasability-api` → Railway `web-production-afd8d.up.railway.app` |
| Orchestration | n8n | Railway `n8n-production-8929d.up.railway.app` |
| Base de règles | Airtable | `appFUtt83fMC6NwgU`, table zoning `tbll7YFXuR9ug1brF` |
| Frontend (prototypes) | Lovable | — |
| 3D assets | GitHub statique | `vincentrmn/terravalu-assets` |
| Documentation projet | Notion | Hub Projet Terravalu |

### 3.1. Repo `vincentrmn/feasability-api`
- `main.py` — **prod legacy**, ne pas toucher (sauf accord explicite de Vincent et Jules). Contient le pipeline complet v2.3 (OBB + reculs + SCB + logements + parkings).
- `palladio_engine.py` — **ton terrain**. Moteur nouvelle génération. Sprint 1 + 1.5 terminés. Sprint 2 à venir.
- `requirements.txt` — doit contenir au minimum : `fastapi`, `shapely`, `pyproj`, `requests`. Vérifier avant tout déploiement Sprint 1.5+.

### 3.2. Endpoints du moteur
- `GET /` — liste les routes FastAPI. **Sert de smoke test post-déploiement Railway**.
- `POST /palladio/calcul` — calcul enveloppe (Sprint 1 + 1.5). Documenté section 6.
- `POST /palladio/calcul/full` — **à créer Sprint 2** (enveloppe + SCB + logements + parkings + warnings).

---

## 4. Workflows n8n — ce qui se touche, ce qui ne se touche pas

### 4.1. Workflows INTOUCHABLES (prod legacy)
- `fNY7LUzIeBHutwcT` — workflow production legacy basé sur `main.py`. **NE JAMAIS TOUCHER.**
- `gdawiNp1oMoYcwAL` — draft legacy. **NE JAMAIS TOUCHER.**

### 4.2. Workflow Palladio actif
- `XFOhmez4MtTnmtnL` — **workflow Palladio**. Publié, version active `906e740c-6085-4673-9bdf-4aacdcac55bd` (Sprint 1.5, ajoute `parcelle_id` au payload).
- Webhook test (HTML form) : `https://n8n-production-8929d.up.railway.app/webhook/palladio`
- Webhook calcul : `https://n8n-production-8929d.up.railway.app/webhook/palladio/calcul?address=...`
- Pipeline : `Webhook → Extract Address → Geocodage v4 → Extract Geocoded → Parcelle 359 → Zone PAG 698-28 → Identify PAG Zone → Lookup Rules Airtable → Build Palladio Payload → Calcul Palladio → Assemble Debug JSON (HTML 7 schemas) → Respond JSON`

### 4.3. Procédure de modification d'un workflow n8n
Toujours dans cet ordre, **sans exception** :
1. `n8n:get_workflow_details` — récupérer l'état authoritatif avant modification.
2. `n8n:validate_workflow` — passer le code TypeScript SDK complet du workflow.
3. `n8n:update_workflow` — passer le **workflow complet** (pas de patch partiel sur un seul node, ça casse).
4. `n8n:publish_workflow` — activer la nouvelle version.

**Gotcha** : les gros strings HTML (>10KB) dans les `jsCode` peuvent casser le parsing si mal échappés. Pattern validé : reconstruire le workflow complet via Python `json.dumps()` pour produire les strings échappées, puis embed directement dans le `.ts`. Le fichier `/home/claude/palladio_workflow.ts` (artifact des sessions précédentes) sert de référence si tu dois reconstruire.

---

## 5. Etat de Palladio engine

### 5.1. Sprint 1 — Enveloppe N-coins (DONE, v0.1)
- Méthode v5 *"architect method"* : `buffer(-recul_lateral)` pour les latéraux (gère naturellement les angles), demi-plans pour reculs avant/arrière, scoring 3-candidats fond via `profondeur × cos²(angle_voirie)`.
- Profondeur max mesurée comme building depth (ex : 6m recul avant + 14m max = 20m depuis bord parcelle).
- Validation : 5/7/11 rue des Tilleuls (Strassen). Pas de débordement sur parcelles obliques.
- Output : polygone N-coins LUREF + WGS84, surface m², ratio vs cadastrale, traces reculs.

### 5.2. Sprint 1.5 — Détection voirie cadastrale (DONE, v0.2)
Le gros morceau de ce qui vient d'être livré. **Lis attentivement ci-dessous, c'est crucial.**

#### Le problème résolu
La méthode héritée (`find_limite_voirie` = arête la plus proche du point géocodé) se trompait souvent sur parcelles complexes (angles, parcelles enclavées, parcelles avec arrière vers une rue secondaire). Vincent l'a vu sur le 5 rue des Tilleuls : l'ancien algo identifiait une mauvaise arête malgré le ratio géocode plausible.

#### La solution
**Détection par adjacence cadastrale** via Geoportail collection 359 (parcelles cadastrales) :
- Pour chaque arête de la parcelle, sonder un point à `3m` perpendiculaire vers l'extérieur.
- Tester si ce point tombe dans une parcelle voisine (récupérée par bbox).
- **Règle** :
  ```python
  PUBLIC_NATURES = {5038, 5043}
  is_voirie(edge) = (edge.voisin is None) or (edge.voisin.k_code_nature in PUBLIC_NATURES)
  ```

#### Codes `k_code_nature` Luxembourg
- `5024` / `5025` — résidentiel privé (mitoyenneté)
- `5038` — **espace public cadastré** (placette, esplanade, trottoir cadastré comme parcelle)
- `5043` — **vide cadastral domaine public** (chaussée cadastrée comme parcelle)
- `5007` / `5009` — terrains agricoles, naturels, divers privés
- `181/4` (et autres) — observés ponctuellement, à investiguer si croisés

**Au Luxembourg, les rues peuvent être cadastrées de DEUX manières** :
1. **Vide cadastral non-parcellisé** — pas de polygone voisin du tout au sondage. La règle "pas de voisin = voirie" suffit.
2. **Parcelle 5038 ou 5043** — la rue est elle-même une parcelle avec un `k_code_nature` public. Sans la règle PUBLIC_NATURES, l'algo classait à tort en "interne".

Le cas qui a fait tomber la première version de l'algo : **29/2523 Rue Pierre Federspiel, Strassen** — la rue est cadastrée comme parcelle `109/3467` (k_nature 5043) et un espace public latéral comme `29/2434` (k_nature 5038). Sans la règle PUBLIC_NATURES, on classait CD en interne et l'algo échouait.

#### Cas validés (4)
| Parcelle | Adresse | Voirie détectée | Méthode validée |
|---|---|---|---|
| 133/2970 | 5 rue des Tilleuls, Strassen | BC (~5.2m via vide cadastral) | aucun voisin au sondage |
| 133/2971 | 7 rue des Tilleuls, Strassen | AB (~10.2m via vide cadastral) | aucun voisin au sondage |
| 100/2949 | Strassen (parcelle d'angle) | 9 arêtes voirie (~50m total) | parcelle d'angle, multi-arêtes vide |
| 29/2523 | Rue Pierre Federspiel, Strassen | **CD (~14.7m via voisin 5038)** | **règle PUBLIC_NATURES déterminante** |

#### Architecture du module Sprint 1.5 dans `palladio_engine.py`
```
CONSTANTES (haut du fichier)
  PUBLIC_NATURES = {5038, 5043}
  PROBE_DISTANCE_M = 3.0
  BBOX_MARGIN_DEG = 0.001
  GEOPORTAIL_359_URL = "https://features.geoportail.lu/collections/359/items"
  NEIGHBORS_HTTP_TIMEOUT_S = 8

FONCTIONS PUBLIQUES Sprint 1.5
  fetch_neighbors_359(bbox_wgs84, exclude_id, timeout)
    → list[dict] avec id, k_code_nature, poly_luref
    → liste vide en cas d'échec (fallback safe)
  
  detect_voirie_by_adjacency(parcelle_poly_luref, voisines, probe_dist=3.0)
    → list[dict] : une entrée par arête avec is_voirie, motif, voisin_id, voisin_nature
  
  select_voirie_edge_from_classification(edges_classified, point_geocode_luref=None)
    → dict avec selected_idx, all_voirie_edges, fallback_used

FALLBACK (interne)
  _detect_voirie_with_fallback(...)
    Cascade :
      1. parcelle_id absent → find_limite_voirie (mode legacy)
      2. parcelle_id présent + API Geoportail OK + voisines fetched → Sprint 1.5
      3. API Geoportail KO ou voisines vides → fallback geocode
      4. exception inattendue → fallback geocode
```

#### Contrat retour `voirie` enrichi
```json
{
  "voirie": {
    "idx": 2,
    "edge_label": "CD",
    "method": "cadastral_adjacency_v0.2",
    "point_luref": [x, y],
    "detection": {
      "selected_idx": 2,
      "method": "cadastral_adjacency_v0.2",
      "edges_classified": [
        { "idx": 0, "label": "AB", "p1": [x,y], "p2": [x,y], "length_m": 4.18,
          "mid": [x,y], "normal": [nx,ny], "probe_point": [x,y],
          "voisin_id": "114B00029002350", "voisin_nature": 5025,
          "is_voirie": false, "motif": "interne via voisin prive (k_nature=5025)" },
        ...
      ],
      "all_voirie_edges": [2],
      "fallback_used": null,
      "n_neighbors_fetched": 18,
      "n_neighbors_public": 3
    }
  }
}
```

#### Payload n8n vers `/palladio/calcul` (mis à jour Sprint 1.5)
Le node "Build Palladio Payload" envoie maintenant :
```js
const payload = {
  parcelle_id: geo.parcel_key,         // ← AJOUT Sprint 1.5
  parcel_geometry_wgs84: parcelGeom,
  point_geocode_wgs84: [geo.lon_wgs84, geo.lat_wgs84],
  recul_avant_m: ...,
  recul_lateral_m: ...,
  recul_arriere_m: ...,
  profondeur_max_m: ...,
};
```

#### HTML debug — Schema 03 enrichi
Le node "Assemble Debug JSON" affiche maintenant dans le schema 3 :
- Les arêtes voirie **en ambre `#c9a961`** (épaisses)
- Les arêtes internes en gris (fines)
- Caption : `Detection cadastrale: X arete(s) voirie sur N, soit Ym total. K voisines fetched (P publiques). OK / Fallback: ...`
- Bandeau supérieur : `voirie: cadastral_adjacency_v0.2` (ou `geocode_proximity_fallback`)

### 5.3. État courant (à la fin de Sprint 1.5)
- ✅ `palladio_engine.py` version `"0.2"` déployé sur Railway
- ✅ Workflow n8n `XFOhmez4MtTnmtnL` publié avec `parcelle_id` dans le payload
- ✅ HTML debug enrichi (schema 3 cadastral overlay + bandeau méthode)
- ✅ Fallback gracieux : si Geoportail down ou parcelle_id manquant → `find_limite_voirie` legacy

---

## 6. Contrat actuel `/palladio/calcul`

### Input
```json
{
  "parcelle_id": "114B00029002523",
  "parcel_geometry_wgs84": { "type": "Polygon", "coordinates": [[[lon, lat], ...]] },
  "point_geocode_wgs84": [lon, lat],
  "recul_avant_m": 6.0,
  "recul_lateral_m": 3.0,
  "recul_arriere_m": 8.0,
  "profondeur_max_m": 14.0
}
```

`parcelle_id` est **optionnel** mais sans lui, le moteur retombe en mode `geocode_proximity`. La rétrocompat est totale.

### Output (résumé)
```
meta { engine, version: "0.2", method }
parcelle { geometry_luref, geometry_wgs84, surface_cadastrale_m2, nb_sommets, id }
voirie { idx, edge_label, method, point_luref, detection { ... } }
fond { idx, edge_label, candidats: [{ idx_fond, fond_label, score_fond, surface_emprise_m2 }] }
reculs_appliques { avant_m, lateral_m, arriere_m, profondeur_max_m }
emprise { geometry_luref, geometry_wgs84, surface_m2, nb_sommets, ratio_vs_cadastrale }
traces_reculs [ { idx, from, to, cat, distance_m } ]
```

---

## 7. Méthode de travail avec Vincent — IMPORTANT

### 7.1. Style de communication
- **Direct, court, prose**. Pas de bullet points par défaut. Pas de "Voici ce que je vais faire" ou "Si vous voulez". Réponse → action.
- **Français informel** sur produit et stratégie. Anglais OK pour code et termes techniques.
- **Vincent peut être agacé**. Réponds plus court si ça pète, pas plus long.
- **Ne jamais expliquer comment tu vas utiliser un outil**. Tu l'utilises, point.
- **Pas d'output terminal verbose**. Si tu dois faire un calcul ou un test, fais-le en silence et reporte le résultat seul.

### 7.2. Workflow Vincent
- Pas de terminal local. Tout via GitHub web UI (édit en place du fichier).
- Test via **HTML debug du webhook n8n**, jamais via curl ou Postman. Il ouvre l'URL dans son navigateur, regarde les schemas.
- Tu lui livres généralement **un seul fichier complet à coller** — pas de patch partiel sauf demande explicite.

### 7.3. Principes de modification
- **Strategy before code** : valide visuellement (prototype matplotlib, ou raisonnement clair) avant tout déploiement.
- **Surgical changes only** : une modification ciblée à la fois. Pas de réécriture massive.
- **Une seule chose en cours à la fois**. Tu ne livres pas le Sprint 2 et un patch en parallèle.
- **Test sur cas réels** avant de déclarer "done". 3-4 parcelles minimum couvrant plusieurs typologies.

### 7.4. Quand tu te plantes
- **Reconnais-le clairement, sans grimace**. Vincent a déjà vu ça.
- **Diagnostic court**, fix, ne pas tourner autour du pot.
- **Pas d'auto-flagellation**. Une phrase "tu as raison, voilà le fix" suffit.

### 7.5. Briefings de fin de session
Vincent attend des `.md` exhaustifs à la fin de chaque sprint majeur pour la continuité Claude → Claude. Voir `TERRAVALU_SPRINT2_BRIEFING.md` comme modèle.

---

## 8. Apprentissages durs (lis ça avant de coder)

### 8.1. Algorithme enveloppe (Sprint 1)
- **Les coefficients COS/CUS seuls ne prédisent jamais la constructibilité**. La géométrie de la parcelle + reculs obligatoires empêche souvent d'atteindre le théorique (parcelles triangulaires, L-shape, drapeau, angles).
- **Pour parcelles complexes : retourner un range min/max/médiane** (top-3 candidats fond testés), pas un chiffre unique. "Consulter un architecte" est un CTA de conversion permanent, pas un signal d'erreur.
- **`buffer(-recul_lateral)`** est la bonne primitive pour les latéraux : gère naturellement les coins en mitre, garantit zéro débordement.
- **Les demi-plans infinis** sont utilisés pour avant/arrière seulement, sur les arêtes voirie et fond identifiées.
- **Profondeur max = `recul_avant + profondeur_max_m`** mesurée depuis la limite voirie, pas depuis le recul avant.

### 8.2. Détection voirie (Sprint 1.5)
- **Ne jamais supposer que proximité physique d'une rue = adjacence voirie cadastrale**. Cas Federspiel : la parcelle est physiquement face à la rue mais cadastralement, une bande tampon privée (29/3457) s'interpose côté sud → seule l'arête CD (vers l'espace public 29/2434) est vraie façade.
- **Toujours valider la détection sur ≥ 3 parcelles réelles** avant de conclure qu'un algo est correct. Une parcelle qui marche ne valide rien.
- **Le format `parcel_key` de Geoportail** : commune (3 chiffres) + section (lettre) + hauptnummer zero-padded 5 + zweitnummer zero-padded 7 (ex : `114B00029002523`).
- **Geoportail collection 359 bbox query** requiert le header CRS explicite : `bbox-crs: http://www.opengis.net/def/crs/OGC/1.3/CRS84`. Sans ça, retour 400.
- **La collection 359 ne retourne PAS la surface cadastrale officielle** dans les properties. Calculer en LUREF via Shoelace. Écart ~1% attendu.

### 8.3. Erreurs que j'ai faites (à NE PAS refaire)
- **Recopier à la main une géométrie depuis un retour JSON** = perte de précision décimale = mitoyennetés cassées = faux positifs voirie. Toujours laisser le moteur appeler l'API directement, ne JAMAIS hardcoder des coords sources.
- **Oublier le passage de `parcelle_id` dans le payload n8n** alors que le moteur le supportait → moteur retombe silencieusement en mode legacy → Vincent voit "rien n'a changé" alors que c'est déployé. La rétrocompat est une bénédiction et une malédiction.
- **Charger trop de gros JSON dans le contexte au lieu de filtrer** côté analyse. Si Vincent paste un bbox 117 features, ne pas tout réafficher : extraire ce qui est pertinent et travailler dessus.
- **Avoir un raisonnement faux mais "plausible"** sur une parcelle complexe et le défendre. Cas Federspiel : j'ai initialement classé DE/EF comme voirie via `109/3467` à cause de mes données mal recopiées. Vincent a immédiatement dit "non, c'est CD". J'ai dû reconnaître l'erreur et corriger. **Quand Vincent voit la carte en face de lui et te dit que tu te trompes, il a raison.**
- **Étaler les outils dans la réponse** alors qu'il ne veut pas voir ça. Si je fais 5 tool calls pour une tâche, la réponse doit présenter le résultat, pas le journal.

### 8.4. Sur la calibration 3D / GLB (hérité, vraisemblablement Sprint 4+)
*Pour mémoire si on doit y revenir, **mais c'est hors scope Sprint 2** :*
- TopoExport centre le GLB sur le **coin sud-ouest du cadre d'export**, pas le centroïde.
- Formule : `V.lurefOffsetCx = cadre_SW_x`, `V.lurefOffsetCy = cadre_SW_y` (aucun averaging).
- Le cadre est un GeoJSON `cadre.geojson` (LineString fermée 5 points, axis-aligned).
- **GLB + parcels.geojson + cadre.geojson doivent provenir du même export TopoExport**, sinon calibration LUREF → world cassée.
- Convention naming sur `vincentrmn/terravalu-assets` : `strassen_11_rue_des_tilleuls.glb`, `strassen_11_rue_des_tilleuls_parcels.geojson`, `strassen_11_rue_des_tilleuls_cadre.geojson`.

---

## 9. Sprint 2 — Ce qu'il reste à faire (la suite)

**Objectif** : porter dans `palladio_engine.py` toute la logique métier que `main.py` v2.3 fait déjà (SCB, logements, parkings) + signalement façade courte, sans toucher `main.py`. Sortir Palladio v0.3.

Voir `TERRAVALU_SPRINT2_BRIEFING.md` (présent dans le projet Vincent) pour le détail complet. Résumé des 7 objectifs :

1. **Calcul SCB** (Surface Construite Brute) — `calculate_scb(enveloppe, zone_pag, pap_qe_rules)` → total + ventilation par niveau (RDC, R+1, ..., combles).
2. **Logements théoriques** — `calculate_logements(scb_total, zone_pag, type_construction)` → nb logements, surface moyenne, mix typologies si applicable. **Bug HAB-1 connu dans main.py** à investiguer.
3. **Parkings réglementaires** — `calculate_parkings(nb_logements, surfaces, zone_pag)` → intérieurs + extérieurs + vélos + surface estimée.
4. **Détection type construction** — `detect_construction_type(parcelle, voisines)` → `maison_isolee_4_facades` / `maison_jumelee` / `maison_mitoyenne_2_facades` / `bande`. Réutilise les voisines de Sprint 1.5. **Question ouverte** : source données bâti (collection Geoportail bâtiments ? TopoExport ? Airtable manuel ?).
5. **Warnings système** — `FACADE_RUE_COURTE` (< 8m), `PARCELLE_QUASI_ENCLAVEE` (< 5m), `PARCELLE_NON_RECTANGULAIRE`, `PROFONDEUR_INSUFFISANTE`, `JUMELAGE_DETECTE_SANS_DROITE`, `ENVELOPPE_VIDE`. Codes + level (info/warning/critique) + message FR/EN + arête concernée.
6. **HTML debug enrichi** — schemas 8 (SCB par niveau), 9 (logements + parkings), 10 (type construction), 11 (warnings).
7. **Endpoint `/palladio/calcul/full`** — séparé de `/palladio/calcul` (Sprint 1). `/full` = enveloppe + voirie + SCB + logements + parkings + warnings (~500-800ms vs ~200ms).

### Cas de test Sprint 2 (9)
| # | Parcelle | But |
|---|---|---|
| 1-3 | 11 / 5 / 7 rue des Tilleuls, Strassen | Non-régression vs main.py v2.3 (écart < 5%) |
| 4 | 29/2523 Rue Federspiel, Strassen | Trigger `FACADE_RUE_COURTE` (14.7m < 8m? non, mais à vérifier seuil) |
| 5 | 100/2949 (angle) Strassen | `type_construction = maison_isolee_4_facades` |
| 6 | À fournir | Zone HAB-2 (mix typologies) |
| 7 | À fournir | Zone MIX-c (commerce + habitation, parkings différents) |
| 8 | Artificielle ultra-étroite (<5m) | `ENVELOPPE_VIDE` + `PARCELLE_QUASI_ENCLAVEE` |
| 9 | Commune sans PAG post-2011 | Fallback gracieux, pas de 500 |

### DoD Sprint 2
- [ ] 5 nouvelles fonctions métier dans `palladio_engine.py`
- [ ] Endpoint `/palladio/calcul/full` live, `palladio_version: "0.3"`
- [ ] HTML debug : 4 nouveaux schemas
- [ ] Tests 1-3 (non-régression) : écart SCB et logements < 5% vs main.py
- [ ] Tests 4-7 : valeurs validées visuellement par Vincent
- [ ] Tests 8-9 : warnings déclenchés correctement, pas de 500
- [ ] Workflow `XFOhmez4MtTnmtnL` **non modifié** Sprint 2 (Sprint 3 fait la bascule)
- [ ] `main.py` non modifié
- [ ] Bug HAB-1 corrigé ou documenté

### Hors scope Sprint 2 (push Sprint 3+)
- Bascule prod (workflow → `/palladio/calcul/full`) → Sprint 3
- Suppression `main.py` → post-Sprint 3 après période d'observation
- 3D rendering frontend N-coins → priorité basse
- Détection bâti voisin via satellite Sentinel-2 → Terravalu Intelligence séparé
- Live edit bâtiment dans viewer 3D → Sprint 4+
- Onboarding nouvelles communes (scraping PDF) → besoin distinct
- Auth + Stripe → sprint produit séparé, post-pivot

---

## 10. Vision long terme et Intelligence (rappel rapide)

Sprint 3+ après bascule prod, on commence à construire **Terravalu Intelligence** en parallèle :
- Pipeline ML satellite Sentinel-1/2 (détection construction + changements)
- API B2B en marque blanche pour banques retail (modélisation risque hypothécaire)
- Expansion Grande Région : LU (fait), FR Lorraine, BE Wallonie, DE Sarre
- Persona prioritaire à valider en premier : banques retail luxembourgeoises

Tout ce que tu codes côté B2C alimente Intelligence ou est neutre. Si ça nuit à Intelligence (ex : sur-investissement 3D), c'est non.

---

## 11. Annexes — données utiles

### 11.1. Codes `k_code_nature` Luxembourg observés
| Code | Signification | Type |
|---|---|---|
| 5007 | Terrain agricole/naturel non bâti | privé |
| 5009 | Variante terrain | privé |
| 5024 | Résidentiel — type A (mitoyenneté) | privé |
| 5025 | Résidentiel — type B (mitoyenneté) | privé |
| **5038** | **Espace public cadastré (placette, esplanade, trottoir parcellisé)** | **public** ← PUBLIC_NATURES |
| **5043** | **Vide cadastral domaine public (chaussée parcellisée)** | **public** ← PUBLIC_NATURES |

Si tu croises un code non listé qui apparaît comme voisin d'une vraie voirie : investigue, et si confirmé, **ajoute à `PUBLIC_NATURES`**. Un patch one-liner.

### 11.2. Endpoints Geoportail utilisés
- `https://apiv4.geoportail.lu/geocode/search?queryString=...&returnParcelInfo=true` — géocodage avec `parcel.key` et `parcel.label`
- `https://features.geoportail.lu/collections/359/items/{parcel_key}?f=json` — détail d'une parcelle (geometry + properties incl. `k_code_nature`)
- `https://features.geoportail.lu/collections/359/items?bbox=lon_min,lat_min,lon_max,lat_max&bbox-crs=http://www.opengis.net/def/crs/OGC/1.3/CRS84&f=json&limit=400` — voisines par bbox (Sprint 1.5)
- `https://features.geoportail.lu/collections/698/28/items?bbox=...` — zones PAG (Plan d'Aménagement Général communal)

Documentation officielle : `https://apiv4.geoportail.lu/proj/1.0/build/apidoc/` — Vincent insiste pour s'y référer.

### 11.3. Airtable
- Base : `appFUtt83fMC6NwgU`
- Table zonage : `tbll7YFXuR9ug1brF` (champ `Commune` + `Code_zone` = clé composite)
- Champs PAG : `Recul_avant_min_m`, `Recul_avant_max_m`, `Recul_lateral_min_m`, `Recul_arriere_min_m`, `Profondeur_max_m`, `COS_max`, `CSS_max`, `Hauteur_corniche_max_m`, `Hauteur_faite_max_m`, `Nom_zone`, `PAP_QE`
- **Gotcha** : `filterByFormula` est case-sensitive. Wrap dans `LOWER()` des deux côtés défensivement. `alwaysOutputData: true` émet un item vide quand zéro match (silent failure si pas géré).

### 11.4. Coordonnées projection
- **WGS84** (EPSG:4326) — entrée user (lon, lat)
- **LUREF** (EPSG:2169) — calculs métriques. **Tous les calculs en LUREF, point.**
- Conversion via `pyproj.Transformer.from_crs("EPSG:4326", "EPSG:2169", always_xy=True)`
- À Strassen (lat ~49.6°N) : `1° lon ≈ 71km`, `1° lat ≈ 111km`. Un `BBOX_MARGIN_DEG = 0.001` ≈ 75-110m de chaque côté.

### 11.5. Notion workspace
Hub Projet Terravalu, 8 sub-spaces, 9 bases :
- **Backlog** (TV-prefixed)
- **Bugs** (BUG-prefixed)
- **Ideas**
- **Decision Log** (ADR-prefixed)
- **Risks**
- **Tools & Costs**
- **Pipeline commercial**
- **Réunions**
- **Discovery Notes**

Si tu décides quelque chose de structurel, log-le en ADR. Si tu trouves un bug en prod, log-le en BUG-XXX.

---

## 12. Checklist de démarrage pour Claude Code

Avant de toucher quoi que ce soit, vérifie dans cet ordre :

1. **Tu as lu ce CLAUDE.md en entier**. Si non, fais-le.
2. **Quelle est la tâche demandée par Vincent** ? (Sprint 2 entier ? Fix ciblé ? Question stratégique ?)
3. **Est-ce dans la zone safe ?** `palladio_engine.py` et workflow `XFOhmez4MtTnmtnL` → oui. `main.py`, workflows `fNY7LUzIeBHutwcT` / `gdawiNp1oMoYcwAL` → **non, demande confirmation explicite**.
4. **Y a-t-il déjà un briefing dédié à la tâche ?** Cherche dans le projet Vincent (`/mnt/project/` si Claude.ai, ou les fichiers `.md` du repo). `TERRAVALU_SPRINT2_BRIEFING.md` est ton point de départ Sprint 2.
5. **Quel est ton plan ?** Formule-le en interne en 3 étapes max. Si tu hésites, demande à Vincent en *une* question concise.
6. **Implémente surgicalement.** Une fonction, un test visuel, commit.
7. **Test sur ≥ 3 cas réels** avant de dire "done".
8. **Reporte en prose courte**. Pas de output journal verbeux.
9. **Si tu vas modifier un workflow n8n** : `get_workflow_details` → édition complète → `validate_workflow` → `update_workflow` → `publish_workflow`. Pas de patch partiel.
10. **À la fin de la session, mets à jour ce CLAUDE.md** (ou demande à Vincent de le faire) si tu as appris quelque chose de nouveau.

---

## 13. Commands & URLs utiles

```bash
# Smoke test moteur Railway
curl https://web-production-afd8d.up.railway.app/

# Test calcul direct
curl -X POST https://web-production-afd8d.up.railway.app/palladio/calcul \
  -H "Content-Type: application/json" \
  -d '{ "parcelle_id": "114B00133002970", "parcel_geometry_wgs84": {...}, ... }'

# HTML form n8n
open https://n8n-production-8929d.up.railway.app/webhook/palladio

# Tests rapides via shortcuts
open "https://n8n-production-8929d.up.railway.app/webhook/palladio/calcul?address=5%20rue%20des%20Tilleuls%2C%20Strassen"
open "https://n8n-production-8929d.up.railway.app/webhook/palladio/calcul?address=29%20rue%20Pierre%20Federspiel%2C%20Strassen"

# Référence doc Geoportail (Vincent insiste)
open https://apiv4.geoportail.lu/proj/1.0/build/apidoc/
```

---

## 14. Tone — comment finir une réponse

Pas de "N'hésite pas à demander si autre chose". Pas de "J'espère que ça t'aide". Si la tâche est faite, dis ce qui a été fait en deux phrases et stop. Si tu attends un input de Vincent, pose **une** question concise.

Exemple correct (fin de Sprint 1.5) :
> Patché et publié. Teste 5 rue des Tilleuls via le HTML form, tu devrais voir dans le bandeau `voirie: cadastral_adjacency_v0.2`. Si la méthode reste sur `geocode_proximity_fallback`, Railway n'a pas redéployé.

Exemple incorrect :
> ✅ Tout est patché et déployé ! 🎉 J'ai mis à jour le workflow n8n et le moteur Palladio est maintenant à jour. N'hésite pas à me dire si tu veux que je fasse autre chose ou si tu as des questions sur l'implémentation. Je reste à ta disposition. 😊

Tu vois la différence.

---

*Fin du document. Bonne session.*
