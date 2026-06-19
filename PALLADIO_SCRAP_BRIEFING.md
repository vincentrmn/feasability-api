# PALLADIO SCRAP — Briefing de mission

> Mission parallèle à Palladio engine. Objectif : alimenter automatiquement la base
> de règles d'urbanisme (Airtable) à partir des règlements communaux luxembourgeois,
> pour passer de 1 commune (Strassen) à la Grande Région puis au pays.
> À lire en entier avant de coder. Rédigé 2026-06-17 après analyse des 3 règlements de Strassen.

---

## 0. TL;DR

- Chaque commune luxembourgeoise possède **3 règlements** qui, ensemble, décrivent ce qu'on peut construire : **PAG** (zonage + coefficients), **PAP Quartier Existant** (prescriptions dimensionnelles du tissu bâti), **RBVS** (règles techniques + stationnement dimensionnel). Ils sont **publics**.
- Faisable techniquement : l'extraction LLM des 3 PDF a déjà été testée avec succès sur Strassen.
- **Coût API négligeable** : ~0,70 $/commune (Sonnet 4.6 + Batch), soit **~70 $ pour ~100 communes** en une passe ; quelques centaines d'€ avec passes de re-extraction + Opus sur les parties délicates.
- **Le vrai coût = ingénierie + validation humaine**, pas les tokens.
- **Risque n°1** : beaucoup de PAP QE sont **contextuels** (« aligne-toi sur les voisins ») et **non réductibles** à une ligne de valeurs fixes. Strassen est un cas facile (valeurs fixes). Ne pas généraliser sans gérer ce cas.
- **Approche recommandée** : (1) enrichir Strassen comme cas de référence, (2) semi-automatique sur 10-15 communes Grande Région (LLM extrait → humain valide), (3) industrialiser.

---

## 1. Contexte & rattachement stratégique

Cette donnée est la **source open-data #3** de Terravalu Intelligence (cadastre / PAG / permis / AED / LISER). Elle est exportable et réutilisable au-delà du B2C. Le moteur Palladio (`palladio_engine.py`) consomme ces règles via Airtable pour calculer la faisabilité. Aujourd'hui **seule Strassen** est renseignée, à la main. Palladio Scrap industrialise ce remplissage.

**Ne pas confondre** avec la *géométrie* PAG (limites de zones), déjà disponible en machine sur `geoportail.lu` (collection OGC Features 698) et déjà utilisée par le moteur. Palladio Scrap récupère la **partie écrite** (les règles chiffrées), qui n'est publiée qu'en **PDF**.

---

## 2. Les 3 documents et ce que chacun apporte

### 2.1. PAG — Plan d'Aménagement Général (partie écrite)
- **Rôle** : zonage (HAB-1, HAB-2, MIX-u, MIX-v, ECO, COM, zones vertes…) + degré d'utilisation du sol.
- **Apport chiffré réel** : COS / CSS / CUS / DL (densité log/ha), et **parts minimales de SCB-logement** par zone, **mais — point capital — uniquement pour les zones "nouveau quartier" (NQ)**, via un *casier graphique* par sous-périmètre. Pour le **tissu existant (QE), le PAG ne donne PAS de COS/CUS/CSS**.
- **Méthode** : le PAG **délègue 100 % du dimensionnel** (reculs, hauteurs, profondeurs, niveaux) au **PAP QE** (existant) et au **PAP NQ** (nouveaux quartiers).
- **Définitions normatives** (Annexe Terminologie, renvoie au RGD du 8 mars 2017) : SCB, CUS (**pondération ×2 si niveau 5-10 m, ×3 si >10 m**), COS, CSS, terrain à bâtir brut vs net, surface non-aménageable, surface habitable nette.
- **Zones superposées / servitudes** : PAP NQ, **zone d'aménagement différé** (gel de constructibilité), servitudes urbanisation, couloirs réservés, secteurs protégés « environnement construit », zone à risques, zone de bruit, Natura 2000, zones inondables. **Ces servitudes peuvent rendre une parcelle inconstructible.**
- **Stationnement** : le barème quantitatif réel est **ici** (PAG Art. 10), pas dans le RBVS.

