// Espace admin de Karine
(function () {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const euro = (c) => (c / 100).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
  const today = () => new Date().toLocaleDateString('en-CA');
  const addDays = (iso, n) => { const d = new Date(iso + 'T12:00:00'); d.setDate(d.getDate() + n); return d.toLocaleDateString('en-CA'); };
  const frDay = (iso) => {
    const s = new Date(iso + 'T12:00:00').toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
    return s.charAt(0).toUpperCase() + s.slice(1);
  };

  const STATUS = {
    nouvelle: 'Nouvelle',
    confirmee: 'Confirmée',
    en_preparation: 'En préparation',
    prete: 'Prête',
    terminee: 'Remise',
    annulee: 'Annulée',
  };
  const ACTIVE = ['nouvelle', 'confirmee', 'en_preparation', 'prete'];

  let orders = [];
  let products = [];
  let shop = {};
  let filter = 'active';
  let search = '';

  // ---------- Outils ----------
  async function api(action, { method = 'GET', body, params } = {}) {
    const qs = new URLSearchParams({ action, ...(params || {}) });
    const r = await fetch('/api/admin?' + qs, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
      credentials: 'same-origin',
    });
    const data = await r.json().catch(() => ({}));
    if (r.status === 401 && action !== 'login') { showLogin(); throw new Error(data.error || 'Session expirée.'); }
    if (!r.ok) throw new Error(data.error || 'Une erreur est survenue.');
    return data;
  }

  let toastTimer;
  function toast(msg, isErr) {
    const t = $('#toast');
    t.textContent = msg;
    t.className = 'toast show' + (isErr ? ' err' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.className = 'toast'), 2600);
  }

  // ---------- Photos : réduction dans le navigateur puis envoi ----------
  async function shrinkImage(file, max = 1600) {
    let src;
    try { src = await createImageBitmap(file, { imageOrientation: 'from-image' }); }
    catch {
      src = await new Promise((ok, ko) => {
        const img = new Image();
        img.onload = () => ok(img);
        img.onerror = () => ko(new Error('Impossible de lire cette photo (format non pris en charge).'));
        img.src = URL.createObjectURL(file);
      });
    }
    const w0 = src.width || src.naturalWidth, h0 = src.height || src.naturalHeight;
    const k = Math.min(1, max / Math.max(w0, h0));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(w0 * k);
    canvas.height = Math.round(h0 * k);
    canvas.getContext('2d').drawImage(src, 0, 0, canvas.width, canvas.height);
    const toBlob = (type, q) => new Promise((ok) => canvas.toBlob(ok, type, q));
    let blob = await toBlob('image/webp', 0.85);
    if (!blob || blob.type !== 'image/webp') blob = await toBlob('image/jpeg', 0.85);
    if (!blob) throw new Error('Impossible de préparer cette photo.');
    return blob;
  }

  async function uploadImage(action, params, file) {
    const blob = await shrinkImage(file);
    const r = await fetch('/api/admin?' + new URLSearchParams({ action, ...params }), {
      method: 'POST', headers: { 'Content-Type': blob.type }, body: blob, credentials: 'same-origin',
    });
    const data = await r.json().catch(() => ({}));
    if (r.status === 401) { showLogin(); throw new Error('Session expirée.'); }
    if (!r.ok) throw new Error(data.error || 'Envoi de la photo impossible.');
    return data;
  }

  // ---------- Connexion ----------
  function showLogin() {
    $('#app').hidden = true;
    $('#login').hidden = false;
    $('#l-pw').focus();
  }

  async function showApp() {
    $('#login').hidden = true;
    $('#app').hidden = false;
    await Promise.all([loadOrders(), loadProducts(), loadSettings(), loadPhotos()]);
  }

  $('#login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = $('button', e.target);
    btn.disabled = true;
    $('#l-status').textContent = '';
    try {
      await api('login', { method: 'POST', body: { password: $('#l-pw').value } });
      $('#l-pw').value = '';
      await showApp();
    } catch (err) {
      $('#l-status').textContent = err.message;
    } finally {
      btn.disabled = false;
    }
  });

  $('#logout').addEventListener('click', async () => {
    try { await api('logout', { method: 'POST' }); } catch {}
    showLogin();
  });

  // ---------- Onglets ----------
  $$('.tabs button').forEach((b) =>
    b.addEventListener('click', () => {
      $$('.tabs button').forEach((x) => x.setAttribute('aria-selected', String(x === b)));
      $$('.tab-panel').forEach((p) => (p.hidden = p.id !== 'tab-' + b.dataset.tab));
      if (b.dataset.tab === 'orders') loadOrders();
    })
  );

  // ---------- Commandes ----------
  async function loadOrders() {
    try {
      ({ orders } = await api('orders'));
      renderOrders();
    } catch (err) { toast(err.message, true); }
  }

  function renderStats() {
    const t = today();
    const week = addDays(t, 7);
    const month = t.slice(0, 7);
    const active = orders.filter((o) => ACTIVE.includes(o.status));
    const nNew = orders.filter((o) => o.status === 'nouvelle').length;
    const nToday = active.filter((o) => o.pickup_date === t).length;
    const nWeek = active.filter((o) => o.pickup_date >= t && o.pickup_date <= week).length;
    const sales = orders
      .filter((o) => o.status !== 'annulee' && o.pickup_date.slice(0, 7) === month)
      .reduce((s, o) => s + o.total_cents, 0);
    $('#stats').innerHTML = `
      <div class="stat ${nNew ? 'hl' : ''}"><div class="v">${nNew}</div><div class="l">Nouvelle${nNew > 1 ? 's' : ''} à confirmer</div></div>
      <div class="stat"><div class="v">${nToday}</div><div class="l">Pour aujourd'hui</div></div>
      <div class="stat"><div class="v">${nWeek}</div><div class="l">Dans les 7 jours</div></div>
      <div class="stat"><div class="v">${euro(sales)}</div><div class="l">Commandes du mois</div></div>`;
    const badge = $('#new-badge');
    badge.textContent = nNew;
    badge.hidden = !nNew;
  }

  function renderOrders() {
    renderStats();
    const t = today();
    const s = search.trim().toLowerCase();
    let list = orders.filter((o) => {
      if (filter === 'active' && !ACTIVE.includes(o.status)) return false;
      if (filter !== 'active' && filter !== 'all' && o.status !== filter) return false;
      if (s) {
        const hay = [o.code, o.customer_name, o.phone, o.email, o.message, ...o.items.map((i) => i.name)].join(' ').toLowerCase();
        if (!hay.includes(s)) return false;
      }
      return true;
    });
    const asc = filter === 'active' || filter === 'nouvelle';
    list.sort((a, b) => (asc ? 1 : -1) * (a.pickup_date.localeCompare(b.pickup_date) || a.id - b.id));

    if (!list.length) {
      $('#orders').innerHTML = `<div class="empty">${orders.length ? 'Aucune commande ne correspond.' : 'Aucune commande pour le moment. Elles apparaîtront ici dès qu\'un client commandera sur le site.'}</div>`;
      return;
    }
    const groups = new Map();
    for (const o of list) {
      if (!groups.has(o.pickup_date)) groups.set(o.pickup_date, []);
      groups.get(o.pickup_date).push(o);
    }
    let html = '';
    for (const [day, os] of groups) {
      const cls = day === t ? 'today' : day < t ? 'past' : '';
      const label = day === t ? 'Aujourd\'hui' : day === addDays(t, 1) ? 'Demain' : '';
      html += `<section class="day"><h2 class="day-title ${cls}">${frDay(day)} ${label ? `<small>${label}</small>` : ''}<small>· ${os.length} commande${os.length > 1 ? 's' : ''}</small></h2><div class="orders-grid">`;
      html += os.map(orderCard).join('');
      html += '</div></section>';
    }
    $('#orders').innerHTML = html;
  }

  function orderCard(o) {
    const created = new Date(o.created_at).toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    return `
      <article class="order" data-id="${o.id}" data-status="${o.status}">
        <div class="order-head">
          <div>
            <h3>${esc(o.customer_name)}</h3>
            <span class="code">${esc(o.code)}</span>${o.source === 'admin' ? '<span class="tag">saisie manuelle</span>' : ''}
          </div>
          <select class="status-select" data-status="${o.status}" aria-label="Statut">
            ${Object.entries(STATUS).map(([k, v]) => `<option value="${k}" ${k === o.status ? 'selected' : ''}>${v}</option>`).join('')}
          </select>
        </div>
        <div class="order-meta">
          ${o.phone ? `<a href="tel:${esc(o.phone.replace(/[^\d+]/g, ''))}">📞 ${esc(o.phone)}</a>` : ''}
          ${o.email ? `<a href="mailto:${esc(o.email)}">✉️ ${esc(o.email)}</a>` : ''}
          <span>${o.mode === 'livraison' ? '🚗 Livraison' : '🏠 Retrait'}${o.pickup_slot ? ' · ' + esc(o.pickup_slot) : ''}</span>
          ${o.address ? `<span>📍 ${esc(o.address)}</span>` : ''}
        </div>
        <ul class="order-items">
          ${o.items.map((i) => `<li><span><span class="q">${i.qty}×</span>${esc(i.name)}${i.unit ? ` <small class="muted">${esc(i.unit)}</small>` : ''}</span><span>${euro(i.qty * i.price_cents)}</span></li>`).join('')}
        </ul>
        <div class="order-total"><span>Total</span><span>${euro(o.total_cents)}</span></div>
        ${o.message ? `<p class="order-msg">${esc(o.message)}</p>` : ''}
        <details>
          <summary>Note, date, suppression${o.admin_note ? ' · 📝' : ''}</summary>
          <div class="field">
            <label>Note personnelle (non visible par le client)</label>
            <textarea rows="2" data-note maxlength="2000">${esc(o.admin_note)}</textarea>
          </div>
          <div class="field-row">
            <div class="field"><label>Date</label><input type="date" data-date value="${o.pickup_date}"></div>
            <div class="field"><label>Créneau</label><input data-slot value="${esc(o.pickup_slot)}" list="slot-list" maxlength="60"></div>
          </div>
          <div class="order-actions">
            <button class="btn btn-primary btn-sm" data-save>Enregistrer</button>
            <span class="grow"></span>
            <button class="link-btn danger" data-delete>Supprimer</button>
          </div>
          <p class="small muted">Reçue le ${created}</p>
        </details>
      </article>`;
  }

  async function patchOrder(id, changes, msg) {
    try {
      const { order } = await api('orders', { method: 'PATCH', body: { id, ...changes } });
      orders = orders.map((o) => (o.id === id ? order : o));
      renderOrders();
      toast(msg || 'Enregistré');
    } catch (err) { toast(err.message, true); renderOrders(); }
  }

  $('#orders').addEventListener('change', (e) => {
    const sel = e.target.closest('.status-select');
    if (!sel) return;
    const id = Number(sel.closest('.order').dataset.id);
    patchOrder(id, { status: sel.value }, 'Statut : ' + STATUS[sel.value]);
  });

  $('#orders').addEventListener('click', async (e) => {
    const card = e.target.closest('.order');
    if (!card) return;
    const id = Number(card.dataset.id);
    if (e.target.closest('[data-save]')) {
      patchOrder(id, {
        admin_note: $('[data-note]', card).value,
        pickup_date: $('[data-date]', card).value,
        pickup_slot: $('[data-slot]', card).value,
      });
    }
    if (e.target.closest('[data-delete]')) {
      const o = orders.find((x) => x.id === id);
      if (!confirm(`Supprimer définitivement la commande ${o.code} de ${o.customer_name} ?`)) return;
      try {
        await api('orders', { method: 'DELETE', params: { id } });
        orders = orders.filter((x) => x.id !== id);
        renderOrders();
        toast('Commande supprimée');
      } catch (err) { toast(err.message, true); }
    }
  });

  $('#filters').addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    filter = b.dataset.f;
    $$('#filters button').forEach((x) => x.classList.toggle('on', x === b));
    renderOrders();
  });
  $('#search').addEventListener('input', (e) => { search = e.target.value; renderOrders(); });

  // Rafraîchit les commandes toutes les 2 minutes quand l'onglet est visible
  setInterval(() => {
    if (!document.hidden && !$('#app').hidden && !$('#tab-orders').hidden && !$('.order details[open]') && !document.querySelector('dialog[open]')) loadOrders();
  }, 120000);

  // ---------- Nouvelle commande (saisie manuelle) ----------
  const od = $('#order-dialog');
  const of = $('#order-form');
  $('#o-status').innerHTML = Object.entries(STATUS).map(([k, v]) => `<option value="${k}" ${k === 'confirmee' ? 'selected' : ''}>${v}</option>`).join('');

  function productOptions() {
    return products.map((p) => `<option value="${p.id}">${esc(p.name)}${p.unit ? ' — ' + esc(p.unit) : ''} (${euro(p.price_cents)})${p.available ? '' : ' [indispo]'}</option>`).join('');
  }
  function addLine(custom) {
    const div = document.createElement('div');
    div.className = 'o-line' + (custom ? ' custom' : '');
    div.innerHTML = custom
      ? `<input placeholder="Article (ex. gâteau licorne 20 parts)" data-name maxlength="120" aria-label="Article"><input type="number" min="0" step="0.01" placeholder="Prix €" data-price aria-label="Prix unitaire"><input type="number" min="1" max="50" value="1" data-qty aria-label="Quantité"><button type="button" class="rm" aria-label="Retirer">×</button>`
      : `<select data-pid aria-label="Article">${productOptions()}</select><input type="number" min="1" max="50" value="1" data-qty aria-label="Quantité"><button type="button" class="rm" aria-label="Retirer">×</button>`;
    $('#o-lines').appendChild(div);
    updateTotal();
  }
  function updateTotal() {
    let total = 0;
    $$('#o-lines .o-line').forEach((l) => {
      const qty = Number($('[data-qty]', l).value) || 0;
      if (l.classList.contains('custom')) total += Math.round((Number($('[data-price]', l).value) || 0) * 100) * qty;
      else total += (products.find((p) => p.id === Number($('[data-pid]', l).value))?.price_cents || 0) * qty;
    });
    $('#o-total').textContent = euro(total);
  }
  $('#o-lines').addEventListener('input', updateTotal);
  $('#o-lines').addEventListener('click', (e) => { if (e.target.closest('.rm')) { e.target.closest('.o-line').remove(); updateTotal(); } });
  $('#o-add-product').addEventListener('click', () => addLine(false));
  $('#o-add-custom').addEventListener('click', () => addLine(true));
  $('#o-mode').addEventListener('change', () => ($('#o-address-field').hidden = $('#o-mode').value !== 'livraison'));

  $('#new-order').addEventListener('click', () => {
    of.reset();
    $('#o-lines').innerHTML = '';
    $('#o-status-msg').textContent = '';
    $('#o-address-field').hidden = true;
    $('#o-date').value = addDays(today(), 1);
    $('#slot-list').innerHTML = (shop.slots || []).map((s) => `<option value="${esc(s)}">`).join('');
    if (products.length) addLine(false); else addLine(true);
    od.showModal();
  });

  of.addEventListener('submit', async (e) => {
    e.preventDefault();
    const items = $$('#o-lines .o-line').map((l) => l.classList.contains('custom')
      ? { custom: true, name: $('[data-name]', l).value, price_cents: Math.round((Number($('[data-price]', l).value) || 0) * 100), qty: Number($('[data-qty]', l).value) }
      : { id: Number($('[data-pid]', l).value), qty: Number($('[data-qty]', l).value) });
    const f = of.elements;
    try {
      const { order } = await api('orders', {
        method: 'POST',
        body: {
          name: f.name.value, phone: f.phone.value, email: f.email.value, date: f.date.value, slot: f.slot.value,
          mode: f.mode.value, address: f.address.value, message: f.message.value, status: f.status.value, items,
        },
      });
      orders.push(order);
      od.close();
      renderOrders();
      toast('Commande ' + order.code + ' créée');
    } catch (err) {
      $('#o-status-msg').textContent = err.message;
    }
  });

  // ---------- Produits ----------
  async function loadProducts() {
    try {
      ({ products } = await api('products'));
      renderProducts();
    } catch (err) { toast(err.message, true); }
  }

  function renderProducts() {
    if (!products.length) {
      $('#products').innerHTML = '<div class="empty">Aucun produit. Ajoutez votre première création !</div>';
      return;
    }
    const groups = new Map();
    for (const p of products) {
      if (!groups.has(p.category)) groups.set(p.category, []);
      groups.get(p.category).push(p);
    }
    $('#products').innerHTML = [...groups].map(([cat, list]) => `
      <section class="prod-cat"><h2>${esc(cat)}</h2><div class="prod-rows">
        ${list.map((p) => `
          <div class="prod-row ${p.available ? '' : 'off'}" data-id="${p.id}">
            ${p.image_url ? `<img class="thumb" src="${esc(p.image_url)}" alt="" loading="lazy">` : '<span class="thumb none" aria-hidden="true">✿</span>'}
            <label class="switch" title="Disponible à la commande"><input type="checkbox" data-avail ${p.available ? 'checked' : ''} aria-label="Disponible : ${esc(p.name)}"><span></span></label>
            <div class="info"><strong>${esc(p.name)}</strong> ${p.unit ? `<small class="muted">${esc(p.unit)}</small>` : ''}<p>${esc(p.description)}</p></div>
            <span class="pr">${euro(p.price_cents)}</span>
            <button class="link-btn" data-edit>Modifier</button>
          </div>`).join('')}
      </div></section>`).join('');
    $('#cat-list').innerHTML = [...groups.keys()].map((c) => `<option value="${esc(c)}">`).join('');
  }

  $('#products').addEventListener('change', async (e) => {
    const cb = e.target.closest('[data-avail]');
    if (!cb) return;
    const p = products.find((x) => x.id === Number(cb.closest('.prod-row').dataset.id));
    try {
      const { product } = await api('products', { method: 'PATCH', body: { ...p, available: cb.checked } });
      products = products.map((x) => (x.id === product.id ? product : x));
      renderProducts();
      toast(product.available ? 'Produit disponible' : 'Produit masqué de la carte');
    } catch (err) { toast(err.message, true); renderProducts(); }
  });

  const pd = $('#product-dialog');
  const pf = $('#product-form');
  let editing = null;
  let pendingFile = null;
  let removePhoto = false;
  let previewUrl = null;
  function showPreview(url) {
    $('#pr-preview').innerHTML = url ? `<img src="${esc(url)}" alt="Photo du produit">` : '<span>Pas de photo</span>';
    $('#pr-photo-remove').hidden = !url;
  }
  $('#pr-file').addEventListener('change', (e) => {
    const f = e.target.files[0];
    if (!f) return;
    pendingFile = f;
    removePhoto = false;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(f);
    showPreview(previewUrl);
  });
  $('#pr-photo-remove').addEventListener('click', () => {
    pendingFile = null;
    removePhoto = true;
    $('#pr-file').value = '';
    showPreview('');
  });
  function openProduct(p) {
    editing = p;
    pendingFile = null;
    removePhoto = false;
    pf.reset();
    showPreview(p?.image_url || '');
    $('#pr-status').textContent = '';
    $('#product-title').textContent = p ? 'Modifier le produit' : 'Nouveau produit';
    $('#pr-delete').hidden = !p;
    const f = pf.elements;
    f.name.value = p?.name || '';
    f.category.value = p?.category || '';
    f.unit.value = p?.unit || '';
    f.description.value = p?.description || '';
    f.price.value = p ? (p.price_cents / 100).toFixed(2) : '';
    f.position.value = p ? p.position : (Math.max(0, ...products.map((x) => x.position)) + 10);
    f.available.checked = p ? p.available : true;
    pd.showModal();
  }
  $('#new-product').addEventListener('click', () => openProduct(null));
  $('#products').addEventListener('click', (e) => {
    if (!e.target.closest('[data-edit]')) return;
    openProduct(products.find((x) => x.id === Number(e.target.closest('.prod-row').dataset.id)));
  });

  pf.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = pf.elements;
    const body = {
      name: f.name.value, category: f.category.value, unit: f.unit.value, description: f.description.value,
      price_cents: Math.round(Number(String(f.price.value).replace(',', '.')) * 100),
      position: Number(f.position.value) || 0, available: f.available.checked,
    };
    const saveBtn = $('button[type=submit]', pf);
    saveBtn.disabled = true;
    try {
      let product;
      if (editing) ({ product } = await api('products', { method: 'PATCH', body: { id: editing.id, ...body } }));
      else ({ product } = await api('products', { method: 'POST', body }));
      if (pendingFile) {
        saveBtn.textContent = 'Envoi de la photo…';
        ({ product } = await uploadImage('product_image', { id: product.id }, pendingFile));
      } else if (removePhoto && product.image_url) {
        ({ product } = await api('product_image', { method: 'DELETE', params: { id: product.id } }));
      }
      if (products.some((x) => x.id === product.id)) products = products.map((x) => (x.id === product.id ? product : x));
      else products.push(product);
      products.sort((a, b) => a.position - b.position || a.id - b.id);
      pd.close();
      renderProducts();
      toast('Produit enregistré');
    } catch (err) {
      $('#pr-status').textContent = err.message;
      loadProducts();
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = 'Enregistrer';
    }
  });

  $('#pr-delete').addEventListener('click', async () => {
    if (!editing || !confirm(`Supprimer « ${editing.name} » de la carte ? (les commandes passées ne sont pas modifiées)`)) return;
    try {
      await api('products', { method: 'DELETE', params: { id: editing.id } });
      products = products.filter((x) => x.id !== editing.id);
      pd.close();
      renderProducts();
      toast('Produit supprimé');
    } catch (err) { $('#pr-status').textContent = err.message; }
  });

  $$('dialog [data-close]').forEach((b) => b.addEventListener('click', () => b.closest('dialog').close()));

  // ---------- Galerie ----------
  let photos = [];
  async function loadPhotos() {
    try {
      ({ photos } = await api('photos'));
      renderPhotos();
    } catch (err) { toast(err.message, true); }
  }
  function renderPhotos() {
    $('#photos').innerHTML = photos.length
      ? photos.map((ph) => `
        <figure class="photo-card" data-id="${ph.id}">
          <img src="${esc(ph.url)}" alt="${esc(ph.caption)}" loading="lazy">
          <div class="body">
            <input value="${esc(ph.caption)}" placeholder="Légende (facultatif)" maxlength="200" data-caption aria-label="Légende">
            <div class="row"><span class="small muted" data-saved></span><button class="link-btn danger" data-del>Supprimer</button></div>
          </div>
        </figure>`).join('')
      : '<div class="empty" style="grid-column:1/-1">Aucune photo pour l\'instant. Ajoutez vos plus belles créations : elles apparaîtront sur la page d\'accueil.</div>';
  }
  $('#gallery-input').addEventListener('change', async (e) => {
    const files = [...e.target.files];
    e.target.value = '';
    const prog = $('#gallery-progress');
    prog.hidden = false;
    let ok = 0;
    for (const [i, f] of files.entries()) {
      prog.textContent = `Envoi de la photo ${i + 1} sur ${files.length}…`;
      try {
        const { photo } = await uploadImage('photos', {}, f);
        photos.unshift(photo);
        renderPhotos();
        ok++;
      } catch (err) { toast(`${f.name} : ${err.message}`, true); }
    }
    prog.hidden = true;
    if (ok) toast(ok > 1 ? `${ok} photos ajoutées` : 'Photo ajoutée');
  });
  $('#photos').addEventListener('change', async (e) => {
    const input = e.target.closest('[data-caption]');
    if (!input) return;
    const card = input.closest('.photo-card');
    const id = Number(card.dataset.id);
    try {
      const { photo } = await api('photos', { method: 'PATCH', body: { id, caption: input.value } });
      photos = photos.map((x) => (x.id === id ? photo : x));
      $('[data-saved]', card).textContent = '✓ Enregistrée';
    } catch (err) { toast(err.message, true); }
  });
  $('#photos').addEventListener('click', async (e) => {
    if (!e.target.closest('[data-del]')) return;
    const id = Number(e.target.closest('.photo-card').dataset.id);
    if (!confirm('Supprimer cette photo de la galerie ?')) return;
    try {
      await api('photos', { method: 'DELETE', params: { id } });
      photos = photos.filter((x) => x.id !== id);
      renderPhotos();
      toast('Photo supprimée');
    } catch (err) { toast(err.message, true); }
  });

  // ---------- Réglages ----------
  async function loadSettings() {
    try {
      ({ shop } = await api('settings'));
      const f = $('#settings-form').elements;
      f.orders_open.checked = shop.orders_open;
      f.delivery.checked = shop.delivery;
      f.lead_days.value = shop.lead_days;
      f.slots.value = (shop.slots || []).join('\n');
      f.notice.value = shop.notice || '';
      f.closed_message.value = shop.closed_message || '';
    } catch (err) { toast(err.message, true); }
  }

  $('#settings-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target.elements;
    try {
      ({ shop } = await api('settings', {
        method: 'PUT',
        body: {
          orders_open: f.orders_open.checked, delivery: f.delivery.checked, lead_days: Number(f.lead_days.value),
          slots: f.slots.value.split('\n'), notice: f.notice.value, closed_message: f.closed_message.value,
        },
      }));
      toast('Réglages enregistrés');
    } catch (err) { toast(err.message, true); }
  });

  $('#password-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api('password', { method: 'POST', body: { current: $('#p-cur').value, next: $('#p-new').value } });
      e.target.reset();
      toast('Mot de passe changé');
    } catch (err) { toast(err.message, true); }
  });

  // ---------- Démarrage ----------
  api('me').then((d) => (d.admin ? showApp() : showLogin())).catch(() => showLogin());
})();
