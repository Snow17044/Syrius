"use strict";
// Conversions de son, sans programme externe :
// - Discord fournit du PCM 48 kHz stéréo 16 bits → on envoie à Syrius un WAV 16 kHz mono (idéal pour Whisper) ;
// - la voix de synthèse (Piper) donne un WAV mono → on le remet en 48 kHz stéréo pour Discord.

/** PCM 48 kHz stéréo (Int16 LE) → PCM 16 kHz mono. */
function downsample48kStereoTo16kMono(buf) {
  const frames = Math.floor(buf.length / 4);
  const outLen = Math.floor(frames / 3);
  const out = Buffer.alloc(outLen * 2);
  for (let i = 0; i < outLen; i++) {
    let sum = 0;
    for (let k = 0; k < 3; k++) {  // moyenne de 3 trames (filtre simple contre le repliement)
      const f = (i * 3 + k) * 4;
      sum += (buf.readInt16LE(f) + buf.readInt16LE(f + 2)) / 2;
    }
    out.writeInt16LE(Math.max(-32768, Math.min(32767, Math.round(sum / 3))), i * 2);
  }
  return out;
}

/** Enveloppe WAV (PCM 16 bits). */
function wav(pcm, rate, channels) {
  const h = Buffer.alloc(44);
  h.write("RIFF", 0);
  h.writeUInt32LE(36 + pcm.length, 4);
  h.write("WAVEfmt ", 8);
  h.writeUInt32LE(16, 16);
  h.writeUInt16LE(1, 20);
  h.writeUInt16LE(channels, 22);
  h.writeUInt32LE(rate, 24);
  h.writeUInt32LE(rate * channels * 2, 28);
  h.writeUInt16LE(channels * 2, 32);
  h.writeUInt16LE(16, 34);
  h.write("data", 36);
  h.writeUInt32LE(pcm.length, 40);
  return Buffer.concat([h, pcm]);
}

/** Lit un WAV PCM 16 bits : { rate, channels, pcm }. */
function readWav(buf) {
  if (buf.length < 44 || buf.toString("ascii", 0, 4) !== "RIFF" || buf.toString("ascii", 8, 12) !== "WAVE") {
    throw new Error("WAV invalide");
  }
  let p = 12, rate = 0, channels = 0, bits = 0;
  while (p + 8 <= buf.length) {
    const id = buf.toString("ascii", p, p + 4), size = buf.readUInt32LE(p + 4);
    if (id === "fmt ") {
      channels = buf.readUInt16LE(p + 10);
      rate = buf.readUInt32LE(p + 12);
      bits = buf.readUInt16LE(p + 22);
    } else if (id === "data") {
      if (bits !== 16 || !rate || !channels) throw new Error("format WAV non pris en charge");
      return { rate, channels, pcm: buf.subarray(p + 8, Math.min(buf.length, p + 8 + size)) };
    }
    p += 8 + size + (size % 2);
  }
  throw new Error("WAV sans données");
}

/** PCM mono (n'importe quelle fréquence) → PCM 48 kHz stéréo pour Discord (interpolation linéaire). */
function toDiscord(pcm, rate, channels) {
  const inFrames = Math.floor(pcm.length / (2 * channels));
  const outFrames = Math.floor(inFrames * 48000 / rate);
  const out = Buffer.alloc(outFrames * 4);
  const sample = (i) => {  // mono : moyenne des canaux
    let s = 0;
    for (let c = 0; c < channels; c++) s += pcm.readInt16LE((i * channels + c) * 2);
    return s / channels;
  };
  for (let j = 0; j < outFrames; j++) {
    const x = j * rate / 48000;
    const i = Math.floor(x), t = x - i;
    const a = sample(Math.min(i, inFrames - 1)), b = sample(Math.min(i + 1, inFrames - 1));
    const v = Math.round(a + (b - a) * t);
    out.writeInt16LE(v, j * 4);
    out.writeInt16LE(v, j * 4 + 2);
  }
  return out;
}

module.exports = { downsample48kStereoTo16kMono, wav, readWav, toDiscord };
