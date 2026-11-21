// /api/admin?action=... — tout l'espace de gestion de Karine.
import { q, getShop, setSetting, DEFAULT_SHOP } from '../lib/db.js';
import { handler, send, allow, readJson, query, HttpError, text, int, isoDate } from '../lib/http.js';
import { isAdmin, requireAdmin, login, sessionCookie, clearCookie, changePassword } from '../lib/auth.js';
import { createOrder, STATUSES, ORDER_COLS, PRODUCT_COLS } from '../lib/orders.js';

function productFields(b) {
  return {
    name: text(b.name, { label: 'Le nom', max: 120, required: true }),
    description: text(b.description, { label: 'La description', max: 500 }),
    category: text(b.category, { label: 'La catégorie', max: 60 }) || 'Autres',
    price_cents: int(b.price_cents, { label: 'Le prix', min: 0, max: 10_000_00 }),
    unit: text(b.unit, { label: 'Le format', max: 60 }),
    available: b.available !== false,
    position: int(b.position ?? 0, { label: 'L\'ordre', min: 0, max: 100000 }),
  };
}

const actions = {
  // ---- Session ----
  async me(req, res) {
    allow(req, 'GET');
    send(res, 200, { admin: await isAdmin(req) });
  },
  async login(req, res) {
    allow(req, 'POST');
    const { password } = await readJson(req);
    await login(req, password);
    send(res, 200, { ok: true }, { 'Set-Cookie': await sessionCookie() });
  },
  async logout(req, res) {
    allow(req, 'POST');
    send(res, 200, { ok: true }, { 'Set-Cookie': clearCookie() });
  },
  async password(req, res) {
    allow(req, 'POST');
    await requireAdmin(req);
    const { current, next } = await readJson(req);
    await changePassword(current, next);
    send(res, 200, { ok: true }, { 'Set-Cookie': await sessionCookie() });
  },

  // ---- Commandes ----
  async orders(req, res) {
    await requireAdmin(req);
    if (req.method === 'GET') {
      const rows = await q(`SELECT ${ORDER_COLS} FROM kb_orders ORDER BY pickup_date DESC, id DESC LIMIT 1000`);
      return send(res, 200, { orders: rows });
    }
    if (req.method === 'POST') {
      const order = await createOrder(await readJson(req), { admin: true });
      return send(res, 201, { order });
    }
    if (req.method === 'PATCH') {
      const b = await readJson(req);
      const id = int(b.id, { label: 'La commande', min: 1 });
      const sets = [];
      const vals = [];
      const add = (col, v) => { vals.push(v); sets.push(`${col} = $${vals.length}`); };
      if (b.status !== undefined) {
        if (!STATUSES.includes(b.status)) throw new HttpError(400, 'Statut inconnu.');
        add('status', b.status);
      }
      if (b.admin_note !== undefined) add('admin_note', text(b.admin_note, { label: 'La note', max: 2000 }));
      if (b.pickup_date !== undefined) add('pickup_date', isoDate(b.pickup_date, 'La date'));
      if (b.pickup_slot !== undefined) add('pickup_slot', text(b.pickup_slot, { label: 'Le créneau', max: 60 }));
      if (!sets.length) throw new HttpError(400, 'Rien à modifier.');
      vals.push(id);
      const rows = await q(
        `UPDATE kb_orders SET ${sets.join(', ')}, updated_at = now() WHERE id = $${vals.length} RETURNING ${ORDER_COLS}`,
        vals
      );
      if (!rows.length) throw new HttpError(404, 'Commande introuvable.');
      return send(res, 200, { order: rows[0] });
    }
    if (req.method === 'DELETE') {
      const id = int(query(req).get('id'), { label: 'La commande', min: 1 });
      await q(`DELETE FROM kb_orders WHERE id = $1`, [id]);
      return send(res, 200, { ok: true });
    }
    throw new HttpError(405, 'Méthode non autorisée.');
  },

  // ---- Produits ----
  async products(req, res) {
    await requireAdmin(req);
    if (req.method === 'GET') {
      return send(res, 200, { products: await q(`SELECT ${PRODUCT_COLS} FROM kb_products ORDER BY position, id`) });
    }
    if (req.method === 'POST') {
      const f = productFields(await readJson(req));
      const rows = await q(
        `INSERT INTO kb_products (name, description, category, price_cents, unit, available, position)
         VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING ${PRODUCT_COLS}`,
        [f.name, f.description, f.category, f.price_cents, f.unit, f.available, f.position]
      );
      return send(res, 201, { product: rows[0] });
    }
    if (req.method === 'PATCH') {
      const b = await readJson(req);
      const id = int(b.id, { label: 'Le produit', min: 1 });
      const f = productFields(b);
      const rows = await q(
        `UPDATE kb_products SET name=$1, description=$2, category=$3, price_cents=$4, unit=$5, available=$6, position=$7
         WHERE id=$8 RETURNING ${PRODUCT_COLS}`,
        [f.name, f.description, f.category, f.price_cents, f.unit, f.available, f.position, id]
      );
      if (!rows.length) throw new HttpError(404, 'Produit introuvable.');
      return send(res, 200, { product: rows[0] });
    }
    if (req.method === 'DELETE') {
      const id = int(query(req).get('id'), { label: 'Le produit', min: 1 });
      await q(`DELETE FROM kb_products WHERE id = $1`, [id]);
      return send(res, 200, { ok: true });
    }
    throw new HttpError(405, 'Méthode non autorisée.');
  },

  // ---- Réglages ----
  async settings(req, res) {
    await requireAdmin(req);
    if (req.method === 'GET') return send(res, 200, { shop: await getShop() });
    allow(req, 'PUT');
    const b = await readJson(req);
    const slots = (Array.isArray(b.slots) ? b.slots : [])
      .map((s) => text(s, { label: 'Un créneau', max: 60 }))
      .filter(Boolean)
      .slice(0, 12);
    const shop = {
      ...DEFAULT_SHOP,
      orders_open: !!b.orders_open,
      delivery: !!b.delivery,
      lead_days: int(b.lead_days, { label: 'Le délai', min: 0, max: 60 }),
      slots,
      notice: text(b.notice, { label: 'Le message d\'information', max: 500 }),
      closed_message: text(b.closed_message, { label: 'Le message de fermeture', max: 500 }),
    };
    await setSetting('shop', shop);
    send(res, 200, { shop });
  },
};

export default handler(async (req, res) => {
  const action = query(req).get('action');
  const fn = Object.hasOwn(actions, action) ? actions[action] : null;
  if (!fn) throw new HttpError(404, 'Action inconnue.');
  await fn(req, res);
});
