// Page de commande en ligne
(function () {
  const $ = (s) => document.querySelector(s);
  const euro = (c) => (c / 100).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
  const frDate = (iso) => new Date(iso + 'T12:00:00').toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });

  // Menu mobile
  const header = $('.site-header');
  const toggle = $('.nav-toggle');
  toggle.addEventListener('click', () => {
    const open = header.classList.toggle('open');
    toggle.setAttribute('aria-expanded', String(open));
  });

  const KEY = 'kb_panier';
  let products = [];
  let shop = {};
  let cart = {};
  try { cart = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch { cart = {}; }
  const saveCart = () => { try { localStorage.setItem(KEY, JSON.stringify(cart)); } catch {} };

  async function load() {
    try {
      const r = await fetch('/api/catalogue');
      if (!r.ok) throw new Error();
      ({ products, shop } = await r.json());
    } catch {
      $('#catalog').innerHTML = '<p class="loading">Impossible de charger la carte pour le moment. Merci de réessayer un peu plus tard.</p>';
      return;
    }
    // retire du panier les articles qui ne sont plus proposés
    const ids = new Set(products.map((p) => String(p.id)));
    for (const k of Object.keys(cart)) if (!ids.has(k)) delete cart[k];
    renderCatalog();
    setupForm();
    renderCart();
  }

  function renderCatalog() {
    if (!shop.orders_open) {
      $('#catalog').innerHTML = `<div class="closed panel"><h2>Commandes fermées</h2><p>${esc(shop.closed_message)}</p></div>`;
      $('#order-form').hidden = true;
      document.querySelector('.order-cart').hidden = true;
      return;
    }
    if (!products.length) {
      $('#catalog').innerHTML = '<p class="loading">La carte est en cours de préparation. Revenez bientôt !</p>';
      return;
    }
    const groups = new Map();
    for (const p of products) {
      if (!groups.has(p.category)) groups.set(p.category, []);
      groups.get(p.category).push(p);
    }
    let html = '';
    for (const [cat, list] of groups) {
      html += `<section class="cat"><h2 class="cat-title">${esc(cat)}</h2><div class="prod-list">`;
      for (const p of list) {
        html += `
          <article class="prod" data-id="${p.id}">
            <div class="prod-info">
              <h3>${esc(p.name)} ${p.unit ? `<span class="unit">${esc(p.unit)}</span>` : ''}</h3>
              ${p.description ? `<p>${esc(p.description)}</p>` : ''}
            </div>
            <div class="prod-buy">
              <span class="price">${euro(p.price_cents)}</span>
              <div class="stepper" role="group" aria-label="Quantité de ${esc(p.name)} ${esc(p.unit)}">
                <button type="button" data-step="-1" aria-label="Retirer un">−</button>
                <output data-qty>0</output>
                <button type="button" data-step="1" aria-label="Ajouter un">+</button>
              </div>
            </div>
          </article>`;
      }
      html += '</div></section>';
    }
    $('#catalog').innerHTML = html;
    $('#catalog').addEventListener('click', (e) => {
      const btn = e.target.closest('[data-step]');
      if (!btn) return;
      const id = btn.closest('.prod').dataset.id;
      const next = Math.max(0, Math.min(50, (cart[id] || 0) + Number(btn.dataset.step)));
      if (next) cart[id] = next; else delete cart[id];
      saveCart();
      renderCart();
    });
  }

  function cartLines() {
    return products.filter((p) => cart[p.id]).map((p) => ({ ...p, qty: cart[p.id] }));
  }

  function renderCart() {
    const lines = cartLines();
    const total = lines.reduce((s, l) => s + l.qty * l.price_cents, 0);
    const count = lines.reduce((s, l) => s + l.qty, 0);
    $('#cart-lines').innerHTML = lines.map((l) => `
      <li><span class="q">${l.qty}×</span><span class="n">${esc(l.name)}${l.unit ? ` <small>${esc(l.unit)}</small>` : ''}</span><span class="p">${euro(l.qty * l.price_cents)}</span></li>`).join('');
    $('#cart-empty').hidden = lines.length > 0;
    $('#cart-total').textContent = euro(total);
    $('#cart-go').hidden = !lines.length;
    $('#bar-count').textContent = count;
    $('#bar-total').textContent = euro(total);
    $('#cart-bar').hidden = !lines.length || !shop.orders_open;
    document.querySelectorAll('.prod').forEach((el) => {
      const q = cart[el.dataset.id] || 0;
      el.querySelector('[data-qty]').textContent = q;
      el.classList.toggle('in-cart', q > 0);
    });
  }

  function setupForm() {
    if (shop.notice) { $('#shop-notice').textContent = shop.notice; $('#shop-notice').hidden = false; }
    const date = $('#f-date');
    date.min = shop.min_date;
    date.max = shop.max_date;
    $('#date-hint').textContent = shop.lead_days > 0
      ? `Au plus tôt le ${frDate(shop.min_date)} (${shop.lead_days} jour${shop.lead_days > 1 ? 's' : ''} de préparation).`
      : '';
    if (shop.slots?.length) {
      $('#f-slot').innerHTML = '<option value="">Choisir…</option>' + shop.slots.map((s) => `<option>${esc(s)}</option>`).join('');
    } else {
      $('#slot-field').hidden = true;
    }
    if (shop.delivery) {
      $('#mode-field').hidden = false;
      $('#mode-field').addEventListener('change', () => {
        const liv = $('#order-form').mode.value === 'livraison';
        $('#address-field').hidden = !liv;
        $('#f-address').required = liv;
      });
    }
  }

  const status = $('#form-status');
  const fail = (msg, el) => {
    status.textContent = msg;
    status.className = 'form-status err';
    if (el) el.focus();
  };

  $('#order-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target;
    const lines = cartLines();
    if (!lines.length) return fail('Votre panier est vide : ajoutez au moins une création.');
    if (!f.name.value.trim()) return fail('Merci d\'indiquer votre nom.', f.name);
    if (f.phone.value.replace(/\D/g, '').length < 9) return fail('Merci d\'indiquer un numéro de téléphone valide.', f.phone);
    if (!f.date.value) return fail('Merci de choisir une date.', f.date);
    if (f.date.value < shop.min_date) return fail(`La date doit être au plus tôt le ${frDate(shop.min_date)}.`, f.date);
    if (shop.slots?.length && !f.slot.value) return fail('Merci de choisir un créneau.', f.slot);
    const mode = shop.delivery ? f.mode.value : 'retrait';
    if (mode === 'livraison' && !f.address.value.trim()) return fail('Merci d\'indiquer l\'adresse de livraison.', f.address);
    if (!$('#f-consent').checked) return fail('Merci de cocher la case d\'acceptation.', $('#f-consent'));

    const btn = $('#submit-btn');
    btn.disabled = true;
    btn.textContent = 'Envoi en cours…';
    status.textContent = '';
    try {
      const r = await fetch('/api/commandes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: f.name.value, phone: f.phone.value, email: f.email.value,
          date: f.date.value, slot: f.slot.value, mode, address: f.address.value,
          message: f.message.value, website: f.website.value,
          items: lines.map((l) => ({ id: l.id, qty: l.qty })),
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.error || 'Une erreur est survenue.');
      showConfirmation(data);
    } catch (err) {
      fail(err.message || 'Connexion impossible. Merci de réessayer.');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Envoyer ma commande';
    }
  });

  function showConfirmation(o) {
    cart = {};
    saveCart();
    $('#order-layout').hidden = true;
    $('#cart-bar').hidden = true;
    $('#confirm-code').textContent = o.code;
    $('#confirm-recap').innerHTML = `
      <ul class="cart-lines recap">${o.items.map((i) => `<li><span class="q">${i.qty}×</span><span class="n">${esc(i.name)}${i.unit ? ` <small>${esc(i.unit)}</small>` : ''}</span><span class="p">${euro(i.qty * i.price_cents)}</span></li>`).join('')}</ul>
      <div class="cart-total"><span>Total</span><strong>${euro(o.total_cents)}</strong></div>
      <p><strong>${o.mode === 'livraison' ? 'Livraison' : 'Retrait'}</strong> le ${frDate(o.pickup_date)}${o.pickup_slot ? ' · ' + esc(o.pickup_slot) : ''}</p>`;
    $('#confirm-track').href = '/suivi?code=' + encodeURIComponent(o.code);
    const c = $('#confirmation');
    c.hidden = false;
    c.scrollIntoView({ behavior: 'smooth', block: 'start' });
    c.focus({ preventScroll: true });
  }

  load();
})();
