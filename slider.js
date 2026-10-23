// ═══ Hero-Slider: 15 Bilder, Bildunterschrift, Punkte zum Springen ═══
var SHOTS = [
  ['01_haushaltsbuch', 'Haushaltsbuch', 'Monat auf einen Blick'],
  ['02_depot_uebersicht', 'Depot', 'Alle Werte, alle Depots'],
  ['03_chart_trend', 'Chartanalyse', 'Kerzen, Volumenprofil, gleitende Durchschnitte'],
  ['04_these_alphabet', 'These je Wert', 'Warum gekauft – schriftlich festgehalten'],
  ['05_wertzuwachs', 'Wertzuwachs', 'mit persönlicher Rendite p. a.'],
  ['06_watchlist_raumfahrt', 'Watchlists', 'nach Thema, mit Quartalszahlen-Terminen'],
  ['07_fixkosten', 'Fixkosten', 'Wiederkehrende Buchungen auf einen Klick'],
  ['08_dividende', 'Dividenden', 'Prognose und Kalender je Position'],
  ['09_thesen_check', 'Analyse', 'Investitionsplan und fällige Thesen-Prüfung'],
  ['10_mehrere_depots', 'Mehrere Depots', 'einzeln oder zusammen'],
  ['11_chart_momentum', 'Chart mit RSI', 'Indikatoren ohne Limit, als Setup speicherbar'],
  ['12_aufteilung_klassen', 'Aufteilung', 'nach Klasse, Position oder Thema'],
  ['13_eigene_trades', 'Eigene Käufe im Chart', 'Einstiege sichtbar machen'],
  ['14_sparplaene', 'Sparpläne', 'Raten, Intervall, Stichtag'],
  ['15_auswertung', 'Auswertung', 'Soll/Ist und Sparquote']
];
(function () {
  var box = document.getElementById('shots'), cap = document.getElementById('shotCap'), dots = document.getElementById('shotDots');
  var cur = 0, timer, imgs = [];
  document.getElementById('shotPrev').onclick = function () { show((cur - 1 + SHOTS.length) % SHOTS.length); restart(); };
  document.getElementById('shotNext').onclick = function () { show((cur + 1) % SHOTS.length); restart(); };
  SHOTS.forEach(function (s, i) {
    var im = new Image();
    var base = 'img/ff/slider/' + s[0]; im.src = base + '.webp'; im.srcset = base + '.webp 1x, ' + base + '@2x.webp 2x'; im.alt = 'FinFide – ' + s[1];
    if (i > 1) im.loading = 'lazy';
    box.appendChild(im); imgs.push(im);
    var b = document.createElement('button');
    b.setAttribute('aria-label', s[1]);
    b.onclick = function () { show(i); restart(); };
    dots.appendChild(b);
  });
  box.addEventListener('click', function (e) {   // Klick aufs Bild (nicht auf die Pfeile) = vergrößern
    if (e.target.closest('.shot-arrow') || !window.ffZoom) return;
    window.ffZoom(SHOTS.map(function (s) { return { src: 'img/ff/slider/' + s[0] + '@2x.webp', alt: s[1] + ' – ' + s[2] }; }), cur);
  });
  function show(i) {
    imgs[cur].classList.remove('on'); dots.children[cur].classList.remove('on');
    cur = i;
    imgs[cur].classList.add('on'); dots.children[cur].classList.add('on');
    cap.innerHTML = SHOTS[cur][1] + '<small>' + SHOTS[cur][2] + '</small>';
    [imgs[(cur + 1) % SHOTS.length], imgs[(cur - 1 + SHOTS.length) % SHOTS.length]].forEach(function (im) { if (im.loading === 'lazy') im.loading = 'eager'; });
  }
  function restart() { clearInterval(timer); timer = setInterval(function () { show((cur + 1) % SHOTS.length); }, 4500); }
  show(0); restart();
})();
