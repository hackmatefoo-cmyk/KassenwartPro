// Klick-Vergrößerung für Screenshots (eingeführt 2026-10-23).
// Bilder mit class="zoom" und data-full="<großes Bild>" öffnen sich groß; ←/→ blättern, Esc oder Klick daneben schließt.
// Von anderen Skripten nutzbar: ffZoom([{src, alt}, ...], index)
(function () {
  var box, img, cap, list = [], cur = 0;
  function build() {
    box = document.createElement('div');
    box.className = 'zoom-modal';
    box.innerHTML = '<button class="zoom-close" aria-label="Schließen">×</button><button class="zoom-nav prev" aria-label="Vorheriges Bild">‹</button>'
      + '<figure><img alt=""><figcaption></figcaption></figure><button class="zoom-nav next" aria-label="Nächstes Bild">›</button>';
    document.body.appendChild(box);
    img = box.querySelector('img'); cap = box.querySelector('figcaption');
    box.addEventListener('click', function (e) {
      if (e.target.classList.contains('prev')) return go(-1);
      if (e.target.classList.contains('next')) return go(1);
      if (e.target !== img) close();
    });
    document.addEventListener('keydown', function (e) {
      if (!box.classList.contains('open')) return;
      if (e.key === 'Escape') close();
      else if (e.key === 'ArrowLeft') go(-1);
      else if (e.key === 'ArrowRight') go(1);
    });
  }
  function show() { img.src = list[cur].src; img.alt = list[cur].alt || ''; cap.textContent = list[cur].alt || ''; box.classList.toggle('single', list.length < 2); }
  function go(d) { cur = (cur + d + list.length) % list.length; show(); }
  function close() { box.classList.remove('open'); document.body.style.overflow = ''; img.removeAttribute('src'); }
  window.ffZoom = function (items, i) {
    if (!box) build();
    list = items; cur = i || 0; show();
    box.classList.add('open'); document.body.style.overflow = 'hidden';
  };
  document.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('img.zoom');
    if (!t) return;
    var all = [].slice.call(document.querySelectorAll('main img.zoom'));
    window.ffZoom(all.map(function (x) { return { src: x.getAttribute('data-full') || x.currentSrc || x.src, alt: x.alt }; }), all.indexOf(t));
  });
})();
