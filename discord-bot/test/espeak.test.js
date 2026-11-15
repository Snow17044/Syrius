"use strict";
// Voix eSpeak (utilisée sur téléphone / Termux) : son français lisible et converti pour Discord.
const test = require("node:test");
const assert = require("node:assert");
const { spawnSync } = require("node:child_process");
const audio = require("../audio");

const bin = process.env.ESPEAK_BIN || "espeak-ng";
const ok = spawnSync(bin, ["--version"]).status === 0;

test("eSpeak : « Bonjour, je suis Syrius » en WAV puis au format Discord", { skip: !ok && "eSpeak absent" }, () => {
  const r = spawnSync(bin, ["-v", "fr", "-s", "165", "--stdout", "--", "Bonjour, je suis Syrius."]);
  assert.strictEqual(r.status, 0);
  const { rate, channels, pcm } = audio.readWav(r.stdout);
  assert.ok(rate > 8000 && channels === 1 && pcm.length > rate);  // au moins une demi-seconde de son
  const out = audio.toDiscord(pcm, rate, channels);
  assert.ok(out.length > 48000 * 4 * 0.5);
});
