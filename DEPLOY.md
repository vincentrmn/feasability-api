# Palladio — déploiement & exploitation

Moteur de calcul de constructibilité 2D (Luxembourg). Code dans `palladio_engine.py`,
servi par `main.py` (FastAPI) sur Railway. Orchestration via n8n.

## 1. API (Railway)

- Hébergement : Railway, build NIXPACKS (`railway.toml` / `nixpacks.toml`).
- Démarrage : `uvicorn main:app` (cf. `Procfile` / `railway.toml`).
- Déploiement : push sur `main` → Railway redéploie automatiquement (~1-2 min).

### Smoke test post-déploiement
```bash
curl https://web-production-afd8d.up.railway.app/        # liste les routes
curl https://web-production-afd8d.up.railway.app/health  # health check
```

### Endpoints Palladio
| Méthode | URL | Description |
|---------|-----|-------------|
| GET  | `/` | Liste des routes (smoke test) |
| POST | `/palladio/calcul` | Enveloppe + voirie (rapide, ~200 ms) |
| POST | `/palladio/calcul/full` | Enveloppe + SCB + logements + parkings + mitoyenneté bâtie + warnings |

Contrat d'entrée/sortie : voir `CLAUDE.md` (section 6).

## 2. Workflow n8n (`XFOhmez4MtTnmtnL`)

Pipeline : `Webhook → Geocodage → Parcelle 359 → Zone PAG → Lookup Rules Airtable
→ Build Palladio Payload → Calcul Palladio (/palladio/calcul/full)
→ Assemble Palladio Page → Respond JSON`.

Le node **Calcul Palladio** appelle l'API Railway ; **Assemble Palladio Page** génère
la page HTML de résultat (mobile, pédagogique). Les `jsCode` sont versionnés dans
`n8n/` (source de vérité, cf. `CLAUDE.md` 8.3).

### Procédure de mise à jour d'un node
`get_workflow_details` → `update_workflow` (draft) → vérif intégrité (fetch + `node --check`
+ rendu) → `publish_workflow`. Ne jamais patcher un seul node à la main dans l'UI.

## 3. Ajouter une commune

Les règles d'urbanisme (PAG / PAP QE) vivent dans **Airtable**
(base `appFUtt83fMC6NwgU`, table `tbll7YFXuR9ug1brF`), pas dans le code. Pour couvrir
une nouvelle commune : alimenter la table (à terme automatiquement via **Palladio Scrap**,
cf. `PALLADIO_SCRAP_BRIEFING.md`). Aucun redéploiement nécessaire côté moteur.

## 4. Garde-fous

- `main.py` contient aussi le moteur legacy v2.3 et ses routes, encore utilisées par
  des workflows legacy en prod. Ne pas toucher sans accord explicite.
- Tous les calculs métriques se font en LUREF (EPSG:2169).
