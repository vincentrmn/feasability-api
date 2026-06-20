# Workflow Palladio (n8n `XFOhmez4MtTnmtnL`) — scripts source

Source de vérité des `jsCode` des Code nodes du workflow Palladio, pour éviter de
recopier à la main de gros strings (cf. `CLAUDE.md`).

## Pipeline
`Webhook Calcul → Extract Address → Geocodage v4 → Extract Geocoded → Parcelle 359
→ Zone PAG 698/28 → Identify PAG Zone → Lookup Rules Airtable → Build Palladio Payload
→ Calcul Palladio (POST /palladio/calcul/full/html) → Assemble Palladio Page (passe-plat)
→ Respond JSON (text/html)`

## Fichiers
- **`Build_Palladio_Payload.js`** — mappe les règles Airtable dans `zone_pag`, construit
  le payload, la **méthode de recul avant** typée (Palladio Scrap) et le **contexte**
  d'affichage (adresse, label parcelle, COS/CSS, hauteurs).
- **`Assemble_Palladio_Page.js`** — **passe-plat** : le HTML est désormais rendu côté
  serveur (`palladio_render.py`, route `/palladio/calcul/full/html`). Ce node récupère
  juste le HTML renvoyé. L'ancien node de 39 Ko a été supprimé.

## Procédure de mise à jour
`get_workflow_details` → `update_workflow` (draft, `setNodeParameter /jsCode`) →
test sur une parcelle réelle (désactiver temporairement `Webhook Form` pour cibler
`Webhook Calcul`, `execute_workflow` mode manual, inspecter la sortie) → réactiver
`Webhook Form` → `publish_workflow`. Publier **uniquement** si le rendu est OK.
