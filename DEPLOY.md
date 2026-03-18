# FEASIBILITY.LU — Guide de déploiement

## 1. Déployer l'API sur Railway

### Option A : Via GitHub (recommandé)
1. Crée un repo GitHub (ex: `feasibility-api`)
2. Push les fichiers du dossier `feasibility-api/` dedans
3. Va sur https://railway.app → New Project → Deploy from GitHub repo
4. Railway détecte automatiquement Python + le Procfile
5. L'API sera live sur une URL type: `https://feasibility-api-production-xxxx.up.railway.app`

### Option B : Via Railway CLI
```bash
cd feasibility-api
railway login
railway init
railway up
```

### Vérifier que ça marche
```bash
# Health check
curl https://TON-URL.up.railway.app/health

# Test calcul
curl -X POST https://TON-URL.up.railway.app/calcul \
  -H "Content-Type: application/json" \
  -d '{"surface_terrain_m2": 780, "zone_pag": "MIX-u", "commune": "Strassen"}'
```

---

## 2. Brancher dans n8n

### Node "Moteur de calcul" (HTTP Request)

Dans ton workflow n8n, après le node "Assembler données géo" qui récupère la parcelle et la zone PAG,
ajoute un node **HTTP Request** avec cette config :

- **Method**: POST
- **URL**: `https://TON-URL.up.railway.app/calcul`
- **Authentication**: None (ou ajoute un API key plus tard)
- **Body Type**: JSON
- **JSON Body**:

```json
{
  "surface_terrain_m2": {{ $json.surface_terrain }},
  "zone_pag": "{{ $json.zone_pag }}",
  "commune": "{{ $json.commune }}",
  "adresse": "{{ $json.adresse }}",
  "num_cadastral": "{{ $json.num_cadastral }}"
}
```

> ⚠️ Adapte les noms de variables (`$json.surface_terrain`, etc.) à ceux de ton node
> "Assembler données géo". Vérifie les noms exacts dans l'output de ce node.

### Résultat

Le node retourne un JSON avec toute la faisabilité calculée. Exemple de champs disponibles :

```
$json.verdict.constructible        → "Oui" / "Non" / "Sous conditions"
$json.verdict.potentiel            → "Faible" / "Moyen" / "Fort"
$json.programme.nb_logements       → 8
$json.programme.scb_totale_m2      → 881.0
$json.programme.parkings_auto.min  → 10
$json.programme.mix_logements      → {T1_studio: {nb:2, shn_m2:35}, ...}
$json.regles.h_corniche_max        → 11.0
$json.contraintes                  → ["Surface scellée max: 390 m²", ...]
```

---

## 3. Passer les données à Claude pour le rapport

Dans le node "Préparer données rapport", tu construis le body Claude API avec les données du moteur.

Exemple de prompt système pour Claude :

```
Tu es un expert en urbanisme luxembourgeois. Rédige un rapport de faisabilité 
immobilière Level 1 (go/no-go rapide) à partir des données structurées suivantes.

Le rapport doit être concis, professionnel, et structuré en sections :
1. Identification de la parcelle
2. Règles urbanistiques applicables
3. Programme estimé
4. Contraintes et points d'attention
5. Verdict et recommandation

Utilise les données exactes fournies, ne les invente pas.
Indique clairement que c'est une estimation et non un avis d'architecte.
```

Et dans le message user, tu passes le JSON complet :

```
Voici les données de faisabilité calculées pour cette parcelle :

{{ JSON.stringify($json) }}
```

---

## 4. Architecture complète du workflow n8n

```
[Tally Webhook]
    ↓
[Nominatim Geocoding]
    ↓
[Geoportail - Parcelle cadastrale]  →  [Geoportail - Zone PAG]
    ↓                                         ↓
              [Assembler données géo]
                       ↓
              [HTTP Request → API Feasibility]     ← NEW
                       ↓
              [Préparer données rapport]
                       ↓
              [Claude API → Rédiger rapport]
                       ↓
              [Gmail → Envoyer rapport]
```

---

## 5. Endpoints disponibles

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/` | Info service + communes disponibles |
| GET | `/communes` | Liste des communes et zones |
| GET | `/zones/{commune}` | Zones d'une commune |
| POST | `/calcul` | **Calcul de faisabilité** |
| GET | `/health` | Health check |

---

## 6. Pour ajouter une nouvelle commune

1. Extraire les règles du PAG + PAP QE de la commune (via Claude, comme on a fait pour Strassen)
2. Ajouter le dictionnaire de zones dans `main.py` → `ZONES["NomCommune"] = {...}`
3. Redéployer sur Railway (`git push` si GitHub, ou `railway up`)
4. C'est live immédiatement pour toutes les requêtes

---

## Coût estimé Railway
- Plan Starter: 5$/mois (500h d'exécution)
- Cette API consomme quasi rien (calculs CPU purs, pas de DB)
- Compatible avec le plan gratuit si < 500h/mois