### 2.2. PAP « Quartier Existant » (PAP QE) — partie écrite
- **Rôle** : **les prescriptions dimensionnelles du tissu bâti existant** — c'est le document qui gouverne le B2C (parcelles déjà dans un quartier).
- Découpe le territoire en **secteurs** (à Strassen : QE1→QE7) **mappés 1:1 sur les zones PAG**.
- **Apport chiffré** : reculs (avant/latéral/arrière, min ET max), profondeur de construction hors-sol ET sous-sol, reculs sous-sol distincts, hauteurs (corniche/faîte/acrotère), nombre de niveaux pleins + combles, type d'implantation, COS/CSS (puisque le PAG n'en donne pas pour le QE), nb de logements / construction, parts logement.
- **⚠️ Méthode variable selon commune** : Strassen donne des **valeurs FIXES** par secteur → réductible à une ligne Airtable. **D'autres communes donnent des règles CONTEXTUELLES** (« recul = alignement sur les constructions voisines », « profondeur = moyenne du voisinage », « hauteur = celle des immeubles contigus »). Ces dernières **ne sont pas réductibles** à des scalaires : il faut les détecter et les marquer comme « contextuel » plutôt que d'inventer une valeur.

### 2.3. RBVS — Règlement sur les Bâtisses, les Voies publiques et les Sites
- **Rôle** : règles techniques/qualitatives + habitabilité + voirie + chantier.
- **Apport** : **dimensions** d'emplacement de parking (≈12,5 m²/place + bande 6 m, 2 m²/vélo) → convertir un *nombre* de places en *surface*. Surfaces minimales (logement ≥ 30 m²), surfaces de servitude (local ordures 1,5 m²/100 m² SCB, buanderie, rangement, espaces extérieurs 6 m²/logement), hauteurs sous plafond, % toiture végétalisée, bornes de recharge, etc.
- **N'apporte PAS** les ratios de parking (délégués au PAG) ni les définitions de SCB/hauteurs (renvoi au RGD 2017).

---

## 3. Schéma Airtable cible (enrichi)

Base `appFUtt83fMC6NwgU`, table zonage `tbll7YFXuR9ug1brF`. Champs **actuels** conservés. Champs **à ajouter** marqués `[NEW]`.

**Clé composite** : `Commune` + `Code_zone`. Ajouter `[NEW] Regime` ∈ {QE, NQ} car les valeurs diffèrent (une parcelle existante = QE).

