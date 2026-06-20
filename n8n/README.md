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
