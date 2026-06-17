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

// Niveaux hors-sol : "3 + combles/retrait" -> {niveaux:3, combles:true}
function parseNiveaux(v) {
  const s = String(extractAirtable(v) || '').toLowerCase();
  const combles = /comble|retrait/.test(s);
  const m = s.match(/\d+/);
  return { niveaux: m ? parseInt(m[0], 10) : 1, combles };
}
const niv = parseNiveaux(rules.Niveaux_hors_sol_max);

// Regles PAG mappees pour la couche metier Sprint 2 (/palladio/calcul/full)
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
};

return [{ json: {
  _palladio_payload: payload,
  _palladio_resume: {
    parcelle_id: geo.parcel_key,
    reculs_appliques: {
      avant_cible_m: reculAvantCible,
      avant_min_pag: reculAvantMin,
      avant_max_pag: reculAvantMax,
      lateral_m: reculLateral,
      arriere_m: reculArriere,
      profondeur_max_m: profMax,
    },
    parcel_nb_sommets: parcelGeom.coordinates[0].length - 1,
  },
}}];