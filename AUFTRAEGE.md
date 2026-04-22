# Aufträge für Claude Code — Portfolio Tracker

So benutzt du diese Datei:
1. Geh auf claude.ai/code
2. Kopiere EINEN Auftrag (den grauen Block)
3. Füge ihn ein und drücke Enter
4. Claude Code arbeitet, du schaust zu
5. Wenn fertig: prüfen, ggf. korrigieren lassen, dann PR mergen
6. Nächster Auftrag

**Wichtig:** Immer nur EIN Auftrag auf einmal. Nicht drei auf einmal reinkippen.
Reihenfolge einhalten — die Phasen bauen aufeinander auf.

---

## Phase 0 — Vorarbeit

### Auftrag 0.1 — JSON-Schema + Testdaten
```
Lies die Spezifikation in docs/Portfolio_Tracker_Spezifikation_v1.md.

Erstelle eine Datei tests/test_portfolio.json mit einem vollständigen
Test-Dataset. Das Dataset soll enthalten:
- cash_account mit Saldo 1450.00 EUR
- 5 Positionen: IWDA.AS (ETF, 2 Lots), AAPL (Aktie, 1 Lot),
  BTC-EUR (Krypto, 1 Lot), XAUEUR (Edelmetall, 1 Lot),
  NVDA (Aktie, Watchlist-Position ohne Lots)
- 2 Dividenden-Transaktionen (AAPL)
- 1 Verkauf-Transaktion (Teilverkauf AAPL, FIFO)
- 2 Sparplan-Einträge (IWDA.AS monatlich 200 EUR, BTC-EUR monatlich 50 EUR)
- Transaktionslog mit allen bisherigen Buchungen

Benutze die Keys und Typen aus der CLAUDE.md (Transaktionstypen,
Asset-Klassen, Sparplan-Intervalle). Schreibe die JSON-Datei
so dass sie als Referenz für alle späteren Tests dient.
```

### Auftrag 0.2 — Config-Format
```
Erstelle eine Datei docs/config_schema.md die das Format für die
API-Key-Konfiguration beschreibt. Die Config-Datei heißt zur
Laufzeit config_api.dat und liegt neben der .exe.

Format: JSON mit den Keys:
- coingecko_api_key
- metals_api_key
- openfigi_api_key

Erstelle außerdem eine Beispieldatei tests/config_api_example.dat
mit Platzhalter-Keys. Keine echten Keys committen!
```

---

## Phase 1 — Datenmodell

### Auftrag 1.1 — portfolio_data.py Grundgerüst
```
Erstelle portfolio_data.py mit folgender Funktionalität:

1. load_portfolio(filepath) → dict
   - JSON laden, bei fehlender Datei leeres Portfolio mit
     Standardstruktur zurückgeben

2. save_portfolio(filepath, data) → None
   - JSON speichern mit indent=2

3. add_position(data, ticker, asset_class, name, broker="") → data
   - Neue Position mit leerer Lots-Liste anlegen
   - Fehler wenn Ticker schon existiert

4. add_lot(data, ticker, datum, anzahl, kurs) → data
   - Lot zur Position hinzufügen
   - Verrechnungskonto um (anzahl * kurs) belasten
   - Transaktion vom Typ "buy" ins Log schreiben
   - Fehler wenn Verrechnungskonto nicht reicht

5. sell_lots_fifo(data, ticker, anzahl, tatsaechlich_erhalten) → data
   - Älteste Lots zuerst aufbrauchen (FIFO)
   - Teilverkauf innerhalb eines Lots möglich
   - Verrechnungskonto um tatsaechlich_erhalten erhöhen
   - Steuer = (anzahl * aktueller_kurs) - tatsaechlich_erhalten
   - Transaktion vom Typ "sell" ins Log schreiben
   - Fehler wenn nicht genug Anteile vorhanden

6. add_dividend(data, ticker, brutto, tatsaechlich_erhalten) → data
   - Verrechnungskonto um tatsaechlich_erhalten erhöhen
   - Transaktion vom Typ "dividend" ins Log

7. transfer_cash(data, betrag, richtung) → data
   - richtung = "in" oder "out"
   - Verrechnungskonto anpassen
   - Transaktion ins Log

Alle Funktionen geben das modifizierte data-Dict zurück.
Verrechnungskonto darf nie negativ werden — ValueError werfen.
Pfad-Handling: filepath wird von außen übergeben, NICHT intern
über sys.executable (das macht der __main__-Block).
```

