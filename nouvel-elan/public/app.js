// ─────────────────────────────────────────────────────────────
//  À PERSONNALISER : présentation et réseaux de l'association
// ─────────────────────────────────────────────────────────────
const ASSOCIATION = {
  description:
    "Nouvel Élan est un mouvement politique de jeunes qui veulent faire bouger les choses. " +
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
const PAGES = ["accueil", "programme", "articles", "lire", "ajouter", "menu", "asso"];
const CLE_CACHE = "ne-articles";
const CLE_PROGRAMME = "ne-programme";
const CLE_CODE = "ne-code-editeur";
const CLE_QUI = "ne-editeur"; // { nom: "Président", programme: false }

const etat = { articles: [], categories: [], filtre: "Tous", recherche: "", page: "accueil", lecture: null };
let programme = { slogan: "", intro: "", photo: "", lienAdhesion: "", axes: [], maj: null };

function stocker(cle, valeur) { try { valeur == null ? localStorage.removeItem(cle) : localStorage.setItem(cle, valeur); } catch {} }
function lire(cle) { try { return localStorage.getItem(cle); } catch { return null; } }
const codeEditeur = () => lire(CLE_CODE) || "";
function qui() { try { return JSON.parse(lire(CLE_QUI)) || {}; } catch { return {}; } }
const peutModifierProgramme = () => Boolean(codeEditeur());

// Vérifie un code (ou un lien d'accès) auprès du serveur et retient qui est connecté.
async function connecter(code) {
  stocker(CLE_CODE, code);
  try {
    const d = await api("/api/editeur");
    stocker(CLE_QUI, JSON.stringify({ nom: d.nom, programme: d.programme }));
    return d;
  } catch (e) {
    if (e.statut === 401) { stocker(CLE_CODE, null); stocker(CLE_QUI, null); }
    throw e;
  }
}
function deconnecter() { stocker(CLE_CODE, null); stocker(CLE_QUI, null); }

function el(balise, attributs = {}, ...enfants) {
  const n = document.createElement(balise);
  for (const [k, v] of Object.entries(attributs)) {
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) { if (v) n.addEventListener(k.slice(2), v); }
    else if (v !== false && v != null) n.setAttribute(k, v);
  }
  for (const e of enfants.flat()) if (e != null && e !== false) n.append(e);
  return n;
}

// Comme replaceChildren, mais en ignorant les éléments absents (sinon le navigateur écrit « null »).
const remplir = (noeud, ...enfants) => noeud.replaceChildren(...enfants.flat().filter((e) => e != null && e !== false));

function svgIcone(chemin, classe = "") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  if (classe) svg.setAttribute("class", classe);
  svg.innerHTML = chemin; // chemins SVG fixes, écrits dans ce fichier (aucune donnée extérieure)
  return svg;
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

function paragraphes(texte) {
  return String(texte || "").split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean)
    .map((p) => el("p", {}, ...p.split("\n").flatMap((ligne, i) => (i ? [el("br"), ligne] : [ligne]))));
}

