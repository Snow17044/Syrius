// Mini-moteur Markdown SÛR : il construit des éléments DOM avec textContent,
// sans jamais utiliser innerHTML. Aucun HTML venant d'un message (ou d'un email
// cité par l'IA) ne peut donc s'exécuter dans l'app.
"use strict";

(function () {
  function safeUrl(url) {
    try {
      const u = new URL(url, location.origin);
      return (u.protocol === "https:" || u.protocol === "http:" || u.protocol === "mailto:") ? u.href : null;
    } catch (_) { return null; }
  }

  // Éléments en ligne : `code`, **gras**, *italique*, [lien](url), URL nues.
  const INLINE = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(\*[^*\n]+\*)|(\[[^\]\n]+\]\([^)\s]+\))|(https?:\/\/[^\s<>()]+[^\s<>().,;:!?'"])/;

  function inline(parent, text) {
    while (text) {
      const m = INLINE.exec(text);
      if (!m) { parent.appendChild(document.createTextNode(text)); return; }
      if (m.index > 0) parent.appendChild(document.createTextNode(text.slice(0, m.index)));
      const tok = m[0];
      let el;
      if (m[1]) { el = document.createElement("code"); el.textContent = tok.slice(1, -1); }
      else if (m[2]) { el = document.createElement("strong"); inline(el, tok.slice(2, -2)); }
      else if (m[3]) { el = document.createElement("em"); inline(el, tok.slice(1, -1)); }
      else {
        let label = tok, href = tok;
        if (m[4]) { const i = tok.indexOf("]("); label = tok.slice(1, i); href = tok.slice(i + 2, -1); }
        const url = safeUrl(href);
        if (url) {
          el = document.createElement("a");
          el.href = url; el.target = "_blank"; el.rel = "noopener noreferrer nofollow";
          el.textContent = label;
        } else { el = document.createTextNode(label); }
      }
      parent.appendChild(el);
      text = text.slice(m.index + tok.length);
    }
  }

  function render(target, src) {
    target.replaceChildren();
    const lines = String(src || "").replace(/\r/g, "").split("\n");
    let i = 0, para = [], list = null;

    const flushPara = () => {
      if (!para.length) return;
      const p = document.createElement("p");
      para.forEach((l, k) => { if (k) p.appendChild(document.createElement("br")); inline(p, l); });
      target.appendChild(p); para = [];
    };
    const closeList = () => { list = null; };

    while (i < lines.length) {
      const line = lines[i];
      if (/^```/.test(line)) {
        flushPara(); closeList();
        const code = [];
        i++;
        while (i < lines.length && !/^```/.test(lines[i])) code.push(lines[i++]);
        i++;
        const pre = document.createElement("pre"), c = document.createElement("code");
        c.textContent = code.join("\n"); pre.appendChild(c); target.appendChild(pre);
        continue;
      }
      const h = /^(#{1,4})\s+(.*)$/.exec(line);
      const ul = /^\s*[-*•]\s+(.*)$/.exec(line);
      const ol = /^\s*\d+[.)]\s+(.*)$/.exec(line);
      if (h) {
        flushPara(); closeList();
        const el = document.createElement(h[1].length <= 2 ? "h3" : "h4");
        inline(el, h[2]); target.appendChild(el);
      } else if (ul || ol) {
        flushPara();
        const tag = ul ? "UL" : "OL";
        if (!list || list.tagName !== tag) { list = document.createElement(tag); target.appendChild(list); }
        const li = document.createElement("li"); inline(li, (ul || ol)[1]); list.appendChild(li);
      } else if (!line.trim()) {
        flushPara(); closeList();
      } else {
        closeList(); para.push(line);
      }
      i++;
    }
    flushPara();
  }

  window.SyriusMarkdown = { render };
})();
