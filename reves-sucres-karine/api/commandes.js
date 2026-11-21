// POST /api/commandes — un client passe commande depuis le site.
import { handler, send, allow, readJson } from '../lib/http.js';
import { createOrder } from '../lib/orders.js';

export default handler(async (req, res) => {
  allow(req, 'POST');
  const order = await createOrder(await readJson(req));
  send(res, 201, {
    code: order.code,
    pickup_date: order.pickup_date,
    pickup_slot: order.pickup_slot,
    mode: order.mode,
    items: order.items,
    total_cents: order.total_cents,
  });
});
