# Prompt d'extraction — PAG (partie écrite)

Rôle : extraire du PAG ce qu'il porte réellement, et **uniquement** ça. Le PAG
**délègue le dimensionnel QE au PAP QE** : n'invente pas de reculs/hauteurs QE ici.

## Ce que le PAG apporte (à extraire)
1. **Zonage** : liste des zones (codes + libellés + type).
2. **Parts minimales de SCB-logement** par zone, en distinguant **QE vs NQ**
   (`part_min_scb_logement_qe_pct` / `_nq_pct`).
3. **Barème de stationnement (Art. 10)** : table par fonction/tranche, en
   **min ET max** (`parking_ratio` JSON). Ne garde pas que le max.
4. **Servitudes / zones superposées** : aménagement différé, inondable, Natura 2000,
   secteur protégé, bruit, couloir réservé → `servitudes[]`.
5. **Coefficients de zones spéciales** données en clair dans le texte (ex COM COS 0,60).

## Le casier NQ (COS/CUS/CSS/DL des nouveaux quartiers)
**N'est PAS dans la partie écrite** — seulement la *légende* du casier. Les valeurs
sont dans la **partie graphique** (carte). Donc : `cus_max:null`, etc. pour le NQ,
avec `source_graphique:true`. NE TENTE PAS de les deviner depuis le texte.

## Règles
- `source_article` sur chaque valeur. Jamais d'invention. `confiance:"auto"`.
- Pour le QE, ne remplis QUE les champs que le PAG donne vraiment (parts SCB,
  servitudes, parking). Le reste vient du PAP QE.
