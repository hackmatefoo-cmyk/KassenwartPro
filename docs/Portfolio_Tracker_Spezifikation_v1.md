Portfolio Tracker — Funktionsspezifikation v1
Projekt: Kassenwart Pro — Modul "Portfolio"
Stand: 21. April 2026
Status: Brainstorming abgeschlossen, Programmierauftrag


1. Architektur
Zwei-Fenster-Prinzip: Der Portfolio Tracker öffnet sich als eigenes Tkinter-Fenster (Toplevel()), gestartet über einen Button im Haushaltsbuch-Hauptfenster. Eigene .py-Datei (portfolio_tracker.py), gebündelt in dieselbe .exe via PyInstaller.

Datenhaltung: Eigene JSON-Datei für Portfolio-Daten, getrennt vom Haushaltsbuch. Beide Fenster laufen parallel — der Nutzer kann Haushaltsbuch und Depot nebeneinander sehen.

Datenquellen-Abstraktion: Alle Kursabfragen laufen über ein einheitliches Interface:

get_price(ticker) → float

get_history(ticker, start, end) → [(date, close), ...]

get_dividends(ticker) → [(date, amount), ...]

search_ticker(query) → [(symbol, name, exchange), ...]

Dahinter stecken austauschbare Adapter. Die Datenquelle kann gewechselt werden, ohne den Rest der App anzufassen.

Datenquellen v1:

Asset-Klasse
Quelle
API-Key nötig
Kosten
Aktien, ETFs, Indizes
yfinance
Nein
Kostenlos (inoffiziell)
Krypto
CoinGecko
Ja (Free-Plan)
Kostenlos
Edelmetalle (Gold, Silber)
Metals API
Ja
Keys vorhanden
ISIN → Ticker Auflösung
OpenFIGI
Ja
Kostenlos


Alle API-Keys werden in einer lokalen Config-Datei gespeichert (nicht hardcoded). Austausch gegen EODHD oder andere Quellen ist architektonisch vorbereitet, erfordert aber deren Commercial License (~300$/Monat) — daher nicht in v1.


2. Asset-Klassen & Kategorien
Unterstützte Klassen: Aktien, ETFs, Krypto, Anleihen/Festgeld, Rohstoffe, Bargeld (Verrechnungskonto).

Es gibt kein "Sonstiges" — jede Position muss einer definierten Klasse zugeordnet sein. Die Klasse bestimmt die Farbe im Allocation-Chart und den verwendeten Datenadapter.


3. Verrechnungskonto & Budget-Brücke
Das Portfolio hat ein eigenes Verrechnungskonto (Cash-Position). Dieses ist im Allocation-Pie-Chart als eigene Scheibe sichtbar.

Überträge in beide Richtungen:

Haushaltsbuch → Depot: z.B. "500 EUR zum Investieren überweisen"
Depot → Haushaltsbuch: z.B. "Dividende aufs Girokonto"

Jeder Übertrag erzeugt je eine Buchung in beiden Datendateien (Haushaltsbuch + Portfolio). Die Buchung muss atomar sein — entweder beide Seiten oder keine.


4. Positionen & Lot-Tracking
Ein Depot (kein Multi-Depot). Pro Position kann ein Broker/Börse als Info-Feld hinterlegt werden (z.B. "Trade Republic", "Scalable Capital", "Bitpanda").

Lot-Tracking: Jeder Kauf wird als eigenes Lot gespeichert:

{

  "ticker": "AAPL",

  "lots": [

    {"datum": "2024-03-15", "anzahl": 10, "kurs": 172.50},

    {"datum": "2024-07-01", "anzahl": 5, "kurs": 195.00}

  ]

}

Kostenbasis: FIFO (First In, First Out) — steuerlich vorgeschrieben in DE (§ 20 Abs. 4 S. 7 EStG). Bei Teilverkäufen werden die ältesten Lots zuerst aufgebraucht. Rundungsdifferenzen werden akzeptiert — der Nutzer korrigiert über den tatsächlich erhaltenen Betrag im Verkauf-Popup.


5. Sparplan
Anlage: Der Nutzer definiert pro Position einen Sparplan mit:

Betrag (z.B. 50 EUR)
Intervall (wöchentlich, 2-wöchentlich, monatlich, quartalsweise, halbjährlich, jährlich)
Stichtag (z.B. 1. des Monats, jeden Freitag)
Start-/Enddatum (optional)

UX: Orientiert sich am Einstellungs-Dialog für wiederkehrende Buchungen im Haushaltsbuch.

Ausführung — Auto-Nachbuchung beim App-Start:

