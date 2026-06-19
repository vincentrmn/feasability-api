# Prompt d'extraction — RBVS (Règlement Bâtisses, Voies publiques et Sites)

Rôle : extraire du RBVS les **dimensions** et **surfaces de servitude** qui
convertissent les *nombres* (de places, de logements) en *surfaces*, et les minima
d'habitabilité. Le RBVS **n'apporte PAS** les ratios de parking (→ PAG Art. 10) ni
les définitions de SCB/hauteurs (→ RGD 2017).

## À extraire
1. **Dimensions de stationnement** : place standard (ex 2,50 × 5,00 m), libre d'un
   côté, longitudinal, deux-roues, bande de circulation (ex 6 m), bornes de recharge.
2. **Surfaces minimales** : logement (ex 30 m²), habitation légère (ex 15 m²).
3. **Surfaces de servitude** : local ordures (ex 1,5 m² + 0,5 m²/100 m² SCB),
   espace extérieur/logement (ex 6 m²), buanderie/rangement.
4. **Autres** : hauteurs sous plafond mini, % toiture végétalisée, etc.

## Règles
- `source_article` sur chaque valeur. Jamais d'invention. `confiance:"auto"`.
- Sortie JSON : `{ "commune": "...", "rbvs": { ... } }`.
