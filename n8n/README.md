# Workflow Palladio (n8n `XFOhmez4MtTnmtnL`) — scripts source

Source de vérité des `jsCode` des Code nodes du workflow Palladio, pour éviter de
recopier à la main de gros strings (cf. `CLAUDE.md` 8.3).

## Fichiers
- **`Build_Palladio_Payload.js`** — node *Build Palladio Payload* : mappe les règles
  Airtable (reculs, COS/CUS, niveaux, densité log/ha, max logements…) dans `zone_pag`
  et construit le payload envoyé à `/palladio/calcul/full`.
- **`Assemble_Palladio_Page.js`** — node *Assemble Palladio Page* : génère la page HTML
  de résultat (mobile, police Inter, une explication suivie de son schéma, mitoyenneté
  bâtie, dimensions sur l'emprise, comptage logements ancré dans le règlement).

## Procédure de mise à jour
`get_workflow_details` → `update_workflow` (draft, `setNodeParameter /jsCode`) →
vérif intégrité (re-fetch + `node --check` + rendu sur mock) → `publish_workflow`.
Publier **uniquement** si le rendu est OK (le draft ne part jamais en prod sinon).