Beim Start prüft die App: welche Sparplan-Stichtage liegen zwischen letztem App-Start und heute?
Für jeden fälligen Stichtag: historischen Schlusskurs am Stichtag via yfinance abrufen
Wochenende/Feiertag → letzter Handelstag davor
Kauf automatisch buchen (neues Lot, Betrag vom Verrechnungskonto abziehen)
Notification an den Nutzer: "3 Sparplan-Ausführungen nachgebucht"

Komplexitäts-Hinweis: Sorgfältige Prüfung auf Doppelbuchungen nötig. Letztes Ausführungsdatum pro Sparplan speichern und bei jeder Prüfung dagegen abgleichen.


6. Performance-Kennzahlen
V1 — vereinfacht:

Gewinn/Verlust pro Position (absolut in EUR + prozentual)
Gewinn/Verlust Gesamtdepot
Annualisierte Rendite (einfache Formel: (aktuell/investiert)^(1/Jahre) - 1)
Realisierte Gewinne YTD (Summe aus Verkäufen)
Dividenden YTD (Summe + Anzahl Zahlungen)

Nicht in v1: TTWROR (zeitgewichtete Rendite), IZF/IRR (interner Zinsfuß). Kommen in einem späteren Update, wenn die Datenbasis stabil steht.


7. Verkauf-Popup (Simplified Steuer)
Beim Verkauf einer Position öffnet sich ein Popup:

Feld
Wert
Quelle
Verkaufswert
992,50 EUR
Anzahl × aktueller Kurs
Einkaufswert (FIFO)
787,50 EUR
Summe der ältesten Lots
Gewinn (brutto)
+205,00 EUR
Berechnet
Tatsächlich erhalten
[Eingabefeld]
Nutzer tippt ein
→ Steuer (berechnet)
52,38 EUR
Verkaufswert − tatsächlich erhalten
→ Aufs Verrechnungskonto
940,12 EUR
= tatsächlich erhalten


Kein Steuermodell, keine Vorabpauschale, keine Teilfreistellung. Der Nutzer weiß von seiner Broker-Abrechnung, was er bekommen hat — fertig.


8. Dividenden
Gleiche Popup-Logik wie Verkauf:

System zeigt Brutto-Dividende (aus yfinance oder manuell eingetragen)
Nutzer gibt tatsächlich erhaltenen Betrag ein
Differenz = Steuer
Betrag geht aufs Verrechnungskonto

Dividendenkalender: Zeigt nur vergangene Dividenden aus dem Transaktionslog als einfache Liste pro Monat. Keine Prognose, keine Vorhersage zukünftiger Dividenden.


9. Charts
Depotwert-Verlauf (Liniendiagramm):

Gesamtdepotwert über Zeit
Benchmark-Vergleich als gestrichelte Linie (z.B. MSCI World, wählbar)
Zeitraum-Umschaltung: 1M, 3M, 6M, 1J, Max
Historische Kursdaten werden lokal gecacht (yfinance Rate-Limits, Offline-Nutzung)

Einzelposition-Chart: Klick auf eine Position (via ⋯-Menü → "Chart anzeigen") zeigt den Kursverlauf dieser Position im gleichen Chart-Bereich.

Allocation Pie/Donut-Chart:

Ist-Verteilung nach Asset-Klasse
Bargeld (Verrechnungskonto) als eigene Scheibe
Zweiter Modus: Soll vs. Ist (Soll-Werte vom Nutzer definiert, als zweiter Ring im Donut)


10. Watchlist
Watchlist-Positionen leben in der gleichen Tabelle wie echte Positionen, aber ausgegraut und ohne Wert/Anteile. Nur Ticker, Name, aktueller Kurs.

Durchschalt-Button oben neben der Tabelle:

Drei Zustände: Alle → Positionen → Watchlist → Alle ...
Ein Button, kein Dropdown
Textlabel daneben zeigt den aktuellen Filter


11. Orderhistorie / Transaktionslog
Chronologische Liste aller Buchungen im Sub-Tab "Orderhistorie":

Typ
Beschreibung
Kauf
Manueller Kauf einer Position
Verkauf
Teilverkauf oder Vollverkauf
Sparplan
Automatisch ausgeführter Sparplan-Kauf
Dividende
Erhaltene Dividendenzahlung
Übertrag rein
Geld vom Haushaltsbuch ins Depot
Übertrag raus
Geld vom Depot ins Haushaltsbuch


Jeder Eintrag: Datum, Typ, Ticker, Anzahl, Kurs, Betrag, Broker.


12. Prognose-Rechner ("Spielwiese")
Eigener Dialog/Popup, erreichbar über einen Button im Portfolio-Fenster.

Vorbefüllung: Übernimmt aktuelle Werte — Depotwert, aktive Sparpläne, monatliche Sparrate.

Einstellbare Parameter:

Erwartete jährliche Rendite (Slider, z.B. 3–12%)
Anlagehorizont (Slider, z.B. 1–40 Jahre)
Monatliche Sparrate (anpassbar, auch dynamisierbar: z.B. "+50 EUR/Jahr")
Einmalzahlungen (optional)

