"use strict";
// Syrius dans un salon vocal Discord.
// Il rejoint ton salon quand tu y entres, écoute UNIQUEMENT les comptes autorisés dans ton Syrius, et ne
// répond que si ta phrase commence par « Syrius ». Le son n'est jamais enregistré sur ce serveur.
//
// Variables (fichier /etc/syrius-discord.env, jamais dans le code) :
//   DISCORD_TOKEN  : jeton du bot (portail développeur Discord)
//   SYRIUS_BOT_KEY : clé du bot créée dans les réglages de ton Syrius
//   SYRIUS_URL     : adresse de ton Syrius (ex. https://syriusprojet1.vercel.app)
//   PIPER_URL      : voix de synthèse locale (par défaut http://127.0.0.1:5000)

const { Client, GatewayIntentBits, Events } = require("discord.js");
const {
  joinVoiceChannel, getVoiceConnection, createAudioPlayer, createAudioResource, StreamType, EndBehaviorType,
  AudioPlayerStatus, entersState, VoiceConnectionStatus,
} = require("@discordjs/voice");
const prism = require("prism-media");
const { Readable } = require("node:stream");
const audio = require("./audio");

const SYRIUS_URL = (process.env.SYRIUS_URL || "").replace(/\/+$/, "");
const BOT_KEY = process.env.SYRIUS_BOT_KEY || "";
const PIPER_URL = (process.env.PIPER_URL || "http://127.0.0.1:5000").replace(/\/+$/, "");
const MAX_SECONDS = 15;     // une phrase de 15 s au plus
const MIN_SECONDS = 0.6;    // en dessous : bruit, ignoré
const SILENCE_MS = 900;     // fin de phrase après ce silence

if (!process.env.DISCORD_TOKEN || !BOT_KEY || !/^https:\/\//.test(SYRIUS_URL)) {
  console.error("Configuration incomplète : DISCORD_TOKEN, SYRIUS_BOT_KEY et SYRIUS_URL (https) sont nécessaires.");
  process.exit(1);
}

let allowed = new Set();
const players = new Map();   // salon → lecteur audio
const busy = new Set();      // personnes dont on traite déjà une phrase
const queues = new Map();    // salon → file des réponses à dire

async function syrius(path, opts = {}) {
  const res = await fetch(SYRIUS_URL + path, {
    ...opts,
    headers: { Authorization: `Bearer ${BOT_KEY}`, "X-Syrius": "1", "User-Agent": "SyriusDiscord/1.0", ...(opts.headers || {}) },
    signal: AbortSignal.timeout(90_000),
  });
  if (!res.ok) throw new Error(`Syrius a répondu ${res.status}`);
  return res.json();
}

async function refreshAllowed() {
  try {
    const cfg = await syrius("/api/bot/config");
    allowed = new Set((cfg.discord_ids || []).filter((id) => /^[0-9]{15,21}$/.test(id)));
    console.log(`Comptes autorisés : ${allowed.size}`);
  } catch (err) {
    console.error("Configuration indisponible :", err.message);
  }
}

/** Texte → voix (Piper, sur ce serveur) → son au format Discord. */
async function synthesize(text) {
  const res = await fetch(PIPER_URL + "/synthesize", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: text.slice(0, 1200) }), signal: AbortSignal.timeout(60_000),
  });
  if (!res.ok) throw new Error(`voix indisponible (${res.status})`);
  const { rate, channels, pcm } = audio.readWav(Buffer.from(await res.arrayBuffer()));
  return audio.toDiscord(pcm, rate, channels);
}

function player(guildId) {
  if (!players.has(guildId)) {
    const p = createAudioPlayer();
    p.on("error", (e) => console.error("Lecture :", e.message));
    p.on(AudioPlayerStatus.Idle, () => playNext(guildId));
    players.set(guildId, p);
  }
  return players.get(guildId);
}

function playNext(guildId) {
  const q = queues.get(guildId) || [];
  const p = player(guildId);
  if (!q.length || p.state.status !== AudioPlayerStatus.Idle) return;
  const pcm = q.shift();
  p.play(createAudioResource(Readable.from([pcm]), { inputType: StreamType.Raw }));
}

async function say(guildId, text) {
  try {
    const pcm = await synthesize(text);
    if (!queues.has(guildId)) queues.set(guildId, []);
    queues.get(guildId).push(pcm);
    playNext(guildId);
  } catch (err) {
    console.error("Voix :", err.message);
  }
}

