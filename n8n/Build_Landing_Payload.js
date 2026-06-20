// node "Build Landing Payload" du workflow Palladio (n8n XFOhmez4MtTnmtnL).
// Branche "page d'accueil" (Webhook Form GET /webhook/palladio).
// Agrege les tables Airtable listees en amont et les passe au rendu serveur
// (POST /palladio/landing/html, module cockpit_render). Le calcul de couverture
// et le HTML vivent dans le repo (versionnes/testes), pas ici.
function recs(name) {
  try { return $(name).all().map(i => i.json.fields || i.json); }
  catch (e) { return []; }
}
const payload = {
  zones: recs('List Zones PAG'),
  stationnement: recs('List Stationnement'),
  velo: recs('List Velo'),
  servitudes: recs('List Servitudes'),
  pap_nq: recs('List PAP NQ'),
  communes: recs('List Communes'),
};
return [{ json: { _landing_payload: payload } }];