### Auftrag 1.2 — Tests für portfolio_data.py
```
Erstelle tests/test_portfolio_data.py mit pytest-Tests:

1. test_load_empty — leere Datei laden ergibt Standardstruktur
2. test_add_position — Position anlegen, prüfen ob in positions
3. test_add_lot — Lot anlegen, Verrechnungskonto wird belastet
4. test_sell_fifo — 2 Lots anlegen, Teilverkauf, prüfen dass
   das ältere Lot zuerst aufgebraucht wird
5. test_sell_too_many — mehr verkaufen als vorhanden → ValueError
6. test_negative_cash — Kauf der Verrechnungskonto überzieht → ValueError
7. test_dividend — Dividende buchen, Verrechnungskonto prüfen
8. test_transfer — Übertrag rein/raus, Saldo prüfen
9. test_transaction_log — nach mehreren Aktionen prüfen ob
   alle Transaktionen im Log stehen

Lade tests/test_portfolio.json als Referenz-Fixture.
Führe die Tests aus und zeig mir das Ergebnis.
```

---

## Phase 2 — Datenquellen-Adapter

### Auftrag 2.1 — Interface + yfinance-Adapter
```
Erstelle portfolio_api.py mit:

1. Abstraktes Interface (Klasse DataAdapter):
   - get_price(ticker) → float
   - get_history(ticker, start, end) → list of (date, close)
   - get_dividends(ticker) → list of (date, amount)
   - search_ticker(query) → list of (symbol, name, exchange)

2. YFinanceAdapter(DataAdapter):
   - Implementiere alle 4 Methoden mit yfinance
   - Timeout: 10 Sekunden
   - Bei Fehler/Timeout: None zurückgeben, nicht crashen
   - Logging bei Fehlern (print reicht erstmal)

3. get_adapter(asset_class) → DataAdapter
   - Gibt den passenden Adapter für die Asset-Klasse zurück
   - Erstmal nur YFinanceAdapter für stock, etf
   - Andere Klassen geben None zurück (Platzhalter)

Teste mit: AAPL, IWDA.AS, MSFT. Zeig mir die Ergebnisse.
```

### Auftrag 2.2 — CoinGecko-Adapter
```
Ergänze portfolio_api.py um CoinGeckoAdapter(DataAdapter):

- API-Key aus config_api.dat laden
- get_price: /simple/price Endpoint
- get_history: /coins/{id}/market_chart/range
- search_ticker: /search
- Kein API-Key → Fehlermeldung statt Crash
- Rate-Limiting beachten (max 10-30 calls/min im Free-Plan)

Registriere den Adapter in get_adapter() für asset_class="crypto".
Teste mit bitcoin und ethereum.
```

### Auftrag 2.3 — Metals-API + OpenFIGI
```
Ergänze portfolio_api.py um:

1. MetalsAdapter(DataAdapter):
   - Metals API für Gold (XAU) und Silber (XAG)
   - API-Key aus config_api.dat
   - Kurse in EUR

2. OpenFigiAdapter:
   - Nur eine Funktion: resolve_isin(isin) → ticker
   - API-Key aus config_api.dat

Registriere MetalsAdapter für asset_class="precious_metal".
```

### Auftrag 2.4 — Cache-Layer
```
Ergänze portfolio_api.py um CacheLayer:

- Speichert historische Kurse in cache.dat (JSON)
- Format: {"AAPL": {"2024-03-15": 172.50, ...}, "last_update": "2024-03-20"}
- Beim Laden: prüfe ob last_update älter als heute
  → wenn ja, aktualisiere beim nächsten get_history-Aufruf
- Offline-Fallback: wenn Adapter None zurückgibt, Cache benutzen
- Funktion get_cached_price(ticker) → (preis, alter_in_tagen)
  damit die UI "Kurs von vor X Tagen" anzeigen kann
```

