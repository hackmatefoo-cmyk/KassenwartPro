// Video-Fenster für Anleitungsvideos (eingeführt 2026-09-30).
// Einbinden: <script src="video.js" defer></script>
// Knopf:     <button class="vid-btn" data-video="A04_Depot_im_Ueberblick">Depot im Überblick</button>
// Dateien:   video/<name>.mp4 + video/<name>.jpg (Vorschaubild)
(function () {
  var box;
  function build() {
    box = document.createElement('div');
    box.className = 'vid-modal';
    box.innerHTML = '<div class="vid-frame"><button class="vid-close" aria-label="Schließen">×</button>'
      + '<video controls playsinline preload="none"></video><div class="vid-title"></div></div>';
    document.body.appendChild(box);
    box.addEventListener('click', function (e) { if (e.target === box || e.target.classList.contains('vid-close')) close(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && box.classList.contains('open')) close(); });
  }
  function open(name, title) {
    if (!box) build();
    var v = box.querySelector('video');
    v.poster = 'video/' + name + '.jpg';
    v.src = 'video/' + name + '.mp4';
    box.querySelector('.vid-title').textContent = title || '';
    box.classList.add('open');
    document.body.style.overflow = 'hidden';
    var p = v.play(); if (p && p.catch) p.catch(function () {});
  }
  function close() {
    var v = box.querySelector('video');
    v.pause(); v.removeAttribute('src'); v.load();
    box.classList.remove('open');
    document.body.style.overflow = '';
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-video]');
    if (!b) return;
    e.preventDefault();
    open(b.getAttribute('data-video'), b.getAttribute('data-title') || b.textContent.replace(/^\s*▶\s*/, '').trim());
  });
})();
