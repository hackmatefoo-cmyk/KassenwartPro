# CLAUDE.md — Projektbriefing für Claude Code

## Projekt

**Kassenwart Pro** — Windows-Desktop-Haushaltsbuch + Portfolio Tracker.
Python/Flask-App, verpackt als .exe via PyInstaller.
Vertrieb: 15€ Einmalkauf, deutscher Markt.

Produkt & Philosophie
KassenwartPro ist eine Windows-Desktop-App für privates Haushaltsbudget — lokal, offline, ohne Bankverbindung, ohne Abo.
Kernprinzip: Preis-Leistungs-Effizienz durch bewusste Reduktion.
Das Produkt kostet einmalig 15 € und bietet genau die Features, die ein Normalhaushalt täglich braucht — nicht mehr. Jedes Feature hat einen Platz, weil es einen echten Nutzen hat, nicht weil es die Feature-Liste verlängert. Das ist kein Mangel, das ist das Konzept.
Zielgruppe: Privatpersonen in Deutschland, die ihre Einnahmen und Ausgaben im Blick behalten wollen — ohne sich mit Banking-Apps, Datenweitergabe oder Abo-Modellen auseinandersetzen zu müssen.
Bewusste Abgrenzung:

WISO Haushaltsbuch: überladen, viele Funktionen die kaum jemand nutzt
Finanzguru / Banking-Apps: erfordern Bankzugang, Cloud, laufende Kosten
YNAB: teures Abo (~100 €/Jahr), englischsprachig, für den deutschen Markt nicht optimiert

KassenwartPro ist die Alternative für Nutzer, die ein Werkzeug wollen — kein Ökosystem



## Architektur

- **Runtime:** Python + Flask (lokaler Webserver) + Browser-UI (HTML/CSS/JS)
- **Packaging:** `pyinstaller --onefile --noconsole --icon=KassenwartPro.ico KassenwartPro_app.py`
- **Datenhaltung:** JSON-Dateien im selben Verzeichnis wie die .exe
- **Kein Server, kein Cloud, kein Login** — alles läuft lokal
- **Packaging: PyInstaller --onefile --noconsole --icon=KassenwartPro.ico
- **Build-Befehl: pyinstaller --onefile --noconsole --icon=KassenwartPro.ico KassenwartPro_app.py
- **Datenhaltung: Lokale JSON- und .dat-Dateien, kein Server, keine Cloud
- **Distribution: GitHub Releases (früher .zip jetzt direkt .exe zum download), Stripe Einmalkauf

Lizenz- & Revoke-System

Aktivierung schreibt HWID-Check in check.dat
Background-Daemon prüft alle 15 Tage gegen den Server
Nach 3 × "valid" (~45 Tage): permanently_valid = True → keine weiteren Pings
10 × Offline-Fehler (~150 Tage) → Blocking
"Revoked"-Antwort → Fullscreen-HTML-Lockout via before_request-Interceptor


Verkaufs-Infrastruktur

Zahlungen: Stripe (Einmalkauf, live)
Webhook: Google Apps Script → Google Sheets (Tabs: Lizenzen, Verkaeufe, Refunds)
Lizenzauslieferung: Automatische Gmail-Delivery nach Stripe-Webhook
Bewertungen: Trustpilot AFS via BCC




## Dateistruktur

```
KassenwartPro/
├── KassenwartPro_app.py          # Hauptdatei (Flask + Haushaltsbuch)
├── portfolio_tracker.py          # Portfolio-Modul (NEU, wird gebaut)
├── portfolio_data.py             # Portfolio-Datenmodell (NEU)
├── portfolio_api.py              # Datenquellen-Adapter (NEU)
├── templates/                    # HTML-Templates (Jinja2)
│   ├── index.html                # Haushaltsbuch-UI
│   └── portfolio.html            # Portfolio-UI (NEU)
├── static/                       # CSS, JS, Bilder
├── docs/                         # Spezifikationen, Pläne
│   ├── Portfolio_Tracker_Spezifikation_v1.md
│   └── Programmierplan_Portfolio_Tracker.md
├── CLAUDE.md                     # Diese Datei
├── index.html                    # Landing Page (GitHub Pages)
└── KassenwartPro.ico             # App-Icon
```

## Datendateien (zur Laufzeit, neben der .exe)

| Datei | Inhalt |
|-------|--------|
| `app.dat` | Lizenzschlüssel + Aktivierungsdaten |
| `config.dat` | Benutzereinstellungen, Kategorien, Budgets |
| `check.dat` | Lizenz-Revoke-Prüfstatus |
| `portfolio.dat` | **NEU** — Alle Portfolio-Daten (Positionen, Lots, Transaktionen, Sparpläne, Watchlist, Cash) |
| `cache.dat` | **NEU** — Gecachte Kursdaten für Offline-Nutzung |
| `wal.dat` | **NEU** — Write-Ahead-Log für atomare Überträge (Phase 5) |

## ⚠️ KRITISCHE Regeln

