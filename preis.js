// ═══ Preisleiter + Zähler ═══
// ENTWURF – Stufen, Preise und Stripe-Links vor Veröffentlichung festlegen.
// endpoint: Sheet-B-Web-App mit ?action=price_status → {ok, sold, as_of} (Zähler zählt Käufe ohne Erstattungen; Stufen und Preise stehen unten im Skript)
var PRICE = {
  endpoint: 'https://script.google.com/macros/s/AKfycbxG4J9d0lccrSQr_xCRtx6u2s9eUS3J-zKUjzwlWN1IC9DZhVs2fpm20D0lhE8ZYrw2jw/exec',
  fallbackSold: 0,
  stages: [
    { upto: 50,   price: 15, link: 'https://buy.stripe.com/7sY9AUaHX37RcNxelZ6Ri0c', kind: 'Einführung',   goal: 'Start',              text: 'Bekannt werden, erstes Feedback, Feinschliff' },
    { upto: 150,  price: 29, link: 'https://buy.stripe.com/9B628s03jdMv7td4Lp6Ri09', kind: 'Einführung',   goal: 'Erste Update-Runde', text: 'Wünsche der Käufer umsetzen' },
    { upto: 300,  price: 49, link: 'https://buy.stripe.com/eVq00k8zP23N3cX0v96Ri0b', kind: 'Einführung',   goal: 'Abstimmung',         text: 'Rein lokal bleiben – oder optionaler Live-Kurs-Dienst?' },
    { upto: 500,  price: 69, link: 'https://buy.stripe.com/3cI5kE6rHeQz14PcdR6Ri0a', kind: 'Regulär',      goal: 'Mehrsprachig',       text: 'Englisch und Spanisch · höhere Partnerprämie' },
    { upto: null, price: null, link: '#', kind: 'Mit Live-Ausbau', goal: 'Alarme & mehr', text: 'z. B. Kurs-Alarm per Telegram, Broker-Schnittstellen, Mac-Version?' }
  ]
};
var REGULAR = 69;   // regulärer Preis – Bezugspunkt für die Einführungsstufen
function renderPrice(sold, liveLink) {
  var st = PRICE.stages, k = st.findIndex(function (s) { return s.upto === null || sold < s.upto; });
  if (k < 0) k = st.length - 1;
  while (k > 0 && st[k].price === null) k--;   // Stufe ohne festen Preis: regulärer Preis gilt weiter
  var from = k ? st[k - 1].upto : 0;
  document.getElementById('ladder').innerHTML = st.map(function (s, i) {
    var lo = i ? st[i - 1].upto + 1 : 1;
    var range = s.upto === null ? 'ab Kauf ' + lo : 'Kauf ' + lo + '–' + s.upto;
    return '<div class="rung ' + (i < k ? 'done' : i === k ? 'now' : '') + '"><div class="kd">' + s.kind + '</div><div class="p">' + (s.price === null ? '?' : s.price) + ' €</div><div class="r">' + range + '</div></div>';
  }).join('');
  document.getElementById('roadmap').innerHTML = st.map(function (s, i) {
    var cls = i < k ? 'done' : i === k ? 'now' : 'idea';
    var mark = i < k ? '✓ erreicht' : i === k ? '● läuft' : '○ Idee';
    return '<div class="mile ' + cls + '"><span class="m-state">' + mark + '</span><b><i class="m-price">' + (s.price === null ? '?' : s.price) + ' € · </i>' + s.goal + '</b><span>' + s.text + '</span></div>';
  }).join('');
  var cur = st[k], txt;
  if (cur.upto === null || cur.price >= REGULAR) {
    txt = 'Preis: <b>' + cur.price + ' €</b> einmalig';
    document.getElementById('meterBar').style.width = '100%';
  } else {
    var left = cur.upto - sold;
    txt = 'Noch <b>' + left + '</b> von ' + (cur.upto - from) + ' Lizenzen zum Einführungspreis von <b>' + cur.price + ' €</b> · regulär ' + REGULAR + ' €';
    document.getElementById('meterBar').style.width = Math.round((sold - from) / (cur.upto - from) * 100) + '%';
  }
  document.getElementById('counterText').innerHTML = txt;
  var buy = document.getElementById('buyBtn');
  buy.textContent = 'Jetzt kaufen · ' + cur.price + ' €';
  buy.href = (window.KPREF ? KPREF.buy(liveLink || cur.link) : (liveLink || cur.link));
  document.querySelectorAll('[data-price-btn]').forEach(function (b) { b.innerHTML = (cur.price < REGULAR ? 'Noch für ' : 'Für ') + cur.price + ' € sichern<small>↓ mehr</small>'; });
}
renderPrice(PRICE.fallbackSold);
if (PRICE.endpoint) {
  fetch(PRICE.endpoint + '?action=price_status', { cache: 'no-store' })
    .then(function (r) { return r.json(); })
    .then(function (d) { if (typeof d.sold === 'number') renderPrice(d.sold, d.checkout_link); })
    .catch(function () {});
}
