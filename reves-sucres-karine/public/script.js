// Les rêves sucrés de Karine — petites interactions
(function () {
  const header = document.querySelector('.site-header');
  const toggle = document.querySelector('.nav-toggle');

  // En-tête opaque après défilement
  const onScroll = () => header.classList.toggle('scrolled', window.scrollY > 30);
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });

  // Menu mobile
  toggle.addEventListener('click', () => {
    const open = header.classList.toggle('open');
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Fermer le menu' : 'Ouvrir le menu');
  });
  document.querySelectorAll('.nav-links a').forEach((a) =>
    a.addEventListener('click', () => {
      header.classList.remove('open');
      toggle.setAttribute('aria-expanded', 'false');
    })
  );

  // Pétales de cerisier qui tombent dans l'accueil
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const petals = document.querySelector('.petals');
  if (petals && !reduce) {
    for (let i = 0; i < 16; i++) {
      const p = document.createElement('span');
      p.className = 'petal';
      const size = 8 + Math.random() * 10;
      p.style.left = Math.random() * 100 + '%';
      p.style.width = p.style.height = size + 'px';
      p.style.animationDuration = 9 + Math.random() * 10 + 's';
      p.style.animationDelay = -Math.random() * 18 + 's';
      p.style.setProperty('--drift', (Math.random() * 160 - 80).toFixed(0) + 'px');
      petals.appendChild(p);
    }
  }

  // Apparition douce des blocs au défilement
  const targets = document.querySelectorAll('.section-head, .card, .steps li, .quotes figure, .about-text, .about-visual, .contact-info, .contact-form');
  if ('IntersectionObserver' in window && !reduce) {
    targets.forEach((el) => el.classList.add('reveal'));
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) { e.target.classList.add('visible'); io.unobserve(e.target); }
      });
    }, { threshold: 0.12 });
    targets.forEach((el) => io.observe(el));
  }

  // Formulaire : ouvre la messagerie avec la demande pré-remplie
  // (à remplacer plus tard par un vrai service d'envoi, ex. Formspree)
  const form = document.getElementById('contact-form');
  const status = form.querySelector('.form-status');
  const EMAIL = 'contact@exemple.fr';
  form.addEventListener('submit', (ev) => {
    ev.preventDefault();
    const d = Object.fromEntries(new FormData(form));
    if (!d.nom.trim() || !d.message.trim()) {
      status.textContent = 'Merci d\'indiquer votre nom et votre message.';
      status.className = 'form-status err';
      return;
    }
    const body = [
      'Nom : ' + d.nom,
      d.tel ? 'Téléphone : ' + d.tel : '',
      d.date ? 'Date souhaitée : ' + d.date : '',
      'Occasion : ' + d.occasion,
      '',
      d.message,
    ].filter((l, i) => l !== '' || i === 4).join('\n');
    const url = 'mailto:' + EMAIL +
      '?subject=' + encodeURIComponent('Demande de commande — ' + d.occasion) +
      '&body=' + encodeURIComponent(body);
    window.location.href = url;
    status.textContent = 'Votre messagerie s\'ouvre pour envoyer la demande. Merci !';
    status.className = 'form-status ok';
  });

  document.getElementById('annee').textContent = new Date().getFullYear();
})();