/** Une phrase d'un compte autorisé : enregistrée en mémoire, envoyée à Syrius, réponse lue à voix haute. */
function listen(connection, guildId, userId) {
  if (busy.has(userId) || !allowed.has(userId)) return;
  busy.add(userId);
  const opus = connection.receiver.subscribe(userId, { end: { behavior: EndBehaviorType.AfterSilence, duration: SILENCE_MS } });
  const decoder = new prism.opus.Decoder({ rate: 48000, channels: 2, frameSize: 960 });
  const chunks = [];
  let size = 0;
  const limit = 48000 * 4 * MAX_SECONDS;
  const stream = opus.pipe(decoder);
  stream.on("data", (c) => {
    if (size < limit) { chunks.push(c); size += c.length; }
  });
  const finish = async () => {
    try {
      if (size < 48000 * 4 * MIN_SECONDS) return;
      const pcm16 = audio.downsample48kStereoTo16kMono(Buffer.concat(chunks));
      const r = await syrius("/api/bot/voice", {
        method: "POST", body: audio.wav(pcm16, 16000, 1),
        headers: { "Content-Type": "audio/wav", "X-Discord-User": userId },
      });
      if (!r.ignored && r.text) await say(guildId, r.text);
    } catch (err) {
      console.error("Question :", err.message);
    } finally {
      busy.delete(userId);
    }
  };
  stream.once("end", finish);
  stream.once("error", (e) => { console.error("Son :", e.message); busy.delete(userId); });
}

async function join(channel) {
  const existing = getVoiceConnection(channel.guild.id);
  if (existing && existing.joinConfig.channelId === channel.id) return;
  if (existing) existing.destroy();
  const connection = joinVoiceChannel({
    channelId: channel.id, guildId: channel.guild.id, adapterCreator: channel.guild.voiceAdapterCreator,
    selfDeaf: false, selfMute: false,
  });
  try {
    await entersState(connection, VoiceConnectionStatus.Ready, 20_000);
  } catch (err) {
    console.error("Connexion au salon impossible :", err.message);
    connection.destroy();
    return;
  }
  connection.subscribe(player(channel.guild.id));
  connection.receiver.speaking.on("start", (userId) => listen(connection, channel.guild.id, userId));
  console.log(`Dans le salon « ${channel.name} »`);
  say(channel.guild.id, "Syrius est là. Dis Syrius, puis ta question.");
}

const client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildVoiceStates] });

client.once(Events.ClientReady, async (c) => {
  console.log(`Connecté à Discord : ${c.user.tag}`);
  await refreshAllowed();
  if (!allowed.size) {  // personne d'autorisé : le créateur du bot (toi) l'est automatiquement
    try {
      const app = await c.application.fetch();
      const owner = app.owner && (app.owner.ownerId || app.owner.id);
      if (owner) {
        await syrius("/api/bot/owner", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ discord_id: String(owner) }) });
        await refreshAllowed();
      }
    } catch (err) {
      console.error("Créateur du bot introuvable :", err.message);
    }
  }
  setInterval(refreshAllowed, 5 * 60_000);
  // Si tu es déjà dans un salon au démarrage, Syrius te rejoint.
  for (const guild of c.guilds.cache.values()) {
    for (const id of allowed) {
      const vs = guild.voiceStates.cache.get(id);
      if (vs && vs.channel) { await join(vs.channel); break; }
    }
  }
});

client.on(Events.VoiceStateUpdate, async (oldState, newState) => {
  const id = newState.id;
  if (!allowed.has(id) || id === client.user.id) return;
  if (newState.channel && newState.channelId !== oldState.channelId) {
    await join(newState.channel);  // tu entres (ou changes de salon) : Syrius te suit
  } else if (!newState.channel && oldState.channel) {
    const stillThere = [...oldState.channel.members.keys()].some((m) => allowed.has(m));
    if (!stillThere) {
      getVoiceConnection(oldState.guild.id)?.destroy();  // tu pars : Syrius part aussi
      console.log("Salon quitté");
    }
  }
});

// Hébergement de type « Space » (Hugging Face) : une petite page d'état sur le port demandé.
if (process.env.PORT) {
  require("node:http").createServer((req, res) => {
    const ready = client.isReady();
    res.writeHead(200, { "Content-Type": "text/plain; charset=utf-8" });
    res.end(ready ? `Syrius sur Discord : connecté (${client.user.tag})` : "Syrius sur Discord : démarrage…");
  }).listen(Number(process.env.PORT), "0.0.0.0");
}

process.on("unhandledRejection", (e) => console.error("Erreur :", e && e.message));
client.login(process.env.DISCORD_TOKEN);
