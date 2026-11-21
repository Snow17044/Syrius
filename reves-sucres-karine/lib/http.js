// Petits outils HTTP communs aux fonctions de l'API.

export class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export function send(res, status, data, headers = {}) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  for (const [k, v] of Object.entries(headers)) res.setHeader(k, v);
  res.end(JSON.stringify(data));
}

export async function readJson(req) {
  let body;
  try { body = req.body; } catch { throw new HttpError(400, 'Données invalides.'); }
  if (body && typeof body === 'object' && !Buffer.isBuffer(body)) return body;
  if (typeof body === 'string' || Buffer.isBuffer(body)) {
    const s = body.toString();
    return s ? JSON.parse(s) : {};
  }
  const chunks = [];
  let size = 0;
  for await (const c of req) {
    size += c.length;
    if (size > 100_000) throw new HttpError(413, 'Requête trop volumineuse.');
    chunks.push(c);
  }
  const s = Buffer.concat(chunks).toString('utf8');
  return s ? JSON.parse(s) : {};
}

export function query(req) {
  return new URL(req.url, 'http://localhost').searchParams;
}

export function clientIp(req) {
  const fwd = req.headers['x-forwarded-for'];
  return (fwd ? String(fwd).split(',')[0].trim() : '') || req.socket?.remoteAddress || 'inconnu';
}

export function handler(fn) {
  return async (req, res) => {
    try {
      await fn(req, res);
    } catch (e) {
      if (e instanceof HttpError) return send(res, e.status, { error: e.message });
      if (e instanceof SyntaxError) return send(res, 400, { error: 'Données invalides.' });
      console.error(e);
      send(res, 500, { error: 'Erreur du serveur, merci de réessayer plus tard.' });
    }
  };
}

export function allow(req, ...methods) {
  if (!methods.includes(req.method)) throw new HttpError(405, 'Méthode non autorisée.');
}

// ---- Validation ----
export function text(v, { label, max = 200, required = false } = {}) {
  const s = (v == null ? '' : String(v)).trim();
  if (required && !s) throw new HttpError(400, `${label} est obligatoire.`);
  if (s.length > max) throw new HttpError(400, `${label} est trop long (${max} caractères max).`);
  return s;
}

export function int(v, { label, min = 0, max = 1e9 } = {}) {
  const n = Number(v);
  if (!Number.isInteger(n) || n < min || n > max) throw new HttpError(400, `${label} invalide.`);
  return n;
}

// ---- Dates (heure de Paris) ----
export function todayParis() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Paris' }).format(new Date());
}

export function addDays(iso, days) {
  const d = new Date(iso + 'T12:00:00Z');
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function isoDate(v, label) {
  const s = String(v || '');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s) || Number.isNaN(Date.parse(s + 'T12:00:00Z')) || addDays(s, 0) !== s) {
    throw new HttpError(400, `${label} invalide.`);
  }
  return s;
}
