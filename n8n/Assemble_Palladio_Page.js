// node "Assemble Palladio Page" du workflow Palladio (n8n XFOhmez4MtTnmtnL).
// Depuis 2026-06-20 : le rendu HTML est fait CÔTÉ SERVEUR par palladio_render.py
// (route /palladio/calcul/full/html). Ce node n'est plus qu'un passe-plat qui
// récupère le HTML renvoyé par "Calcul Palladio" et l'expose en `html` pour le
// node "Respond JSON". (L'ancien node de 39 Ko a été retiré — historique git.)
const inp = $json;
const html = inp.data || inp.body || (typeof inp === 'string' ? inp : '') || '<h1>Erreur de rendu</h1>';
return [{ json: { html } }];