### Auftrag 2.5 — Währungsumrechnung
```
Ergänze portfolio_api.py um:

- Funktion convert_to_eur(amount_usd) → float
- Benutzt yfinance mit Ticker "EURUSD=X"
- Cache den Wechselkurs für 1 Stunde
- Fallback: fester Kurs 0.92 wenn kein Internet
```

---

## Phase 3 — Flask-Routing & UI

### Auftrag 3.1 — Portfolio-Route + Grundgerüst
```
Lies die UI-Übersicht in docs/Portfolio_Tracker_Spezifikation_v1.md
(Abschnitt 14).

Erstelle:
1. In KassenwartPro_app.py: neue Route /portfolio
2. templates/portfolio.html mit dem kompletten UI-Grundgerüst:
   - Kopfzeile: Depotwert + Gewinn/Verlust gesamt
   - Vier KPI-Kacheln (Investiert, Dividenden YTD,
     Verrechnungskonto, Realisierte G/V)
   - Chart-Bereiche als Platzhalter (leere Divs)
   - Positionstabelle mit Spalten: Ticker, Anzahl, Kurs, G/V%, ⋯-Menü
   - Sub-Tab-Navigation: Positionen / Sparpläne / Orderhistorie
   - Durchschalt-Button für Watchlist-Filter

Stil: orientiere dich am bestehenden Haushaltsbuch-Design
(gleiche CSS-Variablen, gleiche Farben, gleiches Layout-Gefühl).

Die Daten kommen erstmal als Dummy/Hardcoded — die echte
Anbindung kommt in Phase 4.
```

### Auftrag 3.2 — Portfolio-Button im Haushaltsbuch
```
Füge im Haushaltsbuch-Template (templates/index.html) einen
Button "Portfolio" hinzu. Position: in der Hauptnavigation,
neben den bestehenden Elementen.

Klick auf den Button: window.open('/portfolio', '_blank')
— öffnet den Portfolio Tracker in einem neuen Browser-Tab.

Dazu in portfolio.html: visibilitychange-Event, das bei
Tab-Fokus die Daten neu vom Server lädt (damit Änderungen
aus dem Haushaltsbuch sofort sichtbar sind).
```

---

## Phase 4 — Kauf, Verkauf, Dividende

### Auftrag 4.1 — Kauf-Dialog
```
Erstelle den Kauf-Dialog als Modal/Popup in portfolio.html:

1. Suchfeld: Nutzer tippt Ticker oder Name ein
   → search_ticker() aufrufen via AJAX (/api/portfolio/search)
   → Ergebnisse als Dropdown anzeigen

2. Eingabefelder: Anzahl, Kaufkurs (vorbefüllt mit aktuellem Kurs),
   Datum (default: heute), Broker (optional), Asset-Klasse (Dropdown)

3. Anzeige: Gesamtkosten = Anzahl × Kurs, Verrechnungskonto-Stand

4. "Kaufen"-Button → POST an /api/portfolio/buy
   → Server ruft add_lot() auf
   → Erfolg: Tabelle neu laden, Modal schließen

Erstelle die nötigen Flask-Routen:
- GET /api/portfolio/search?q=... → search_ticker()
- POST /api/portfolio/buy → add_lot()
- GET /api/portfolio/data → komplette Portfolio-Daten als JSON
```

### Auftrag 4.2 — Verkauf-Popup
```
Erstelle den Verkauf-Dialog laut Spezifikation Abschnitt 7:

Anzeige (automatisch berechnet):
- Verkaufswert = Anzahl × aktueller Kurs
- Einkaufswert (FIFO) = Summe der ältesten Lots
- Gewinn (brutto) = Differenz

Eingabefeld: "Tatsächlich erhalten" (das tippt der Nutzer ein)
→ Steuer wird automatisch als Differenz berechnet
→ Aufs Verrechnungskonto geht der eingegebene Betrag

Eingabefeld: Anzahl (default: alle)

Route: POST /api/portfolio/sell → sell_lots_fifo()
```

### Auftrag 4.3 — Dividenden-Dialog
```
Gleiche Logik wie Verkauf-Popup:
- Brutto-Dividende anzeigen (aus API oder manuell eintippen)
- "Tatsächlich erhalten"-Feld
- Differenz = Steuer
- Betrag geht aufs Verrechnungskonto

Route: POST /api/portfolio/dividend → add_dividend()
```

