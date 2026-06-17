# Workflow Palladio (n8n XFOhmez4MtTnmtnL) — scripts source

Source de vérité des `jsCode` des Code nodes du workflow Palladio, pour éviter
de recopier à la main de gros strings (cf. CLAUDE.md 8.3).

## Sprint 2 — modifications
- **Calcul Palladio** (httpRequest) : URL -> `/palladio/calcul/full`
- **Build Palladio Payload** : ajoute `zone_pag` (règles PAG mappées Airtable)
- **Assemble Debug JSON** : schemas 08 (SCB), 09 (logements+parkings),
  10 (type construction), 11 (warnings). Rétrocompatible `/calcul` (affiche
  "Indisponible" si pas de couche métier).

Procédure de mise à jour : get_workflow_details -> update_workflow (draft)
-> vérif intégrité -> publish_workflow.