| Champ | Source | Notes |
|---|---|---|
| Commune, Code_zone, Nom_zone, Type_zone | PAG | clé + libellés |
| `[NEW] Regime` (QE/NQ) | — | dédoublonne QE vs NQ |
| `[NEW] Methode_reculs` (fixe/contextuel) | PAP QE | si "contextuel" → ne pas se fier aux valeurs |
| Recul_avant_min_m / _max_m | PAP QE | |
| Recul_lateral_min_m | PAP QE | 0 si accolé |
| Recul_arriere_min_m | PAP QE | |
| `[NEW] Recul_arriere_sous_sol_min_m` | PAP QE | ex Strassen QE2 = 4,5 |
| Profondeur_max_m (hors-sol) | PAP QE | |
| `[NEW] Profondeur_sous_sol_max_m` | PAP QE | ex Strassen QE2 = 18 |
| `[NEW] Recul_lie_hauteur` (bool) | PAP QE | recul = ½ corniche → couplage hauteur |
| `[NEW] Regime_voirie_special` | PAP QE | ex "Route d'Arlon : 15 m depuis l'axe" |
| Hauteur_corniche_max_m / _faite_ / _acrotere_ | PAP QE | |
| Niveaux_hors_sol_max (+combles) / Niveaux_sous_sol_max | PAP QE | |
| COS_max, CSS_max | PAP QE (QE) / PAG casier (NQ) | |
| CUS_max | PAG casier (NQ) / PAP QE | + `[NEW] CUS_pondere` (×2/×3 selon hauteur d'étage) |
| DL_max_log_ha | PAG | densité |
| Nb_logements_max | PAP QE | "2 par construction" etc. |
| Logement_autorise, Commerce_autorise | PAG | |
| `[NEW] Min_SCB_logement_QE_%` / `[NEW] Min_SCB_logement_NQ_%` | PAG | scinder l'actuel champ unique |
| `[NEW] Min_logements_unifamilial_%` | PAG | |
| `[NEW] Plafond_surface_vente_m2` | PAG | commerce |
| `[NEW] Parking_ratio` (JSON par fonction/tranche) | PAG Art. 10 | barème min/max |
| `[NEW] Servitudes` (multi) | PAG zones superposées | amenagement_differe, inondable, natura2000, secteur_protege, bruit, couloir_reserve… |
| `[NEW] Surface_min_logement_m2` | RBVS | ex 30 |
| `[NEW] PDF_source_url`, `[NEW] PDF_version_date`, `[NEW] Confiance` (auto/validé) | méta | traçabilité + validation |

---

## 4. Pipeline d'extraction

```
Pour chaque commune :
  1. LOCATE    : trouver les URLs des 3 PDF (PAG / PAP QE / RBVS), version coordonnée la plus récente.
                 Sources : site communal, portail national d'aménagement communal, recherche web.
  2. DOWNLOAD  : récupérer les PDF, hasher, stocker (date + version).
  3. EXTRACT   : par document, LLM → JSON structuré par zone/secteur (mapper sur le schéma §3).
                 - PAG : zones, casier COS/CSS/CUS/DL (souvent en partie GRAPHIQUE → vision),
                         parts-logement, servitudes superposées, parking Art.10, définitions.
                 - PAP QE : secteurs + dimensionnel (fixe vs contextuel !), mapping secteur→zone PAG.
                 - RBVS : stationnement (dimensions), surfaces mini, servitudes internes.
  4. NORMALIZE : fusionner les 3 sources en lignes Airtable (clé Commune+Code_zone+Regime).
                 Marquer Methode_reculs=contextuel quand non chiffrable.
  5. VALIDATE  : règles de cohérence auto (reculs>0, COS≤CSS≤1, etc.) + revue humaine par commune.
  6. WRITE     : upsert dans Airtable, avec Confiance=auto puis =validé après revue.
```

### Choix modèle & coût
- **Extraction** : **Sonnet 4.6** (3 $/15 $ par M tokens) — bon compromis fiabilité/coût sur du juridique dense. Réserver **Opus 4.8** (5 $/25 $) aux parties ambiguës (casier graphique, PAP QE contextuels).
- **Batch API** (-50 %) pour le volume + **prompt caching** (le prompt d'extraction + le schéma sont stables → cache la partie fixe).
- Ordre de grandeur : 3 docs ≈ 150-200 pages ≈ ~380K tokens d'entrée + ~20K sortie / commune.
  - Sonnet + Batch ≈ **~0,70 $/commune** → **~70 $ / 100 communes** (une passe).
  - Avec re-extractions + Opus sur le délicat : **quelques centaines d'€** pour le pays.
- **Le token n'est pas le facteur limitant.** L'effort réel = pipeline LOCATE/NORMALIZE + validation humaine.

---

## 5. Risques & pièges (lus en dur, à respecter)

1. **PAP QE contextuels** : ~la moitié des communes n'ont pas de valeurs fixes. Détecter et marquer `Methode_reculs=contextuel` ; ne JAMAIS inventer un chiffre. Pour ces communes, le moteur devra basculer sur une logique d'alignement voisinage (qu'il sait partiellement faire via l'adjacence cadastrale Sprint 1.5).
2. **Casier COS/CUS en partie graphique** : souvent une image, pas du texte. Extraction vision, sujette à erreurs d'ordre de cellules. Recouper, ne pas livrer sans contrôle.
3. **Versioning** : il existe des versions successives coordonnées. Sur Strassen, page 11 (ancienne) et page 26 (coordonnée 2025) **divergeaient**. Toujours prendre la version coordonnée la plus récente et tracer la date.
4. **Régimes QE vs NQ** : valeurs différentes pour le même code zone. Ne pas écraser l'un par l'autre.
5. **Validation = obligation** : un recul faux → faisabilité fausse → responsabilité. Aucune ligne `Confiance=auto` ne doit servir le B2C sans relecture.
6. **Hétérogénéité de nommage** : les codes zone varient (Strassen n'a pas de `MIX-c`, juste MIX-u/MIX-v). Construire un mapping de normalisation, pas un parser rigide.

---

## 6. Plan par phases

- **Phase 0 — Référence Strassen** : enrichir la ligne Strassen avec les champs `[NEW]` (sous-sol, servitudes, scission QE/NQ, parking JSON, CUS pondéré). Sert de **schéma cible + jeu de vérité** pour calibrer l'extraction.
- **Phase 1 — Grande Région prioritaire** (~10-15 communes LU autour de Strassen/Luxembourg-ville) en **semi-automatique** : LLM extrait → humain valide. Mesurer le taux d'erreur réel.
- **Phase 2 — Industrialisation** : automatiser LOCATE + NORMALIZE, étendre au pays, garder la validation humaine en boucle.
- **Hors scope immédiat** : FR Lorraine / BE Wallonie / DE Sarre (réglementations différentes — chantier séparé, plus tard).

---

## 7. Valeurs de référence Strassen (jeu de vérité)

Issues de l'analyse des 3 règlements (PAP QE version coordonnée 19/03/2024, PAG coordonné 30/01/2025).

**QE1 = HAB-1 (résidentiel) :** recul avant 3-6 m, latéral 3 m (0 si accolé), arrière 10 m (bungalow 8), profondeur 14 m ; COS 0,35, CSS 0,60 ; 2 niveaux pleins + 1 combles/retrait, 1 sous-sol ; corniche 8 m, faîte 12 m, acrotère +50 cm ; **2 logements max/construction** ; implantation isolé/jumelé/bande.

**QE2 = HAB-2 / MIX-u / MIX-v (urbain) :** recul avant 3-7 m, latéral 4,5 m, arrière **12 m hors-sol / 4,5 m sous-sol** ; profondeur **14 m hors-sol / 18 m sous-sol** (RDC non-logement jusqu'à 20 m, 30 m le long Route d'Arlon) ; COS 0,35, CSS 0,50 ; 3 niveaux pleins + 1 combles/retrait, sous-sol libre ; corniche 11 m, faîte 15 m ; **densité 105 log/ha** (pas de plafond par construction) ; **≥ 70 % SCB logement**. **Régime spécial Route d'Arlon : recul avant 15 m depuis l'axe ; latéral = ½ corniche (plancher 4,5 m).**

**Parking (PAG Art. 10) :** logement < 60 m² = 1 place, 60-90 m² = 2, ≥ 90 m² = 3 ; ≥ 1 en garage/car-port obligatoire. Dimensions (RBVS) : 2,5×5 m standard, 2 m²/vélo. Surface logement mini (RBVS) : 30 m².

**Parts SCB-logement (PAG) :** HAB-1 NQ ≥ 90 % ; HAB-2 NQ ≥ 80 % ; MIX-u QE ≥ 50 % / NQ ≥ 25 % ; MIX-v QE ≥ 70 % / NQ ≥ 50 %.

**Définitions à coder (PAG / RGD 2017) :** CUS pondéré ×2 (étage 5-10 m) / ×3 (>10 m) ; SCB exclut sous-sol/combles non-aménageables et surfaces non closes ; COS sur terrain net, CUS/DL sur terrain brut. **Pas de CBD/coefficient de biotope à Strassen.**

---

## 8. Premiers pas pour l'instance qui prend la mission

1. Lire ce briefing + le `CLAUDE.md` du repo (contexte produit, Airtable, conventions).
2. Phase 0 : créer les champs `[NEW]` dans Airtable et remplir Strossen à la main depuis le §7 (jeu de vérité).
3. Écrire le prompt d'extraction (un par type de doc) qui sort le JSON du schéma §3, et le tester **sur les 3 PDF de Strassen** (présents dans l'historique de cette session, ou re-téléchargeables) → comparer au §7 pour mesurer la fidélité.
4. Seulement ensuite : automatiser LOCATE sur 2-3 communes voisines et boucler la validation.

## 9. Limites connues

### 9.1. Casier NQ (COS/CUS/CSS/DL des nouveaux quartiers) — non extractible du texte
Les valeurs de degré d'utilisation du sol des zones **PAP « nouveau quartier » (NQ)** — COS, CUS, CSS, DL — **ne figurent pas dans la partie écrite du PAG**. Le PAG (Strassen, p.9) le dit explicitement : « Les valeurs maxima […] sont définies pour les zones inscrites en PAP nouveau quartier **dans le casier figurant dans la partie graphique** du plan d'aménagement général. » La partie écrite ne contient que la *légende* du casier (le gabarit vide), pas les valeurs par sous-périmètre.

Conséquence :
- Aucun outil texte (pdftotext, pdf→md, ou LLM sur le texte) ne récupérera ces valeurs : l'information n'est physiquement pas dans le PDF de la partie écrite. Elle est imprimée dans les cases du casier **sur la carte** (partie graphique).
- Vérifié sur Strassen : ces valeurs sont **également absentes de l'Airtable rempli à la main**. Ce n'est donc pas un défaut d'extraction mais un trou de source que même le remplissage manuel n'a pas comblé.

**Décision : NQ laissé de côté pour l'instant.** Sans impact sur le cas d'usage immédiat — une parcelle existante relève du régime **QE**, dont tout le dimensionnel est dans le PAP QE (extraction texte fidèle, validée contre l'Airtable Strassen). Le casier NQ ne bloque pas le B2C.

Piste de résolution quand on en aura besoin (chantier séparé) : OCR vision de la **carte** PAG, ou — préférable — vérifier si geoportail expose le `degré d'utilisation du sol` en attributs vectoriels (collection 698 ou voisine). À traiter comme une question de *source de données*, pas de parsing.

### 9.2. PAP QE contextuels (rappel)
Voir §5.1 : les communes à reculs/hauteurs contextuels (« alignement sur les voisins ») ne sont pas réductibles à des scalaires. Strassen est un cas à valeurs fixes ; ne pas généraliser. À marquer `Methode_reculs=contextuel`.

---

## 10. Calibration pilote (4 communes) + Roadmap d'industrialisation

### 10.1. Conclusion de la calibration (2026-06-19)
Pilote sur **Strassen + Bertrange + Mamer + Junglinster**. Résultat central :
**aucune commune ne paramètre le QE de la même façon.** Le texte s'extrait
fidèlement partout (`pdftotext -layout` / pdf→md, zéro hallucination) ; la
difficulté n'est jamais l'OCR mais la **normalisation** et l'**adaptativité moteur**.

| Aspect | Strassen | Bertrange | Mamer | Junglinster |
|---|---|---|---|---|
| Recul avant | fixe | alignement_voisins (+fixe+lié-H) | alignement_voisins | fixe (alignement en dérogation) |
| COS/CSS en QE | présents (PAP QE) | absents | absents | absents (degré géométrique) |
| Hauteurs | fixes | fixes | par_niveaux | par_niveaux |
| Nb logements | fixe / par_ha | fixe | formule | graphique |
| Voirie spéciale | Route d'Arlon | lié-H QGSC | rues nommées (bande 20m) | alignement PAG |

Données brutes par commune : `palladio_scrap/communes/*.json` (jeu de vérité +
futur contenu Airtable). Schéma typé figé : `palladio_scrap/SCHEMA.md`. Prompts
d'extraction réutilisables : `palladio_scrap/prompts/`.

### 10.2. Constat d'environnement (egress)
Le conteneur de dev (Claude Code web) a un **egress en allowlist** : il peut
*chercher* (WebSearch) mais **pas télécharger** les PDF communaux ni joindre
geoportail/data.public.lu (403). Le portail national `data.public.lu` ne porte de
toute façon **ni le PAP QE ni le RBVS** (uniquement PAG écrit + GML + PAP NQ) →
les docs utiles sont sur les sites communaux. Conséquences :
- Pilote = **upload** des PDF (fait pour les 4 communes).
- Industrialisation (LOCATE/DOWNLOAD/crawl) = **doit tourner sur Railway/n8n**
  (egress ouvert, atteint déjà geoportail), pas dans la session.
- Validation = **essais réels sur Railway** puis relecture Airtable (décision Vincent
  2026-06-19 : autonomie, validation a posteriori).

### 10.3. Roadmap « Palladio sur toutes les communes »
Couches (cf. plan béton) :
1. **Schéma typé** — FAIT (`SCHEMA.md`). Reculs typés, COS/CSS nullable, hauteurs/
   logements modélisés, `source_articles` par champ.
2. **Données 4 communes** — FAIT (`communes/*.json`).
3. **Prompts d'extraction** — FAIT (`prompts/`).
4. **Moteur adaptatif (recul avant)** — FAIT + câblé. `compute_recul_avant_effectif()`
   dispatch {fixe, lie_hauteur, alignement_voisins} + câblage dans
   `calculer_palladio_full` (params `recul_avant_methode` + `corniche_effective_m`,
   re-calcul de l'enveloppe, sortie `recul_avant_adaptatif`). **Gate** : sans
   `recul_avant_methode`, comportement prod strictement inchangé. Tests 5/5 OK.
5. **Alignement par bâtiments voisins** — FAIT. `alignment_band_ra()` réutilise
   `fetch_buildings` (collection 2214). Recul avant = moyenne des distances façade
   des voisins à la ligne de voirie ; fallback chiffré si 0 voisin. **À calibrer
   sur parcelles réelles Railway** (sélection des voisins adjacents = heuristique v0.1).
6. **Justification + liens articles** — le dispatch renvoie `{type, recul_m,
   source_article, fronts_m, ...}` dans `recul_avant_adaptatif`. **Reste** : HTML debug.
7. **Pipeline déployé** (Railway/n8n) — à faire : LOCATE (WebSearch + sites
   communaux) → download → pdf→md → extraction (prompts) → JSON schéma → upsert
   Airtable via `airtable_sync.py`. Vision (Opus) réservée au graphique.
8. **Migration Airtable** — FAIT (2026-06-19). 9 champs typés ajoutés à `Zones_PAG`
   (additifs) + 8 secteurs écrits (Bertrange/Mamer/Junglinster, `Confiance=auto`) +
   4 lignes Strassen alignées (`Confiance=valide`). Script rejouable : `airtable_sync.py`.

**Déploiement** : `main` fast-forwardé sur la branche (2026-06-19) → Railway redéploie.
Le câblage moteur est live mais **dormant** tant que le workflow n8n `XFOhmez4MtTnmtnL`
ne passe pas `recul_avant_methode` dans le payload (bascule = étape suivante). Donc
`/palladio/calcul` et `/full` actuels (Strassen) sont inchangés.

### 10.5. Reste à faire (état au 2026-06-19)
- **Bascule n8n** : faire passer `recul_avant_methode` + `corniche_effective_m` depuis
  Airtable dans le payload `/palladio/calcul/full` (procédure §4.3, workflow complet).
- **Calibrer l'alignement** sur une parcelle réelle de Bertrange (Railway) : affiner
  la sélection des bâtiments voisins adjacents (corridor latéral de la façade).
- **HTML debug** : afficher `recul_avant_adaptatif` (méthode + recul retenu + fronts voisins).
- **Pipeline LOCATE/DOWNLOAD** sur Railway/n8n pour scaler au-delà des 4 communes pilotes.

### 10.4. Règle d'or moteur (dégradation gracieuse)
Zone contextuelle sans voisins calculables, ou donnée graphique manquante → calculer
ce qu'on peut + warning + CTA « consulter un architecte » (signal de conversion, pas
erreur). Jamais de 500, jamais de chiffre inventé. `Confiance=auto` ne sert pas le
B2C sans relecture.

---

*Fin du briefing.*
