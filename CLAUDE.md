# CLAUDE.md — Projektbriefing für Claude Code

## Projekt

**Kassenwart Pro** — Windows-Desktop-Haushaltsbuch + Portfolio Tracker.
Python/Flask-App, verpackt als .exe via PyInstaller.
Vertrieb: 15€ Einmalkauf, deutscher Markt.

## Architektur

- **Runtime:** Python + Flask (lokaler Webserver) + Browser-UI (HTML/CSS/JS)
- **Packaging:** `pyinstaller --onefile --noconsole --icon=KassenwartPro.ico KassenwartPro_app.py`
- **Datenhaltung:** JSON-Dateien im selben Verzeichnis wie die .exe
- **Kein Server, kein Cloud, kein Login** — alles läuft lokal

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
