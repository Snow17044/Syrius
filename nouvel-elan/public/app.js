// ─────────────────────────────────────────────────────────────
//  À PERSONNALISER : présentation et réseaux de l'association
// ─────────────────────────────────────────────────────────────
const ASSOCIATION = {
  description:
    "Nouvel Élan est une association politique de jeunes qui veulent faire bouger les choses. " +
    "Débats, actions de terrain, propositions : rejoins le mouvement !",
  reseaux: [
    // Remplace les liens ci-dessous par les vrais comptes (ou supprime une ligne).
    { nom: "Instagram", icone: "📸", lien: "https://www.instagram.com/" },
    { nom: "TikTok", icone: "🎵", lien: "https://www.tiktok.com/" },
    { nom: "X (Twitter)", icone: "✖️", lien: "https://x.com/" },
    { nom: "Nous écrire", icone: "✉️", lien: "mailto:contact@exemple.fr" },
  ],
};
// ─────────────────────────────────────────────────────────────

const $ = (s) => document.querySelector(s);
const PAGES = ["accueil", "articles", "ajouter", "asso"];
const CLE_CACHE = "ne-articles";
const CLE_CODE = "ne-code-editeur";

const etat = { articles: [], categories: [], filtre: "Tous", recherche: "" };

function stocker(cle, valeur) { try { valeur == null ? localStorage.removeItem(cle) : localStorage.setItem(cle, valeur); } catch {} }
function lire(cle) { try { return localStorage.getItem(cle); } catch { return null; } }
const codeEditeur = () => lire(CLE_CODE) || "";

function el(balise, attributs = {}, ...enfants) {
  const n = document.createElement(balise);
  for (const [k, v] of Object.entries(attributs)) {
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) n.setAttribute(k, v);
  }
  for (const e of enfants.flat()) if (e != null && e !== false) n.append(e);
  return n;
}

function toast(texte) {
  const t = $("#toast");
  t.textContent = texte;
  t.hidden = false;
  clearTimeout(toast.minuteur);
  toast.minuteur = setTimeout(() => (t.hidden = true), 2600);
}

function dateCourte(iso) {
  const d = new Date(iso);
  const jours = Math.floor((Date.now() - d) / 86400000);
  if (jours <= 0) return "Aujourd'hui";
  if (jours === 1) return "Hier";
  if (jours < 7) return `Il y a ${jours} jours`;
  return d.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: d.getFullYear() === new Date().getFullYear() ? undefined : "numeric" });
}

// ── Navigation ───────────────────────────────────────────────
function aller(page, { historique = true } = {}) {
  if (!PAGES.includes(page)) page = "accueil";
  for (const p of PAGES) $(`#page-${p}`).hidden = p !== page;
  document.querySelectorAll(".barre button").forEach((b) =>
    b.dataset.aller === page ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current"));
  $("#titre-page").textContent = $(`#page-${page}`).dataset.titre;
  if (historique && location.hash !== `#${page}`) history.pushState(null, "", `#${page}`);
  window.scrollTo(0, 0);
  if (page === "ajouter") majBlocCode();
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-aller]");
  if (b) aller(b.dataset.aller);
});
window.addEventListener("popstate", () => aller(location.hash.slice(1), { historique: false }));

