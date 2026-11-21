// Stockage des photos.
// En ligne : Vercel Blob (variable BLOB_READ_WRITE_TOKEN fournie par Vercel).
// En local (tests) : un dossier sur le disque, servi sous /uploads/.
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { HttpError } from './http.js';

export const MAX_IMAGE_BYTES = 4 * 1024 * 1024;

// Vérifie le vrai type du fichier à partir de ses premiers octets.
function detectType(buf) {
  if (buf.length > 3 && buf[0] === 0xff && buf[1] === 0xd8 && buf[2] === 0xff) return ['image/jpeg', 'jpg'];
  if (buf.length > 8 && buf.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) return ['image/png', 'png'];
  if (buf.length > 12 && buf.toString('ascii', 0, 4) === 'RIFF' && buf.toString('ascii', 8, 12) === 'WEBP') return ['image/webp', 'webp'];
  return null;
}

export async function readImage(req) {
  const chunks = [];
  let size = 0;
  for await (const c of req) {
    size += c.length;
    if (size > MAX_IMAGE_BYTES) throw new HttpError(413, 'Photo trop lourde (4 Mo maximum).');
    chunks.push(c);
  }
  let buf = Buffer.concat(chunks);
  if (!buf.length && Buffer.isBuffer(req.body)) buf = req.body;
  if (!buf.length) throw new HttpError(400, 'Aucune photo reçue.');
  const type = detectType(buf);
  if (!type) throw new HttpError(400, 'Format non pris en charge (JPEG, PNG ou WebP).');
  return { buf, contentType: type[0], ext: type[1] };
}

export async function saveImage({ buf, contentType, ext }, folder = 'photos') {
  const name = `${folder}/${Date.now()}-${crypto.randomBytes(6).toString('hex')}.${ext}`;
  if (process.env.BLOB_READ_WRITE_TOKEN) {
    const { put } = await import('@vercel/blob');
    const r = await put(name, buf, { access: 'public', contentType, addRandomSuffix: false, cacheControlMaxAge: 31536000 });
    return r.url;
  }
  const dir = process.env.LOCAL_UPLOAD_DIR;
  if (!dir) throw new HttpError(500, 'Stockage des photos non configuré.');
  await fs.mkdir(path.join(dir, folder), { recursive: true });
  await fs.writeFile(path.join(dir, name), buf);
  return '/uploads/' + name;
}

export async function deleteImage(url) {
  if (!url) return;
  try {
    if (process.env.BLOB_READ_WRITE_TOKEN && /^https:\/\/[^/]+\.blob\.vercel-storage\.com\//.test(url)) {
      const { del } = await import('@vercel/blob');
      await del(url);
    } else if (url.startsWith('/uploads/') && process.env.LOCAL_UPLOAD_DIR) {
      const rel = path.normalize(url.slice('/uploads/'.length));
      if (!rel.startsWith('..')) await fs.unlink(path.join(process.env.LOCAL_UPLOAD_DIR, rel));
    }
  } catch (e) {
    console.error('Suppression de photo impossible', e?.message);
  }
}
