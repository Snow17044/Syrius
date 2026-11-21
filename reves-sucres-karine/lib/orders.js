// Création et lecture des commandes.
import crypto from 'node:crypto';
import { q, getShop } from './db.js';
import { HttpError, text, int, isoDate, todayParis, addDays } from './http.js';

export const STATUSES = ['nouvelle', 'confirmee', 'en_preparation', 'prete', 'terminee', 'annulee'];

export const ORDER_COLS = `id, code, customer_name, phone, email,
  to_char(pickup_date, 'YYYY-MM-DD') AS pickup_date, pickup_slot, mode, address, message,
  items, total_cents, status, admin_note, source, created_at, updated_at`;

export const PRODUCT_COLS = `id, name, description, category, price_cents, unit, available, position, image_url`;

const CODE_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
function newCode() {
  const bytes = crypto.randomBytes(6);
  let s = '';
  for (const b of bytes) s += CODE_CHARS[b % CODE_CHARS.length];
  return 'KB-' + s;
}

export function phoneDigits(p) {
  return String(p || '').replace(/\D/g, '');
}

export async function createOrder(body, { admin = false } = {}) {
  const shop = await getShop();
  if (!admin && !shop.orders_open) throw new HttpError(403, shop.closed_message || 'Les commandes sont fermées.');
  if (!admin && body.website) throw new HttpError(400, 'Demande refusée.'); // champ piège anti-robots

  const customer_name = text(body.name, { label: 'Le nom', max: 100, required: true });
  const phone = text(body.phone, { label: 'Le téléphone', max: 30, required: !admin });
  if (phone && phoneDigits(phone).length < 9) throw new HttpError(400, 'Le numéro de téléphone semble incomplet.');
  const email = text(body.email, { label: 'L\'e-mail', max: 150 });
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new HttpError(400, 'L\'adresse e-mail semble incorrecte.');

  const pickup_date = isoDate(body.date, 'La date');
  if (!admin) {
    const min = addDays(todayParis(), Number(shop.lead_days) || 0);
    if (pickup_date < min) throw new HttpError(400, `La date doit être au plus tôt le ${frDate(min)}.`);
    if (pickup_date > addDays(todayParis(), 365)) throw new HttpError(400, 'La date est trop lointaine.');
  }

  let pickup_slot = text(body.slot, { label: 'Le créneau', max: 60 });
  if (!admin && shop.slots?.length) {
    if (!shop.slots.includes(pickup_slot)) throw new HttpError(400, 'Merci de choisir un créneau.');
  }

  const mode = body.mode === 'livraison' ? 'livraison' : 'retrait';
  if (mode === 'livraison' && !admin && !shop.delivery) throw new HttpError(400, 'La livraison n\'est pas proposée pour le moment.');
  const address = text(body.address, { label: 'L\'adresse', max: 300, required: mode === 'livraison' });
  const message = text(body.message, { label: 'Le message', max: 1500 });

  const raw = Array.isArray(body.items) ? body.items : [];
  if (!raw.length) throw new HttpError(400, 'Votre panier est vide.');
  if (raw.length > 40) throw new HttpError(400, 'Trop d\'articles dans la commande.');

  const qtyById = new Map();
  const customLines = [];
  for (const it of raw) {
    const qty = int(it?.qty, { label: 'La quantité', min: 1, max: 50 });
    if (admin && it?.custom) {
      customLines.push({
        product_id: null,
        name: text(it.name, { label: 'Le nom de l\'article', max: 120, required: true }),
        unit: text(it.unit, { label: 'Le format', max: 60 }),
        price_cents: int(it.price_cents, { label: 'Le prix', min: 0, max: 10_000_00 }),
        qty,
      });
    } else {
      const id = int(it?.id, { label: 'L\'article', min: 1 });
      qtyById.set(id, (qtyById.get(id) || 0) + qty);
    }
  }

  const items = [];
  if (qtyById.size) {
    const ids = [...qtyById.keys()];
    const products = await q(`SELECT ${PRODUCT_COLS} FROM kb_products WHERE id = ANY($1::int[])`, [ids]);
    const byId = new Map(products.map((p) => [p.id, p]));
    for (const [id, qty] of qtyById) {
      const p = byId.get(id);
      if (!p || (!admin && !p.available)) throw new HttpError(400, 'Un article de votre panier n\'est plus disponible. Merci de rafraîchir la page.');
      if (qty > 50) throw new HttpError(400, 'Quantité trop importante pour un article.');
      items.push({ product_id: p.id, name: p.name, unit: p.unit, price_cents: p.price_cents, qty });
    }
  }
  items.push(...customLines);
  const total_cents = items.reduce((s, it) => s + it.price_cents * it.qty, 0);

  for (let attempt = 0; attempt < 5; attempt++) {
    const code = newCode();
    const rows = await q(
      `INSERT INTO kb_orders (code, customer_name, phone, email, pickup_date, pickup_slot, mode, address, message, items, total_cents, status, source)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11,$12,$13)
       ON CONFLICT (code) DO NOTHING
       RETURNING ${ORDER_COLS}`,
      [code, customer_name, phone, email, pickup_date, pickup_slot, mode, address, message,
        JSON.stringify(items), total_cents, admin ? (body.status && STATUSES.includes(body.status) ? body.status : 'confirmee') : 'nouvelle',
        admin ? 'admin' : 'site']
    );
    if (rows.length) return rows[0];
  }
  throw new HttpError(500, 'Impossible d\'enregistrer la commande, réessayez.');
}

export function frDate(iso) {
  return new Date(iso + 'T12:00:00Z').toLocaleDateString('fr-FR', {
    weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC',
  });
}
