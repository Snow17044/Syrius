// GET /api/galerie — les photos de la galerie, pour la page d'accueil.
import { q } from '../lib/db.js';
import { handler, send, allow } from '../lib/http.js';

export default handler(async (req, res) => {
  allow(req, 'GET');
  const photos = await q(`SELECT id, url, caption FROM kb_photos ORDER BY position DESC, id DESC LIMIT 60`);
  send(res, 200, { photos });
});