async function api(chemin, options = {}) {
  const r = await fetch(chemin, {
    ...options,
    headers: { "Content-Type": "application/json", "X-Code-Editeur": codeEditeur(), ...(options.headers || {}) },
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(d.erreur || "Connexion impossible."), { statut: r.status });
  return d;
}

async function partager(titre, url) {
  if (navigator.share) { try { await navigator.share({ title: titre, url }); } catch {} return; }
  try { await navigator.clipboard.writeText(url); toast("Lien copié !"); } catch { prompt("Copie ce lien :", url); }
}

// ── Navigation : barre du bas + rubriques du haut + menu ─────
function aller(page, { historique = true } = {}) {
  if (!PAGES.includes(page)) page = "accueil";
  if (page === "lire" && !etat.lecture) page = "accueil";
  etat.page = page;
  for (const p of PAGES) $(`#page-${p}`).hidden = p !== page;
  $("#titre-page").textContent = $(`#page-${page}`).dataset.titre;
  const cible = page === "lire" ? `#lire/${etat.lecture}` : `#${page}`;
  if (historique && location.hash !== cible) history.pushState(null, "", cible);
  window.scrollTo(0, 0);
  if (page === "ajouter") majBlocCode();
  if (page !== "programme" && !$("#programme-edition").hidden) fermerEdition();
  majNavigation();
}

function allerRubrique(categorie) {
  etat.filtre = categorie;
  etat.recherche = "";
  $("#recherche").value = "";
  afficherArticles();
  aller("articles");
}

function majNavigation() {
  const p = etat.page;
  document.querySelectorAll(".barre button").forEach((b) => {
    const actif = b.dataset.aller === p || (b.dataset.page === "articles" && (p === "articles" || p === "lire"));
    actif ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current");
  });
  document.querySelectorAll("#rubriques button").forEach((b) => {
    const actif = b.dataset.aller ? b.dataset.aller === p : p === "articles" && b.dataset.rubrique === etat.filtre;
    actif ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current");
  });
  const actif = $("#rubriques [aria-current]");
  if (actif) {
    const barre = $("#rubriques");
    const gauche = actif.offsetLeft - 16;
    if (gauche < barre.scrollLeft || actif.offsetLeft + actif.offsetWidth > barre.scrollLeft + barre.clientWidth) barre.scrollTo({ left: gauche, behavior: "smooth" });
  }
}

function construireRubriques() {
  $("#rubriques").replaceChildren(
    el("button", { type: "button", "data-aller": "accueil" }, "À la une"),
    el("button", { type: "button", "data-aller": "programme" }, "Programme"),
    el("button", { type: "button", "data-rubrique": "Tous" }, "Actualités"),
    ...etat.categories.map((c) => el("button", { type: "button", "data-rubrique": c }, c)),
    el("button", { type: "button", "data-aller": "asso" }, "Qui sommes-nous"));
  majNavigation();
}

document.addEventListener("click", (e) => {
  if (e.target.closest('[data-action="modifier-programme"]')) { aller("programme"); return ouvrirEdition(); }
  const r = e.target.closest("[data-rubrique]");
  if (r) return allerRubrique(r.dataset.rubrique);
  const b = e.target.closest("[data-aller]");
  if (b) aller(b.dataset.aller);
});

// Lien d'accès personnel : https://…/#acces=JETON (le jeton ne part jamais vers le serveur dans l'adresse).
async function ouvrirLienAcces(jeton) {
  history.replaceState(null, "", "/#ajouter"); // on efface le jeton de la barre d'adresse et de l'historique
  aller("ajouter", { historique: false });
  try {
    const d = await connecter(jeton);
    toast(`Bienvenue (${d.nom}) ! Tu peux publier ✅`);
  } catch (e) {
    toast(e.message);
    aller("accueil", { historique: false });
  }
  majModeEditeur();
  chargerArticles();
  chargerProgramme();
}

function routeDepuisHash() {
  const h = location.hash.slice(1);
  if (h.startsWith("acces=")) return ouvrirLienAcces(decodeURIComponent(h.slice(6)));
  if (h.startsWith("lire/")) { etat.lecture = h.slice(5); afficherLecture(); return aller("lire", { historique: false }); }
  aller(h || "accueil", { historique: false });
}
window.addEventListener("popstate", routeDepuisHash);

// ── Photos ───────────────────────────────────────────────────
// La photo est réduite sur le téléphone (1600 px, JPEG) avant l'envoi : rapide même en 4G.
async function reduirePhoto(fichier) {
  const image = await createImageBitmap(fichier);
  const echelle = Math.min(1, 1600 / Math.max(image.width, image.height));
  const toile = document.createElement("canvas");
  toile.width = Math.round(image.width * echelle);
  toile.height = Math.round(image.height * echelle);
  toile.getContext("2d").drawImage(image, 0, 0, toile.width, toile.height);
  return toile.toDataURL("image/jpeg", 0.85);
}

function demanderCode() {
  const saisi = $("#champ-code").value.trim();
  if (saisi) stocker(CLE_CODE, saisi);
  if (!codeEditeur()) {
    const code = prompt("Code éditeur :");
    if (code) stocker(CLE_CODE, code.trim());
  }
  if (codeEditeur() && !qui().nom) connecter(codeEditeur()).then(majModeEditeur).catch(() => {});
  return codeEditeur();
}

// Bloc « choisir une photo » réutilisable : aperçu, changer, retirer.
function choixPhoto(conteneur, valeurInitiale = "") {
  let valeur = valeurInitiale;
  const entree = el("input", { type: "file", accept: "image/*", hidden: true, class: "entree-photo" });
  const rendre = (enCours = false) => remplir(conteneur, entree,
    valeur ? el("img", { src: valeur, alt: "", class: "choix-photo-apercu" }) : null,
    el("div", { class: "choix-photo-boutons" },
      el("button", { type: "button", class: "btn-secondaire", disabled: enCours || null, onclick: () => entree.click() },
        enCours ? "Envoi…" : valeur ? "📷 Changer la photo" : "📷 Ajouter une photo"),
      valeur && !enCours ? el("button", { type: "button", class: "btn-secondaire danger", onclick: () => { valeur = ""; rendre(); } }, "Retirer") : null));
  entree.addEventListener("change", async () => {
    const f = entree.files[0];
    entree.value = "";
    if (!f) return;
    if (!demanderCode()) return toast("Entre d'abord le code éditeur.");
    rendre(true);
    try {
      const data = await reduirePhoto(f);
      valeur = (await api("/api/photo", { method: "POST", body: JSON.stringify({ data }) })).url;
      toast("Photo ajoutée ✅");
    } catch (e) {
      if (e.statut === 401) { deconnecter(); majModeEditeur(); }
      toast(e.statut ? e.message : "Impossible de lire cette photo.");
    }
    rendre();
  });
  rendre();
  return { get valeur() { return valeur; }, set valeur(v) { valeur = v || ""; rendre(); } };
}

// Les zones de texte s'agrandissent avec leur contenu (pratique pour coller un long texte).
function ajuster(t) { t.style.height = "auto"; t.style.height = `${Math.max(t.scrollHeight + 2, 110)}px`; }
document.addEventListener("input", (e) => { if (e.target.matches("textarea.auto")) ajuster(e.target); });
const ajusterTextes = (racine) => racine.querySelectorAll("textarea.auto").forEach(ajuster);

// ── Actualités ───────────────────────────────────────────────
async function chargerArticles() {
  const cache = lire(CLE_CACHE);
  if (cache) { try { Object.assign(etat, JSON.parse(cache)); afficherArticles(); } catch {} }
  try {
    const d = await api("/api/articles");
    etat.articles = d.articles;
    etat.categories = d.categories;
    stocker(CLE_CACHE, JSON.stringify({ articles: d.articles, categories: d.categories }));
  } catch (e) {
    if (!cache) toast(navigator.onLine ? e.message : "Hors connexion : actualités indisponibles.");
  }
  afficherArticles();
}

function vignette(a, classe) {
  const vide = () => el("div", { class: `${classe} ${classe === "article-image" ? "vide" : "une-vide"}` }, "NÉ");
  if (!a.image) return vide();
  const img = el("img", { class: classe, src: a.image, alt: "", loading: "lazy", referrerpolicy: "no-referrer" });
  img.addEventListener("error", () => img.replaceWith(vide()));
  return img;
}

const SVG_PARTAGE = '<circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="m8.2 10.8 7.6-4.4M8.2 13.2l7.6 4.4"/>';
const SVG_EPINGLE = '<path d="M9 3h6l-1 6 4 4H6l4-4zM12 13v8"/>';
const SVG_SUPPR = '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>';

function iconeBtn(titre, chemin, action, danger = false) {
  return el("button", { class: `icone-btn${danger ? " danger" : ""}`, type: "button", "aria-label": titre, title: titre,
    onclick: (e) => { e.preventDefault(); e.stopPropagation(); action(); } }, svgIcone(chemin));
}

// Un simple lien vers un article s'ouvre sur le site du journal ; une publication avec texte s'ouvre dans l'appli.
const externe = (a) => Boolean(a.url && !a.texte);
const lienPartage = (a) => (externe(a) ? a.url : `${location.origin}/#lire/${a.id}`);
function attributsLien(a) {
  return externe(a)
    ? { href: a.url, target: "_blank", rel: "noopener noreferrer" }
    : { href: `#lire/${a.id}`, onclick: (e) => { e.preventDefault(); ouvrirLecture(a.id); } };
}

function carte(a) {
  const actions = [iconeBtn("Partager", SVG_PARTAGE, () => partager(a.titre, lienPartage(a)))];
  if (codeEditeur()) {
    actions.push(iconeBtn(a.epingle ? "Retirer de la une" : "Mettre à la une", SVG_EPINGLE, () => epingler(a)));
    actions.push(iconeBtn("Supprimer", SVG_SUPPR, () => supprimer(a), true));
  }
  return el("a", { class: "article", ...attributsLien(a) },
    vignette(a, "article-image"),
    el("div", { class: "article-corps" },
      el("span", { class: "article-theme" }, a.categorie, a.epingle ? el("span", { class: "epingle" }, "📌") : null),
      el("h4", { class: "article-titre" }, a.titre),
      el("div", { class: "article-bas" },
        el("span", { class: "article-infos" }, `${a.source} · ${dateCourte(a.date)}`),
        el("div", { class: "article-actions" }, actions))));
}

function etatVide(texte, avecBouton = false) {
  return el("div", { class: "vide-etat" }, el("p", {}, texte),
    avecBouton ? el("button", { class: "btn-secondaire", "data-aller": "ajouter", type: "button" }, "＋ Publier") : null);
}

function afficherArticles() {
  const tous = etat.articles;
  const une = tous.find((a) => a.epingle) || tous[0];
  $("#une").replaceChildren(une
    ? el("a", { class: "une", ...attributsLien(une) },
        vignette(une, "une-img"),
        el("div", { class: "une-corps" },
          el("span", { class: "article-theme" }, une.categorie),
          el("h4", {}, une.titre),
          une.resume ? el("p", {}, une.resume) : null))
    : etatVide("Aucune actualité pour l'instant.", Boolean(codeEditeur())));
  // Nouveautés (au-dessus du programme) : la une + les 3 suivantes, pour que le programme reste visible juste après.
  $("#derniers").replaceChildren(...tous.filter((a) => a !== une).slice(0, 3).map(carte));
  // Rien de publié : la section est cachée aux visiteurs (l'équipe garde le bouton « Publier »).
  $("#bloc-nouveautes").hidden = !tous.length && !codeEditeur();

  $("#rubrique-titre").textContent = etat.filtre === "Tous" ? "Toute l'actualité" : etat.filtre;
  const q = etat.recherche.toLowerCase();
  const filtres = tous.filter((a) =>
    (etat.filtre === "Tous" || a.categorie === etat.filtre) &&
    (!q || `${a.titre} ${a.resume} ${a.texte || ""} ${a.source}`.toLowerCase().includes(q)));
  $("#compteur").textContent = `${filtres.length} publication${filtres.length > 1 ? "s" : ""}`;
  $("#liste-articles").replaceChildren(...(filtres.length ? filtres.map(carte)
    : [etatVide(tous.length ? "Rien dans cette rubrique pour l'instant." : "Aucune actualité pour l'instant.", Boolean(codeEditeur()))]));

  const sel = $("#champ-categorie");
  if (sel.options.length !== etat.categories.length) sel.replaceChildren(...etat.categories.map((c) => el("option", { value: c }, c)));
  if ($("#rubriques").children.length !== etat.categories.length + 4) construireRubriques();
  if (etat.page === "lire") afficherLecture();
  construireMenu();
}
$("#recherche").addEventListener("input", (e) => { etat.recherche = e.target.value; afficherArticles(); });

function ouvrirLecture(id) { etat.lecture = id; afficherLecture(); aller("lire"); }

function afficherLecture() {
  const a = etat.articles.find((x) => x.id === etat.lecture);
  if (!a) {
    $("#lecture").replaceChildren(etatVide(etat.articles.length ? "Cette publication n'existe plus." : "Chargement…"));
    return;
  }
  remplir($("#lecture"),
    el("button", { class: "lien-btn retour", type: "button", onclick: () => (history.length > 1 ? history.back() : aller("accueil")) }, "← Retour"),
    a.image ? el("img", { class: "photo-large", src: a.image, alt: "", referrerpolicy: "no-referrer" }) : null,
    el("span", { class: "article-theme" }, a.categorie),
    el("h2", { class: "lecture-titre" }, a.titre),
    el("p", { class: "lecture-infos" }, `${a.source} · ${dateCourte(a.date)}`),
    el("div", { class: "texte-long lecture-texte" }, paragraphes(a.texte || a.resume)),
    a.url ? el("a", { class: "btn-secondaire large lien-bouton", href: a.url, target: "_blank", rel: "noopener noreferrer" }, "Lire l'article complet ↗") : null,
    el("button", { class: "btn-secondaire large", type: "button", onclick: () => partager(a.titre, lienPartage(a)) }, "🔗 Partager"));
}

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
    toast("Publication supprimée");
    chargerArticles();
  } catch (e) { erreurEditeur(e); }
}

