// Connexion à l'espace admin : mot de passe + cookie de session signé.
import crypto from 'node:crypto';
import { q, getSetting, setSetting } from './db.js';
import { HttpError, clientIp } from './http.js';

const COOKIE = 'kb_admin';
const SESSION_DAYS = 14;

function sessionSecret() {
  const s = process.env.SESSION_SECRET;
  if (!s) throw new HttpError(500, 'Configuration manquante (SESSION_SECRET).');
  return s;
}

// La clé de signature dépend aussi du mot de passe : le changer déconnecte toutes les sessions.
async function signingKey() {
  const stored = await getSetting('admin_password', null);
  return sessionSecret() + '|' + (stored || process.env.ADMIN_PASSWORD || '');
}

function mac(key, payload) {
  return crypto.createHmac('sha256', key).update(payload).digest('base64url');
}

function safeEqual(a, b) {
  const x = Buffer.from(String(a));
  const y = Buffer.from(String(b));
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}

function readCookie(req, name) {
  const raw = req.headers.cookie || '';
  for (const part of raw.split(';')) {
    const i = part.indexOf('=');
    if (i > 0 && part.slice(0, i).trim() === name) return decodeURIComponent(part.slice(i + 1).trim());
  }
  return '';
}

export async function isAdmin(req) {
  const token = readCookie(req, COOKIE);
  const [exp, sig] = token.split('.');
  if (!exp || !sig || Number(exp) < Date.now()) return false;
  return safeEqual(sig, mac(await signingKey(), exp));
}

export async function requireAdmin(req) {
  if (!(await isAdmin(req))) throw new HttpError(401, 'Veuillez vous connecter.');
}

export async function sessionCookie() {
  const exp = String(Date.now() + SESSION_DAYS * 864e5);
  const token = exp + '.' + mac(await signingKey(), exp);
  return `${COOKIE}=${token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${SESSION_DAYS * 86400}`;
}

export function clearCookie() {
  return `${COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0`;
}

// ---- Mots de passe ----
function hashPassword(pw) {
  const salt = crypto.randomBytes(16).toString('base64url');
  const hash = crypto.scryptSync(pw, salt, 32).toString('base64url');
  return `scrypt$${salt}$${hash}`;
}

async function checkPassword(pw) {
  const stored = await getSetting('admin_password', null);
  if (stored) {
    const [, salt, hash] = String(stored).split('$');
    return safeEqual(crypto.scryptSync(pw, salt, 32).toString('base64url'), hash);
  }
  const envPw = process.env.ADMIN_PASSWORD;
  if (!envPw) throw new HttpError(500, 'Configuration manquante (ADMIN_PASSWORD).');
  const h = (s) => crypto.createHash('sha256').update(s).digest('hex');
  return safeEqual(h(pw), h(envPw));
}

export async function login(req, password) {
  const ip = clientIp(req);
  await q(`DELETE FROM kb_login_attempts WHERE at < now() - interval '1 day'`);
  const [{ n }] = await q(
    `SELECT count(*)::int AS n FROM kb_login_attempts WHERE ip = $1 AND at > now() - interval '15 minutes'`,
    [ip]
  );
  if (n >= 8) throw new HttpError(429, 'Trop de tentatives. Réessayez dans 15 minutes.');
  if (!password || !(await checkPassword(String(password)))) {
    await q(`INSERT INTO kb_login_attempts (ip) VALUES ($1)`, [ip]);
    await new Promise((r) => setTimeout(r, 600));
    throw new HttpError(401, 'Mot de passe incorrect.');
  }
  await q(`DELETE FROM kb_login_attempts WHERE ip = $1`, [ip]);
}

export async function changePassword(current, next) {
  if (!(await checkPassword(String(current || '')))) throw new HttpError(400, 'Le mot de passe actuel est incorrect.');
  next = String(next || '');
  if (next.length < 10) throw new HttpError(400, 'Le nouveau mot de passe doit faire au moins 10 caractères.');
  if (next.length > 200) throw new HttpError(400, 'Le nouveau mot de passe est trop long.');
  await setSetting('admin_password', hashPassword(next));
}
