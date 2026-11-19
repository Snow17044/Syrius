// Vérifie la répartition du travail : ordres simples → téléphone, questions → grandes IA en ligne.
const src = require("fs").readFileSync(__dirname + "/../../web/local.js", "utf8");
const m = src.match(/const CMD = \[[\s\S]*?function isCommand[\s\S]*?\n  }\n/)[0];
eval(m + "; globalThis.isCommand = isCommand");
const yes = ["Mets un minuteur de 10 minutes", "Syrius, réveille-moi à 7h", "Rappelle-moi d'appeler maman demain à 18h",
  "Allume la lampe torche", "Monte le volume", "Appelle Papa", "Envoie un SMS à Julie", "Joue du Daft Punk",
  "Ouvre WhatsApp", "Emmène-moi à la gare", "Retiens que ma soeur s'appelle Clara", "Hey Syrius, un minuteur de 3 minutes"];
const no = ["Pourquoi le ciel est bleu ?", "Explique-moi la photosynthèse", "Raconte une blague", "Combien font 12 fois 13 ?",
  "Comment fonctionne un moteur à volume variable ?", "Écris-moi un long mail pour mon patron afin de demander un rendez-vous",
  "Qui est le président de la France ?", "", "x".repeat(200) + " minuteur"];
const bad = yes.filter((t) => !isCommand(t)).concat(no.filter((t) => isCommand(t)));
if (bad.length) { console.error("Mal classés :", bad); process.exit(1); }
console.log("ok");
