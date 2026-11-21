// Accès à la base de données.
// En ligne : Postgres Neon (variable DATABASE_URL fournie par Vercel).
// En local (tests) : PGlite, un Postgres embarqué, si DATABASE_URL est absent.

let clientPromise;
let ready;

function getClient() {
  if (!clientPromise) clientPromise = makeClient().catch((e) => { clientPromise = null; throw e; });
  return clientPromise;
}

async function makeClient() {
  const url = process.env.DATABASE_URL || process.env.POSTGRES_URL;
  if (url) {
    const { neon } = await import('@neondatabase/serverless');
    const sql = neon(url);
    return { query: (text, params = []) => sql.query(text, params) };
  }
  const { PGlite } = await import('@electric-sql/pglite');
  const db = new PGlite(process.env.PGLITE_DIR || undefined);
  return { query: async (text, params = []) => (await db.query(text, params)).rows };
}

const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS kb_products (
     id SERIAL PRIMARY KEY,
     name TEXT NOT NULL,
     description TEXT NOT NULL DEFAULT '',
     category TEXT NOT NULL DEFAULT 'Autres',
     price_cents INTEGER NOT NULL DEFAULT 0,
     unit TEXT NOT NULL DEFAULT '',
     available BOOLEAN NOT NULL DEFAULT TRUE,
     position INTEGER NOT NULL DEFAULT 0,
     created_at TIMESTAMPTZ NOT NULL DEFAULT now())`,
  `CREATE TABLE IF NOT EXISTS kb_orders (
     id SERIAL PRIMARY KEY,
     code TEXT UNIQUE NOT NULL,
     customer_name TEXT NOT NULL,
     phone TEXT NOT NULL,
     email TEXT NOT NULL DEFAULT '',
     pickup_date DATE NOT NULL,
     pickup_slot TEXT NOT NULL DEFAULT '',
     mode TEXT NOT NULL DEFAULT 'retrait',
     address TEXT NOT NULL DEFAULT '',
     message TEXT NOT NULL DEFAULT '',
     items JSONB NOT NULL,
     total_cents INTEGER NOT NULL,
     status TEXT NOT NULL DEFAULT 'nouvelle',
     admin_note TEXT NOT NULL DEFAULT '',
     source TEXT NOT NULL DEFAULT 'site',
     created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
     updated_at TIMESTAMPTZ NOT NULL DEFAULT now())`,
  `CREATE INDEX IF NOT EXISTS kb_orders_pickup ON kb_orders (pickup_date)`,
  `CREATE TABLE IF NOT EXISTS kb_settings (key TEXT PRIMARY KEY, value JSONB NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS kb_login_attempts (ip TEXT NOT NULL, at TIMESTAMPTZ NOT NULL DEFAULT now())`,
  `ALTER TABLE kb_products ADD COLUMN IF NOT EXISTS image_url TEXT NOT NULL DEFAULT ''`,
  `CREATE TABLE IF NOT EXISTS kb_photos (
     id SERIAL PRIMARY KEY,
     url TEXT NOT NULL,
     caption TEXT NOT NULL DEFAULT '',
     position INTEGER NOT NULL DEFAULT 0,
     created_at TIMESTAMPTZ NOT NULL DEFAULT now())`,
];

// Carte de départ (prix indicatifs, modifiables depuis l'espace admin)
const SEED = [
  ['Gâteau d\'anniversaire', 'Génoise moelleuse, crème légère et décor personnalisé.', 'Gâteaux de fête', 3200, '6 parts'],
  ['Gâteau d\'anniversaire', 'Génoise moelleuse, crème légère et décor personnalisé.', 'Gâteaux de fête', 4800, '10 parts'],
  ['Layer cake', 'Plusieurs étages de biscuit et de crème, décor fleuri.', 'Gâteaux de fête', 5500, '12 parts'],
  ['Entremets framboise', 'Mousse framboise, insert fruité, biscuit amande.', 'Entremets', 2800, '6 parts'],
  ['Entremets trois chocolats', 'Mousses chocolat noir, lait et blanc sur croustillant praliné.', 'Entremets', 3000, '6 parts'],
  ['Boîte de macarons', 'Assortiment de parfums du moment.', 'Macarons', 1300, '6 pièces'],
  ['Boîte de macarons', 'Assortiment de parfums du moment.', 'Macarons', 2400, '12 pièces'],
  ['Cupcakes', 'Cupcakes décorés, parfums au choix.', 'Gourmandises', 1800, '6 pièces'],
  ['Cookies gourmands', 'Pépites de chocolat, cœur fondant.', 'Gourmandises', 1000, '6 pièces'],
  ['Tarte citron meringuée', 'Pâte sablée maison, crème citron, meringue flambée.', 'Tartes', 2400, '6 parts'],
  ['Tarte aux fraises', 'Crème pâtissière vanille et fraises de saison.', 'Tartes', 2600, '6 parts'],
  ['Coffret cadeau', 'Assortiment de douceurs joliment emballé.', 'Coffrets', 2500, '1 coffret'],
];

export const DEFAULT_SHOP = {
  orders_open: true,
  lead_days: 3,
  delivery: false,
  slots: ['Matin (9h – 12h)', 'Après-midi (14h – 18h)'],
  notice: 'Le règlement se fait au moment du retrait (espèces, chèque ou virement).',
  closed_message: 'Les commandes en ligne sont momentanément fermées. Merci de votre patience !',
};

async function migrate(c) {
  for (const stmt of SCHEMA) await c.query(stmt);
  const first = await c.query(
    `INSERT INTO kb_settings (key, value) VALUES ('seeded', 'true'::jsonb) ON CONFLICT (key) DO NOTHING RETURNING key`
  );
  if (first.length) {
    let pos = 0;
    for (const [name, description, category, price, unit] of SEED) {
      await c.query(
        `INSERT INTO kb_products (name, description, category, price_cents, unit, position) VALUES ($1,$2,$3,$4,$5,$6)`,
        [name, description, category, price, unit, (pos += 10)]
      );
    }
    await c.query(
      `INSERT INTO kb_settings (key, value) VALUES ('shop', $1::jsonb) ON CONFLICT (key) DO NOTHING`,
      [JSON.stringify(DEFAULT_SHOP)]
    );
  }
}

export async function q(text, params) {
  const c = await getClient();
  if (!ready) ready = migrate(c).catch((e) => { ready = null; throw e; });
  await ready;
  return c.query(text, params);
}

export async function getSetting(key, fallback) {
  const rows = await q(`SELECT value FROM kb_settings WHERE key = $1`, [key]);
  return rows.length ? rows[0].value : fallback;
}

export async function setSetting(key, value) {
  await q(
    `INSERT INTO kb_settings (key, value) VALUES ($1, $2::jsonb)
     ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value`,
    [key, JSON.stringify(value)]
  );
}

export async function getShop() {
  return { ...DEFAULT_SHOP, ...(await getSetting('shop', {})) };
}
