const geo = $('Extract Geocoded').first().json;
const parcelle = $('Parcelle 359').first().json;
const zoneInfo = $('Identify PAG Zone').first().json;
const allRules = $('Lookup Rules Airtable').all().map(item => item.json);
const palladioResume = $('Build Palladio Payload').first().json._palladio_resume || {};
const palladioResponse = $input.first().json;

let etape5;
if (palladioResponse && palladioResponse.emprise) {
  etape5 = {
    status: 'ok',
    reculs_envoyes: palladioResume.reculs_appliques,
    parcel_nb_sommets_envoyes: palladioResume.parcel_nb_sommets,
    voirie: palladioResponse.voirie,
    fond: palladioResponse.fond,
    emprise: palladioResponse.emprise,
    traces_reculs: palladioResponse.traces_reculs,
    meta_engine: palladioResponse.meta,
    scb: palladioResponse.scb || null,
    logements: palladioResponse.logements || null,
    parkings: palladioResponse.parkings || null,
    type_construction: palladioResponse.type_construction || null,
    warnings: palladioResponse.warnings || [],
  };
} else {
  etape5 = {
    status: 'error',
    reculs_envoyes: palladioResume.reculs_appliques,
    error: palladioResponse && palladioResponse.detail ? palladioResponse.detail : 'Reponse Palladio inattendue',
    raw_response: palladioResponse,
  };
}

const debug = {
  meta: {
    workflow: 'Palladio',
    version: '0.5',
    timestamp: new Date().toISOString(),
    address_input: geo.adresse,
  },
  etape_1_geocodage: {
    adresse: geo.adresse, accuracy: geo.accuracy, ratio: geo.ratio,
    lat_wgs84: geo.lat_wgs84, lon_wgs84: geo.lon_wgs84,
    x_luref: geo.x_luref, y_luref: geo.y_luref,
    commune: geo.commune, zip: geo.zip, street: geo.street, postnumber: geo.postnumber,
    parcel_key: geo.parcel_key, parcel_label: geo.parcel_label, bbox_wgs84: geo.bbox,
  },
  etape_2_parcelle: { type: parcelle.type || null, properties: parcelle.properties || null, geometry: parcelle.geometry || null },
  etape_3_zone_pag: {
    features_count_in_bbox: zoneInfo.pag_features_count,
    code_zone: zoneInfo.code_zone,
    categorie: zoneInfo.pag_categorie, genre: zoneInfo.pag_genre,
    nom_fichier: zoneInfo.pag_nom_fichier, hit_properties: zoneInfo.pag_hit_properties,
  },
  etape_4_regles_airtable: {
    query: { commune_lower: zoneInfo.commune_lower, code_zone_lower: zoneInfo.code_zone_lower },
    matches_count: allRules.length,
    matches: allRules,
  },
  etape_5_emprise: etape5,
};