Ausgabe: Liniendiagramm mit projiziertem Depotwert über Zeit. Motivierend, nicht bindend — kein "Ziel", sondern "Was wäre wenn".


13. Erstbefüllung (Schnelleingabe)
Für Nutzer, die bereits ein Depot haben: einfaches Tabellen-Formular zum Durchtippen.

Pro Zeile: Ticker | Datum | Anzahl | Kaufkurs

Kein CSV-Import in v1. Zielgruppe hat typischerweise 3–15 Positionen — in 10 Minuten eingetippt.


14. UI-Übersicht
┌─────────────────────────────────────────────────┐

│  [Haushaltsbuch]  [Portfolio ←aktiv]            │

├─────────────────────────────────────────────────┤

│                                                 │

│  24.831,47 EUR              [Watchlist] [+ Pos] │

│  +1.247,83 (+5,29%) gesamt                      │

│                                                 │

│  ┌──────────┐┌──────────┐┌──────────┐┌────────┐ │

│  │Investiert││Divid. YTD││Verrechn. ││Real.G/V│ │

│  │23.583,64 ││312,50    ││1.450,00  ││+580,20 │ │

│  └──────────┘└──────────┘└──────────┘└────────┘ │

│                                                 │

│  ┌─── Depotwert-Verlauf ──┐ ┌── Allocation ──┐ │

│  │ [1M][3M][6M][1J][Max]  │ │   Donut-Chart  │ │

│  │ ───── Depot            │ │  (Ist / Soll)  │ │

│  │ - - - Benchmark        │ │                │ │

│  └────────────────────────┘ └────────────────┘ │

│                                                 │

│  [Positionen] [Sparpläne] [Orderhistorie]       │

│  ┌─────────────────────────────────────────────┐│

│  │ IWDA.AS  │ 142,3 │ 82,14 │ +9,6%  │  ⋯   ││

│  │ AAPL 🔄  │ 18    │198,50 │ +13,4% │  ⋯   ││

│  │ BTC-EUR  │ 0,045 │62.500 │ -6,3%  │  ⋯   ││

│  │ NVDA 👁  │  —    │875,30 │   —    │  ⋯   ││

│  └─────────────────────────────────────────────┘│

│                                                 │

│  [⟳ Alle ▸]  Prognose-Rechner: [📈 Spielwiese] │

└─────────────────────────────────────────────────┘

⋯-Menü pro Zeile: Kaufen · Verkaufen · Sparplan anlegen · Chart anzeigen · Zur Watchlist · Broker ändern · Löschen


15. Währung
Nur EUR in v1. Kurse für USD-notierte Wertpapiere werden automatisch in EUR umgerechnet angezeigt.


16. Bewusst ausgeschlossen (v1)
Feature
Grund
Geplant für
TTWROR / IZF
Komplex, fehleranfällig, geringer Mehrwert in v1
Update 2+
Kursalarme
UI-Aufwand, Benachrichtigungssystem nötig
Update 3
Chartanalyse
Trader-Feature, nicht Zielgruppe
Update 3
Rebalancing-Vorschläge
Gestrichen
—
Dividenden-Prognose
Unzuverlässige Daten, falsche Erwartungen
—
CSV-Import
Broker-spezifische Formate = Wartungs-Albtraum
Evtl. später
Multi-Depot
"Alles auf einer Sicht" ist das Konzept
—
Multi-Währung
Erstmal nur EUR
Update 2+
Export (CSV/PDF)
Noch offen, Priorität unklar
Offen



17. Technische Eckpunkte
Runtime: Python, Flask (für Webview falls nötig), Tkinter (GUI)
Packaging: PyInstaller --onefile --noconsole --icon=KassenwartPro.ico
Datenformat: JSON (wie Haushaltsbuch)
Charting in Tkinter: matplotlib + FigureCanvasTkAgg oder tkchart
Kurs-Cache: Lokale Speicherung historischer Kurse, tägliches Update bei App-Start
API-Keys: In lokaler Config-Datei, nicht hardcoded
Datei-Struktur: portfolio_tracker.py (Hauptmodul), portfolio_data.py (Datenmodell), portfolio_api.py (Datenquellen-Adapter)


18. Zielgruppe & Positionierung
Long-Term-Investoren. ETF-lastig, vereinzelte Aktien, etwas Krypto. Kein Trading, kein Daytrading. Das Tool dient dem Vermögensaufbau — die Alternative zum klassischen "Schaffen, Sparen, Haus kaufen", das für viele nicht mehr funktioniert.

Kernaussage: Alles auf einer Sicht — Haushaltsbuch und Depot in einer App. Wissen, wo das Geld bleibt UND wo es wächst.

