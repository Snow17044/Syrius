"use strict";
const test = require("node:test");
const assert = require("node:assert");
const audio = require("../audio");

test("48 kHz stéréo → 16 kHz mono → WAV relu", () => {
  const frames = 4800;  // 0,1 s
  const buf = Buffer.alloc(frames * 4);
  for (let i = 0; i < frames; i++) { buf.writeInt16LE(1000, i * 4); buf.writeInt16LE(3000, i * 4 + 2); }
  const mono = audio.downsample48kStereoTo16kMono(buf);
  assert.strictEqual(mono.length, 1600 * 2);
  assert.strictEqual(mono.readInt16LE(100), 2000);
  const w = audio.readWav(audio.wav(mono, 16000, 1));
  assert.strictEqual(w.rate, 16000);
  assert.strictEqual(w.channels, 1);
  assert.strictEqual(w.pcm.length, mono.length);
});

test("voix 22 050 Hz mono → 48 kHz stéréo pour Discord", () => {
  const pcm = Buffer.alloc(22050 * 2);
  for (let i = 0; i < 22050; i++) pcm.writeInt16LE(500, i * 2);
  const out = audio.toDiscord(pcm, 22050, 1);
  assert.ok(Math.abs(out.length / 4 - 48000) <= 2);
  assert.strictEqual(out.readInt16LE(400), 500);
  assert.strictEqual(out.readInt16LE(402), 500);
});

test("WAV invalide refusé", () => {
  assert.throws(() => audio.readWav(Buffer.from("pas un wav du tout, vraiment pas")));
});
