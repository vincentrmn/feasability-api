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
`Webhook Form → List Zones PAG → List Stationnement → List Velo → List Servitudes
→ List PAP NQ → List Communes → Build Landing Payload
→ Render Landing (POST /palladio/landing/html) → Serve Form HTML (text/html)`

## Fichiers
- **`Build_Palladio_Payload.js`** — mappe les règles Airtable dans `zone_pag`, construit
  le payload, la **méthode de recul avant** typée (Palladio Scrap) et le **contexte**
  d'affichage (adresse, label parcelle, COS/CSS, hauteurs).
- **`Assemble_Palladio_Page.js`** — **passe-plat** : le HTML est désormais rendu côté
  serveur (`palladio_render.py`, route `/palladio/calcul/full/html`). Ce node récupère
  juste le HTML renvoyé. L'ancien node de 39 Ko a été supprimé.
- **`Build_Landing_Payload.js`** — agrège les 6 tables Airtable listées et les passe au
  rendu serveur (`cockpit_render.py`, route `/palladio/landing/html`). Le node
  **Serve Form HTML** rend désormais cette page (formulaire + cockpit), plus le
  formulaire statique d'avant. Les 6 nodes `List *` sont des Airtable `search`
  (returnAll, sans filtre) sur la base `appFUtt83fMC6NwgU`.

## Procédure de mise à jour
`get_workflow_details` → `update_workflow` (draft, `setNodeParameter /jsCode`) →
test sur une parcelle réelle (désactiver temporairement `Webhook Form` pour cibler
`Webhook Calcul`, `execute_workflow` mode manual, inspecter la sortie) → réactiver
`Webhook Form` → `publish_workflow`. Publier **uniquement** si le rendu est OK.

> Limite outil : `execute_workflow` ne pilote pas un webhook en `responseNode`
> (il attend un vrai appel HTTP) — la branche page d'accueil se teste en ouvrant
> l'URL `/webhook/palladio` dans le navigateur.