// ── Articles ─────────────────────────────────────────────────
async function api(chemin, options = {}) {
  const r = await fetch(chemin, {
    ...options,
    headers: { "Content-Type": "application/json", "X-Code-Editeur": codeEditeur(), ...(options.headers || {}) },
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(d.erreur || "Connexion impossible."), { statut: r.status });
  return d;
}

async function chargerArticles() {
  const cache = lire(CLE_CACHE);
  if (cache) { try { Object.assign(etat, JSON.parse(cache)); afficher(); } catch {} }
  try {
    const d = await api("/api/articles");
    etat.articles = d.articles;
    etat.categories = d.categories;
    stocker(CLE_CACHE, JSON.stringify({ articles: d.articles, categories: d.categories }));
  } catch (e) {
    if (!cache) toast(navigator.onLine ? e.message : "Hors connexion : articles indisponibles.");
    else if (!navigator.onLine) toast("Hors connexion : derniers articles enregistrés.");
  }
  afficher();
}

function vignette(a, classe) {
  if (a.image) {
    const img = el("img", { class: classe, src: a.image, alt: "", loading: "lazy", referrerpolicy: "no-referrer" });
    img.addEventListener("error", () => img.replaceWith(el("div", { class: `${classe} ${classe === "article-image" ? "vide" : "une-vide"}` }, "NÉ")));
    return img;
  }
  return el("div", { class: `${classe} ${classe === "article-image" ? "vide" : "une-vide"}` }, "NÉ");
}

function iconeBtn(titre, chemin, action, danger = false) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.innerHTML = chemin; // chemins SVG fixes, écrits ci-dessous (aucune donnée extérieure)
  return el("button", { class: `icone-btn${danger ? " danger" : ""}`, type: "button", "aria-label": titre, title: titre,
    onclick: (e) => { e.preventDefault(); e.stopPropagation(); action(); } }, svg);
}
const SVG_PARTAGE = '<circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="m8.2 10.8 7.6-4.4M8.2 13.2l7.6 4.4"/>';
const SVG_EPINGLE = '<path d="M9 3h6l-1 6 4 4H6l4-4zM12 13v8"/>';
const SVG_SUPPR = '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>';

async function partager(titre, url) {
  if (navigator.share) { try { await navigator.share({ title: titre, url }); } catch {} return; }
  try { await navigator.clipboard.writeText(url); toast("Lien copié !"); } catch { prompt("Copie ce lien :", url); }
}

function carte(a) {
  const actions = [iconeBtn("Partager", SVG_PARTAGE, () => partager(a.titre, a.url))];
  if (codeEditeur()) {
    actions.push(iconeBtn(a.epingle ? "Retirer de la une" : "Mettre à la une", SVG_EPINGLE, () => epingler(a)));
    actions.push(iconeBtn("Supprimer", SVG_SUPPR, () => supprimer(a), true));
  }
  return el("a", { class: "article", href: a.url, target: "_blank", rel: "noopener noreferrer" },
    vignette(a, "article-image"),
    el("div", { class: "article-corps" },
      el("span", { class: "article-theme" }, a.categorie, a.epingle ? el("span", { class: "epingle" }, "📌") : null),
      el("h4", { class: "article-titre" }, a.titre),
      el("div", { class: "article-bas" },
        el("span", { class: "article-infos" }, `${a.source} · ${dateCourte(a.date)}`),
        el("div", { class: "article-actions" }, actions))));
}

function etatVide(texte, avecBouton = true) {
  return el("div", { class: "vide-etat" }, el("p", {}, texte),
    avecBouton ? el("button", { class: "btn-secondaire", "data-aller": "ajouter", type: "button" }, "＋ Ajouter un article") : null);
}

function puces(conteneur, auClic) {
  conteneur.replaceChildren(...["Tous", ...etat.categories].map((c) =>
    el("button", { class: "puce", type: "button", "aria-pressed": String(etat.filtre === c), onclick: () => auClic(c) }, c)));
}

