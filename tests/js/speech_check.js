// Texte lu à voix haute : nettoyé (émojis, code, liens, actions cachées) et assez long pour une page entière.
const src = require("fs").readFileSync(__dirname + "/../../web/app.js", "utf8");
eval(src.match(/function spokenText[\s\S]*?\n}\n/)[0] + "; globalThis.spokenText = spokenText");
const out = spokenText("Salut 😀 !\n- **Premier** point\n- Voir https://x.fr/a\n```js\nx=1\n```\nOk <tool_call>{\"name\":\"a\"}</tool_call> fin 👍🏽");
const bad = [];
if (out !== "Salut ! Premier point. Voir lien. Ok fin") bad.push("nettoyage : " + JSON.stringify(out));
const long = spokenText("Une phrase assez longue pour le test. ".repeat(400));  // ≈ 15 000 caractères
if (long.length < 5500 || long.length > 6000) bad.push("longueur : " + long.length);
if (bad.length) { console.error(bad.join("\n")); process.exit(1); }
console.log("ok");