### PyInstaller-Pfade
Alle Dateipfade müssen über `os.path.dirname(sys.executable)` aufgelöst werden.
Wenn eine neue .dat-Datei eingeführt wird, muss der Pfad auch im `__main__`-Block
von KassenwartPro_app.py als globale Variable gesetzt werden. Beispiel:
```python
if __name__ == '__main__':
    BASE_DIR = os.path.dirname(sys.executable)
    LICENSE_FILE = os.path.join(BASE_DIR, 'app.dat')
    CONFIG_FILE = os.path.join(BASE_DIR, 'config.dat')
    CHECK_FILE = os.path.join(BASE_DIR, 'check.dat')
    PORTFOLIO_FILE = os.path.join(BASE_DIR, 'portfolio.dat')  # NEU
    CACHE_FILE = os.path.join(BASE_DIR, 'cache.dat')          # NEU
```
**Das wird leicht vergessen und führt zu schwer findbaren Bugs.**

### Kein Feature-Bloat
Die App ist bewusst einfach. Keine überflüssigen Features, keine unnötigen Abhängigkeiten.

### Erst reden, dann coden
Bei größeren Architekturentscheidungen: erst mit Simon besprechen, nicht eigenständig umbauen.

### Error Handling
Kein Crash bei fehlender Internetverbindung. Immer Fallback auf Cache oder Fehlermeldung.

### Keine API-Keys im Code
Alle Keys kommen in die lokale Config-Datei, nie hardcoded.

## Code-Stil

- **Sprache im Code:** Englisch (Variablen, Funktionen, Kommentare)
- **Sprache in der UI:** Deutsch (alle Texte die der Nutzer sieht)
- **Einrückung:** 4 Spaces
- **Dateinamen:** snake_case
- **Kein Overengineering:** Einfache Lösungen bevorzugen

## Portfolio Tracker — Kurzreferenz

### Haupt-Keys in portfolio.dat
`version` · `cash_account` · `positions` · `savings_plans` · `transactions`

### Transaktionstypen (Keys → UI-Label)
`buy` → Kauf | `sell` → Verkauf | `savings_plan` → Sparplan-Ausführung | `dividend` → Dividende | `transfer_in` → Übertrag ins Depot | `transfer_out` → Übertrag aus dem Depot

### Asset-Klassen
`stock` → Aktie | `etf` → ETF | `crypto` → Krypto | `precious_metal` → Edelmetall | `commodity` → Rohstoff | `bond` → Anleihe | `cash` → Bargeld

### Sparplan-Intervalle
`weekly` · `biweekly` · `monthly` · `quarterly` · `semiannual` · `yearly`

### Datenquellen (v1)
| Asset-Klasse | Quelle | API-Key? |
|---|---|---|
| Aktien, ETFs, Indizes | yfinance | Nein |
| Krypto | CoinGecko | Ja (Free-Plan) |
| Edelmetalle | Metals API | Ja |
| ISIN → Ticker | OpenFIGI | Ja |

### FIFO-Pflicht
Teilverkäufe verbrauchen immer die ältesten Lots zuerst (§ 20 Abs. 4 S. 7 EStG).

### Verkauf/Dividende
Kein Steuermodell. Der Nutzer gibt den "tatsächlich erhaltenen" Betrag ein, die Differenz zum Brutto wird als Steuer verbucht.

## Nicht anfassen (ohne Rücksprache)

- `KassenwartPro_app.py` — Kernlogik des Haushaltsbuchs (nur für Budget-Brücke in Phase 5)
- Lizenz-System (app.dat, check.dat, Aktivierung)
- Landing Page (index.html) — separate Pflege
- Apps Script / Stripe-Webhook — läuft separat

## Vollständige Spezifikation

Siehe `docs/Portfolio_Tracker_Spezifikation_v1.md` für alle Details zu:
Architektur, Lot-Tracking, Sparplan-Logik, Charts, Watchlist, Prognose-Rechner, UI-Layout.



Entwicklungs-Regeln
Erst reden, dann coden. Bei größeren Änderungen immer erst Plan besprechen, dann implementieren.
Kein Feature-Bloat. Jedes neue Feature muss einen konkreten Nutzen für die Zielgruppe haben. Funktionalität um ihrer selbst willen kommt nicht rein.
Code-Edits: Exakte Zeilennummern + Suchsnippet + gezielter Ersetzungsblock. Keine Full-File-Rewrites außer wenn zwingend nötig.
PyInstaller-Regel: Neue Datei-Pfade (CHECK_FILE, LICENSE_FILE etc.) immer sofort in __main__ als globale Pfadvariable eintragen.
Stripe-Webhook-Regel: Beim Ändern der Endpoint-URL muss whsec_-Secret neu abgerufen werden — nicht kopieren.
Dateibenennung: Versionssuffix als Zahl (_flask_2.py, _flask_2_1.py).
Sprache: Kommunikation und Kommentare auf Deutsch. UI-Texte auf Deutsch.

Hosting & Services
ZweckServiceLanding PageGitHub Pages (kassenwartpro.de)Live-DemoPythonAnywhereEXE-DistributionGitHub ReleasesDomainIONOS (kassenwartpro.de)SEOGoogle Search Console (verifiziert)PaymentsStripeAutomationGoogle Apps Script

Positionierung (für Marketingtexte)
Unpersönlicher Stil (keine direkte Du/Dein-Ansprache auf der Landing Page). Ehrliche Vergleiche statt Superlative. Die Einfachheit ist ein USP, keine Einschränkung.
Kernaussage Portfolio-Modul: Alles auf einer Sicht — Haushaltsbuch und Depot in einer App. Wissen, wo das Geld bleibt UND wo es wächst.