function afficher() {
  const tous = etat.articles;
  // Accueil : la une (article épinglé, sinon le plus récent) + les 5 suivants
  const une = tous.find((a) => a.epingle) || tous[0];
  $("#une").replaceChildren(une
    ? el("a", { class: "une", href: une.url, target: "_blank", rel: "noopener noreferrer" },
        vignette(une, "une-img"),
        el("div", { class: "une-corps" },
          el("span", { class: "article-theme" }, une.categorie),
          el("h4", {}, une.titre),
          une.resume ? el("p", {}, une.resume) : null))
    : etatVide("Aucun article pour l'instant. Le premier, c'est toi ?"));
  $("#derniers").replaceChildren(...tous.filter((a) => a !== une).slice(0, 5).map(carte));
  puces($("#puces-accueil"), (c) => { etat.filtre = c; afficher(); aller("articles"); });

  // Page Articles : filtre + recherche
  puces($("#puces-articles"), (c) => { etat.filtre = c; afficher(); });
  const q = etat.recherche.toLowerCase();
  const filtres = tous.filter((a) =>
    (etat.filtre === "Tous" || a.categorie === etat.filtre) &&
    (!q || `${a.titre} ${a.resume} ${a.source}`.toLowerCase().includes(q)));
  $("#compteur").textContent = `${filtres.length} article${filtres.length > 1 ? "s" : ""}`;
  $("#liste-articles").replaceChildren(...(filtres.length ? filtres.map(carte)
    : [etatVide(tous.length ? "Aucun article ne correspond." : "Aucun article pour l'instant.", !tous.length)]));

  const sel = $("#champ-categorie");
  if (sel.options.length !== etat.categories.length) sel.replaceChildren(...etat.categories.map((c) => el("option", { value: c }, c)));
}
$("#recherche").addEventListener("input", (e) => { etat.recherche = e.target.value; afficher(); });

async function epingler(a) {
  try {
    if (!a.epingle) for (const autre of etat.articles.filter((x) => x.epingle)) await api("/api/articles", { method: "PATCH", body: JSON.stringify({ id: autre.id, epingle: false }) });
    await api("/api/articles", { method: "PATCH", body: JSON.stringify({ id: a.id, epingle: !a.epingle }) });
    toast(a.epingle ? "Retiré de la une" : "Mis à la une 📌");
    chargerArticles();
  } catch (e) { erreurEditeur(e); }
}

async function supprimer(a) {
  if (!confirm(`Supprimer « ${a.titre} » ?`)) return;
  try {
    await api(`/api/articles?id=${encodeURIComponent(a.id)}`, { method: "DELETE" });
    toast("Article supprimé");
    chargerArticles();
  } catch (e) { erreurEditeur(e); }
}

function erreurEditeur(e) {
  if (e.statut === 401) { stocker(CLE_CODE, null); majModeEditeur(); afficher(); }
  toast(e.message);
}

// ── Ajouter un article ───────────────────────────────────────
let apercuActuel = null;

function extraireLien(texte) {
  const m = String(texte || "").match(/https?:\/\/[^\s<>"']+/i);
  return m ? m[0].replace(/[).,;!?]+$/, "") : "";
}

async function chargerApercu() {
  const lien = extraireLien($("#champ-lien").value);
  const boite = $("#apercu");
  if (!lien) { boite.hidden = true; $("#details").hidden = true; apercuActuel = null; return; }
  if (apercuActuel?.url === lien) return;
  $("#champ-lien").value = lien;
  boite.hidden = false;
  boite.className = "apercu chargement";
  boite.replaceChildren(el("div", {}, "Recherche des informations de l'article…"));
  try {
    const r = await fetch(`/api/apercu?url=${encodeURIComponent(lien)}`);
    apercuActuel = await r.json();
    if (!r.ok) throw new Error(apercuActuel.erreur);
  } catch (e) {
    apercuActuel = { url: lien, titre: "", resume: "", image: "", source: new URL(lien).hostname };
  }
  boite.className = "apercu";
  boite.replaceChildren(
    apercuActuel.image ? el("img", { src: apercuActuel.image, alt: "", referrerpolicy: "no-referrer", onerror: (e) => e.target.remove() }) : "",
    el("div", {}, apercuActuel.titre ? `${apercuActuel.source} — ${apercuActuel.resume || "aperçu prêt"}` : "Pas d'aperçu automatique pour ce site : écris le titre toi-même ci-dessous."));
  $("#champ-titre").value = apercuActuel.titre || "";
  $("#details").hidden = false;
  if (!apercuActuel.titre) $("#champ-titre").focus();
}

let minuteurLien;
$("#champ-lien").addEventListener("input", () => { clearTimeout(minuteurLien); minuteurLien = setTimeout(chargerApercu, 500); });
$("#champ-lien").addEventListener("paste", () => setTimeout(chargerApercu, 0));
$("#btn-coller").addEventListener("click", async () => {
  try {
    $("#champ-lien").value = await navigator.clipboard.readText();
    chargerApercu();
  } catch { $("#champ-lien").focus(); toast("Appuie longuement dans le champ puis « Coller »."); }
});

function majBlocCode() { $("#bloc-code").hidden = Boolean(codeEditeur()); }

$("#form-ajout").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#message-ajout");
  msg.className = "message";
  msg.textContent = "";
  await chargerApercu();
  if (!apercuActuel) { msg.className = "message erreur"; msg.textContent = "Colle d'abord un lien valide."; return; }
  const nouveauCode = $("#champ-code").value.trim();
  if (nouveauCode) stocker(CLE_CODE, nouveauCode);
  if (!codeEditeur()) { msg.className = "message erreur"; msg.textContent = "Entre le code éditeur."; $("#champ-code").focus(); return; }

  const btn = $("#btn-publier");
  btn.disabled = true;
  btn.textContent = "Publication…";
  try {
    await api("/api/articles", {
      method: "POST",
      body: JSON.stringify({ ...apercuActuel, titre: $("#champ-titre").value, categorie: $("#champ-categorie").value }),
    });
    $("#form-ajout").reset();
    $("#champ-code").value = "";
    $("#apercu").hidden = true;
    $("#details").hidden = true;
    apercuActuel = null;
    majModeEditeur();
    toast("Article publié ! 🎉");
    await chargerArticles();
    aller("accueil");
  } catch (err) {
    if (err.statut === 401) { stocker(CLE_CODE, null); majBlocCode(); majModeEditeur(); }
    msg.className = "message erreur";
    msg.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Publier l'article";
  }
});