function erreurEditeur(e) {
  if (e.statut === 401) { deconnecter(); majModeEditeur(); afficherArticles(); }
  toast(e.message);
}

// ── Publier ──────────────────────────────────────────────────
let apercuActuel = null;
const photoPublication = choixPhoto($("#champ-photo"));

function extraireLien(texte) {
  const m = String(texte || "").match(/https?:\/\/[^\s<>"']+/i);
  return m ? m[0].replace(/[).,;!?]+$/, "") : "";
}

async function chargerApercu() {
  const lien = extraireLien($("#champ-lien").value);
  const boite = $("#apercu");
  if (!lien) { boite.hidden = true; apercuActuel = null; return; }
  if (apercuActuel?.url === lien) return;
  $("#champ-lien").value = lien;
  boite.hidden = false;
  boite.className = "apercu chargement";
  boite.replaceChildren(el("div", {}, "Recherche des informations de l'article…"));
  try {
    const r = await fetch(`/api/apercu?url=${encodeURIComponent(lien)}`);
    apercuActuel = await r.json();
    if (!r.ok) throw new Error(apercuActuel.erreur);
  } catch {
    apercuActuel = { url: lien, titre: "", resume: "", image: "", source: new URL(lien).hostname };
  }
  boite.className = "apercu";
  boite.replaceChildren(
    apercuActuel.image ? el("img", { src: apercuActuel.image, alt: "", referrerpolicy: "no-referrer", onerror: (e) => e.target.remove() }) : "",
    el("div", {}, apercuActuel.titre ? `${apercuActuel.source} — ${apercuActuel.resume || "aperçu prêt"}` : "Pas d'aperçu automatique pour ce site : écris le titre toi-même."));
  if (apercuActuel.titre && !$("#champ-titre").value) $("#champ-titre").value = apercuActuel.titre;
  if (!$("#champ-titre").value) $("#champ-titre").focus();
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
  const erreur = (t) => { msg.className = "message erreur"; msg.textContent = t; };
  msg.className = "message";
  msg.textContent = "";
  await chargerApercu();
  const texte = $("#champ-texte").value.trim();
  if (!apercuActuel && !texte && !photoPublication.valeur) return erreur("Ajoute un lien, une photo ou un texte.");
  if (!$("#champ-titre").value.trim()) { $("#champ-titre").focus(); return erreur("Donne un titre à la publication."); }
  if (!demanderCode()) { $("#champ-code").focus(); return erreur("Entre le code éditeur."); }

  const btn = $("#btn-publier");
  btn.disabled = true;
  btn.textContent = "Publication…";
  try {
    await api("/api/articles", {
      method: "POST",
      body: JSON.stringify({
        ...(apercuActuel || {}),
        titre: $("#champ-titre").value,
        categorie: $("#champ-categorie").value,
        texte,
        image: photoPublication.valeur || apercuActuel?.image || "",
      }),
    });
    $("#form-ajout").reset();
    photoPublication.valeur = "";
    $("#apercu").hidden = true;
    apercuActuel = null;
    majModeEditeur();
    toast("Publié ! 🎉");
    await chargerArticles();
    aller("accueil");
  } catch (err) {
    if (err.statut === 401) { deconnecter(); majModeEditeur(); }
    erreur(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Publier";
  }
});

// ── Programme ────────────────────────────────────────────────
async function chargerProgramme() {
  const cache = lire(CLE_PROGRAMME);
  if (cache) { try { programme = JSON.parse(cache); afficherProgramme(); } catch {} }
  try {
    programme = (await api("/api/programme")).programme;
    stocker(CLE_PROGRAMME, JSON.stringify(programme));
  } catch {}
  afficherProgramme();
}

function ouvrirAxe(id) {
  aller("programme");
  const d = document.getElementById(`axe-${id}`);
  if (d) { d.open = true; setTimeout(() => d.scrollIntoView({ behavior: "smooth", block: "start" }), 50); }
}

function afficherProgramme() {
  const p = programme;
  const vide = !p.axes.length && !p.intro;

  // Bannière d'accueil (la photo de couverture passe en fond si elle existe)
  if (p.slogan) $("#banniere-slogan").textContent = p.slogan;
  if (p.intro) {
    const ligne = p.intro.split("\n")[0];
    $("#banniere-texte").textContent = ligne.length > 180 ? `${ligne.slice(0, 180)}…` : ligne;
  }
  $("#banniere").classList.toggle("avec-photo", Boolean(p.photo));
  $("#banniere").style.backgroundImage = p.photo ? `linear-gradient(180deg, rgba(0,36,106,.45), rgba(0,36,106,.92)), url("${p.photo}")` : "";
  for (const id of ["#btn-rejoindre-accueil", "#btn-rejoindre-programme", "#btn-rejoindre-entete", "#btn-rejoindre-asso"]) {
    $(id).hidden = !p.lienAdhesion;
    if (p.lienAdhesion) $(id).href = p.lienAdhesion;
  }

  // Tuiles des axes sur l'accueil
  $("#axes-accueil").replaceChildren(...(p.axes.length
    ? p.axes.map((a) => el("button", { class: `axe-tuile${a.photo ? " avec-photo" : ""}`, type: "button", onclick: () => ouvrirAxe(a.id) },
        a.photo ? el("img", { class: "axe-tuile-photo", src: a.photo, alt: "", loading: "lazy" }) : el("span", { class: "axe-tuile-icone", "aria-hidden": "true" }, a.icone || "🔹"),
        el("span", { class: "axe-tuile-titre" }, a.titre),
        el("span", { class: "axe-tuile-nb" }, a.propositions.length ? `${a.propositions.length} proposition${a.propositions.length > 1 ? "s" : ""}` : "Lire →")))
    : [el("div", { class: "vide-etat" },
        el("p", {}, peutModifierProgramme() ? "Le programme n'est pas encore rédigé." : "Notre programme arrive très bientôt !"),
        peutModifierProgramme() ? el("button", { class: "btn-secondaire", type: "button", onclick: () => { aller("programme"); ouvrirEdition(); } }, "✏️ Rédiger le programme") : null)]));

  // Page programme
  $("#programme-photo").hidden = !p.photo;
  if (p.photo) $("#programme-photo").src = p.photo;
  $("#programme-slogan").textContent = p.slogan || "Notre programme";
  $("#programme-intro").replaceChildren(...(vide ? [el("p", {}, "Notre programme est en cours de rédaction. Reviens très vite !")] : paragraphes(p.intro)));
  $("#programme-maj").textContent = p.maj ? `Mis à jour le ${new Date(p.maj).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })}` : "";
  $("#programme-axes").replaceChildren(...p.axes.map((a, i) => el("details", { class: "axe", id: `axe-${a.id}` },
    el("summary", {},
      el("span", { class: "axe-num", "aria-hidden": "true" }, a.icone || String(i + 1)),
      el("span", { class: "axe-titre" }, a.titre),
      svgIcone('<path d="m6 9 6 6 6-6"/>', "axe-fleche")),
    el("div", { class: "axe-corps" },
      a.photo ? el("img", { class: "photo-large", src: a.photo, alt: "", loading: "lazy" }) : null,
      el("div", { class: "texte-long" }, paragraphes(a.resume)),
      a.propositions.length ? el("ul", {}, a.propositions.map((x) => el("li", {}, x))) : null,
      peutModifierProgramme() ? el("button", { type: "button", class: "btn-secondaire large", onclick: () => ouvrirEdition(a.id) }, "✏️ Modifier cet axe") : null))));
  $("#btn-modifier-programme").hidden = !peutModifierProgramme();
  construireMenu();
}

$("#btn-partager-programme").addEventListener("click", () => partager("Le programme de Nouvel Élan", `${location.origin}/#programme`));

// Édition du programme (mode éditeur)
let photoCouverture = null;
const photosAxes = new WeakMap();

function blocAxe(a = { icone: "", titre: "", photo: "", resume: "", propositions: [] }) {
  const zonePhoto = el("div", { class: "choix-photo" });
  const bloc = el("div", { class: "ed-axe" },
    el("div", { class: "ed-axe-tete" },
      el("input", { type: "text", class: "ed-icone", placeholder: "🎓", "aria-label": "Icône (emoji)", value: a.icone || "" }),
      el("strong", { class: "ed-num" })),
    el("label", { class: "etiquette" }, "Titre de l'axe",
      el("input", { type: "text", class: "ed-titre", placeholder: "Ex. : Éducation", value: a.titre || "" })),
    el("span", { class: "etiquette" }, "Photo de l'axe (facultatif)"), zonePhoto,
    el("label", { class: "etiquette" }, "Présentation",
      el("textarea", { class: "ed-resume auto", rows: "3", placeholder: "Notre vision sur ce sujet…" })),
    el("label", { class: "etiquette" }, "Propositions (une par ligne)",
      el("textarea", { class: "ed-props auto", rows: "4", placeholder: "Première proposition\nDeuxième proposition" })),
    el("div", { class: "ed-boutons" },
      el("button", { type: "button", onclick: () => { bloc.previousElementSibling?.before(bloc); numeroter(); } }, "↑ Monter"),
      el("button", { type: "button", onclick: () => { bloc.nextElementSibling?.after(bloc); numeroter(); } }, "↓ Descendre"),
      el("button", { type: "button", class: "danger", onclick: () => { if (confirm("Supprimer cet axe ?")) { bloc.remove(); numeroter(); } } }, "Supprimer")));
  bloc.querySelector(".ed-resume").value = a.resume || "";
  bloc.querySelector(".ed-props").value = (a.propositions || []).join("\n");
  bloc.dataset.id = a.id || "";
  photosAxes.set(bloc, choixPhoto(zonePhoto, a.photo || ""));
  return bloc;
}
function numeroter() { document.querySelectorAll("#ed-axes .ed-num").forEach((n, i) => (n.textContent = `Axe ${i + 1}`)); }

function ouvrirEdition(axeId) {
  $("#ed-slogan").value = programme.slogan || "";
  $("#ed-intro").value = programme.intro || "";
  $("#ed-adhesion").value = programme.lienAdhesion || "";
  photoCouverture = choixPhoto($("#ed-photo"), programme.photo || "");
  $("#ed-axes").replaceChildren(...(programme.axes.length ? programme.axes : [undefined]).map((a) => blocAxe(a)));
  numeroter();
  $("#ed-message").textContent = "";
  $("#programme-lecture").hidden = true;
  $("#programme-edition").hidden = false;
  ajusterTextes($("#programme-edition"));
  window.scrollTo(0, 0);
  const cible = axeId && [...document.querySelectorAll("#ed-axes .ed-axe")].find((b) => b.dataset.id === axeId);
  if (cible) setTimeout(() => { cible.scrollIntoView({ block: "start" }); window.scrollBy(0, -150); cible.querySelector(".ed-titre").focus({ preventScroll: true }); }, 50);
}
function fermerEdition() { $("#programme-edition").hidden = true; $("#programme-lecture").hidden = false; }

$("#btn-modifier-programme").addEventListener("click", ouvrirEdition);
$("#ed-annuler").addEventListener("click", () => { fermerEdition(); window.scrollTo(0, 0); });
$("#ed-ajouter-axe").addEventListener("click", () => {
  const b = blocAxe(); $("#ed-axes").append(b); numeroter(); b.querySelector(".ed-titre").focus();
});

$("#programme-edition").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#ed-message");
  const axes = [...document.querySelectorAll("#ed-axes .ed-axe")].map((b, i) => ({
    id: b.dataset.id || `axe-${Date.now().toString(36)}-${i}`,
    icone: b.querySelector(".ed-icone").value.trim(),
    titre: b.querySelector(".ed-titre").value.trim(),
    photo: photosAxes.get(b)?.valeur || "",
    resume: b.querySelector(".ed-resume").value.trim(),
    propositions: b.querySelector(".ed-props").value.split("\n").map((x) => x.replace(/^\s*[-•*–]\s*/, "").trim()).filter(Boolean),
  })).filter((a) => a.titre || a.resume || a.propositions.length || a.photo);
  const sansTitre = axes.findIndex((a) => !a.titre);
  if (sansTitre >= 0) { msg.className = "message erreur"; msg.textContent = `Donne un titre à l'axe ${sansTitre + 1}.`; return; }
  const btn = $("#ed-enregistrer");
  btn.disabled = true; btn.textContent = "Enregistrement…";
  try {
    const d = await api("/api/programme", { method: "PUT", body: JSON.stringify({
      slogan: $("#ed-slogan").value, intro: $("#ed-intro").value, photo: photoCouverture?.valeur || "",
      lienAdhesion: $("#ed-adhesion").value.trim(), axes }) });
    programme = d.programme;
    stocker(CLE_PROGRAMME, JSON.stringify(programme));
    afficherProgramme();
    fermerEdition();
    window.scrollTo(0, 0);
    toast("Programme enregistré ✅");
  } catch (err) {
    if (err.statut === 401) { deconnecter(); majModeEditeur(); }
    msg.className = "message erreur"; msg.textContent = err.message;
  } finally { btn.disabled = false; btn.textContent = "Enregistrer le programme"; }
});

