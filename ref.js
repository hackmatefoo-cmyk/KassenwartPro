/* Partner-Link (?ref=AFF-XXXX): Kennung bleibt nur in der Adresszeile (kein Cookie, kein Speicher).
   Sie wird an interne Links und den Kaufen-Knopf (Stripe: client_reference_id) angehängt. */
(function () {
  var m = /[?&]ref=([A-Za-z0-9-]{4,16})/.exec(location.search);
  var code = m && /^AFF-[A-Z0-9]{4,10}$/.test(m[1].toUpperCase()) ? m[1].toUpperCase() : '';
  window.KPREF = {
    code: code,
    buy: function (url) {
      if (!code || !url || url.charAt(0) === '#') return url;
      return url + (url.indexOf('?') < 0 ? '?' : '&') + 'client_reference_id=' + encodeURIComponent(code);
    }
  };
  if (!code) return;
  document.addEventListener('DOMContentLoaded', function () {
    var links = document.querySelectorAll('a[href]');
    for (var i = 0; i < links.length; i++) {
      var h = links[i].getAttribute('href');
      if (!h || h.charAt(0) === '#' || /^(mailto:|tel:|javascript:)/i.test(h)) continue;
      try {
        var u = new URL(h, location.href);
        if (u.origin !== location.origin) {
          if (u.hostname === 'buy.stripe.com') links[i].setAttribute('href', KPREF.buy(h));
          continue;
        }
        u.searchParams.set('ref', code);
        links[i].setAttribute('href', u.pathname + u.search + u.hash);
      } catch (e) { /* Link unverändert lassen */ }
    }
  });
})();
