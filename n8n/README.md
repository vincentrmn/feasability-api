# Workflow Palladio (n8n `XFOhmez4MtTnmtnL`) — scripts source

Source de vérité des `jsCode` des Code nodes du workflow Palladio, pour éviter de
recopier à la main de gros strings (cf. `CLAUDE.md`).

## Pipelines (2 webhooks)

**Calcul** (résultat d'une adresse) :
`Webhook Calcul → Extract Address → Geocodage v4 → Extract Geocoded → Parcelle 359
→ Zone PAG 698/28 → Identify PAG Zone → Lookup Rules Airtable → Build Palladio Payload
→ Calcul Palladio (POST /palladio/calcul/full/html) → Assemble Palladio Page (passe-plat)
→ Respond JSON (text/html)`

**Page d'accueil** (formulaire + cockpit de couverture) :
`Webhook Form → Fetch Landing (GET /palladio/landing/html) → Serve Form HTML (text/html)`
Un seul appel HTTP. L'API lit Airtable **côté serveur** (en cache 5 min,
`airtable_landing.py`) et rend la page. On ne liste **plus** Airtable depuis n8n ici :
6 appels Airtable par visite saturaient la limite (5 req/s) et faisaient ramer/planter
la page d'accueil.

## Fichiers
- **`Build_Palladio_Payload.js`** — mappe les règles Airtable dans `zone_pag`, construit
  le payload, la **méthode de recul avant** typée (Palladio Scrap) et le **contexte**
  d'affichage (adresse, label parcelle, COS/CSS, hauteurs, + **références d'articles**
  PAG/PAP : `articles` depuis `Source_articles_json`, `article_pag`, `article_pap_qe`,
  affichées dans les justifications de la page résultat).
- **`Assemble_Palladio_Page.js`** — **passe-plat** : le HTML est désormais rendu côté
  serveur (`palladio_render.py`, route `/palladio/calcul/full/html`). Ce node récupère
  juste le HTML renvoyé. L'ancien node de 39 Ko a été supprimé.
- **Page d'accueil** — plus de node Code ni de nodes Airtable côté n8n. Le node
  **Fetch Landing** (HTTP GET) appelle l'endpoint `/palladio/landing/html` qui lit
  Airtable côté serveur (cache) et rend la page (formulaire + cockpit,
  `cockpit_render.py`). **Serve Form HTML** renvoie ce HTML (`{{ $json.data }}`).
  Le cockpit ne s'affiche que si la variable d'env Railway `AIRTABLE_API_KEY` est
  définie ; sinon la page affiche le formulaire seul (dégradation gracieuse).

## Procédure de mise à jour
`get_workflow_details` → `update_workflow` (draft, `setNodeParameter /jsCode`) →
test sur une parcelle réelle (désactiver temporairement `Webhook Form` pour cibler
`Webhook Calcul`, `execute_workflow` mode manual, inspecter la sortie) → réactiver
`Webhook Form` → `publish_workflow`. Publier **uniquement** si le rendu est OK.

> Limite outil : `execute_workflow` ne pilote pas un webhook en `responseNode`
> (il attend un vrai appel HTTP) — la branche page d'accueil se teste en ouvrant
> l'URL `/webhook/palladio` dans le navigateur.

---

# Workflow « Palladio Scrap — Onboarding commune » (n8n `kBeouxMu3m3g1djr`)

Pipeline d'industrialisation des règles (roadmap point 7). Ajoute/met à jour une
commune dans Airtable à partir de ses règlements en ligne.

`Manual Trigger → Input (commune, pag_url, pap_url) → Download PAG → PDF vers texte
→ Download PAP → PDF vers texte PAP → Build doc (concatène PAG + PAP QE)
→ Extraction Claude (nœud LLM, prompt = palladio_scrap/prompts/onboarding_airtable.md)
→ Parse rows (normalise booléens Oui/Non, nombres→texte pour les singleSelect)
→ Write Airtable (upsert sur Commune + Code_zone, Confiance=auto, typecast)`

## Onboarder une commune
1. Trouver les URLs PDF du **PAG partie écrite** et du **PAP QE partie écrite**
   (site communal ou data.public.lu).
2. Ouvrir le node **Input**, renseigner `commune`, `pag_url`, `pap_url`.
3. Exécuter (manuel). Les zones constructibles sont créées/mises à jour en
   `Confiance=auto`, puis relues par un humain (passage à `valide`).
4. La commune apparaît automatiquement dans le cockpit de la page d'accueil
   (qui lit Airtable).

## Notes
- **PAG seul = affectation + articles, pas les dimensions** : reculs/hauteurs/COS
  sont dans le PAP QE. Toujours fournir les deux.
- Modèle : Claude Sonnet (gros contexte). Credential n8n `Anthropic account`.
- Credential Airtable en **écriture** requis (`data.records:write` sur la base).
- `upsert` (clé Commune+Code_zone) → un re-run ne crée pas de doublons.
- Validé le 2026-06-20 sur **Leudelange** (5 zones : HAB-1/HAB-2/MIX-v/MIX-r/BEP-1).
