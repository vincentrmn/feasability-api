const geo = $('Extract Geocoded').first().json;
const parcelle = $('Parcelle 359').first().json;
const zoneInfo = $('Identify PAG Zone').first().json;
const allRules = $('Lookup Rules Airtable').all().map(item => item.json);
const palladioResume = $('Build Palladio Payload').first().json._palladio_resume || {};
const palladioResponse = $input.first().json;

const FORM_URL = 'https://n8n-production-8929d.up.railway.app/webhook/palladio';

let etape5;
if (palladioResponse && palladioResponse.emprise) {
  etape5 = {
    status: 'ok',
    reculs_envoyes: palladioResume.reculs_appliques,
    parcel_nb_sommets_envoyes: palladioResume.parcel_nb_sommets,
    parcelle: palladioResponse.parcelle,
    voirie: palladioResponse.voirie,
    fond: palladioResponse.fond,
    emprise: palladioResponse.emprise,
    traces_reculs: palladioResponse.traces_reculs,
    meta_engine: palladioResponse.meta,
    scb: palladioResponse.scb || null,
    logements: palladioResponse.logements || null,
    parkings: palladioResponse.parkings || null,
    type_construction: palladioResponse.type_construction || null,
    mitoyennete_batie: palladioResponse.mitoyennete_batie || null,
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
    version: '0.6',
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

  // Parcelle dessinee depuis la geometrie LUREF FUSIONNEE du moteur (faces entieres,
  // labels coherents avec voirie/fond).
  const ptLuref = e5.voirie.point_luref;
  const parcelLurefPts = e5.parcelle.geometry_luref.coordinates[0].slice(0, -1);
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
  const partyWalls = (e5.emprise && e5.emprise.mitoyennete_batie_appliquee) || [];

  const verticesLabels = parcelLurefPts.map((p, i) => {
    const lbl = vertexLabel(i);
    return `<text x="${projX(lbl[0]).toFixed(2)}" y="${projY(lbl[1]).toFixed(2)}" class="lbl-vertex">${String.fromCharCode(65 + i)}</text>`;
  }).join('');
  const verticesDots = parcelLurefPts.map(p =>
    `<circle cx="${projX(p[0]).toFixed(2)}" cy="${projY(p[1]).toFixed(2)}" r="0.5" class="dot-vertex"/>`
  ).join('');
  const ptGeocodeSvg = `<circle cx="${projX(ptLuref[0]).toFixed(2)}" cy="${projY(ptLuref[1]).toFixed(2)}" r="0.8" class="dot-geocode"/>`;

  // --- Schema parcelle ---
  const schParcelle = `<svg viewBox="${viewBox}" class="schema-svg"><polygon points="${pts2svg(parcelLurefPts)}" class="parcel-fill"/>${verticesDots}${verticesLabels}${ptGeocodeSvg}</svg><div class="schema-caption">Polygone cadastral (LUREF EPSG:2169), ${parcelLurefPts.length} sommets. Surface <strong>${(polygonArea(parcelLurefPts)).toFixed(1)} m²</strong>. Le point bleu est l'adresse géocodée.</div>`;

  // --- Schema detection voirie ---
  const edgesVoirieSvg = parcelLurefPts.map((p, i) => {
    const n = parcelLurefPts.length;
    const a = p;
    const b = parcelLurefPts[(i + 1) % n];
    const isWinner = (i === idxVoirie);
    const cls = isWinner ? 'edge-voirie-winner' : 'edge-voirie-other';
    const mid = edgeMid(i);
    const dd = distPtSeg(ptLuref[0], ptLuref[1], a[0], a[1], b[0], b[1]);
    return `<line x1="${projX(a[0]).toFixed(2)}" y1="${projY(a[1]).toFixed(2)}" x2="${projX(b[0]).toFixed(2)}" y2="${projY(b[1]).toFixed(2)}" class="${cls}"/><text x="${projX(mid[0]).toFixed(2)}" y="${projY(mid[1]).toFixed(2)}" class="${isWinner ? 'lbl-edge-winner' : 'lbl-edge'}">${dd.toFixed(1)}m</text>`;
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
      const color = ec.is_voirie ? '#c9a961' : '#bbb';
      const width = ec.is_voirie ? '1.5' : '0.6';
      return `<line x1="${ax}" y1="${ay}" x2="${bx}" y2="${by}" stroke="${color}" stroke-width="${width}" fill="none"/>`;
    }).join('');
    const nbVoirie = voirieDetection.edges_classified.filter(e => e.is_voirie).length;
    const totalVoirieLen = voirieDetection.edges_classified.filter(e => e.is_voirie).reduce((s, e) => s + e.length_m, 0);
    cadastralCaption = ` Les arêtes en ambre touchent le domaine public : <strong>${nbVoirie}</strong> sur ${voirieDetection.edges_classified.length} (${totalVoirieLen.toFixed(1)} m de façade rue).`;
  }

  const schVoirie = `<svg viewBox="${viewBox}" class="schema-svg"><polygon points="${pts2svg(parcelLurefPts)}" class="parcel-fill-light"/>${edgesVoirieSvg}${cadastralOverlay}${verticesLabels}<line x1="${projX(ptLuref[0]).toFixed(2)}" y1="${projY(ptLuref[1]).toFixed(2)}" x2="${projX(winMid[0]).toFixed(2)}" y2="${projY(winMid[1]).toFixed(2)}" class="line-perp"/>${ptGeocodeSvg}</svg><div class="schema-caption">Distance du point d'adresse à chaque côté. La façade sur rue retenue est l'arête <strong>${e5.voirie.edge_label}</strong>.${cadastralCaption}</div>`;

  // --- Schema candidats fond ---
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
    return `<div class="cand-row ${isChosen ? 'cand-chosen' : ''}"><span class="cand-label">${c.fond_label}</span><span class="cand-score">score ${c.score_fond}</span><span class="cand-surf">${c.surface_emprise_m2.toFixed(1)} m²</span>${isChosen ? '<span class="cand-pick">retenu</span>' : ''}</div>`;
  }).join('');
  const schFond = `<svg viewBox="${viewBox}" class="schema-svg"><polygon points="${pts2svg(parcelLurefPts)}" class="parcel-fill-light"/>${candsSvg}${voirieLine}${verticesLabels}</svg><div class="schema-caption">On teste les côtés candidats pour le fond. <strong>${e5.fond.edge_label}</strong> est retenu. La façade rue ${e5.voirie.edge_label} est en rouge.</div><div class="cand-list">${candsLegend}</div>`;

  // --- Schema mitoyennete batie (Sprint 3) ---
  const mito = e5.mitoyennete_batie;
  let schMito;
  if (mito && mito.edges && mito.edges.length) {
    const mitoEdgesSvg = parcelLurefPts.map((p, i) => {
      const n = parcelLurefPts.length;
      const a = p;
      const b = parcelLurefPts[(i + 1) % n];
      const isParty = partyWalls.indexOf(i) !== -1;
      const isVoirie = (i === idxVoirie);
      const color = isParty ? '#e08a2e' : (isVoirie ? '#2962ff' : '#ccc');
      const width = isParty ? '1.8' : (isVoirie ? '1' : '0.5');
      let lbl = '';
      if (isParty) {
        const mid = edgeMid(i);
        lbl = `<text x="${projX(mid[0]).toFixed(2)}" y="${projY(mid[1]).toFixed(2)}" class="lbl-mito">mur mitoyen</text>`;
      }
      return `<line x1="${projX(a[0]).toFixed(2)}" y1="${projY(a[1]).toFixed(2)}" x2="${projX(b[0]).toFixed(2)}" y2="${projY(b[1]).toFixed(2)}" stroke="${color}" stroke-width="${width}" fill="none"/>${lbl}`;
    }).join('');
    const nMurs = mito.n_murs_mitoyens_batis || 0;
    const detailMito = mito.edges.filter(x => x.mur_mitoyen_bati)
      .map(x => `${x.label} (${x.overlap_bati_m} m de mur)`).join(', ');
    schMito = `<svg viewBox="${viewBox}" class="schema-svg"><polygon points="${pts2svg(parcelLurefPts)}" class="parcel-fill-light"/>${mitoEdgesSvg}${verticesLabels}</svg><div class="schema-caption">${mito.n_batiments} bâtiment(s) voisin(s) analysé(s). <strong>${nMurs}</strong> mur(s) mitoyen(s) bâti(s) détecté(s)${detailMito ? ' : ' + detailMito : ''}. Les côtés en orange passent en recul 0.</div>`;
  } else {
    schMito = `<div class="schema-content"><div class="schema-caption">Détection de mitoyenneté bâtie indisponible pour cette parcelle.</div></div>`;
  }

  // --- Schema reculs lateraux (avec recul 0 sur murs mitoyens) ---
  const lateralCotsSvg = parcelLurefPts.map((p, i) => {
    if (i === idxVoirie || i === idxFond) return '';
    const isParty = partyWalls.indexOf(i) !== -1;
    if (isParty) {
      const a = p, b = parcelLurefPts[(i + 1) % parcelLurefPts.length];
      return `<line x1="${projX(a[0]).toFixed(2)}" y1="${projY(a[1]).toFixed(2)}" x2="${projX(b[0]).toFixed(2)}" y2="${projY(b[1]).toFixed(2)}" class="edge-mitoyen"/>`;
    }
    const offset = edgeOffsetInward(i, rl, 0);
    return `<line x1="${projX(offset[0][0]).toFixed(2)}" y1="${projY(offset[0][1]).toFixed(2)}" x2="${projX(offset[1][0]).toFixed(2)}" y2="${projY(offset[1][1]).toFixed(2)}" class="line-recul-lateral"/>`;
  }).join('');
  const lateralLabels = parcelLurefPts.map((p, i) => {
    if (i === idxVoirie || i === idxFond) return '';
    const isParty = partyWalls.indexOf(i) !== -1;
    const mid = edgeMid(i);
    if (isParty) {
      return `<text x="${projX(mid[0]).toFixed(2)}" y="${projY(mid[1]).toFixed(2)}" class="lbl-mito">mitoyen 0m</text>`;
    }
    const offset = edgeOffsetInward(i, rl, 0);
    const omid = [(offset[0][0] + offset[1][0]) / 2, (offset[0][1] + offset[1][1]) / 2];
    return `<text x="${projX(omid[0]).toFixed(2)}" y="${projY(omid[1]).toFixed(2)}" class="lbl-recul">${rl}m</text>`;
  }).join('');
  const schLateral = `<svg viewBox="${viewBox}" class="schema-svg"><polygon points="${pts2svg(parcelLurefPts)}" class="parcel-fill-light"/>${lateralCotsSvg}${lateralLabels}${verticesLabels}</svg><div class="schema-caption">Reculs latéraux : <strong>${rl} m</strong> de chaque côté${partyWalls.length ? `, sauf sur le(s) côté(s) mitoyen(s) en orange où le recul tombe à <strong>0</strong>` : ''}.</div>`;

  // --- Schema reculs avant / arriere / profondeur ---
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
  const schAvAr = `<svg viewBox="${viewBox}" class="schema-svg"><polygon points="${pts2svg(parcelLurefPts)}" class="parcel-fill-light"/><line x1="${projX(aWin[0]).toFixed(2)}" y1="${projY(aWin[1]).toFixed(2)}" x2="${projX(bWin[0]).toFixed(2)}" y2="${projY(bWin[1]).toFixed(2)}" class="edge-voirie-thick"/><line x1="${projX(parcelLurefPts[idxFond][0]).toFixed(2)}" y1="${projY(parcelLurefPts[idxFond][1]).toFixed(2)}" x2="${projX(parcelLurefPts[(idxFond+1) % parcelLurefPts.length][0]).toFixed(2)}" y2="${projY(parcelLurefPts[(idxFond+1) % parcelLurefPts.length][1]).toFixed(2)}" class="edge-fond-thick"/><line x1="${projX(cotAvant[0][0]).toFixed(2)}" y1="${projY(cotAvant[0][1]).toFixed(2)}" x2="${projX(cotAvant[1][0]).toFixed(2)}" y2="${projY(cotAvant[1][1]).toFixed(2)}" class="line-recul-avant"/><text x="${projX(midAvant[0]).toFixed(2)}" y="${projY(midAvant[1]).toFixed(2)}" class="lbl-recul-avant">avant ${ra}m</text><line x1="${projX(cotArriere[0][0]).toFixed(2)}" y1="${projY(cotArriere[0][1]).toFixed(2)}" x2="${projX(cotArriere[1][0]).toFixed(2)}" y2="${projY(cotArriere[1][1]).toFixed(2)}" class="line-recul-arriere"/><text x="${projX(midArriere[0]).toFixed(2)}" y="${projY(midArriere[1]).toFixed(2)}" class="lbl-recul-arriere">arriere ${rr}m</text>${cotProfMax}${verticesLabels}</svg><div class="schema-caption">Recul avant de <strong>${ra} m</strong> depuis la rue (${e5.voirie.edge_label}), recul arrière de <strong>${rr} m</strong> depuis le fond (${e5.fond.edge_label})${profMax ? `, et profondeur bâtie limitée à ${ra + profMax} m depuis la rue` : ''}.</div>`;

  // --- Schema emprise finale (avec dimensions sur chaque cote du batiment) ---
  const empDimLabels = empriseLurefPts.map((p, i) => {
    const n = empriseLurefPts.length;
    const a = p;
    const b = empriseLurefPts[(i + 1) % n];
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (len < 1.5) return '';
    // decale le label legerement vers l'exterieur de l'emprise
    let mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
    let dx = b[0] - a[0], dy = b[1] - a[1];
    const L = Math.hypot(dx, dy) || 1;
    let nx = dy / L, ny = -dx / L;
    const ecx = empriseLurefPts.reduce((s, q) => s + q[0], 0) / n;
    const ecy = empriseLurefPts.reduce((s, q) => s + q[1], 0) / n;
    if (nx * (mx - ecx) + ny * (my - ecy) < 0) { nx = -nx; ny = -ny; }
    mx += nx * 1.6; my += ny * 1.6;
    return `<text x="${projX(mx).toFixed(2)}" y="${projY(my).toFixed(2)}" class="lbl-dim">${len.toFixed(1)}m</text>`;
  }).join('');
  const empEdgeLens = empriseLurefPts.map((p, i) => {
    const b = empriseLurefPts[(i + 1) % empriseLurefPts.length];
    return Math.hypot(b[0] - p[0], b[1] - p[1]);
  }).filter(l => l >= 1.5).sort((x, y) => y - x);
  const dimResume = empEdgeLens.length >= 2 ? ` Gabarit au sol : environ <strong>${empEdgeLens[0].toFixed(1)} m × ${empEdgeLens[1].toFixed(1)} m</strong>.` : '';
  const schEmprise = `<svg viewBox="${viewBox}" class="schema-svg"><polygon points="${pts2svg(parcelLurefPts)}" class="parcel-fill-final"/><polygon points="${pts2svg(empriseLurefPts)}" class="emprise-fill"/>${empDimLabels}${verticesLabels}</svg><div class="schema-caption">La zone noire est l'emprise constructible : <strong>${e5.emprise.surface_m2} m²</strong> sur un terrain de <strong>${polygonArea(parcelLurefPts).toFixed(1)} m²</strong>, soit <strong>${(e5.emprise.ratio_vs_cadastrale * 100).toFixed(1)}%</strong>.${dimResume} Les cotes sont en mètres.</div>`;

  // --- Schemas metier (texte) ---
  const scb = e5.scb;
  const schScb = scb ? `<div class="schema-content">${scb.ventilation_par_niveau.map(v => `<div class="text-row"><span class="k">${v.niveau}</span><span class="v mono">${v.scb_m2} m²</span></div>`).join('')}<div class="text-row"><span class="k">SCB totale</span><span class="v"><strong>${scb.scb_totale_m2} m²</strong></span></div><div class="text-row"><span class="k">Surface habitable</span><span class="v">${scb.surface_habitable_m2} m² (SCB × 0,80)</span></div>${scb.cus_applique ? `<div class="text-row"><span class="k">Plafond densité (CUS)</span><span class="v">${scb.cus_applique.scb_max_cus_m2} m² ${scb.cus_applique.limitant ? '⚠ limitant' : 'OK'}</span></div>` : ''}</div>` : '';

  const lg = e5.logements;
  const pk = e5.parkings;
  const mixRows = (lg && lg.mix_detail) ? Object.entries(lg.mix_detail).map(([t, m]) => `<div class="text-row"><span class="k">${t}</span><span class="v">${m.nb} × ${m.shn_m2} m² SHN</span></div>`).join('') : '';
  const flLabelShort = { surface: 'surface de plancher', densite: 'densité (log/ha)', construction: 'max par construction' };
  const plRow = (lg && lg.plafonds && lg.plafonds.facteur_limitant) ? `<div class="text-row"><span class="k">Limite appliquée</span><span class="v">${flLabelShort[lg.plafonds.facteur_limitant] || lg.plafonds.facteur_limitant}</span></div>` : '';
  const schLog = lg ? `<div class="schema-content"><div class="text-row"><span class="k">Logements</span><span class="v"><strong>${lg.nb_logements}</strong></span></div>${mixRows}<div class="text-row"><span class="k">Moyenne par logement</span><span class="v">${lg.surface_moyenne_shn_m2} m² habitables</span></div>${plRow}${pk ? `<div class="text-row"><span class="k">Parkings voiture</span><span class="v">${pk.auto_min} à ${pk.auto_max}</span></div><div class="text-row"><span class="k">Parkings vélo</span><span class="v">${pk.velo}</span></div>` : ''}</div>` : '';

  const wn = e5.warnings || [];
  const lvlColor = { info: '#2962ff', warning: '#c9a961', critique: '#c00' };
  const schWarn = `<div class="schema-content">${wn.length ? wn.map(w => `<div class="warn-row"><span class="warn-lvl" style="background:${lvlColor[w.level] || '#888'}">${w.level}</span><span class="warn-code">${w.code}${w.edge ? ' (' + w.edge + ')' : ''}</span><span class="warn-msg">${w.message_fr}</span></div>`).join('') : '<div class="schema-caption">Aucun point de vigilance.</div>'}</div>`;

  const ruleMatch = e4.matches.length > 0 ? e4.matches[0].fields : {};
  const cos = ruleMatch.COS_max || '?';
  const css = ruleMatch.CSS_max || '?';
  const dlMax = ruleMatch.DL_max_log_ha;
  const nbLogMaxRule = ruleMatch.Nb_logements_max;
  const hFaite = ruleMatch.Hauteur_faite_max_m || '?';
  const hCorniche = ruleMatch.Hauteur_corniche_max_m || '?';

  // ===== Textes pedagogiques =====
  const fmt = (x) => (x == null ? '?' : Math.round(x).toLocaleString('fr-FR'));
  const terrain = (e5.parcelle && e5.parcelle.surface_cadastrale_m2) || polygonArea(parcelLurefPts);
  const empriseM2 = e5.emprise.surface_m2;
  const ratioPct = (e5.emprise.ratio_vs_cadastrale * 100).toFixed(0);
  const nomZone = ruleMatch.Nom_zone || e3.code_zone;
  const cusInfo = (scb && scb.cus_applique) ? scb.cus_applique : null;
  const tc = e5.type_construction;

  const txtParcelle = `À partir de l'adresse <strong>${e1.adresse}</strong>, on identifie le terrain au cadastre : parcelle <strong>${e1.parcel_label}</strong>, d'une surface de <strong>${fmt(terrain)} m²</strong>.`;

  let reglesLi = `<li>Recul avant (distance entre la rue et la maison) : <strong>${ra} m</strong></li>`
    + `<li>Reculs latéraux (de chaque côté) : <strong>${rl} m</strong></li>`
    + `<li>Recul arrière (vers le fond) : <strong>${rr} m</strong></li>`;
  if (scb) reglesLi += `<li>Hauteur autorisée : <strong>${scb.niveaux_pleins} niveaux${scb.combles ? ' + combles aménageables' : ''}</strong></li>`;
  if (cos !== '?') reglesLi += `<li>COS (part du terrain qu'on peut couvrir au sol) : <strong>${cos}</strong></li>`;
  if (css !== '?') reglesLi += `<li>CUS (total de plancher autorisé par m² de terrain) : <strong>${css}</strong></li>`;
  const txtRegles = `Votre terrain est classé en zone <strong>${e3.code_zone}</strong> (${nomZone}) au PAG, le <em>Plan d'Aménagement Général</em> : le règlement communal qui décide ce qu'on a le droit de construire. Voici ce qu'il impose ici :<ul>${reglesLi}</ul>`;

  const txtRueFond = `Pour orienter le bâtiment, on repère le côté qui donne sur la rue (la <em>voirie</em>) et le côté du fond. La façade sur rue est l'arête <strong>${e5.voirie.edge_label}</strong>${voirieMethod === 'cadastral_adjacency_v0.2' ? ', détectée en regardant quelles limites de la parcelle touchent le domaine public' : ', détectée par proximité du point d\'adresse'}. Le fond retenu est <strong>${e5.fond.edge_label}</strong>.`;

  let txtMito;
  if (mito && mito.edges && mito.edges.length) {
    txtMito = `On regarde les bâtiments voisins. Quand une maison voisine est déjà collée à la limite de votre terrain (un <em>mur mitoyen</em>), vous avez le droit de bâtir contre cette même limite, sans recul. On détecte ces murs grâce à la couche des bâtiments du cadastre.`;
    if (partyWalls.length) {
      txtMito += ` Ici, <strong>${partyWalls.length} côté${partyWalls.length > 1 ? 's sont concernés' : ' est concerné'}</strong> : le recul latéral y passe à <strong>0</strong>, ce qui agrandit la surface constructible.`;
    } else {
      txtMito += ` Ici, <strong>aucun mur mitoyen bâti</strong> n'a été détecté : les reculs latéraux normaux s'appliquent des deux côtés.`;
    }
    if (tc && tc.type) txtMito += ` Type de construction estimé : <strong>${tc.type.replace(/_/g, ' ')}</strong>.`;
  } else {
    txtMito = `La détection des murs mitoyens bâtis n'est pas disponible pour cette parcelle ; les reculs latéraux standards s'appliquent.`;
  }

  const txtPlacement = `On part des <strong>${fmt(terrain)} m²</strong> du terrain et on retire les bandes où il est interdit de bâtir : ${ra} m le long de la rue, ${rl} m sur chaque côté (sauf murs mitoyens), et ${rr} m au fond. La surface réellement constructible au sol — l'<em>emprise au sol</em> — est de <strong>${fmt(empriseM2)} m²</strong>, soit <strong>${ratioPct} %</strong> du terrain.`;

  let txtScb = '';
  if (scb) {
    let nivLi = `<li>Rez-de-chaussée : ${fmt(empriseM2)} m²</li>`;
    for (let k = 1; k < scb.niveaux_pleins; k++) nivLi += `<li>${k}${k === 1 ? 'ᵉʳ' : 'ᵉ'} étage : ${fmt(empriseM2)} m²</li>`;
    if (scb.combles) nivLi += `<li>Combles (comptés à 60 % car sous pente) : ${fmt(scb.scb_combles_m2)} m²</li>`;
    const brute = scb.scb_niveaux_m2 + scb.scb_combles_m2;
    txtScb = `On empile les niveaux autorisés. La somme des planchers s'appelle la <strong>SCB</strong> (<em>Surface Construite Brute</em>) :<ul>${nivLi}</ul>Total = <strong>${fmt(brute)} m²</strong>.`;
    if (cusInfo && cusInfo.limitant) {
      txtScb += ` Mais la zone plafonne la densité à ${fmt(terrain)} m² × ${cusInfo.cus_max} = <strong>${fmt(cusInfo.scb_max_cus_m2)} m²</strong> : c'est inférieur, donc on retient ce plafond.`;
    } else if (cusInfo) {
      txtScb += ` Le plafond de densité (${fmt(cusInfo.scb_max_cus_m2)} m²) n'est pas atteint, on garde <strong>${fmt(scb.scb_totale_m2)} m²</strong>.`;
    }
  }

  let txtLog = '';
  if (lg) {
    if (lg.nb_logements > 0) {
      const pl = lg.plafonds || {};
      const cap = pl.capacite_surface;
      txtLog = `Le règlement ne fixe pas directement un nombre de logements : il pose des <strong>limites</strong>, et on prend la plus stricte. On compare trois choses :<ul>`;
      if (cap != null) txtLog += `<li><strong>La surface disponible</strong> : avec un logement moyen d'environ 75 m² brut, les ${fmt(lg.scb_logement_m2)} m² de plancher logement peuvent contenir ~<strong>${Math.floor(cap)}</strong> logement${Math.floor(cap) > 1 ? 's' : ''}.</li>`;
      if (pl.plafond_par_construction != null) txtLog += `<li><strong>Le maximum par construction</strong> fixé par le PAP de la zone ${e3.code_zone} : <strong>${pl.plafond_par_construction} logement${pl.plafond_par_construction > 1 ? 's' : ''}</strong>.</li>`;
      if (pl.plafond_densite_log != null && dlMax) txtLog += `<li><strong>La densité maximale</strong> : ${dlMax} logements/hectare, soit <strong>${pl.plafond_densite_log.toFixed(1)}</strong> sur ce terrain de ${fmt(terrain)} m².</li>`;
      txtLog += `</ul>`;
      const facteurLabel = { surface: 'la surface de plancher disponible', densite: 'la densité réglementaire', construction: 'le plafond du règlement par construction' };
      const fl = facteurLabel[pl.facteur_limitant] || 'la limite la plus stricte';
      txtLog += `La limite qui s'applique ici est <strong>${fl}</strong>, d'où <strong>${lg.nb_logements} logement${lg.nb_logements > 1 ? 's' : ''}</strong>`;
      if (lg.scb_commerce_m2 > 0) txtLog += ` + un commerce en rez-de-chaussée (zone mixte)`;
      txtLog += `.`;
    } else {
      txtLog = `Cette zone n'autorise pas le logement (ou la surface est insuffisante) : <strong>aucun logement</strong>.`;
    }
    if (pk) txtLog += ` Côté stationnement, le règlement impose <strong>${pk.auto_min} à ${pk.auto_max} places voiture</strong> et <strong>${pk.velo} emplacement${pk.velo > 1 ? 's' : ''} vélo</strong>.`;
  }

  let synthese = `Sur ce terrain de <strong>${fmt(terrain)} m²</strong>, on peut bâtir une emprise au sol de <strong>${fmt(empriseM2)} m²</strong>`;
  if (scb) synthese += `, soit environ <strong>${fmt(scb.scb_totale_m2)} m²</strong> de plancher`;
  if (lg) synthese += `, ce qui représente <strong>${lg.nb_logements} logement${lg.nb_logements > 1 ? 's' : ''}</strong>`;
  if (lg && lg.scb_commerce_m2 > 0) synthese += ` + un commerce`;
  if (pk) synthese += `, avec <strong>${pk.auto_min}-${pk.auto_max} places de parking</strong>`;
  synthese += `.`;

  // ===== Sections : chaque explication suivie de son schema =====
  function section(num, title, text, schema) {
    return `<section class="section"><div class="section-head"><span class="section-num">${num}</span><span class="section-title">${title}</span></div>`
      + (text ? `<div class="section-text">${text}</div>` : '')
      + (schema ? `<div class="schema">${schema}</div>` : '')
      + `</section>`;
  }

  let n = 0;
  let sectionsHtml = '';
  sectionsHtml += section(++n, 'On retrouve votre parcelle', txtParcelle, schParcelle);
  sectionsHtml += section(++n, "Les règles d'urbanisme de votre zone", txtRegles, '');
  sectionsHtml += section(++n, 'On identifie la rue et le fond', txtRueFond, schVoirie + schFond);
  sectionsHtml += section(++n, 'Mitoyenneté : les murs déjà accolés', txtMito, schMito);
  sectionsHtml += section(++n, 'Où peut-on poser le bâtiment ?', txtPlacement, schLateral + schAvAr + schEmprise);
  if (scb) sectionsHtml += section(++n, 'Combien de surface de plancher ?', txtScb, schScb);
  if (lg) sectionsHtml += section(++n, 'Logements et stationnement', txtLog, schLog);
  if (wn.length) sectionsHtml += section(++n, 'Points de vigilance', '', schWarn);
  sectionsHtml += section(++n, 'En résumé', synthese, '');

  const heroHtml = `<div class="hero"><h1>${e1.adresse}</h1><div class="addr">Parcelle ${e1.parcel_label} · zone ${e3.code_zone}${nomZone ? ' · ' + nomZone : ''}</div><div class="hero-grid"><div class="kpi"><div class="label">Terrain</div><div class="value">${fmt(terrain)} m²</div></div><div class="kpi"><div class="label">Règles (COS / CUS)</div><div class="value">${cos} / ${css}</div><div class="sub">h. ${hCorniche}m / ${hFaite}m</div></div><div class="kpi kpi-result"><div class="label">Emprise constructible</div><div class="value-big">${e5.emprise.surface_m2} m²</div><div class="sub">${ratioPct}% du terrain</div></div>${(lg ? `<div class="kpi"><div class="label">Logements estimés</div><div class="value">${lg.nb_logements}</div></div>` : '')}</div></div>`;

  const topbar = `<div class="topbar"><span class="brand">Palladio</span><a class="btn-home" href="${FORM_URL}">← Nouvelle recherche</a></div>`;

  return `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Palladio · ${e1.adresse}</title><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet"><style>${styles()}</style></head><body>${topbar}<div class="wrap">${heroHtml}${sectionsHtml}<a class="btn-home btn-home-bottom" href="${FORM_URL}">← Nouvelle recherche</a><footer class="footer"><span>Palladio engine ${e5.meta_engine.version}</span><span>${d.meta.timestamp.slice(0, 16).replace('T', ' ')}</span></footer></div></body></html>`;
}