// ── Menu complet ─────────────────────────────────────────────
let invitationInstall = null;
const estIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
const installee = matchMedia("(display-mode: standalone)").matches || navigator.standalone;

function ligneMenu(icone, texte, action, lien) {
  const contenu = [el("span", { class: "menu-icone", "aria-hidden": "true" }, icone), el("span", { class: "menu-texte" }, texte),
    el("span", { class: "menu-fleche", "aria-hidden": "true" }, lien ? "↗" : "›")];
  return lien
    ? el("a", { class: "menu-ligne", href: lien, target: "_blank", rel: "noopener noreferrer" }, contenu)
    : el("button", { class: "menu-ligne", type: "button", onclick: action }, contenu);
}

function construireMenu() {
  const p = programme;
  const sections = [
    ["Le programme", [
      ligneMenu("🚩", "Le programme complet", () => aller("programme")),
      ...p.axes.map((a, i) => ligneMenu(a.icone || String(i + 1), a.titre, () => ouvrirAxe(a.id))),
    ]],
    ["L'actualité", [
      ligneMenu("📰", "Toute l'actualité", () => allerRubrique("Tous")),
      ...etat.categories.map((c) => ligneMenu("•", c, () => allerRubrique(c))),
    ]],
    ["Le mouvement", [
      ligneMenu("👥", "Qui sommes-nous", () => aller("asso")),
      p.lienAdhesion ? ligneMenu("✊", "Nous rejoindre", null, p.lienAdhesion) : null,
      ...ASSOCIATION.reseaux.map((r) => ligneMenu(r.icone, r.nom, null, r.lien)),
    ]],
    ["L'application", [
      invitationInstall ? ligneMenu("📲", "Installer l'application", installer) : null,
      estIOS && !installee ? el("p", { class: "aide petite menu-aide" }, "Sur iPhone : Partager → « Sur l'écran d'accueil » pour installer l'application.") : null,
      ligneMenu("🔗", "Partager l'application", () => partager("Nouvel Élan", location.origin)),
      codeEditeur() && qui().nom ? el("p", { class: "aide petite menu-aide" }, `✅ Connecté en mode éditeur : ${qui().nom}`) : null,
      ligneMenu("✏️", codeEditeur() ? "Quitter le mode éditeur" : "Mode éditeur (équipe)", basculerEditeur),
    ]],
  ];
  $("#menu-contenu").replaceChildren(...sections.map(([titre, lignes]) =>
    el("div", { class: "menu-section" }, el("h3", { class: "section-titre" }, titre), el("div", { class: "menu-groupe" }, lignes))));
}