function renderPage(d) {
  if (d.etape_5_emprise.status !== 'ok') {
    return renderErrorPage(d);
  }

  const e1 = d.etape_1_geocodage;
  const e2 = d.etape_2_parcelle;
  const e3 = d.etape_3_zone_pag;
  const e4 = d.etape_4_regles_airtable;
  const e5 = d.etape_5_emprise;

  const wgsRing = e2.geometry.coordinates[0].slice(0, -1);
  const ptWgs = [e1.lon_wgs84, e1.lat_wgs84];
  const ptLuref = e5.voirie.point_luref;

  const COS_LAT = Math.cos(49.6 * Math.PI / 180);
  const SCALE_X = 111000 * COS_LAT;
  const SCALE_Y = 111000;
  function wgsToLurefApprox(lon, lat) {
    return [
      (lon - ptWgs[0]) * SCALE_X + ptLuref[0],
      (lat - ptWgs[1]) * SCALE_Y + ptLuref[1],
    ];
  }

  const parcelLurefPts = wgsRing.map(([lon, lat]) => wgsToLurefApprox(lon, lat));
  const empriseLurefPts = e5.emprise.geometry_luref.coordinates[0].slice(0, -1);

  const allXs = [...parcelLurefPts.map(p => p[0]), ...empriseLurefPts.map(p => p[0]), ptLuref[0]];
  const allYs = [...parcelLurefPts.map(p => p[1]), ...empriseLurefPts.map(p => p[1]), ptLuref[1]];
  const bbox = {
    xmin: Math.min(...allXs) - 8,
    xmax: Math.max(...allXs) + 8,
    ymin: Math.min(...allYs) - 8,
    ymax: Math.max(...allYs) + 8,
  };
  const bboxW = bbox.xmax - bbox.xmin;
  const bboxH = bbox.ymax - bbox.ymin;

  function projX(x) { return x - bbox.xmin; }
  function projY(y) { return bboxH - (y - bbox.ymin); }
  function pts2svg(pts) { return pts.map(p => projX(p[0]).toFixed(2) + ',' + projY(p[1]).toFixed(2)).join(' '); }

  const viewBox = `0 0 ${bboxW.toFixed(2)} ${bboxH.toFixed(2)}`;

  const cx = parcelLurefPts.reduce((s, p) => s + p[0], 0) / parcelLurefPts.length;
  const cy = parcelLurefPts.reduce((s, p) => s + p[1], 0) / parcelLurefPts.length;

  function edgeOffsetInward(idx, distance, extension) {
    const n = parcelLurefPts.length;
    const a = parcelLurefPts[idx];
    const b = parcelLurefPts[(idx + 1) % n];
    let dx = b[0] - a[0], dy = b[1] - a[1];
    const L = Math.hypot(dx, dy);
    dx /= L; dy /= L;
    let nx = -dy, ny = dx;
    const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    if (nx * (cx - mid[0]) + ny * (cy - mid[1]) < 0) {
      nx = -nx; ny = -ny;
    }
    const ext = extension || 0;
    return [
      [a[0] + nx * distance - dx * ext, a[1] + ny * distance - dy * ext],
      [b[0] + nx * distance + dx * ext, b[1] + ny * distance + dy * ext],
    ];
  }

  function edgeMid(idx) {
    const n = parcelLurefPts.length;
    const a = parcelLurefPts[idx];
    const b = parcelLurefPts[(idx + 1) % n];
    return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  }

  function vertexLabel(idx) {
    const n = parcelLurefPts.length;
    const p = parcelLurefPts[idx];
    const ox = p[0] - cx, oy = p[1] - cy;
    const L = Math.hypot(ox, oy);
    return [p[0] + (ox / L) * 1.5, p[1] + (oy / L) * 1.5];
  }

  function distPtSeg(px, py, ax, ay, bx, by) {
    const dx = bx - ax, dy = by - ay;
    const L2 = dx * dx + dy * dy;
    if (L2 < 1e-9) return Math.hypot(px - ax, py - ay);
    let t = ((px - ax) * dx + (py - ay) * dy) / L2;
    t = Math.max(0, Math.min(1, t));
    const qx = ax + t * dx, qy = ay + t * dy;
    return Math.hypot(px - qx, py - qy);
  }

  const idxVoirie = e5.voirie.idx;
  const idxFond = e5.fond.idx;
  const ra = e5.reculs_envoyes.avant_cible_m;
  const rl = e5.reculs_envoyes.lateral_m;
  const rr = e5.reculs_envoyes.arriere_m;
  const profMax = e5.reculs_envoyes.profondeur_max_m;
  const voirieMethod = (e5.voirie && e5.voirie.method) || 'unknown';
  const voirieDetection = (e5.voirie && e5.voirie.detection) || null;

  const sch1 = `<div class="schema-content schema-text-only"><div class="text-row"><span class="k">Adresse</span><span class="v">${e1.adresse}</span></div><div class="text-row"><span class="k">Numero cadastral</span><span class="v">${e1.parcel_label}</span></div><div class="text-row"><span class="k">Commune / Code postal</span><span class="v">${e1.commune} / ${e1.zip}</span></div><div class="text-row"><span class="k">Point geocode WGS84</span><span class="v mono">[${e1.lon_wgs84.toFixed(7)}, ${e1.lat_wgs84.toFixed(7)}]</span></div><div class="text-row"><span class="k">Point geocode LUREF</span><span class="v mono">[${e1.x_luref.toFixed(2)}, ${e1.y_luref.toFixed(2)}]</span></div><div class="text-row"><span class="k">Precision</span><span class="v">accuracy=${e1.accuracy} (8 = numero de maison), ratio=${e1.ratio}</span></div><div class="text-row"><span class="k">Methode voirie</span><span class="v mono">${voirieMethod}</span></div></div>`;

  const verticesLabels = parcelLurefPts.map((p, i) => {
    const lbl = vertexLabel(i);
    return `<text x="${projX(lbl[0]).toFixed(2)}" y="${projY(lbl[1]).toFixed(2)}" class="lbl-vertex">${String.fromCharCode(65 + i)}</text>`;
  }).join('');
  const verticesDots = parcelLurefPts.map(p =>
    `<circle cx="${projX(p[0]).toFixed(2)}" cy="${projY(p[1]).toFixed(2)}" r="0.5" class="dot-vertex"/>`
  ).join('');
  const ptGeocodeSvg = `<circle cx="${projX(ptLuref[0]).toFixed(2)}" cy="${projY(ptLuref[1]).toFixed(2)}" r="0.8" class="dot-geocode"/>`;

  const sch2 = `<svg viewBox="${viewBox}" class="schema-svg"><polygon points="${pts2svg(parcelLurefPts)}" class="parcel-fill"/>${verticesDots}${verticesLabels}${ptGeocodeSvg}</svg><div class="schema-caption">Polygone cadastral en LUREF EPSG:2169. ${parcelLurefPts.length} sommets. Surface <strong>${(polygonArea(parcelLurefPts)).toFixed(1)} m\u00b2</strong>. Point geocode en bleu.</div>`;

  const edgesVoirieSvg = parcelLurefPts.map((p, i) => {
    const n = parcelLurefPts.length;
    const a = p;
    const b = parcelLurefPts[(i + 1) % n];
    const d = distPtSeg(ptLuref[0], ptLuref[1], a[0], a[1], b[0], b[1]);
    const isWinner = (i === idxVoirie);
    const cls = isWinner ? 'edge-voirie-winner' : 'edge-voirie-other';
    const mid = edgeMid(i);
    return `<line x1="${projX(a[0]).toFixed(2)}" y1="${projY(a[1]).toFixed(2)}" x2="${projX(b[0]).toFixed(2)}" y2="${projY(b[1]).toFixed(2)}" class="${cls}"/><text x="${projX(mid[0]).toFixed(2)}" y="${projY(mid[1]).toFixed(2)}" class="${isWinner ? 'lbl-edge-winner' : 'lbl-edge'}">${d.toFixed(1)}m</text>`;
  }).join('');
  const aWin = parcelLurefPts[idxVoirie];
  const bWin = parcelLurefPts[(idxVoirie + 1) % parcelLurefPts.length];
  const winMid = edgeMid(idxVoirie);

  let cadastralOverlay = '';
  let cadastralCaption = '';
  if (voirieDetection && voirieDetection.edges_classified && voirieDetection.edges_classified.length > 0) {
    cadastralOverlay = voirieDetection.edges_classified.map(ec => {
      const ax = projX(ec.p1[0]).toFixed(2), ay = projY(ec.p1[1]).toFixed(2);
      const bx = projX(ec.p2[0]).toFixed(2), by = projY(ec.p2[1]).toFixed(2);
      const color = ec.is_voirie ? '#c9a961' : '#888';
      const width = ec.is_voirie ? '1.5' : '0.6';
      return `<line x1="${ax}" y1="${ay}" x2="${bx}" y2="${by}" stroke="${color}" stroke-width="${width}" fill="none"/>`;
    }).join('');
    const nbVoirie = voirieDetection.edges_classified.filter(e => e.is_voirie).length;
    const totalVoirieLen = voirieDetection.edges_classified.filter(e => e.is_voirie).reduce((s, e) => s + e.length_m, 0);
    cadastralCaption = ` Detection cadastrale: <strong>${nbVoirie}</strong> arete(s) voirie sur ${voirieDetection.edges_classified.length}, soit <strong>${totalVoirieLen.toFixed(1)}m</strong>. ${voirieDetection.n_neighbors_fetched} voisines fetched (${voirieDetection.n_neighbors_public} publiques). ${voirieDetection.fallback_used ? 'Fallback: ' + voirieDetection.fallback_used : 'OK'}.`;
  }

  const sch3 = `<svg viewBox="${viewBox}" class="schema-svg"><polygon points="${pts2svg(parcelLurefPts)}" class="parcel-fill-light"/>${edgesVoirieSvg}${cadastralOverlay}${verticesLabels}<line x1="${projX(ptLuref[0]).toFixed(2)}" y1="${projY(ptLuref[1]).toFixed(2)}" x2="${projX(winMid[0]).toFixed(2)}" y2="${projY(winMid[1]).toFixed(2)}" class="line-perp"/>${ptGeocodeSvg}</svg><div class="schema-caption">Distance du point geocode (bleu) a chaque arete. <strong>Arete ${e5.voirie.edge_label}</strong> retenue comme voirie.${cadastralCaption}</div>`;

  const cands = e5.fond.candidats;
  const candColors = ['#222', '#555', '#888'];
  const candsSvg = cands.map((c, k) => {
    const n = parcelLurefPts.length;
    const a = parcelLurefPts[c.idx_fond];
    const b = parcelLurefPts[(c.idx_fond + 1) % n];
    const isChosen = (c.idx_fond === idxFond);
    const stroke = isChosen ? '#000' : candColors[k];
    const width = isChosen ? '2' : '1.2';
    const dash = isChosen ? '' : '2,2';
    return `<line x1="${projX(a[0]).toFixed(2)}" y1="${projY(a[1]).toFixed(2)}" x2="${projX(b[0]).toFixed(2)}" y2="${projY(b[1]).toFixed(2)}" stroke="${stroke}" stroke-width="${width}" stroke-dasharray="${dash}" fill="none"/>`;
  }).join('');
  const voirieLine = `<line x1="${projX(aWin[0]).toFixed(2)}" y1="${projY(aWin[1]).toFixed(2)}" x2="${projX(bWin[0]).toFixed(2)}" y2="${projY(bWin[1]).toFixed(2)}" stroke="#c00" stroke-width="2.5" fill="none"/>`;

  const candsLegend = cands.map((c, k) => {
    const isChosen = (c.idx_fond === idxFond);
    return `<div class="cand-row ${isChosen ? 'cand-chosen' : ''}"><span class="cand-label">${c.fond_label}</span><span class="cand-score">score ${c.score_fond}</span><span class="cand-surf">${c.surface_emprise_m2.toFixed(1)} m\u00b2</span>${isChosen ? '<span class="cand-pick">retenu</span>' : ''}</div>`;
  }).join('');

  const sch4 = `<svg viewBox="${viewBox}" class="schema-svg"><polygon points="${pts2svg(parcelLurefPts)}" class="parcel-fill-light"/>${candsSvg}${voirieLine}${verticesLabels}</svg><div class="schema-caption">Top-3 candidats arete-fond. <strong>${e5.fond.edge_label}</strong> retenue. Voirie ${e5.voirie.edge_label} en rouge.</div><div class="cand-list">${candsLegend}</div>`;

  const lateralCotsSvg = parcelLurefPts.map((p, i) => {
    if (i === idxVoirie || i === idxFond) return '';
    const offset = edgeOffsetInward(i, rl, 0);
    return `<line x1="${projX(offset[0][0]).toFixed(2)}" y1="${projY(offset[0][1]).toFixed(2)}" x2="${projX(offset[1][0]).toFixed(2)}" y2="${projY(offset[1][1]).toFixed(2)}" class="line-recul-lateral"/>`;
  }).join('');
  const lateralLabels = parcelLurefPts.map((p, i) => {
    if (i === idxVoirie || i === idxFond) return '';
    const offset = edgeOffsetInward(i, rl, 0);
    const mid = [(offset[0][0] + offset[1][0]) / 2, (offset[0][1] + offset[1][1]) / 2];
    return `<text x="${projX(mid[0]).toFixed(2)}" y="${projY(mid[1]).toFixed(2)}" class="lbl-recul">${rl}m</text>`;
  }).join('');

  const sch5 = `<svg viewBox="${viewBox}" class="schema-svg"><polygon points="${pts2svg(parcelLurefPts)}" class="parcel-fill-light"/>${lateralCotsSvg}${lateralLabels}${verticesLabels}</svg><div class="schema-caption">Etape 1 du moteur : <code>buffer(-${rl}m)</code> applique uniformement aux aretes laterales.</div>`;

  const cotAvant = edgeOffsetInward(idxVoirie, ra, 0);
  const cotArriere = edgeOffsetInward(idxFond, rr, 0);
  let cotProfMax = '';
  if (profMax) {
    const cotProf = edgeOffsetInward(idxVoirie, ra + profMax, 0);
    const profMid = [(cotProf[0][0] + cotProf[1][0]) / 2, (cotProf[0][1] + cotProf[1][1]) / 2];
    cotProfMax = `<line x1="${projX(cotProf[0][0]).toFixed(2)}" y1="${projY(cotProf[0][1]).toFixed(2)}" x2="${projX(cotProf[1][0]).toFixed(2)}" y2="${projY(cotProf[1][1]).toFixed(2)}" class="line-recul-prof"/><text x="${projX(profMid[0]).toFixed(2)}" y="${projY(profMid[1]).toFixed(2)}" class="lbl-recul-prof">prof max ${ra}+${profMax}=${ra + profMax}m</text>`;
  }
  const midAvant = [(cotAvant[0][0] + cotAvant[1][0]) / 2, (cotAvant[0][1] + cotAvant[1][1]) / 2];
  const midArriere = [(cotArriere[0][0] + cotArriere[1][0]) / 2, (cotArriere[0][1] + cotArriere[1][1]) / 2];

  const sch6 = `<svg viewBox="${viewBox}" class="schema-svg"><polygon points="${pts2svg(parcelLurefPts)}" class="parcel-fill-light"/><line x1="${projX(aWin[0]).toFixed(2)}" y1="${projY(aWin[1]).toFixed(2)}" x2="${projX(bWin[0]).toFixed(2)}" y2="${projY(bWin[1]).toFixed(2)}" class="edge-voirie-thick"/><line x1="${projX(parcelLurefPts[idxFond][0]).toFixed(2)}" y1="${projY(parcelLurefPts[idxFond][1]).toFixed(2)}" x2="${projX(parcelLurefPts[(idxFond+1) % parcelLurefPts.length][0]).toFixed(2)}" y2="${projY(parcelLurefPts[(idxFond+1) % parcelLurefPts.length][1]).toFixed(2)}" class="edge-fond-thick"/><line x1="${projX(cotAvant[0][0]).toFixed(2)}" y1="${projY(cotAvant[0][1]).toFixed(2)}" x2="${projX(cotAvant[1][0]).toFixed(2)}" y2="${projY(cotAvant[1][1]).toFixed(2)}" class="line-recul-avant"/><text x="${projX(midAvant[0]).toFixed(2)}" y="${projY(midAvant[1]).toFixed(2)}" class="lbl-recul-avant">avant ${ra}m</text><line x1="${projX(cotArriere[0][0]).toFixed(2)}" y1="${projY(cotArriere[0][1]).toFixed(2)}" x2="${projX(cotArriere[1][0]).toFixed(2)}" y2="${projY(cotArriere[1][1]).toFixed(2)}" class="line-recul-arriere"/><text x="${projX(midArriere[0]).toFixed(2)}" y="${projY(midArriere[1]).toFixed(2)}" class="lbl-recul-arriere">arriere ${rr}m</text>${cotProfMax}${verticesLabels}</svg><div class="schema-caption">Demi-plan avant (recul ${ra}m depuis voirie ${e5.voirie.edge_label}), demi-plan arriere (recul ${rr}m depuis fond ${e5.fond.edge_label})${profMax ? ', clip a ' + (ra + profMax) + 'm de profondeur max' : ''}.</div>`;

  const sch7 = `<svg viewBox="${viewBox}" class="schema-svg"><polygon points="${pts2svg(parcelLurefPts)}" class="parcel-fill-final"/><polygon points="${pts2svg(empriseLurefPts)}" class="emprise-fill"/>${verticesLabels}</svg><div class="schema-caption">Resultat final : enveloppe constructible <strong>${e5.emprise.surface_m2} m\u00b2</strong> (${e5.emprise.nb_sommets} sommets) sur parcelle de <strong>${polygonArea(parcelLurefPts).toFixed(1)} m\u00b2</strong>. Ratio constructible <strong>${(e5.emprise.ratio_vs_cadastrale * 100).toFixed(1)}%</strong>.</div>`;

  // ===== Sprint 2 : schemas metier 08-11 =====
  const scb = e5.scb;
  const sch8 = scb ? `<div class="schema-content schema-text-only">${scb.ventilation_par_niveau.map(v => `<div class="text-row"><span class="k">${v.niveau}</span><span class="v mono">${v.scb_m2} m²</span></div>`).join('')}<div class="text-row"><span class="k">SCB totale</span><span class="v"><strong>${scb.scb_totale_m2} m²</strong></span></div><div class="text-row"><span class="k">Surface habitable</span><span class="v">${scb.surface_habitable_m2} m² (SCB × 0.80)</span></div>${scb.cus_applique ? `<div class="text-row"><span class="k">Plafond CUS</span><span class="v">${scb.cus_applique.scb_max_cus_m2} m² ${scb.cus_applique.limitant ? '⚠ limitant' : 'OK'}</span></div>` : ''}</div><div class="schema-caption">Emprise au sol ${scb.emprise_au_sol_m2} m² × ${scb.niveaux_pleins} niveaux${scb.combles ? ' + combles (60% emprise)' : ''}.</div>` : `<div class="schema-caption">Indisponible (endpoint /calcul sans couche metier).</div>`;

  const lg = e5.logements;
  const pk = e5.parkings;
  const mixRows = (lg && lg.mix_detail) ? Object.entries(lg.mix_detail).map(([t, m]) => `<div class="text-row"><span class="k">${t}</span><span class="v">${m.nb} × ${m.shn_m2} m² SHN</span></div>`).join('') : '';
  const sch9 = lg ? `<div class="schema-content schema-text-only"><div class="text-row"><span class="k">Logements</span><span class="v"><strong>${lg.nb_logements}</strong></span></div>${mixRows}<div class="text-row"><span class="k">Moyenne SHN</span><span class="v">${lg.surface_moyenne_shn_m2} m²</span></div>${pk ? `<div class="text-row"><span class="k">Parkings auto</span><span class="v">${pk.auto_min} a ${pk.auto_max}</span></div><div class="text-row"><span class="k">Parkings velo</span><span class="v">${pk.velo}</span></div><div class="text-row"><span class="k">Surface SS estimee</span><span class="v">${pk.surface_sous_sol_estimee_m2} m²</span></div>` : ''}</div><div class="schema-caption">${(lg.contraintes && lg.contraintes.length) ? lg.contraintes.join(' · ') : 'Aucune contrainte logement.'}${(lg.hab1 && lg.hab1.corrige) ? ' · HAB-1 corrige' : ' · fidele main.py (HAB-1)'}</div>` : `<div class="schema-caption">Indisponible.</div>`;

  const tc = e5.type_construction;
  const sch10 = tc ? `<div class="schema-content schema-text-only"><div class="text-row"><span class="k">Type</span><span class="v"><strong>${tc.type}</strong></span></div><div class="text-row"><span class="k">Mitoyennetes laterales</span><span class="v">${tc.n_mitoyens != null ? tc.n_mitoyens : '?'} sur ${tc.n_lateraux != null ? tc.n_lateraux : '?'} laterales</span></div><div class="text-row"><span class="k">Methode</span><span class="v mono">${tc.method}</span></div><div class="text-row"><span class="k">Confiance</span><span class="v">${tc.confiance || '?'}</span></div></div><div class="schema-caption">Proxy d'adjacence cadastrale (Sprint 1.5) : adjacence fonciere, pas mitoyennete batie reelle.</div>` : `<div class="schema-caption">Indisponible.</div>`;

  const wn = e5.warnings || [];
  const lvlColor = { info: '#2962ff', warning: '#c9a961', critique: '#c00' };
  const sch11 = `<div class="schema-content">${wn.length ? wn.map(w => `<div style="display:flex;gap:12px;align-items:baseline;padding:8px 0;border-bottom:1px solid #f0f0f0"><span style="font-family:ui-monospace,monospace;font-size:11px;text-transform:uppercase;color:#fff;background:${lvlColor[w.level] || '#888'};padding:2px 6px;border-radius:3px">${w.level}</span><span style="font-family:ui-monospace,monospace;font-size:12px;color:#888;min-width:210px">${w.code}${w.edge ? ' (' + w.edge + ')' : ''}</span><span style="font-size:13px;color:#111">${w.message_fr}</span></div>`).join('') : '<div class="schema-caption">Aucun warning.</div>'}</div>`;

  const ruleMatch = e4.matches.length > 0 ? e4.matches[0].fields : {};
  const cos = ruleMatch.COS_max || '?';
  const css = ruleMatch.CSS_max || '?';
  const hFaite = ruleMatch.Hauteur_faite_max_m || '?';
  const hCorniche = ruleMatch.Hauteur_corniche_max_m || '?';

  const bandeauHtml = `<header class="bandeau"><h1>Palladio \u00b7 debug</h1><div class="bandeau-meta">v${d.meta.version} \u00b7 ${d.meta.timestamp.slice(0, 16).replace('T', ' ')} \u00b7 voirie: ${voirieMethod}</div><div class="bandeau-grid"><div class="info-block"><div class="info-label">Adresse</div><div class="info-value">${e1.adresse}</div><div class="info-sub">${e1.parcel_label}</div></div><div class="info-block"><div class="info-label">Zone PAG</div><div class="info-value">${e3.code_zone}</div><div class="info-sub">${ruleMatch.Nom_zone || ''} \u00b7 ${ruleMatch.PAP_QE || ''}</div></div><div class="info-block"><div class="info-label">Reculs appliques</div><div class="info-value">${ra} / ${rl} / ${rr} m</div><div class="info-sub">avant / lateral / arriere \u00b7 prof max ${profMax}m</div></div><div class="info-block"><div class="info-label">Constructibilite</div><div class="info-value">COS ${cos} \u00b7 CSS ${css}</div><div class="info-sub">h corniche ${hCorniche}m \u00b7 h faite ${hFaite}m</div></div><div class="info-block info-result"><div class="info-label">Emprise calculee</div><div class="info-value-big">${e5.emprise.surface_m2} m\u00b2</div><div class="info-sub">${(e5.emprise.ratio_vs_cadastrale * 100).toFixed(1)}% de la parcelle \u00b7 ${e5.emprise.nb_sommets} sommets</div></div></div></header>`;

  return `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Palladio debug \u00b7 ${e1.adresse}</title><style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:14px;line-height:1.5;color:#111;background:#fff;padding:32px 40px 80px}.mono{font-family:ui-monospace,'SF Mono','Menlo','Consolas',monospace;font-size:12px}.bandeau{margin-bottom:48px;padding-bottom:24px;border-bottom:1px solid #e5e5e5}.bandeau h1{font-size:24px;font-weight:600;letter-spacing:-0.01em}.bandeau-meta{color:#888;font-size:12px;font-family:ui-monospace,monospace;margin-bottom:24px}.bandeau-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:24px}.info-block{padding:16px 0}.info-label{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#888;margin-bottom:6px}.info-value{font-size:15px;font-weight:500;color:#111}.info-value-big{font-size:28px;font-weight:600;color:#111;letter-spacing:-0.02em}.info-sub{font-size:12px;color:#777;margin-top:4px}.info-result{padding:16px 20px;background:#f7f7f5;border-radius:6px}.schemas-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:32px}.schema-card{border:1px solid #e5e5e5;border-radius:6px;padding:24px;background:#fff}.schema-card.wide{grid-column:1 / -1}.schema-header{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px}.schema-num{font-size:11px;font-family:ui-monospace,monospace;color:#888}.schema-title{font-size:16px;font-weight:600;letter-spacing:-0.01em}.schema-svg{width:100%;height:360px;display:block}.schema-card.wide .schema-svg{height:500px}.schema-caption{font-size:13px;color:#555;margin-top:12px;line-height:1.55}.schema-content{padding:8px 0}.schema-text-only .text-row{display:grid;grid-template-columns:200px 1fr;gap:16px;padding:10px 0;border-bottom:1px solid #f0f0f0}.schema-text-only .text-row:last-child{border-bottom:0}.schema-text-only .k{font-size:12px;color:#888;text-transform:uppercase;letter-spacing:.04em}.schema-text-only .v{font-size:14px;color:#111}.parcel-fill{fill:#fafafa;stroke:#111;stroke-width:0.4}.parcel-fill-light{fill:#fafafa;stroke:#ccc;stroke-width:0.3}.parcel-fill-final{fill:#f3f3f3;stroke:#888;stroke-width:0.3}.emprise-fill{fill:#111;fill-opacity:0.85;stroke:#000;stroke-width:0.3}.dot-vertex{fill:#111}.dot-geocode{fill:#2962ff}.lbl-vertex{font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:1.8px;font-weight:600;fill:#111;text-anchor:middle;dominant-baseline:middle}.edge-voirie-other{stroke:#ccc;stroke-width:0.3;fill:none}.edge-voirie-winner{stroke:#c00;stroke-width:0.8;fill:none}.lbl-edge{font-size:1.4px;fill:#888;text-anchor:middle;dominant-baseline:middle}.lbl-edge-winner{font-size:1.6px;fill:#c00;font-weight:600;text-anchor:middle;dominant-baseline:middle}.line-perp{stroke:#2962ff;stroke-width:0.3;stroke-dasharray:0.8,0.8;fill:none}.line-recul-lateral{stroke:#555;stroke-width:0.4;stroke-dasharray:1.2,1.2;fill:none}.lbl-recul{font-size:1.4px;fill:#555;text-anchor:middle;dominant-baseline:middle}.edge-voirie-thick{stroke:#c00;stroke-width:0.7;fill:none}.edge-fond-thick{stroke:#2a7;stroke-width:0.7;fill:none}.line-recul-avant{stroke:#c00;stroke-width:0.4;stroke-dasharray:1.2,1.2;fill:none}.line-recul-arriere{stroke:#2a7;stroke-width:0.4;stroke-dasharray:1.2,1.2;fill:none}.line-recul-prof{stroke:#84c;stroke-width:0.4;stroke-dasharray:0.6,0.6;fill:none}.lbl-recul-avant{font-size:1.4px;fill:#c00;font-weight:600;text-anchor:middle;dominant-baseline:middle}.lbl-recul-arriere{font-size:1.4px;fill:#2a7;font-weight:600;text-anchor:middle;dominant-baseline:middle}.lbl-recul-prof{font-size:1.3px;fill:#84c;font-weight:600;text-anchor:middle;dominant-baseline:middle}.cand-list{margin-top:12px;padding-top:12px;border-top:1px solid #f0f0f0;display:flex;flex-direction:column;gap:4px}.cand-row{display:grid;grid-template-columns:60px 100px 100px 1fr;gap:12px;padding:4px 0;font-size:13px}.cand-row.cand-chosen{font-weight:600}.cand-label{font-family:ui-monospace,monospace}.cand-score{color:#888;font-size:12px}.cand-pick{color:#2a7;font-size:12px;text-transform:uppercase;letter-spacing:.05em}.footer{margin-top:64px;padding-top:24px;border-top:1px solid #e5e5e5;display:flex;justify-content:space-between;color:#888;font-size:12px;font-family:ui-monospace,monospace}</style></head><body>${bandeauHtml}<div class="schemas-grid"><div class="schema-card wide"><div class="schema-header"><span class="schema-num">01</span><span class="schema-title">Geocodage</span></div>${sch1}</div><div class="schema-card"><div class="schema-header"><span class="schema-num">02</span><span class="schema-title">Parcelle cadastrale</span></div>${sch2}</div><div class="schema-card"><div class="schema-header"><span class="schema-num">03</span><span class="schema-title">Detection voirie</span></div>${sch3}</div><div class="schema-card"><div class="schema-header"><span class="schema-num">04</span><span class="schema-title">Candidats arete-fond</span></div>${sch4}</div><div class="schema-card"><div class="schema-header"><span class="schema-num">05</span><span class="schema-title">Buffer lateral uniforme</span></div>${sch5}</div><div class="schema-card wide"><div class="schema-header"><span class="schema-num">06</span><span class="schema-title">Reculs avant / arriere / profondeur max</span></div>${sch6}</div><div class="schema-card wide"><div class="schema-header"><span class="schema-num">07</span><span class="schema-title">Emprise constructible finale</span></div>${sch7}</div><div class="schema-card"><div class="schema-header"><span class="schema-num">08</span><span class="schema-title">SCB par niveau</span></div>${sch8}</div><div class="schema-card"><div class="schema-header"><span class="schema-num">09</span><span class="schema-title">Logements &amp; parkings</span></div>${sch9}</div><div class="schema-card"><div class="schema-header"><span class="schema-num">10</span><span class="schema-title">Type de construction</span></div>${sch10}</div><div class="schema-card wide"><div class="schema-header"><span class="schema-num">11</span><span class="schema-title">Warnings</span></div>${sch11}</div></div><footer class="footer"><span>Palladio engine ${e5.meta_engine.version} \u00b7 ${e5.meta_engine.method}</span><span>${d.meta.timestamp}</span></footer></body></html>`;
}

function renderErrorPage(d) {
  return `<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Palladio error</title><style>body{font-family:Helvetica,Arial,sans-serif;max-width:800px;margin:60px auto;padding:0 24px;color:#111}.err{background:#fff5f5;border:1px solid #fcc;border-radius:6px;padding:24px}h1{font-size:20px;margin-bottom:12px}pre{background:#f7f7f5;padding:16px;border-radius:6px;font-size:12px;overflow:auto}</style></head><body><h1>Palladio \u00b7 erreur de calcul</h1><div class="err"><strong>${d.etape_5_emprise.error || 'Erreur inconnue'}</strong></div><h2 style="font-size:14px;margin-top:32px;margin-bottom:8px;color:#888;">Debug data</h2><pre>${JSON.stringify(d, null, 2)}</pre></body></html>`;
}

function polygonArea(pts) {
  let s = 0;
  const n = pts.length;
  for (let i = 0; i < n; i++) {
    const [x1, y1] = pts[i];
    const [x2, y2] = pts[(i + 1) % n];
    s += x1 * y2 - x2 * y1;
  }
  return Math.abs(s / 2);
}

const html = renderPage(debug);
return [{ json: { ...debug, html } }];