function styles() {
  return `*{box-sizing:border-box;margin:0;padding:0}`
    + `:root{--ink:#111;--muted:#777;--line:#e6e6e6;--soft:#f7f7f5;--amber:#e08a2e;--blue:#2962ff;--green:#2a7;--red:#c00}`
    + `body{font-family:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;font-size:15px;line-height:1.55;color:var(--ink);background:#fff;-webkit-font-smoothing:antialiased}`
    + `.mono{font-family:ui-monospace,'SF Mono',Menlo,Consolas,monospace;font-size:12px}`
    + `.topbar{position:sticky;top:0;z-index:10;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 20px;background:rgba(255,255,255,.92);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}`
    + `.topbar .brand{font-weight:700;font-size:17px;letter-spacing:-.01em}`
    + `.btn-home{display:inline-flex;align-items:center;gap:6px;font-size:13px;font-weight:500;color:#fff;background:var(--ink);padding:9px 15px;border-radius:9px;text-decoration:none}`
    + `.btn-home:active{opacity:.8}`
    + `.btn-home-bottom{margin:8px 0 0}`
    + `.wrap{max-width:880px;margin:0 auto;padding:24px 20px 72px}`
    + `.hero{padding:4px 0 22px;border-bottom:1px solid var(--line);margin-bottom:26px}`
    + `.hero h1{font-size:22px;font-weight:600;letter-spacing:-.01em;margin-bottom:4px}`
    + `.hero .addr{color:var(--muted);font-size:14px}`
    + `.hero-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:14px;margin-top:20px}`
    + `.kpi{background:var(--soft);border-radius:11px;padding:14px 16px}`
    + `.kpi .label{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:6px}`
    + `.kpi .value{font-size:16px;font-weight:600}`
    + `.kpi .value-big{font-size:26px;font-weight:700;letter-spacing:-.02em}`
    + `.kpi .sub{font-size:12px;color:var(--muted);margin-top:3px}`
    + `.kpi-result{background:#111;color:#fff}.kpi-result .label,.kpi-result .sub{color:#bbb}`
    + `.section{margin-bottom:20px;padding:20px;border:1px solid var(--line);border-radius:14px}`
    + `.section-head{display:flex;gap:12px;align-items:center;margin-bottom:10px}`
    + `.section-num{flex:0 0 26px;width:26px;height:26px;border-radius:50%;background:var(--ink);color:#fff;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:600}`
    + `.section-title{font-size:16px;font-weight:600;letter-spacing:-.01em}`
    + `.section-text{font-size:14px;color:#333;line-height:1.65}`
    + `.section-text ul{margin:10px 0 2px 18px}.section-text li{margin:4px 0}`
    + `.schema{margin-top:16px}`
    + `.schema-svg{width:100%;height:auto;max-height:440px;display:block;background:#fff;border:1px solid #f0f0f0;border-radius:8px}`
    + `.schema-caption{font-size:13px;color:#555;margin-top:10px;line-height:1.55}`
    + `.schema-content{padding:4px 0}`
    + `.text-row{display:grid;grid-template-columns:minmax(120px,210px) 1fr;gap:12px;padding:9px 0;border-bottom:1px solid #f0f0f0}`
    + `.text-row:last-child{border-bottom:0}`
    + `.k{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}.v{font-size:14px}`
    + `.cand-list{margin-top:12px;padding-top:12px;border-top:1px solid #f0f0f0;display:flex;flex-direction:column;gap:4px}`
    + `.cand-row{display:grid;grid-template-columns:60px 90px 90px 1fr;gap:10px;padding:4px 0;font-size:13px}`
    + `.cand-row.cand-chosen{font-weight:600}.cand-label{font-family:ui-monospace,monospace}.cand-score{color:#888;font-size:12px}.cand-pick{color:var(--green);font-size:12px;text-transform:uppercase;letter-spacing:.05em}`
    + `.warn-row{display:flex;gap:10px;align-items:baseline;padding:8px 0;border-bottom:1px solid #f0f0f0;flex-wrap:wrap}`
    + `.warn-lvl{font-family:ui-monospace,monospace;font-size:11px;text-transform:uppercase;color:#fff;padding:2px 6px;border-radius:3px}`
    + `.warn-code{font-family:ui-monospace,monospace;font-size:12px;color:#888}.warn-msg{font-size:13px;color:#111;flex:1;min-width:200px}`
    + `.parcel-fill{fill:#fafafa;stroke:#111;stroke-width:0.4}.parcel-fill-light{fill:#fafafa;stroke:#ccc;stroke-width:0.3}.parcel-fill-final{fill:#f3f3f3;stroke:#888;stroke-width:0.3}`
    + `.emprise-fill{fill:#111;fill-opacity:0.85;stroke:#000;stroke-width:0.3}`
    + `.dot-vertex{fill:#111}.dot-geocode{fill:#2962ff}`
    + `.lbl-vertex{font-family:'Inter',sans-serif;font-size:1.8px;font-weight:600;fill:#111;text-anchor:middle;dominant-baseline:middle}`
    + `.edge-voirie-other{stroke:#ccc;stroke-width:0.3;fill:none}.edge-voirie-winner{stroke:#c00;stroke-width:0.8;fill:none}`
    + `.lbl-edge{font-family:'Inter',sans-serif;font-size:1.4px;fill:#888;text-anchor:middle;dominant-baseline:middle}`
    + `.lbl-edge-winner{font-family:'Inter',sans-serif;font-size:1.6px;fill:#c00;font-weight:600;text-anchor:middle;dominant-baseline:middle}`
    + `.line-perp{stroke:#2962ff;stroke-width:0.3;stroke-dasharray:0.8,0.8;fill:none}`
    + `.line-recul-lateral{stroke:#555;stroke-width:0.4;stroke-dasharray:1.2,1.2;fill:none}`
    + `.edge-mitoyen{stroke:#e08a2e;stroke-width:1.6;fill:none}`
    + `.lbl-mito{font-family:'Inter',sans-serif;font-size:1.5px;fill:#e08a2e;font-weight:600;text-anchor:middle;dominant-baseline:middle}`
    + `.lbl-recul{font-family:'Inter',sans-serif;font-size:1.4px;fill:#555;text-anchor:middle;dominant-baseline:middle}`
    + `.lbl-dim{font-family:'Inter',sans-serif;font-size:1.6px;font-weight:600;fill:#fff;paint-order:stroke;stroke:#111;stroke-width:0.3px;text-anchor:middle;dominant-baseline:middle}`
    + `.edge-voirie-thick{stroke:#c00;stroke-width:0.7;fill:none}.edge-fond-thick{stroke:#2a7;stroke-width:0.7;fill:none}`
    + `.line-recul-avant{stroke:#c00;stroke-width:0.4;stroke-dasharray:1.2,1.2;fill:none}.line-recul-arriere{stroke:#2a7;stroke-width:0.4;stroke-dasharray:1.2,1.2;fill:none}.line-recul-prof{stroke:#84c;stroke-width:0.4;stroke-dasharray:0.6,0.6;fill:none}`
    + `.lbl-recul-avant{font-family:'Inter',sans-serif;font-size:1.4px;fill:#c00;font-weight:600;text-anchor:middle;dominant-baseline:middle}`
    + `.lbl-recul-arriere{font-family:'Inter',sans-serif;font-size:1.4px;fill:#2a7;font-weight:600;text-anchor:middle;dominant-baseline:middle}`
    + `.lbl-recul-prof{font-family:'Inter',sans-serif;font-size:1.3px;fill:#84c;font-weight:600;text-anchor:middle;dominant-baseline:middle}`
    + `.footer{margin-top:48px;padding-top:20px;border-top:1px solid var(--line);display:flex;justify-content:space-between;color:#999;font-size:12px;font-family:ui-monospace,monospace}`
    + `@media(max-width:600px){.wrap{padding:18px 14px 60px}.section{padding:16px 14px}.text-row{grid-template-columns:1fr;gap:2px}.hero h1{font-size:20px}.kpi .value-big{font-size:23px}}`;
}

function renderErrorPage(d) {
  return `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Palladio · erreur</title><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet"><style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:'Inter',system-ui,sans-serif;max-width:760px;margin:0 auto;padding:32px 20px 60px;color:#111}.topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:28px}.brand{font-weight:700;font-size:17px}.btn-home{font-size:13px;font-weight:500;color:#fff;background:#111;padding:9px 15px;border-radius:9px;text-decoration:none}h1{font-size:20px;margin-bottom:12px}.err{background:#fff5f5;border:1px solid #fcc;border-radius:10px;padding:20px;line-height:1.5}pre{background:#f7f7f5;padding:16px;border-radius:10px;font-size:12px;overflow:auto;margin-top:24px}</style></head><body><div class="topbar"><span class="brand">Palladio</span><a class="btn-home" href="${FORM_URL}">← Nouvelle recherche</a></div><h1>Le calcul n'a pas abouti</h1><div class="err"><strong>${d.etape_5_emprise.error || 'Erreur inconnue'}</strong></div><pre>${JSON.stringify(d, null, 2)}</pre></body></html>`;
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