async function basculerEditeur() {
  if (codeEditeur()) { deconnecter(); toast("Mode éditeur désactivé"); }
  else {
    const code = prompt("Code éditeur :");
    if (!code) return;
    try {
      const d = await connecter(code.trim());
      toast(d.programme ? "Mode éditeur activé : tu peux publier et modifier le programme" : `Bienvenue (${d.nom}) : tu peux publier`);
    } catch (e) { toast(e.message); }
  }
  majModeEditeur();
  afficherArticles();
  afficherProgramme();
}

function majModeEditeur() {
  $("#btn-modifier-programme").hidden = !peutModifierProgramme();
  // Le bouton « Publier » n'apparaît que pour l'équipe : les visiteurs voient d'abord le programme.
  $(".barre-plus").hidden = !codeEditeur();
  $("#equipe-accueil").hidden = !codeEditeur();
  $("#equipe-programme").hidden = !codeEditeur();
  majBlocCode();
  construireMenu();
}

async function installer() {
  if (!invitationInstall) return;
  invitationInstall.prompt();
  await invitationInstall.userChoice;
  invitationInstall = null;
  construireMenu();
}
window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); invitationInstall = e; construireMenu(); });

// ── Qui sommes-nous ──────────────────────────────────────────
$("#asso-description").textContent = ASSOCIATION.description;
$("#reseaux").replaceChildren(...ASSOCIATION.reseaux.map((r) =>
  el("a", { class: "ligne-lien", href: r.lien, target: "_blank", rel: "noopener noreferrer" }, el("span", {}, r.icone), r.nom)));

// ── Démarrage ────────────────────────────────────────────────
// Lien partagé vers l'application (menu « Partager » du téléphone) ou lien du type /?ajouter=https://…
const params = new URLSearchParams(location.search);
const lienRecu = extraireLien(params.get("ajouter") || params.get("url") || params.get("text") || params.get("title"));
construireRubriques();
majModeEditeur();
// Code enregistré avant les liens d'accès : on redemande au serveur qui c'est (et ses droits).
if (codeEditeur() && !location.hash.startsWith("#acces=")) connecter(codeEditeur()).then(() => { majModeEditeur(); afficherProgramme(); }).catch(() => majModeEditeur());
if (lienRecu) {
  history.replaceState(null, "", "/#ajouter");
  aller("ajouter", { historique: false });
  $("#champ-lien").value = lienRecu;
  chargerArticles().then(chargerApercu);
} else {
  routeDepuisHash();
  chargerArticles();
}
chargerProgramme();

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
