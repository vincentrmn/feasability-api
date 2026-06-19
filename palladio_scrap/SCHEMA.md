# Palladio Scrap — Schéma typé des règles QE (v1, figé sur 4 communes)

> Figé après calibration Strassen + Bertrange + Mamer + Junglinster (2026-06-19).
> Conclusion : **aucune commune ne paramètre le QE pareil**. Le texte s'extrait
> fidèlement partout ; la difficulté est la NORMALISATION et l'adaptativité moteur.
> Un schéma de scalaires plat ne suffit pas → reculs **typés**, COS/CSS **nullable**,
> hauteurs/logements **modélisés**, traçabilité **par champ**.

## Modèles rencontrés (preuve de l'hétérogénéité)

| Aspect | Strassen | Bertrange | Mamer | Junglinster |
|---|---|---|---|---|
| Recul avant | `fixe` | `alignement_voisins` (+ `fixe`/`lie_hauteur` selon secteur) | `alignement_voisins` | `fixe` (alignement en dérogation) |
| COS/CSS en QE | présents (PAP QE) | absents | absents | absents (degré géométrique) |
| Hauteurs | fixes/secteur | fixes | `par_niveaux` | `par_niveaux` |
| Nb logements | `fixe` / `par_ha` | `fixe` | `formule` | `graphique` |
| Voirie spéciale | Route d'Arlon | lié-hauteur QGSC | rues Kirpach/Commerce/Dippach | alignement PAG |

## Clé

`commune` + `code_pap` (secteur PAP QE) + `regime` ∈ {QE, NQ}.
Le `code_pap` mappe 1:n vers des `zone_pag` (ex. Strassen QE2 → HAB-2/MIX-u/MIX-v).

## Structure d'un secteur

```jsonc
{
  "code_pap": "QFD",            // libellé secteur du PAP QE (varie par commune)
  "zone_pag": ["HAB-1"],        // zone(s) PAG correspondante(s)
  "regime": "QE",
  "libelle": "Quartier d'habitation de faible densité",

  // --- RECULS TYPÉS (un objet par recul) ---
  "recul_avant":   { "type": "fixe|alignement_voisins|lie_hauteur",
                     "min_m": null, "max_m": null,
                     "fallback_m": null,         // si alignement et 0 voisin bâti
                     "coef_hauteur": null,       // si lie_hauteur (ex 0.5 = ½ corniche)
                     "plancher_m": null,         // plancher du lié-hauteur
                     "source_article": "" },
  "recul_lateral": { "type": "fixe|lie_hauteur",
                     "min_m": null, "zero_si_accole": true,
                     "coef_hauteur": null, "plancher_m": null, "source_article": "" },
  "recul_arriere": { "type": "fixe|lie_hauteur",
                     "min_m": null, "min_sous_sol_m": null,
                     "coef_hauteur": null, "plancher_m": null, "source_article": "" },

  // --- ENVELOPPE ---
  "profondeur_max_m": null,            // hors-sol
  "profondeur_sous_sol_max_m": null,
  "bande_construction_max_m": null,    // concept absent de Strassen, présent ailleurs
  "regime_voirie_special": null,       // ex { "voie":"Route d'Arlon", "recul_avant_m":15, "depuis":"axe" }

  // --- HAUTEURS (modélisées) ---
  "hauteur_modele": "fixe|par_niveaux",
  "hauteur_corniche_max_m": null,      // si fixe
  "hauteur_faite_max_m": null,
  "hauteur_acrotere_max_m": null,
  "hauteur_par_niveaux": null,         // si par_niveaux : [{niveaux, corniche_m, faite_m, acrotere_m}]

  // --- NIVEAUX ---
  "niveaux_hors_sol_max": null,        // niveaux pleins
  "niveaux_combles_retrait": null,     // +1 typiquement
  "niveaux_sous_sol_max": null,        // int | "libre"

  // --- DEGRÉ D'UTILISATION (nullable : absent ≠ 0) ---
  "cos_max": null,
  "css_max": null,
  "cus_max": null,                     // souvent dans le casier NQ graphique → null en QE
  "dl_max_log_ha": null,

  // --- LOGEMENTS (modélisé) ---
  "logements_modele": "fixe|par_ha|formule|graphique",
  "logements_max_par_construction": null,
  "logements_max_par_ha": null,
  "logements_formule": null,           // texte de la formule si modele=formule
  "part_min_scb_logement_qe_pct": null,

  // --- TRAÇABILITÉ ---
  "source_articles": {},               // { champ: "réf article" } pour la justification
  "notes": "",
  "confiance": "auto"                  // auto | valide
}
```

## Règles dures de normalisation

1. **Ne jamais inventer un scalaire pour un recul contextuel.** `type=alignement_voisins` →
   le `fallback_m` ne sert QUE quand aucun voisin bâti ; la vraie valeur se calcule (moteur).
2. **COS/CSS absent = `null`, jamais `0`.** Un `0` casserait le calcul SCB.
3. **Donnée en partie graphique = `null` + flag** (`logements_modele=graphique`, ou casier NQ).
   À récupérer via vision/geoportail (chantier séparé), pas via le texte.
4. **`source_article` obligatoire** sur chaque valeur chiffrée (justification + couverture juridique).
5. **`confiance=auto`** par défaut ; ne sert le B2C qu'après relecture (`valide`).