---

## Phase 5 — Budget-Brücke

### Auftrag 5.1 — Übertrag-Dialog + WAL
```
Erstelle den Übertrag-Dialog zwischen Haushaltsbuch und Depot:

1. Dialog: Betrag + Richtung (→ Depot / ← Depot)

2. Write-Ahead-Log (wal.dat):
   - VOR der eigentlichen Buchung: Absicht in wal.dat schreiben
   - Dann: Portfolio-JSON updaten (Verrechnungskonto)
   - Dann: Haushaltsbuch-JSON updaten (Buchung mit Kategorie
     "Depot-Übertrag", system: true)
   - Dann: wal.dat löschen

3. Crash-Recovery beim App-Start:
   - Prüfe ob wal.dat existiert
   - Wenn ja: lese die Absicht und führe die fehlenden
     Schritte nach

4. System-Kategorie "Depot-Übertrag" im Haushaltsbuch
   anlegen (analog zu "Rücklagen", system: true, wird vom
   Nutzer nicht gelöscht werden können)

ACHTUNG: Das ist der einzige Auftrag der KassenwartPro_app.py
verändert. Mach minimale Änderungen — nur die neue Kategorie
und die Route für Überträge.
```

---

## Phase 6 — Charts

### Auftrag 6.1 — Allocation + Depotverlauf
```
Binde Chart.js ein (CDN) und erstelle:

1. Allocation Donut-Chart:
   - Aufteilung nach Asset-Klasse
   - Cash (Verrechnungskonto) als eigene Scheibe
   - Farben pro Klasse fest definieren

2. Depotwert-Verlauf (Liniendiagramm):
   - Zeitraum-Buttons: 1M / 3M / 6M / 1J / Max
   - Depotwert-Linie (durchgezogen)
   - Benchmark-Linie (gestrichelt, default: MSCI World via IWDA.AS)
   - Daten kommen aus dem Cache (get_history)

Route: GET /api/portfolio/chart-data?period=1M → historische Daten
```

### Auftrag 6.2 — Einzelposition-Chart + Soll/Ist
```
Ergänze die Charts um:

1. Einzelposition-Chart:
   - Klick auf ⋯-Menü → "Chart anzeigen"
   - Zeigt Kursverlauf dieser Position im Chart-Bereich
   - Gleiche Zeitraum-Buttons

2. Soll vs. Ist Donut:
   - Zweiter Ring im Donut-Chart
   - Nutzer kann Soll-Werte pro Asset-Klasse definieren
     (kleines Settings-Popup)
   - Soll-Werte werden in portfolio.dat unter einem neuen Key
     "target_allocation" gespeichert
```

---

## Phase 7 — Watchlist & Orderhistorie

### Auftrag 7.1 — Watchlist + Orderhistorie
```
1. Watchlist:
   - Positionen ohne Lots werden ausgegraut dargestellt
   - Nur Ticker, Name, aktueller Kurs
   - Durchschalt-Button: Alle → Positionen → Watchlist → Alle
   - "Zur Watchlist"-Option im ⋯-Menü

2. Orderhistorie (Sub-Tab):
   - Chronologische Liste aller Transaktionen aus dem Log
   - Spalten: Datum, Typ (deutsch), Ticker, Anzahl, Kurs, Betrag
   - Typ wird übersetzt: buy → Kauf, sell → Verkauf, etc.
```

---

## Phase 8 — Sparplan

### Auftrag 8.1 — Sparplan anlegen/verwalten
```
Erstelle den Sparplan-Dialog:

1. Anlegen: Ticker, Betrag, Intervall (Dropdown mit:
   wöchentlich, 2-wöchentlich, monatlich, quartalsweise,
   halbjährlich, jährlich), Stichtag, Start-/Enddatum (optional)

2. Sparpläne werden in portfolio.dat unter "savings_plans" gespeichert
   mit einem Feld "last_executed" (Datum der letzten Ausführung)

3. Sub-Tab "Sparpläne": Liste aller Sparpläne mit
   Status (aktiv/pausiert), nächste Ausführung, Betrag

4. ⋯-Menü: Bearbeiten, Pausieren, Löschen
```

