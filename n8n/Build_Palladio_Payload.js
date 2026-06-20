// node "Build Palladio Payload" du workflow Palladio (n8n XFOhmez4MtTnmtnL).
// Source de vérité — synchroniser ici à chaque modif du node (cf. README).
// Mappe les règles Airtable -> payload envoyé à POST /palladio/calcul/full/html,
// incluant la méthode de recul avant typée (Palladio Scrap) et le contexte d'affichage.
function extractAirtable(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === 'object' && !Array.isArray(v) && v.name !== undefined) return v.name;
  if (Array.isArray(v) && v.length > 0 && typeof v[0] === 'object' && v[0].name) return v.map(x => x.name).join(', ');
  return v;
}
function toFloat(v) {
  const x = extractAirtable(v);
  if (x === null || x === undefined || x === '') return null;
  if (typeof x === 'number') return x;
  const s = String(x).replace(',', '.').trim();
  if (!s || ['libre','null','none','nan'].includes(s.toLowerCase())) return null;
  const m = s.match(/-?\d+(\.\d+)?/);
  return m ? parseFloat(m[0]) : null;
}

const geo = $('Extract Geocoded').first().json;
const zoneInfo = $('Identify PAG Zone').first().json;
const allRules = $input.all();
const rules = allRules.length > 0 ? (allRules[0].json.fields || allRules[0].json) : {};

const parcelGeom = zoneInfo.parcel_geometry_wgs84;
if (!parcelGeom || !parcelGeom.coordinates) {
  throw new Error('Pas de geometrie parcelle WGS84 disponible pour Palladio');
}

const reculAvantMin = toFloat(rules.Recul_avant_min_m);
const reculAvantMax = toFloat(rules.Recul_avant_max_m);
const reculAvantCible = (reculAvantMax !== null && reculAvantMax > 0) ? reculAvantMax : (reculAvantMin || 0);

const reculLateral = toFloat(rules.Recul_lateral_min_m);
const reculArriere = toFloat(rules.Recul_arriere_min_m);
const profMax = toFloat(rules.Profondeur_max_m);

if (reculLateral === null || reculArriere === null) {
  throw new Error('Reculs lateral ou arriere manquants dans Airtable pour ' + zoneInfo.code_zone);
}

function parseNiveaux(v) {
  const s = String(extractAirtable(v) || '').toLowerCase();
  const combles = /comble|retrait/.test(s);
  const m = s.match(/\d+/);
  return { niveaux: m ? parseInt(m[0], 10) : 1, combles };
}
const niv = parseNiveaux(rules.Niveaux_hors_sol_max);

function parseArticles(v) {
  const s = extractAirtable(v);
  if (!s || typeof s !== 'string') return {};
  try { const o = JSON.parse(s); return (o && typeof o === 'object') ? o : {}; }
  catch (e) { return {}; }
}

const zone_pag = {
  code_zone: zoneInfo.code_zone,
  nom_zone: extractAirtable(rules.Nom_zone),
  type_zone: extractAirtable(rules.Type_zone),
  niveaux_pleins_max: niv.niveaux,
  combles_retrait: niv.combles,
  logement_autorise: extractAirtable(rules.Logement_autorise) || 'Non',
  commerce_autorise: extractAirtable(rules.Commerce_autorise) || 'Non',
  cus_max: (toFloat(rules.CUS_max) !== null ? toFloat(rules.CUS_max) : toFloat(rules.CSS_max)),
  cos_max: toFloat(rules.COS_max),
  min_scb_logement_pct: toFloat(rules['Min_SCB_logement_%_QE']),
  dl_max: toFloat(rules.DL_max_log_ha),
  nb_log_max_par_construction: toFloat(rules.Nb_logements_max),
};

const payload = {
  parcelle_id: geo.parcel_key,
  parcel_geometry_wgs84: parcelGeom,
  point_geocode_wgs84: [geo.lon_wgs84, geo.lat_wgs84],
  recul_avant_m: reculAvantCible,
  recul_lateral_m: reculLateral,
  recul_arriere_m: reculArriere,
  profondeur_max_m: profMax,
  zone_pag: zone_pag,
  adresse: geo.adresse || geo.address || '',
  contexte: {
    adresse: geo.adresse || '',
    parcel_label: geo.parcel_label || '',
    code_zone: zoneInfo.code_zone,
    nom_zone: extractAirtable(rules.Nom_zone),
    regles: {
      COS_max: toFloat(rules.COS_max),
      CSS_max: toFloat(rules.CSS_max),
      Hauteur_corniche_max_m: toFloat(rules.Hauteur_corniche_max_m),
      Hauteur_faite_max_m: toFloat(rules.Hauteur_faite_max_m),
      DL_max_log_ha: toFloat(rules.DL_max_log_ha),
    },
    // references d'articles pour les justifications (point 8). Map granulaire
    // {reculs, profondeur, bande, hauteurs, logements} + articles generaux.
    articles: parseArticles(rules.Source_articles_json),
    article_pag: extractAirtable(rules.Article_PAG),
    article_pap_qe: extractAirtable(rules.Article_PAP_QE),
  },
};

// Recul avant adaptatif : injecté seulement si non-fixe (alignement_voisins / lie_hauteur).
// 'fixe' -> rien -> comportement scalaire historique (zéro régression).
const methodeAvant = extractAirtable(rules.Methode_recul_avant);
if (methodeAvant && methodeAvant !== 'fixe') {
  const mAv = { type: methodeAvant, source_article: extractAirtable(rules.Article_PAP_QE) };
  if (methodeAvant === 'alignement_voisins') { mAv.fallback_m = toFloat(rules.Recul_avant_fallback_m); }
  else if (methodeAvant === 'lie_hauteur') { mAv.coef_hauteur = 0.5; mAv.plancher_m = toFloat(rules.Recul_avant_fallback_m); }
  payload.recul_avant_methode = mAv;
  const fbAv = mAv.fallback_m || mAv.plancher_m;
  if (fbAv && (!reculAvantCible || reculAvantCible <= 0)) payload.recul_avant_m = fbAv;
  const cornicheAv = toFloat(rules.Hauteur_corniche_max_m);
  if (cornicheAv !== null) payload.corniche_effective_m = cornicheAv;
}

return [{ json: { _palladio_payload: payload } }];
