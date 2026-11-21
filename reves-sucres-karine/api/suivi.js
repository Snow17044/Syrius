// GET /api/suivi?code=KB-XXXXXX&tel=0600000000 — un client suit sa commande.
import { q } from '../lib/db.js';
import { handler, send, allow, query, HttpError } from '../lib/http.js';
import { phoneDigits } from '../lib/orders.js';

export default handler(async (req, res) => {
  allow(req, 'GET');
  const params = query(req);
  const code = String(params.get('code') || '').trim().toUpperCase().replace(/^KB-?/, 'KB-');
  const tel = phoneDigits(params.get('tel')).slice(-9);
  if (!/^KB-[A-Z0-9]{6}$/.test(code) || tel.length < 9) {
    throw new HttpError(400, 'Merci d\'indiquer le numéro de commande et le téléphone utilisé.');
  }
  const rows = await q(
    `SELECT code, customer_name, phone, to_char(pickup_date, 'YYYY-MM-DD') AS pickup_date, pickup_slot, mode,
            items, total_cents, status
       FROM kb_orders WHERE code = $1`,
    [code]
  );
  const o = rows[0];
  if (!o || phoneDigits(o.phone).slice(-9) !== tel) {
    throw new HttpError(404, 'Aucune commande trouvée avec ces informations.');
  }
  send(res, 200, {
    code: o.code,
    first_name: o.customer_name.split(/\s+/)[0],
    pickup_date: o.pickup_date,
    pickup_slot: o.pickup_slot,
    mode: o.mode,
    items: o.items,
    total_cents: o.total_cents,
    status: o.status,
  });
});