// ── Page association ─────────────────────────────────────────
$("#asso-description").textContent = ASSOCIATION.description;
$("#reseaux").replaceChildren(...ASSOCIATION.reseaux.map((r) =>
  el("a", { class: "ligne-lien", href: r.lien, target: "_blank", rel: "noopener noreferrer" }, el("span", {}, r.icone), r.nom)));

$("#btn-partager-app").addEventListener("click", () => partager("Nouvel Élan", location.origin));

function majModeEditeur() {
  $("#txt-mode-editeur").textContent = codeEditeur() ? "Quitter le mode éditeur" : "Mode éditeur (bureau)";
  majBlocCode();
}
$("#btn-mode-editeur").addEventListener("click", () => {
  if (codeEditeur()) { stocker(CLE_CODE, null); toast("Mode éditeur désactivé"); }
  else {
    const code = prompt("Code éditeur :");
    if (!code) return;
    stocker(CLE_CODE, code.trim());
    toast("Mode éditeur activé : tu peux épingler et supprimer");
  }
  majModeEditeur();
  afficher();
});

let invitationInstall = null;
window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); invitationInstall = e; $("#btn-installer").hidden = false; });
$("#btn-installer").addEventListener("click", async () => {
  if (!invitationInstall) return;
  invitationInstall.prompt();
  await invitationInstall.userChoice;
  invitationInstall = null;
  $("#btn-installer").hidden = true;
});
const estIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
const installee = matchMedia("(display-mode: standalone)").matches || navigator.standalone;
$("#aide-ios").hidden = !(estIOS && !installee);

// ── Démarrage ────────────────────────────────────────────────
// Lien partagé vers l'application (menu « Partager » du téléphone) ou lien du type /?ajouter=https://…
const params = new URLSearchParams(location.search);
const lienRecu = extraireLien(params.get("ajouter") || params.get("url") || params.get("text") || params.get("title"));
majModeEditeur();
if (lienRecu) {
  history.replaceState(null, "", "/#ajouter");
  aller("ajouter", { historique: false });
  $("#champ-lien").value = lienRecu;
  chargerArticles().then(chargerApercu);
} else {
  aller(location.hash.slice(1) || "accueil", { historique: false });
  chargerArticles();
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