### Auftrag 8.2 — Auto-Nachbuchung
```
Implementiere die Sparplan-Ausführung beim App-Start:

1. Beim Start von /portfolio: prüfe alle aktiven Sparpläne
2. Für jeden: welche Stichtage liegen zwischen last_executed und heute?
3. Pro fälligem Stichtag:
   - Historischen Schlusskurs am Stichtag holen (get_history)
   - Wochenende/Feiertag → letzter Handelstag davor
   - Neues Lot anlegen, Verrechnungskonto belasten
   - Transaktion vom Typ "savings_plan" ins Log
   - last_executed aktualisieren
4. Notification: "X Sparplan-Ausführungen nachgebucht" als Banner

KRITISCH: Doppelbuchungs-Prüfung! Immer gegen last_executed
prüfen. Wenn App 2x am gleichen Tag gestartet wird, darf
nichts doppelt gebucht werden.
```

---

## Phase 9 — Extras

### Auftrag 9.1 — Prognose-Rechner
```
Erstelle den Prognose-Rechner als Modal/Dialog:

1. Vorbefüllt mit aktuellen Werten (Depotwert, Sparrate)
2. Slider: Erwartete Rendite (3-12% p.a.)
3. Slider: Anlagehorizont (1-40 Jahre)
4. Eingabe: Monatliche Sparrate (anpassbar)
5. Optional: Einmalzahlungen
6. Chart.js Liniendiagramm: projizierter Depotwert über Zeit

Reine Mathematik, keine API-Calls. Zinseszins-Formel.
```

### Auftrag 9.2 — Erstbefüllung
```
Erstelle eine Schnelleingabe für bestehende Depots:

1. Tabellen-Formular mit Zeilen: Ticker | Datum | Anzahl | Kaufkurs
2. Nutzer tippt Zeile für Zeile durch
3. "Alle importieren"-Button → legt alle Positionen + Lots an
4. Kein CSV-Import, nur manuelles Tippen

Erreichbar über einen Button "Bestehendes Depot einpflegen"
der nur bei leerem Portfolio angezeigt wird.
```

---

## Phase 10 — Integration & Hardening

### Auftrag 10.1 — Fehlerbehandlung
```
Gehe durch alle API-Aufrufe in portfolio_api.py und stelle sicher:

1. Timeout bei jedem Request (10 Sekunden)
2. try/except um jeden API-Call
3. Bei Fehler: Cache benutzen, Hinweis "Offline-Daten" anzeigen
4. Korrupte portfolio.dat → Backup anlegen, neu initialisieren
5. Leeres Depot → saubere Anzeige mit "Noch keine Positionen"
6. Ungültiger Ticker → Fehlermeldung im Dialog

Teste jeden Fall und zeig mir die Ergebnisse.
```

### Auftrag 10.2 — PyInstaller-Bundle prüfen
```
Prüfe ob alle neuen Dateien korrekt im PyInstaller-Bundle
landen würden:

1. Liste alle neuen .py-Dateien die importiert werden
2. Liste alle neuen Template-Dateien
3. Prüfe ob Pfade im __main__-Block vollständig sind
4. Prüfe ob alle imports korrekt aufgelöst werden
5. Erstelle eine Checkliste was ich vor dem Build
   auf meinem Windows-Rechner prüfen muss

NICHT den Build selbst ausführen (geht nur auf meinem
Windows-Rechner mit pyinstaller). Nur die Vorbereitung.
```

---

## Tipps für die Arbeit mit Claude Code

**Wenn etwas nicht klappt:** Sag einfach "Das hat nicht funktioniert,
hier ist der Fehler: [Fehlermeldung]". Claude Code kann den Fehler
lesen und fixen.

**Wenn du unsicher bist:** Sag "Erkläre mir erst was du vorhast,
bevor du es umsetzt." Dann beschreibt er den Plan und du sagst
ja oder nein.

**Wenn du Änderungen willst:** "Ändere X in Y" oder "Das gefällt
mir nicht, mach es stattdessen so: ..."

**Wenn du den Stand sehen willst:** "Zeig mir die aktuelle
Dateistruktur" oder "Was haben wir bisher gemacht?"
