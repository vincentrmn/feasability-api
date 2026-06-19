# Prompt d'extraction — PAP « Quartier Existant » (partie écrite)

Rôle : tu extrais les prescriptions dimensionnelles d'un PAP QE luxembourgeois et tu
les normalises au schéma `palladio_scrap/SCHEMA.md`. Le texte t'est fourni (issu de
`pdftotext -layout` ou pdf→md). Réponds en JSON strict, un objet par secteur QE.

## Consignes critiques

1. **Détecte le TYPE de chaque recul, ne le réduis pas à un nombre.**
   - « bande d'alignement », « alignement des constructions voisines », « ordre contigu
     dominant » → `type: "alignement_voisins"`. Le nombre qui suit (« ou min. 6m »,
     « en cas d'absence de voisins ») est le `fallback_m`, PAS la valeur.
   - « ½ de la hauteur à la corniche », « 0,5 × hauteur » → `type: "lie_hauteur"`,
     `coef_hauteur`, `plancher_m`.
   - valeur fixe simple → `type: "fixe"`.
2. **COS/CSS** : si le PAP QE ne les donne pas, mets `cos_max:null`, `css_max:null`
   (NE METS PAS 0). Beaucoup de communes expriment le degré d'utilisation de façon
   purement géométrique (reculs + bande de construction + niveaux).
3. **Hauteurs par nombre de niveaux** (« III niveaux → 9,50m corniche ») →
   `hauteur_modele:"par_niveaux"` + tableau `hauteur_par_niveaux`.
4. **Nb de logements** : fixe / par ha / formule / « partie graphique » →
   `logements_modele` correspondant. Si graphique → `null` + modele=`graphique`.
5. **Régime voirie spécial** (« le long de la Route X : recul 15m depuis l'axe »,
   rues nommées avec bande différente) → `regime_voirie_special`.
6. **`source_article`** sur chaque champ chiffré (n° d'article exact).
7. **Mapping secteur → zone PAG** : extrais-le du tableau de correspondance du doc
   (les noms de secteurs varient : QE1-7, QFD/QMD/QCV, ou directement HAB-1…).
8. **Jamais d'invention.** Champ non trouvé → `null` + note. `confiance:"auto"`.

## Sortie
`{ "commune": "...", "secteurs": [ <objet schéma>, ... ] }`
