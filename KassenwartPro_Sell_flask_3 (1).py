#!/usr/bin/env python3
import json
import os
import hmac
import hashlib
from datetime import datetime
from flask import Flask, request, Response
import time
import subprocess
import urllib.request
import urllib.parse
import win32com.client

app = Flask(__name__)

import sys as _sys

def _get_base_dir():
    """Gibt das Installationsverzeichnis zurück (neben der .exe oder .py)."""
    if getattr(_sys, 'frozen', False):
        # Läuft als .exe (PyInstaller)
        exe_dir = os.path.dirname(_sys.executable)
        # Prüfen ob bereits installiert (install.dat vorhanden)
        marker = os.path.join(exe_dir, 'install.dat')
        if os.path.exists(marker):
            with open(marker, 'r', encoding='utf-8') as f:
                install_dir = f.read().strip()
            if os.path.isdir(install_dir):
                return install_dir
        return exe_dir
    else:
        # Läuft als .py (Entwicklung)
        return os.path.dirname(os.path.abspath(__file__))

BASE_DIR          = _get_base_dir()
SETTINGS_FILE     = os.path.join(BASE_DIR, 'config.dat')
TRANSACTIONS_FILE = os.path.join(BASE_DIR, 'data.dat')
LEGACY_FILE       = os.path.join(BASE_DIR, 'budget_data.json')

DEFAULT_SETTINGS = {
    "categories": [
        {"name": "Gehalt",               "kind": "fix"},
        {"name": "Miete & Nebenkosten",  "kind": "fix"},
        {"name": "Kommunikation",        "kind": "fix"},
        {"name": "Versicherung & Sparen","kind": "fix"},
        {"name": "Rücklagen",            "kind": "fix", "system": True},
        {"name": "Lebensmittel",         "kind": "variabel"},
        {"name": "Freizeit & Extras",    "kind": "variabel"},
        {"name": "Kleidung",             "kind": "variabel"},
        {"name": "Persönlich",           "kind": "variabel"},
        {"name": "Mobilität / Tanken",   "kind": "variabel"}
    ],
    "fixed_templates": [
        {
            "desc": "Gehalt", "amount": 70.0, "category": "Gehalt", "type": "in", "day": 1
        }
    ],
    "reserves_sub": [
        {
            "name": "Reparatur",
            "amount": 60.0,
            "freq": "yearly",
            "due_day": 10,
            "due_month": 8,
            "paid": False
        }
    ],
    "initial_cash":     0.0,
    "cash_min":         100.0,
    "initial_reserves": 10.0,
    "reserves_goal":    25.0,
    "initial_date":     datetime.now().strftime("%Y-%m-%d"),
    "budget_goals": {
    "Miete & Nebenkosten": 1,
    "Lebensmittel":      1,
    "Freizeit & Extras": 1,
    "Kleidung":          1,
    },
    "rollover_config": {}
    }

DEFAULT_TRANSACTIONS = {
    "transactions":    [],
    "monthly_archive": [],
    "recurring":       []
}

def _migrate_fields(d):
    fix_names = ['miete','strom','gas','wasser','versicherung','kredit',
                 'gehalt','kindergeld','rente','ruecklagen','internet',
                 'telefon','kommunikation','gez','rundfunk']
    def guess_kind(name):
        return 'fix' if any(f in name.lower() for f in fix_names) else 'variabel'
    if d.get("categories") and isinstance(d["categories"][0], str):
        d["categories"] = [{"name": c, "kind": guess_kind(c)} for c in d["categories"]]
    # Migration: "Ruecklagen" -> "Rücklagen" + system-Flag setzen
    for cat in d.get("categories", []):
        if isinstance(cat, dict) and cat.get("name") in ("Ruecklagen", "Rücklagen"):
            cat["name"] = "Rücklagen"
            cat["system"] = True
    for sub in d.get("reserves_sub", []):
        sub.setdefault("due_day",   1)
        sub.setdefault("due_month", 1)
        sub.setdefault("paid",      False)
    if "cash" in d and "initial_cash" not in d:
        d["initial_cash"] = d.pop("cash", 5000.0)
    if "cash_start" in d and "initial_cash" not in d:
        d["initial_cash"] = d.pop("cash_start")
    if "reserves" in d and "initial_reserves" not in d:
        d["initial_reserves"] = d.pop("reserves", 0.0)
    if "reserves_start" in d and "initial_reserves" not in d:
        d["initial_reserves"] = d.pop("reserves_start")
    d.pop("last_month", None)
    d.setdefault("initial_date", datetime.now().strftime("%Y-%m-%d"))
    return d

def _write_settings(data):
    s = {k: data[k] for k in DEFAULT_SETTINGS if k in data}
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)

def _write_transactions(data):
    t = {k: data[k] for k in DEFAULT_TRANSACTIONS if k in data}
    with open(TRANSACTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(t, f, indent=2, ensure_ascii=False)

def load_data():
    settings     = {k: v for k, v in DEFAULT_SETTINGS.items()}
    transactions = {k: v for k, v in DEFAULT_TRANSACTIONS.items()}

    # Migration: alte Einzeldatei -> zwei neue Dateien
    if os.path.exists(LEGACY_FILE) and not os.path.exists(SETTINGS_FILE):
        with open(LEGACY_FILE, "r", encoding="utf-8") as f:
            legacy = json.load(f)
        legacy = _migrate_fields(legacy)
        for k in DEFAULT_SETTINGS:
            if k in legacy:
                settings[k] = legacy[k]
        for k in DEFAULT_TRANSACTIONS:
            if k in legacy:
                transactions[k] = legacy[k]
        _write_settings(settings)
        _write_transactions(transactions)
    else:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                s = json.load(f)
            s = _migrate_fields(s)
            for k, v in DEFAULT_SETTINGS.items():
                s.setdefault(k, v)
            settings = s
        if os.path.exists(TRANSACTIONS_FILE):
            with open(TRANSACTIONS_FILE, "r", encoding="utf-8") as f:
                t = json.load(f)
            for k, v in DEFAULT_TRANSACTIONS.items():
                t.setdefault(k, v)
            transactions = t

    data = {}
    data.update(settings)
    data.update(transactions)
    return data

def save_data(data):
    _write_settings(data)
    _write_transactions(data)


HTML = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Kassenwart Pro</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #e4ebe6;
  --card: #ffffff;
  --primary: #4a7c68;
  --primary-light: #7aad99;
  --text: #1a2a24;
  --muted: #6b8278;
  --border: #cdd8d2;
  --green: #2d6e4a;
  --red: #a83a3f;
  --orange: #c47a2a;
  --shadow: 0 3px 16px rgba(0,0,0,0.09);
}
body { font-family: system-ui,-apple-system,sans-serif; background:var(--bg); padding:20px; color:var(--text); font-size:14px; line-height:1.5; }

.header { display:flex; align-items:center; justify-content:center; margin-bottom:20px; position:relative; }
.header h1 { font-weight:700; font-size:1.1rem; color:var(--text); letter-spacing:0.04em; text-transform:uppercase; }
.header-month { font-size:0.9rem; color:var(--muted); margin-left:12px; font-weight:500; }
.settings-btn {
  position:absolute; right:0; z-index:50;
  background:var(--card); border:1px solid var(--border); border-radius:10px;
  width:42px; height:42px; font-size:1.15rem; cursor:pointer;
  display:flex; align-items:center; justify-content:center;
  box-shadow:var(--shadow); color:var(--muted); transition:background 0.15s,color 0.15s;
}
.settings-btn:hover { background:#f0f4f2; color:var(--primary); }
.settings-btn .warn-dot {
  position:absolute; top:6px; right:6px;
  width:9px; height:9px; border-radius:50%;
  background:var(--red); display:none;
}
.settings-btn .warn-dot.visible { display:block; }

.main { max-width:1380px; margin:auto; display:grid; grid-template-columns:260px 1fr 340px; gap:18px; align-items:start; }
.left-col { display:flex; flex-direction:column; gap:16px; }

.card { background:var(--card); border-radius:14px; box-shadow:var(--shadow); padding:20px; border:1px solid var(--border); }

.big-val { font-size:1.85rem; font-weight:700; color:var(--text); margin:6px 0 2px; letter-spacing:-0.02em; }
.big-val.good { color:var(--green); }
.big-val.warn { color:var(--red); }
.card-label { font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:0.08em; color:var(--muted); margin-bottom:2px; }

/* Savings bar (inverted: under goal = red, over = green) */
.bar-wrap { margin-top:12px; }
.bar-row { display:flex; justify-content:space-between; font-size:0.76rem; color:var(--muted); margin-bottom:4px; }
.bar-track { height:8px; background:#dde7e2; border-radius:999px; overflow:visible; position:relative; }
.bar-fill { height:100%; border-radius:999px; transition:width 0.4s ease; }
.bar-fill.savings-ok { background:linear-gradient(90deg,var(--green),#5aad7a); }
.bar-fill.savings-warn { background:linear-gradient(90deg,var(--red),var(--orange)); }

/* Budget bar with goal marker */
.budget-bar-wrap { position:relative; height:10px; background:#dde7e2; border-radius:999px; overflow:visible; margin:5px 0 2px; }
.budget-bar-fill { height:100%; border-radius:999px; transition:width 0.4s; max-width:110%; }
.budget-bar-fill.ok { background:linear-gradient(90deg,var(--primary),var(--primary-light)); }
.budget-bar-fill.at-goal { background:linear-gradient(90deg,var(--green),#5aad7a); }
.budget-bar-fill.over { background:linear-gradient(90deg,var(--red),var(--orange)); }
.budget-spent.at-goal { color:var(--green); }
.budget-bar-fill.neutral { background:#cdd8d2; }
.budget-spent.neutral { color:var(--muted); }
.budget-goal-marker { position:absolute; top:-3px; width:3px; height:16px; background:var(--text); border-radius:2px; opacity:0.35; }

/* Budget section */
.budget-section-title {
  font-size:0.7rem; font-weight:700; text-transform:uppercase;
  letter-spacing:0.08em; color:var(--muted); margin:0 0 12px;
  padding-bottom:6px; border-bottom:1px solid var(--border);
}
.budget-section-gap { margin-top:24px; border-top:2px solid var(--border); padding-top:16px; }
.budget-item { margin-bottom:14px; }
.budget-row { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:0; }
.budget-name { font-weight:500; font-size:0.88rem; }
.budget-spent { font-size:0.82rem; font-weight:700; }
.budget-spent.ok { color:var(--green); }
.budget-spent.over { color:var(--red); }
.budget-goal-label { font-size:0.76rem; color:var(--muted); }

/* Summary */
.summary { display:flex; justify-content:space-around; background:var(--card); padding:14px; border-radius:13px; margin-bottom:16px; box-shadow:var(--shadow); border:1px solid var(--border); }
.stat { text-align:center; }
.stat .lbl { font-size:0.72rem; color:var(--muted); display:block; margin-bottom:2px; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; }
.stat .val { font-size:1.2rem; font-weight:700; }
.pos { color:var(--green); }
.neg { color:var(--red); }

/* Form */
.form-group { margin-bottom:10px; }
.form-group label { display:block; font-size:0.76rem; color:var(--muted); margin-bottom:3px; font-weight:600; }
input[type=text],input[type=number],input[type=date],select {
  width:100%; padding:9px 12px; border-radius:8px; border:1px solid var(--border);
  font-size:14px; background:#f6f9f7; color:var(--text); transition:border-color 0.15s;
}
input:focus,select:focus { outline:none; border-color:var(--primary-light); background:#fff; }

.btn { display:block; width:100%; padding:10px 16px; border-radius:8px; border:none; font-size:14px; font-weight:600; cursor:pointer; transition:opacity 0.15s; margin-top:8px; }
.btn:hover { opacity:0.87; }
.btn-primary { background:var(--primary); color:white; }
.btn-secondary { background:#5a7eb0; color:white; }
.btn-sm { display:inline-block; width:auto; padding:4px 10px; font-size:12px; border-radius:6px; border:none; cursor:pointer; font-weight:600; background:#e8b4b6; color:var(--red); transition:opacity 0.15s; }
.btn-sm:hover { opacity:0.8; }
.btn-month { background:var(--red); color:white; border:none; border-radius:7px; padding:5px 12px; font-size:12px; font-weight:600; cursor:pointer; }

/* Filter */
.filter-bar { display:flex; gap:8px; margin-bottom:14px; align-items:center; }
.filter-bar select { margin:0; padding:7px 10px; font-size:13px; flex:1; }
.filter-label { font-size:0.72rem; color:var(--muted); font-weight:700; text-transform:uppercase; letter-spacing:0.05em; white-space:nowrap; }
.filter-reset { background:none; border:1px solid var(--border); border-radius:7px; padding:6px 10px; font-size:12px; color:var(--muted); cursor:pointer; }
.filter-reset:hover { color:var(--primary); border-color:var(--primary-light); }

/* Table */
table { width:100%; border-collapse:collapse; }
thead th { font-size:0.7rem; font-weight:700; text-transform:uppercase; letter-spacing:0.06em; color:var(--muted); padding:8px 6px; border-bottom:2px solid var(--border); text-align:left; }
tbody td { padding:8px 6px; border-bottom:1px solid #eef2f0; font-size:0.88rem; vertical-align:middle; }
tbody tr:last-child td { border-bottom:none; }
.td-date { color:var(--muted); font-size:0.78rem; white-space:nowrap; }
.td-cat { color:var(--muted); font-size:0.8rem; }
.td-cat.inactive { color:#bbb; font-style:italic; }
.td-amt { font-weight:700; white-space:nowrap; }

/* Collapse */
.collapse-card { background:var(--card); border-radius:14px; box-shadow:var(--shadow); border:1px solid var(--border); overflow:hidden; }
.collapse-header { display:flex; justify-content:space-between; align-items:center; padding:16px 20px; cursor:pointer; user-select:none; transition:background 0.15s; }
.collapse-header:hover { background:#f6faf7; }
.collapse-header .clabel { font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:0.08em; color:var(--muted); }
.collapse-arrow { font-size:0.75rem; color:var(--muted); transition:transform 0.2s; }
.collapse-arrow.open { transform:rotate(180deg); }
.collapse-body { display:none; padding:0 20px 20px; }
.collapse-body.open { display:block; }

/* Sparquote */
.sparquote-row { display:flex; gap:12px; margin-bottom:16px; }
.sq-box { flex:1; background:#f4f8f5; border-radius:10px; padding:10px 12px; text-align:center; border:1px solid var(--border); }
.sq-val { font-size:1.1rem; font-weight:700; color:var(--primary); }
.sq-val.neg  { color:var(--red); }
.sq-val.good { color:var(--green); }
.sq-abs { font-size:0.78rem; color:var(--muted); margin-top:2px; }
.sq-lbl { font-size:0.68rem; color:var(--muted); font-weight:600; text-transform:uppercase; letter-spacing:0.05em; margin-top:3px; }

/* Month table */
.month-table { width:100%; border-collapse:collapse; font-size:0.78rem; table-layout:fixed; }
.month-table th { text-align:right; padding:5px 6px; color:var(--muted); font-weight:600; border-bottom:1px solid var(--border); white-space:nowrap; }
.month-table th:first-child { text-align:left; }
.month-table td { text-align:right; padding:5px 6px; border-bottom:1px solid #eef2f0; white-space:nowrap; }
.month-table td:first-child { text-align:left; font-weight:500; white-space:normal; word-break:break-word; }
.month-table col.col-cat  { width:auto; }
.month-table col.col-amt  { width:80px; }
.month-table col.col-trend{ width:36px; }
.month-table tr:last-child td { border-bottom:none; }
.trend-up    { color:var(--red);   font-size:1.05rem; font-weight:900; }
.trend-up2   { color:#e8845a;      font-size:1.05rem; font-weight:900; }
.trend-eq    { color:var(--muted); font-size:1.05rem; font-weight:900; }
.trend-down2 { color:#5aaa6e;      font-size:1.05rem; font-weight:900; }
.trend-down  { color:var(--green); font-size:1.05rem; font-weight:900; }
.avg-neutral { font-weight:600; color:var(--text); }
.no-archive { text-align:center; color:var(--muted); font-size:0.82rem; padding:12px 0; }

/* Rücklagen Unterpositionen */
.sub-goal { margin-top:10px; padding-top:10px; border-top:1px solid var(--border); }
.sub-goal-row { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:3px; font-size:0.82rem; }
.sub-goal-name { color:var(--text); font-weight:500; }
.sub-goal-nums { color:var(--muted); font-size:0.76rem; }
.sub-goal-hint { font-size:0.72rem; color:var(--primary); font-style:italic; }

/* Fixkosten collapsible in budget */
.budget-fix-header {
  display:flex; justify-content:space-between; align-items:center;
  cursor:pointer; user-select:none; padding:4px 0 8px;
}
.budget-fix-header:hover .budget-section-title { color:var(--primary); }
.budget-fix-toggle { font-size:0.7rem; color:var(--muted); transition:transform 0.2s; }
.budget-fix-toggle.open { transform:rotate(180deg); }
.budget-fix-body { display:none; }
.budget-fix-body.open { display:block; }

/* Modal */
.modal-bg { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.5); align-items:center; justify-content:center; z-index:300; }
.modal-bg.open { display:flex; }
.modal-box { background:var(--card); border-radius:16px; padding:28px; width:500px; max-width:95vw; max-height:90vh; overflow-y:auto; box-shadow:0 20px 60px rgba(0,0,0,0.22); }
.modal-box.wide { width:640px; }
.modal-title { font-size:1.05rem; font-weight:700; color:var(--primary); margin-bottom:20px; padding-bottom:12px; border-bottom:1px solid var(--border); }
.modal-actions { display:flex; gap:10px; margin-top:20px; }
.modal-actions .btn { margin:0; }

/* Settings tabs */
.stab-bar { display:flex; gap:4px; margin-bottom:20px; border-bottom:2px solid var(--border); flex-wrap:wrap; }
.stab { padding:7px 12px; border-radius:8px 8px 0 0; border:none; background:transparent; color:var(--muted); font-size:12px; font-weight:600; cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-2px; }
.stab.active { color:var(--primary); border-bottom-color:var(--primary); }
.stab-panel { display:none; }
.stab-panel.active { display:block; }

.section-row { display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid #eef2f0; font-size:0.88rem; }
.section-row:last-child { border-bottom:none; }
.divider { border:none; border-top:1px solid var(--border); margin:16px 0; }
.empty-hint { text-align:center; color:var(--muted); padding:20px; font-size:0.88rem; }
.add-row { display:flex; gap:8px; margin-top:12px; align-items:flex-end; flex-wrap:wrap; }
.add-row .form-group { margin:0; flex:1; min-width:100px; }
.add-row .btn { margin:0; width:auto; padding:9px 16px; flex-shrink:0; }

/* Fixkosten warning row */
.fix-warn-row { display:flex; justify-content:space-between; align-items:center; background:#fff3f3; border:1px solid #f5c6cb; border-radius:8px; padding:10px 14px; margin-bottom:16px; font-size:0.88rem; }
.fix-warn-row .fix-warn-text { color:var(--red); font-weight:600; }

/* Fixkosten modal list */
.fix-item { display:grid; grid-template-columns:1fr 80px 120px; gap:8px; align-items:center; padding:8px 0; border-bottom:1px solid #eef2f0; font-size:0.88rem; }
.fix-item:last-child { border-bottom:none; }
.fix-item-name { font-weight:500; }
.fix-item-amt { color:var(--muted); font-size:0.82rem; }

/* Right column */
.right-col { display:flex; flex-direction:column; gap:0; }

/* Avg range buttons */
.avg-btn {
  padding:4px 10px; border-radius:6px; border:1px solid var(--border);
  background:#f4f8f5; color:var(--muted); font-size:12px; font-weight:600;
  cursor:pointer; transition:all 0.15s;
}
.avg-btn:hover { background:var(--primary); color:white; border-color:var(--primary); }
.avg-btn.active { background:var(--primary); color:white; border-color:var(--primary); }
/* Rollover Info Icon */
.rollover-info {
  display:inline-flex;align-items:center;justify-content:center;
  width:16px;height:16px;border-radius:50%;font-size:10px;font-weight:700;
  cursor:help;margin-left:6px;position:relative;
}
.rollover-info.positive { background:#d4ecd8;color:var(--green); }
.rollover-info.negative { background:#f5d4d4;color:var(--red); }
.rollover-tooltip {
  display:none;position:absolute;bottom:calc(100% + 6px);left:50%;transform:translateX(-50%);
  background:#1a2a24;color:#fff;padding:8px 12px;border-radius:8px;font-size:12px;
  white-space:nowrap;z-index:100;font-weight:500;line-height:1.5;
  box-shadow:0 4px 12px rgba(0,0,0,0.15);
}
.rollover-tooltip::after {
  content:'';position:absolute;top:100%;left:50%;transform:translateX(-50%);
  border:6px solid transparent;border-top-color:#1a2a24;
}
.rollover-info:hover .rollover-tooltip { display:block; }
</style>
</head>
<body>



<div class="header">
  <h1>Kassenwart Pro</h1>
  <button class="settings-btn" onclick="openSettings()" title="Einstellungen">
    &#9881;<span class="warn-dot" id="warnDot"></span>
  </button>
</div>

<div class="main">

  <!-- LINKE SPALTE -->
  <div class="left-col">

    <div class="card">
      <div class="card-label">Konto</div>
      <div class="big-val" id="cashDisplay">&#8211;</div>
      <div class="bar-wrap">
        <div class="bar-row"><span>Reserve</span><span id="cashBarLabel">&#8211;</span></div>
        <div class="budget-bar-wrap">
          <div class="budget-bar-fill ok" id="cashFill" style="width:0%"></div>
          <div class="budget-goal-marker" id="cashMarker" style="left:85%"></div>
        </div>
      </div>
    </div>

    <!-- Auswertung: Haushaltsplan immer sichtbar, darunter aufklappbar -->
    <div class="collapse-card">
      <div style="padding:16px 20px 14px;">
        <div class="clabel" style="margin-bottom:10px;">Auswertung</div>
        <div style="font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.07em;color:var(--muted);margin-bottom:8px;">Haushaltsplan (Soll)</div>
        <div id="haushaltsplan"></div>
      </div>
      <div class="collapse-header" onclick="toggleAuswertung()" style="padding:10px 20px;border-top:1px solid var(--border);">
        <span class="clabel">&#216; Durchschnitt &amp; Sparquote</span>
        <span class="collapse-arrow" id="auswArrow">&#9660;</span>
      </div>
      <div class="collapse-body" id="auswBody">
        <div style="display:flex;gap:6px;margin-bottom:14px;">
          <button class="avg-btn active" id="avgBtn3" onclick="setAvgRange(3)">3 Mo.</button>
          <button class="avg-btn" id="avgBtn6" onclick="setAvgRange(6)">6 Mo.</button>
          <button class="avg-btn" id="avgBtn12" onclick="setAvgRange(12)">12 Mo.</button>
        </div>
        <div class="sq-box" style="margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;flex-direction:row;padding:10px 14px;">
          <div>
            <div class="sq-lbl" id="sqAvgLbl" style="text-align:left;">Schnitt 3 Mo.</div>
            <div class="sq-abs" id="sqAvgAbs" style="text-align:left;"></div>
          </div>
          <div class="sq-val" id="sqAvg">&#8211;</div>
        </div>
        <div style="font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.07em;color:var(--muted);margin-bottom:8px;">&#216; Ausgaben je Kategorie</div>
        <div id="monthTableWrap"></div>
      </div>
    </div>

  </div>

  <!-- MITTE -->
  <div>
    <div class="summary">
      <div class="stat" style="display:flex;flex-direction:column;align-items:center;justify-content:center;">
        <span class="lbl">Monat</span>
        <select id="filterMonthTop" onchange="syncMonth(this.value)" style="margin-top:4px;padding:4px 8px;font-size:13px;font-weight:600;border-radius:7px;border:1px solid var(--border);background:#f6f9f7;color:var(--primary);cursor:pointer;max-width:100px;"><option value="">Alle</option></select>
      </div>
      <div class="stat"><span class="lbl">Einnahmen</span><span class="val pos" id="sumIn">0,00 &#8364;</span></div>
      <div class="stat"><span class="lbl">Ausgaben</span><span class="val neg" id="sumOut">0,00 &#8364;</span></div>
      <div class="stat"><span class="lbl">Saldo</span><span class="val" id="sumSaldo">0,00 &#8364;</span></div>
      <div class="stat">
        <span class="lbl" id="sqCurrentLbl">Sparquote</span>
        <span class="val" id="sqCurrent">&#8211;</span>
        <div class="sq-abs" id="sqCurrentAbs" style="font-size:0.72rem;color:var(--muted);"></div>
      </div>
    </div>

    <div class="card">
      <div style="font-size:1rem;font-weight:700;color:var(--primary);margin-bottom:14px;">Neue Buchung</div>
      <div id="fixWarnBar" style="display:none;" class="fix-warn-row">
        <span class="fix-warn-text">&#9888; Fixkosten fehlen diesen Monat</span>
        <button class="btn-sm" style="background:#f5c6cb;color:var(--red);" onclick="openFixModal()">Übernehmen</button>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
        <div class="form-group"><label>Beschreibung</label><input type="text" id="desc" placeholder="z.B. Rewe, Miete..."></div>
        <div class="form-group"><label>Betrag (&#8364;)</label><input type="number" id="amount" placeholder="0,00" step="0.01" min="0"></div>
        <div class="form-group"><label>Kategorie</label><select id="category"></select></div>
        <div class="form-group"><label>Typ</label><select id="type"><option value="out">Ausgabe</option><option value="in">Einnahme</option></select></div>
      </div>
      <div class="form-group"><label>Datum</label><input type="date" id="date"></div>
      <button class="btn btn-primary" onclick="addTransaction()">Hinzufügen</button>
    </div>

    <div class="card" style="margin-top:16px;">
      <div style="margin-bottom:12px;">
        <div style="font-size:1rem;font-weight:700;color:var(--primary);">Transaktionen</div>
      </div>
      <div class="filter-bar">
        <span class="filter-label">Filter:</span>
        <select id="filterMonthBottom" onchange="syncMonth(this.value)"><option value="">Alle Monate</option></select>
        <select id="filterCat" onchange="renderTransactions()"><option value="">Alle Kategorien</option></select>
        <button class="filter-reset" onclick="resetFilter()">&#10005; Reset</button>
      </div>
      <table>
        <thead><tr><th>Datum</th><th>Beschreibung</th><th>Kategorie</th><th>Betrag</th><th></th></tr></thead>
        <tbody id="transList"></tbody>
      </table>
      <div id="transEmpty" class="empty-hint" style="display:none;">Keine Buchungen gefunden.</div>
    </div>
  </div>

  <!-- RECHTS -->
  <div class="right-col">

    <div class="card" style="margin-bottom:18px;">
      <div style="font-size:1rem;font-weight:700;color:var(--primary);margin-bottom:16px;">Budget-Übersicht</div>
      <div id="budgetVariable"></div>
      <div id="budgetFixed"></div>
      <div id="budgetEmpty" class="empty-hint" style="display:none;">Keine Budgetziele.<br>Einstellungen &#8594; Budgetziele.</div>
    </div>

    <div class="card">
      <div class="card-label">Rücklagen</div>
      <div style="display:flex;align-items:baseline;justify-content:space-between;margin:6px 0 2px;">
        <div class="big-val" id="resDisplay">&#8211;</div>
        <div id="resMonthlyRate" style="font-size:0.85rem;font-weight:600;color:var(--muted);white-space:nowrap;"></div>
      </div>
      <div class="bar-wrap">
        <div class="bar-row"><span>Sparziel <span id="resGoalAuto" style="font-size:0.7rem;color:var(--primary);font-style:italic;"></span></span><span id="resBarLabel">&#8211;</span></div>
        <div class="budget-bar-wrap">
          <div class="budget-bar-fill ok" id="resFill" style="width:0%"></div>
          <div class="budget-goal-marker" id="resMarker" style="left:75%"></div>
        </div>
      </div>
      <div id="resSubSection" style="display:none;">
        <div class="budget-fix-header" onclick="toggleResSub()" style="margin-top:12px;padding:6px 0 4px;">
          <span style="font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.07em;color:var(--muted);">Unterpositionen</span>
          <span class="budget-fix-toggle" id="resSubArrow">&#9660;</span>
        </div>
        <div class="budget-fix-body" id="resSubBody"></div>
      </div>
    </div>

  </div>

</div>

<!-- Modal: Einstellungen -->
<div id="settingsModal" class="modal-bg">
  <div class="modal-box wide">
    <div class="modal-title">&#9881; Einstellungen</div>
    <div class="stab-bar">
      <button class="stab active" onclick="switchTab('tabKonten')">Konten</button>
      <button class="stab" onclick="switchTab('tabKategorien')">Kategorien</button>
      <button class="stab" onclick="switchTab('tabBudget')">Budgetziele</button>
      <button class="stab" onclick="switchTab('tabRollover')">Rollover</button>
      <button class="stab" onclick="switchTab('tabFixkosten')">Fixkosten <span id="fixTabDot" style="display:none;color:var(--red);">&#9679;</span></button>
      <button class="stab" onclick="switchTab('tabRuecklagen')">Rücklagen</button>
      <button class="stab" onclick="switchTab('tabVerwaltung')">Daten</button>
    </div>

    <div id="tabKonten" class="stab-panel active">
      <div style="font-size:0.78rem;font-weight:700;text-transform:uppercase;letter-spacing:0.07em;color:var(--muted);margin-bottom:10px;">Reserve</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
        <div class="form-group"><label>Initialbestand (&#8364;)</label><input type="number" id="s_initialCash" step="0.01"></div>
        <div class="form-group"><label>Mindestbestand (&#8364;)</label><input type="number" id="s_cashMin" step="10"></div>
      </div>
      <hr class="divider">
      <div style="font-size:0.78rem;font-weight:700;text-transform:uppercase;letter-spacing:0.07em;color:var(--muted);margin-bottom:10px;">Rücklagen</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
        <div class="form-group"><label>Initialbestand (&#8364;)</label><input type="number" id="s_initialReserves" step="0.01"></div>
        <div class="form-group"><label>Sparziel (&#8364;) <span id="s_resGoalHint" style="font-size:0.72rem;color:var(--primary);font-style:italic;"></span></label><input type="number" id="s_resGoal" step="10"></div>
      </div>
    </div>

    <div id="tabKategorien" class="stab-panel">
      <div id="settingsCatList"></div>
      <div class="add-row" style="margin-top:14px;">
        <div class="form-group"><label>Name</label><input type="text" id="s_newCat" placeholder="Neue Kategorie..."></div>
        <div class="form-group"><label>Art</label>
          <select id="s_newCatKind"><option value="variabel">Variabel</option><option value="fix">Fix</option></select>
        </div>
        <button class="btn btn-primary" onclick="addCategory()" style="margin-top:0;align-self:flex-end;">Hinzufuegen</button>
      </div>
    </div>
    <div id="tabRollover" class="stab-panel">
      <div style="font-size:0.82rem;color:var(--muted);margin-bottom:16px;">Übertrage nicht verbrauchtes Budget automatisch in den nächsten Monat. Nur Kategorien mit Budgetziel werden angezeigt.</div>
      <div id="settingsRolloverList"></div>
      <div id="rolloverEmpty" class="empty-hint" style="display:none;">Keine Kategorien mit Budgetziel vorhanden.</div>
    </div>
    <div id="tabBudget" class="stab-panel">
      <div id="settingsBudgetList"></div>
      <div style="font-size:0.78rem;color:var(--muted);margin-top:12px;">Klicke &#9998; um ein Ziel zu setzen oder zu aendern.</div>
    </div>

    <div id="tabFixkosten" class="stab-panel">
      <div style="font-size:0.82rem;color:var(--muted);margin-bottom:16px;">Hinterlege hier regelmaessige Buchungen. Am Monatsanfang kannst du alle fehlenden mit einem Klick uebernehmen.</div>
      <div id="settingsFixList"></div>
      <hr class="divider">
      <div style="font-size:0.78rem;color:var(--muted);margin-bottom:8px;font-weight:600;">Neue Vorlage</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
        <div class="form-group"><label>Beschreibung</label><input type="text" id="s_fixDesc" placeholder="z.B. Miete, Gehalt..."></div>
        <div class="form-group"><label>Betrag (&#8364;)</label><input type="number" id="s_fixAmt" step="0.01" placeholder="0,00"></div>
        <div class="form-group"><label>Kategorie</label><select id="s_fixCat"></select></div>
        <div class="form-group"><label>Typ</label><select id="s_fixType"><option value="out">Ausgabe</option><option value="in">Einnahme</option></select></div>
        <div class="form-group"><label>Fälligkeitstag</label><input type="number" id="s_fixDay" min="1" max="31" value="1" placeholder="1-31"></div>
      </div>
      <button class="btn btn-primary" onclick="addFixTemplate()">Vorlage speichern</button>
    </div>

    <div id="tabRuecklagen" class="stab-panel">
      <div style="font-size:0.82rem;color:var(--muted);margin-bottom:16px;">Hinterlege jaehrliche oder quartalsweise Ausgaben. Die App berechnet die monatliche Sparempfehlung automatisch.</div>
      <div id="settingsResSubList"></div>
      <hr class="divider">
      <div style="font-size:0.78rem;color:var(--muted);margin-bottom:8px;font-weight:600;">Neue Unterposition</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;">
        <div class="form-group"><label>Name</label><input type="text" id="s_subName" placeholder="z.B. KFZ-Versicherung"></div>
        <div class="form-group"><label>Jahresbetrag (&#8364;)</label><input type="number" id="s_subAmt" step="10" placeholder="z.B. 480"></div>
        <div class="form-group"><label>Fälligkeit</label>
          <select id="s_subFreq">
            <option value="yearly">Jährlich</option>
            <option value="halfyear">Halbjährlich</option>
            <option value="quarterly">Quartalsweise</option>
          </select>
        </div>
        <div class="form-group"><label>Fälligkeitstag</label><input type="number" id="s_subDay" min="1" max="31" value="1" placeholder="1-31"></div>
        <div class="form-group"><label>Fälligkeitsmonat</label>
          <select id="s_subMonth">
            <option value="1">Januar</option><option value="2">Februar</option>
            <option value="3">März</option><option value="4">April</option>
            <option value="5">Mai</option><option value="6">Juni</option>
            <option value="7">Juli</option><option value="8">August</option>
            <option value="9">September</option><option value="10">Oktober</option>
            <option value="11">November</option><option value="12">Dezember</option>
          </select>
        </div>
      </div>
      <button class="btn btn-primary" onclick="addResSub()">Unterposition speichern</button>
    </div>

    <div id="tabVerwaltung" class="stab-panel">
      <div style="font-size:0.82rem;color:var(--muted);margin-bottom:16px;">Buchungen und Daten verwalten. Aktionen können nicht rückgängig gemacht werden.</div>

      <div style="font-size:0.78rem;font-weight:700;text-transform:uppercase;letter-spacing:0.07em;color:var(--muted);margin-bottom:10px;">Buchungen löschen</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:10px;">
        <div class="form-group">
          <label>Zeitraum</label>
          <select id="del_scope" onchange="updateDelScope()">
            <option value="all">Alle</option>
            <option value="year">Nach Jahr</option>
            <option value="month">Nach Monat</option>
          </select>
        </div>
        <div class="form-group" id="del_year_wrap" style="display:none;">
          <label>Jahr</label>
          <select id="del_year"></select>
        </div>
        <div class="form-group" id="del_month_wrap" style="display:none;">
          <label>Monat</label>
          <select id="del_month">
            <option value="01">Januar</option><option value="02">Februar</option>
            <option value="03">März</option><option value="04">April</option>
            <option value="05">Mai</option><option value="06">Juni</option>
            <option value="07">Juli</option><option value="08">August</option>
            <option value="09">September</option><option value="10">Oktober</option>
            <option value="11">November</option><option value="12">Dezember</option>
          </select>
        </div>
      </div>
      <button class="btn" style="background:var(--orange);color:white;margin-bottom:20px;" onclick="deleteTransactions()">Buchungen löschen</button>

      <hr class="divider">
      <div style="font-size:0.78rem;font-weight:700;text-transform:uppercase;letter-spacing:0.07em;color:var(--muted);margin-bottom:10px;">Archiv löschen</div>
      <button class="btn" style="background:var(--orange);color:white;margin-bottom:20px;" onclick="deleteArchive()">Gesamtes Archiv löschen</button>

      <hr class="divider">
      <div style="font-size:0.78rem;font-weight:700;text-transform:uppercase;letter-spacing:0.07em;color:var(--red);margin-bottom:10px;">Komplett-Reset</div>
      <div style="font-size:0.82rem;color:var(--muted);margin-bottom:10px;">Löscht alle Daten inkl. Kategorien, Ziele und Einstellungen.</div>
      <button class="btn btn-danger" style="background:var(--red);color:white;" onclick="fullReset()">Alles zurücksetzen</button>
    </div>

    <div class="modal-actions">
      <button class="btn btn-primary" onclick="saveSettings()">Speichern &amp; Schließen</button>
      <button class="btn" style="background:#aaa;color:white;" onclick="closeSettings()">Abbrechen</button>
    </div>
  </div>
</div>

<!-- Modal: Fixkosten übernehmen -->
<div id="fixModal" class="modal-bg">
  <div class="modal-box wide">
    <div class="modal-title">&#9888; Fehlende Buchungen übernehmen</div>
    <div style="font-size:0.85rem;color:var(--muted);margin-bottom:16px;">Wähle Datum für jede Buchung und bestätige.</div>
    <div id="fixModalList"></div>
    <div class="modal-actions">
      <button class="btn btn-primary" onclick="applyFixTemplates()">Alle übernehmen</button>
      <button class="btn" style="background:#aaa;color:white;" onclick="closeFixModal()">Abbrechen</button>
    </div>
  </div>
</div>

<!-- Modal: Zahlung bestätigen -->
<div id="payModal" class="modal-bg">
  <div class="modal-box">
    <div class="modal-title">&#10003; Zahlung bestätigen</div>
    <div id="payModalName" style="font-weight:600;color:var(--text);margin-bottom:4px;font-size:1rem;"></div>
    <div id="payModalHint" style="font-size:0.82rem;color:var(--muted);margin-bottom:16px;"></div>
    <div class="form-group">
      <label>Tatsächlich bezahlter Betrag (&#8364;)</label>
      <input type="number" id="payModalAmt" step="0.01" min="0">
    </div>
    <div class="form-group">
      <label>Datum</label>
      <input type="date" id="payModalDate">
    </div>
    <div class="modal-actions">
      <button class="btn btn-primary" onclick="confirmPayResSub()">Bezahlen &amp; buchen</button>
      <button class="btn" style="background:#aaa;color:white;" onclick="closePayModal()">Abbrechen</button>
    </div>
  </div>
</div>
<!-- Modal: Rollover Setup -->
<div id="rolloverSetupModal" class="modal-bg">
  <div class="modal-box">
    <div class="modal-title">Rollover aktivieren</div>
    <div id="rolloverSetupName" style="font-weight:600;color:var(--text);margin-bottom:4px;font-size:1rem;"></div>
    <div style="font-size:0.82rem;color:var(--muted);margin-bottom:16px;">Lege fest, ab wann der Rollover starten soll und ob ein Startguthaben vorhanden ist.</div>
    <div class="form-group">
      <label>Startmonat (JJJJ-MM)</label>
      <input type="month" id="rolloverSetupMonth">
    </div>
    <div class="form-group">
      <label>Startguthaben (€) — kann auch negativ sein</label>
      <input type="number" id="rolloverSetupBalance" step="0.01" value="0">
    </div>
    <div class="modal-actions">
      <button class="btn btn-primary" onclick="confirmRolloverSetup()">Aktivieren</button>
      <button class="btn" style="background:#aaa;color:white;" onclick="closeRolloverSetup()">Abbrechen</button>
    </div>
  </div>
</div>
<!-- Modal: Wiederkehrend -->
<div id="recModal" class="modal-bg">
  <div class="modal-box">
    <div class="modal-title">Wiederkehrende Buchung</div>
    <div id="recModalText" style="margin-bottom:16px;font-weight:500;color:var(--muted);font-size:0.92rem;"></div>
    <div class="form-group"><label>Häufigkeit</label>
      <select id="recFreq">
        <option value="monthly">Monatlich</option>
        <option value="quarterly">Quartalsweise</option>
        <option value="halfyear">Halbjährlich</option>
        <option value="yearly">Jährlich</option>
      </select>
    </div>
    <div class="form-group"><label>Fällig am Tag des Monats</label><input type="number" id="recDay" min="1" max="31" value="1"></div>
    <div class="modal-actions">
      <button class="btn btn-primary" onclick="saveRecurring()">Speichern</button>
      <button class="btn" style="background:#aaa;color:white;" onclick="closeRecModal()">Abbrechen</button>
    </div>
  </div>
</div>

<script>


var data = {};
var avgRange = 3; // Standard: 3 Monate

function setAvgRange(n) {
  avgRange = n;
  ['3','6','12'].forEach(function(x) {
    var btn = document.getElementById('avgBtn'+x);
    if (btn) btn.classList.toggle('active', parseInt(x) === n);
  });
  var lbl = document.getElementById('sqAvgLbl');
  if (lbl) lbl.textContent = 'Schnitt ' + n + ' Mo.';
  var trans = currentMonth
    ? (data.transactions||[]).filter(function(t){ return t.date && t.date.slice(0,7) === currentMonth; })
    : (data.transactions||[]);
  renderAuswertung(trans);
}

function fmt(n) { return parseFloat(n||0).toFixed(2).replace('.',',') + ' \u20ac'; }
function todayStr() { return new Date().toISOString().split('T')[0]; }
function fmtDate(d) {
  if (!d) return '\u2013';
  var p = d.split('-');
  return p.length === 3 ? p[2]+'.'+p[1]+'.'+p[0].slice(2) : d;
}
function monthLabel(ym) {
  if (!ym) return '';
  var p = ym.split('-');
  var mn = ['Januar','Februar','März','April','Mai','Juni','Juli','August','September','Oktober','November','Dezember'];
  return mn[parseInt(p[1])-1] + ' ' + p[0];
}
function monthLabelShort(ym) {
  if (!ym) return '';
  var p = ym.split('-');
  var mn = ['Jan','Feb','Mrz','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez'];
  return mn[parseInt(p[1])-1] + ' ' + p[0].slice(2);
}
function catNames() { return (data.categories||[]).map(function(c){return c.name;}); }
function catByName(name) { return (data.categories||[]).find(function(c){return c.name===name;}); }

async function loadData() {
  try {
    var r = await fetch('/get_data');
    if (!r.ok) throw new Error('HTTP '+r.status);
    data = await r.json();
    processRollover();
    renderAll();
  } catch(e) { alert('Laden fehlgeschlagen: '+e.message); }
}

async function saveData() {
  try {
    var r = await fetch('/save_data', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)
    });
    if (!r.ok) throw new Error('HTTP '+r.status);
    renderAll();
  } catch(e) { alert('Speichern fehlgeschlagen: '+e.message); }
}

function calcCash() {
  var start = parseFloat(data.initial_cash||0), delta = 0;
  (data.transactions||[]).forEach(function(t) {
    var amt = parseFloat(t.amount||0);
    if (t.category === 'Ruecklagen-Zahlung') return; // Sparkonto-intern, kein Einfluss auf Notgroschen
    if (t.category === 'Rücklagen') {
      delta += t.type === 'out' ? -amt : amt;
    } else {
      delta += t.type === 'in' ? amt : -amt;
    }
  });
  return start + delta;
}

function calcReserves() {
  var start = parseFloat(data.initial_reserves||0), delta = 0;
  (data.transactions||[]).forEach(function(t) {
    var amt = parseFloat(t.amount||0);
    if (t.category === 'Rücklagen') {
      // Einzahlung aufs Sparkonto: out = Geld geht rein, in = Rueckbuchung
      delta += t.type === 'out' ? amt : -amt;
    } else if (t.category === 'Ruecklagen-Zahlung') {
      // Zahlung vom Sparkonto: out = Geld verlässt Sparkonto
      delta += t.type === 'out' ? -amt : amt;
    }
  });
  return start + delta;
}

function calcSparquote(transactions) {
  var inc = 0, out = 0;
  (transactions||[]).forEach(function(t) {
    var amt = parseFloat(t.amount||0);
    if (t.category === 'Ruecklagen-Zahlung') return; // Sparkonto-intern ignorieren
    if (t.category === 'Rücklagen') {
      if (t.type === 'out') out += amt;
      else inc += amt;
    } else {
      if (t.type === 'in') inc += amt; else out += amt;
    }
  });
  if (inc <= 0) return null;
  var pct = Math.round(((inc-out)/inc)*100);
  var abs = inc - out;
  return {pct: pct, abs: abs};
}

function checkFixWarning() {
  var templates = data.fixed_templates || [];
  if (templates.length === 0) return false;
  var trans = data.transactions || [];
  var fm = currentMonth || new Date().toISOString().slice(0,7);
  var missing = templates.filter(function(tpl) {
    return !trans.some(function(t) {
      return t.desc === tpl.desc && t.category === tpl.category
        && t.date && t.date.slice(0,7) === fm;
    });
  });
  return missing.length > 0;
}

function getSelectedTrans() {
  return data.transactions || [];
}

// Gemeinsamer Monatsstatus — beide Dropdowns lesen/schreiben hier
var currentMonth = new Date().toISOString().slice(0,7);
var lastSollSq = null; // Soll-Sparquote fuer Ist-Faerbung

function syncMonth(val) {
  currentMonth = val;
  var top = document.getElementById('filterMonthTop');
  var bot = document.getElementById('filterMonthBottom');
  if (top) top.value = val;
  if (bot) bot.value = val;
  renderAll();
}

function onMonthChange() {
  renderAll();
}

function renderAll() {
  var allTrans = data.transactions || [];
  var goals = data.budget_goals || {};
  var fm = currentMonth;

  // Gefilterte Transaktionen fuer Summary/Budget/Auswertung
  var trans = fm
    ? allTrans.filter(function(t){ return t.date && t.date.slice(0,7) === fm; })
    : allTrans;


  var cash = calcCash();
  var cashMin = parseFloat(data.cash_min||0);
  var cashOk = cash >= cashMin;
  var CMARKER = 75;
  var cashPerc = cashMin > 0
    ? (cash <= cashMin ? (cash/cashMin)*CMARKER : Math.min(CMARKER+((cash-cashMin)/cashMin)*(100-CMARKER), 100))
    : CMARKER;
  var cashEl = document.getElementById('cashDisplay');
  cashEl.textContent = fmt(cash);
  cashEl.className = 'big-val ' + (cashOk ? 'good' : 'warn');
  document.getElementById('cashBarLabel').textContent = fmt(cashMin);
  var cf = document.getElementById('cashFill');
  cf.style.width = cashPerc + '%';
  cf.className = 'budget-bar-fill ' + (cashOk ? 'ok' : 'over');
  var cm = document.getElementById('cashMarker');
  if (cm) cm.style.left = CMARKER + '%';

  // Ruecklagen
  var res = calcReserves();
  var resGoal = parseFloat(data.reserves_goal||0);
  var resOk = res >= resGoal;
  var RMARKER = 75;
  var resPerc = resGoal > 0
    ? (res <= resGoal ? (res/resGoal)*RMARKER : Math.min(RMARKER+((res-resGoal)/resGoal)*(100-RMARKER), 100))
    : 0;
  var resEl = document.getElementById('resDisplay');
  resEl.textContent = fmt(res);
  resEl.className = 'big-val ' + (resOk ? 'good' : 'warn');
  // Monatliche Sparrate aus Unterpositionen
  var subs = data.reserves_sub || [];
  var totalMonthly = subs.reduce(function(s,g){ return s + parseFloat(g.amount||0)/12; }, 0);
  var rateEl = document.getElementById('resMonthlyRate');
  if (rateEl) rateEl.textContent = totalMonthly > 0 ? totalMonthly.toFixed(0) + ' €/Mon.' : '';
  // Balken-Label: nur Sparziel
  document.getElementById('resBarLabel').textContent = fmt(resGoal);
  var rf = document.getElementById('resFill');
  rf.style.width = resPerc + '%';
  rf.className = 'budget-bar-fill ' + (resOk ? 'ok' : 'over');
  var rm = document.getElementById('resMarker');
  if (rm) rm.style.left = RMARKER + '%';

  // Ruecklagen Unterpositionen
  renderResSubGoals(res);

  // Datum
  if (!document.getElementById('date').value) document.getElementById('date').value = todayStr();

  // Kategorie-Dropdown
  var names = catNames();
  var catSel = document.getElementById('category');
  var curCat = catSel.value;
  catSel.innerHTML = names.map(function(n){return '<option value="'+n+'">'+n+'</option>';}).join('');
  if (names.includes('Lebensmittel')) catSel.value = 'Lebensmittel';
  else if (curCat && names.includes(curCat)) catSel.value = curCat;

  // Fixkosten Warnung
  var hasWarn = checkFixWarning();
  document.getElementById('warnDot').className = 'warn-dot' + (hasWarn ? ' visible' : '');
  document.getElementById('fixTabDot').style.display = hasWarn ? 'inline' : 'none';
  document.getElementById('fixWarnBar').style.display = hasWarn ? 'flex' : 'none';

  // Filter
  renderFilterDropdowns(trans, names);
  renderTransactions();

  // Summary - Ruecklagen-Zahlung raus (Sparkonto-intern), Ruecklagen laeuft durch
  var inSum = 0, outSum = 0;
  trans.forEach(function(t) {
    if (t.category === 'Ruecklagen-Zahlung') return;
    var amt = parseFloat(t.amount||0);
    if (t.type === 'in') inSum += amt; else outSum += amt;
  });
  document.getElementById('sumIn').textContent = fmt(inSum);
  document.getElementById('sumOut').textContent = fmt(outSum);
  var saldo = inSum - outSum;
  var saldoEl = document.getElementById('sumSaldo');
  saldoEl.textContent = fmt(Math.abs(saldo));
  saldoEl.className = 'val ' + (saldo >= 0 ? 'pos' : 'neg');

  // Budget
  renderBudget(trans, goals);

  // Ist-Sparquote im Header
  var sqHeader = calcSparquote(trans);
  var sqCurEl = document.getElementById('sqCurrent');
  var sqCurAbsEl = document.getElementById('sqCurrentAbs');
  var sqCurLblEl = document.getElementById('sqCurrentLbl');
  if (sqCurLblEl) sqCurLblEl.textContent = fm ? monthLabelShort(fm) : 'Alle';
  if (sqHeader !== null) {
    sqCurEl.textContent = sqHeader.pct + '%';
    var sqClass = 'val';
    if (lastSollSq !== null) {
      sqClass += sqHeader.pct >= lastSollSq ? ' pos' : ' neg';
    } else {
      sqClass += sqHeader.pct < 0 ? ' neg' : '';
    }
    sqCurEl.className = sqClass;
    if (sqCurAbsEl) sqCurAbsEl.textContent = fmt(sqHeader.abs);
  } else {
    sqCurEl.textContent = '–';
    sqCurEl.className = 'val';
    if (sqCurAbsEl) sqCurAbsEl.textContent = '';
  }

  // Auswertung
  renderAuswertung(trans);
}

function renderFilterDropdowns(trans, catNamesList) {
  var months = {};
  (data.transactions||[]).forEach(function(t) { if(t.date) months[t.date.slice(0,7)] = true; });
  // Aktuellen Kalendermonat immer einfügen (auch wenn keine Buchungen)
  var nowYM = new Date().toISOString().slice(0,7);
  months[nowYM] = true;
  var sorted = Object.keys(months).sort().reverse().slice(0,36);
  if (currentMonth === undefined || (currentMonth !== '' && !sorted.includes(currentMonth))) {
    currentMonth = sorted.includes(nowYM) ? nowYM : (sorted[0] || '');
  }
  var optionsHtml = '<option value="">Alle Monate</option>';
  sorted.forEach(function(ym) {
    optionsHtml += '<option value="'+ym+'">'+monthLabelShort(ym)+'</option>';
  });
  var top = document.getElementById('filterMonthTop');
  var bot = document.getElementById('filterMonthBottom');
  if (top) { top.innerHTML = optionsHtml; top.value = currentMonth; }
  if (bot) { bot.innerHTML = optionsHtml; bot.value = currentMonth; }
  var fCat = document.getElementById('filterCat');
  var curC = fCat.value;
  fCat.innerHTML = '<option value="">Alle Kategorien</option>';
  catNamesList.forEach(function(c) { fCat.innerHTML += '<option value="'+c+'">'+c+'</option>'; });
  if (curC) fCat.value = curC;
}

function renderTransactions() {
  var trans = getSelectedTrans();
  var names = catNames();
  var fm = currentMonth;
  var fc = document.getElementById('filterCat').value;
  var filtered = trans.filter(function(t) {
    return (!fm || (t.date && t.date.slice(0,7) === fm)) && (!fc || t.category === fc);
  });
  var tbody = document.getElementById('transList');
  tbody.innerHTML = '';
  filtered.slice().sort(function(a,b){ return (b.date||'').localeCompare(a.date||''); }).forEach(function(t) {
    var origIdx = data.transactions.indexOf(t);
    var amt = parseFloat(t.amount||0);
    var catOk = names.includes(t.category);
    var row = document.createElement('tr');
    row.id = 'trow_'+origIdx;
    row.innerHTML =
      '<td class="td-date">'+fmtDate(t.date)+'</td>'+
      '<td>'+t.desc+'</td>'+
      '<td class="td-cat'+(catOk?'':' inactive')+'">'+t.category+(catOk?'':' \u2715')+'</td>'+
      '<td class="td-amt '+(t.type==='in'?'pos':'neg')+'">'+(t.type==='in'?'+':'\u2212')+amt.toFixed(2).replace('.',',')+'</td>'+
      '<td style="display:flex;gap:4px;">'+
        '<button class="btn-sm" style="background:#d4ecd8;color:var(--green);" onclick="editTrans('+origIdx+')">&#9998;</button>'+
        '<button class="btn-sm" onclick="deleteTrans('+origIdx+')">&#215;</button>'+
      '</td>';
    tbody.appendChild(row);
  });
  document.getElementById('transEmpty').style.display = filtered.length === 0 ? 'block' : 'none';
}

function resetFilter() {
  var nowYM = new Date().toISOString().slice(0,7);
  document.getElementById('filterCat').value = '';
  syncMonth(nowYM);
}

function renderBudget(trans, goals) {
  var cats = data.categories || [];
  var incomeNames = (data.fixed_templates||[]).filter(function(t){return t.type==='in';}).map(function(t){return t.category;});
  var varCats = cats.filter(function(c){return c.kind==='variabel'  && incomeNames.indexOf(c.name)===-1 && (goals[c.name]||0) > 0;});
  var fixCats = cats.filter(function(c){return c.kind==='fix'  && incomeNames.indexOf(c.name)===-1 && (goals[c.name]||0) > 0;});

  function sortByGoal(list) {
    return list.slice().sort(function(a,b){ return (goals[b.name]||0) - (goals[a.name]||0); });
  }
  varCats = sortByGoal(varCats);
  fixCats = sortByGoal(fixCats);

  function renderBlock(container, catList, title) {
    if (catList.length === 0) { container.innerHTML = ''; return; }
    var items = catList.map(function(cat) {
      var goal = goals[cat.name] || 0;
      var spent = trans.filter(function(t){return t.category===cat.name && t.type==='out';})
        .reduce(function(s,t){return s+parseFloat(t.amount||0);},0);
      var MARKER = 75;
      var hasGoal = goal > 0;
      var overThresh = hasGoal && spent > goal * 1.1;
      var atGoal = hasGoal && spent >= goal && !overThresh;
      var fillPerc = hasGoal
        ? (spent <= goal ? (spent/goal)*MARKER : Math.min(MARKER+((spent-goal)/goal)*MARKER, 100))
        : (spent > 0 ? 30 : 0); // keine Ziel: zeige kleinen Balken wenn was ausgegeben
      var fillClass = !hasGoal ? 'budget-bar-fill neutral'
        : overThresh ? 'budget-bar-fill over'
        : atGoal ? 'budget-bar-fill at-goal'
        : 'budget-bar-fill ok';
      var spentClass = !hasGoal ? 'budget-spent neutral'
        : overThresh ? 'budget-spent over'
        : atGoal ? 'budget-spent at-goal'
        : 'budget-spent ok';
      var goalLabel = hasGoal ? '/ '+goal+' \u20ac' : '/ \u2013';
      return '<div class="budget-item">'+
          '<div class="budget-row">'+
           '<span class="budget-name">'+cat.name+getRolloverIcon(cat.name)+'</span>'+
            '<span>'+
              '<span class="'+spentClass+'">'+spent.toFixed(0)+'</span>'+
              ' <span class="budget-goal-label">'+goalLabel+'</span>'+
            '</span>'+
          '</div>'+
          '<div class="budget-bar-wrap">'+
            '<div class="'+fillClass+'" style="width:'+fillPerc+'%"></div>'+
            (hasGoal ? '<div class="budget-goal-marker" style="left:'+MARKER+'%"></div>' : '')+
          '</div>'+
        '</div>';
    });
    container.innerHTML = '<div class="budget-section-title">'+title+'</div>' + items.join('');
  }

  function buildCollapsibleBlock(container, catList, title, bodyId, toggleFn) {
    if (catList.length === 0) { container.innerHTML = ''; return; }
    var items = catList.map(function(cat) {
      var goal = goals[cat.name] || 0;
      var spent = trans.filter(function(t){return t.category===cat.name && t.type==='out';})
        .reduce(function(s,t){return s+parseFloat(t.amount||0);},0);
      var MARKER = 75;
      var hasGoal = goal > 0;
      var overThresh = hasGoal && spent > goal * 1.1;
      var atGoal = hasGoal && spent >= goal && !overThresh;
      var fillPerc = hasGoal
        ? (spent <= goal ? (spent/goal)*MARKER : Math.min(MARKER+((spent-goal)/goal)*MARKER, 100))
        : (spent > 0 ? 30 : 0);
      var fillClass = !hasGoal ? 'budget-bar-fill neutral'
        : overThresh ? 'budget-bar-fill over'
        : atGoal ? 'budget-bar-fill at-goal'
        : 'budget-bar-fill ok';
      var spentClass = !hasGoal ? 'budget-spent neutral'
        : overThresh ? 'budget-spent over'
        : atGoal ? 'budget-spent at-goal'
        : 'budget-spent ok';
      var goalLabel = hasGoal ? '/ '+goal+' \u20ac' : '/ \u2013';
      return '<div class="budget-item">'+
          '<div class="budget-row">'+
           '<span class="budget-name">'+cat.name+getRolloverIcon(cat.name)+'</span>'+
            '<span>'+
              '<span class="'+spentClass+'">'+spent.toFixed(0)+'</span>'+
              ' <span class="budget-goal-label">'+goalLabel+'</span>'+
            '</span>'+
          '</div>'+
          '<div class="budget-bar-wrap">'+
            '<div class="'+fillClass+'" style="width:'+fillPerc+'%"></div>'+
            (hasGoal ? '<div class="budget-goal-marker" style="left:'+MARKER+'%"></div>' : '')+
          '</div>'+
        '</div>';
    }).join('');
    var isOpen = document.getElementById(bodyId) && document.getElementById(bodyId).classList.contains('open');
    container.innerHTML =
      '<div class="budget-fix-header" onclick="'+toggleFn+'()">'+
        '<span class="budget-section-title" style="margin:0;border:none;padding:0;">'+title+'</span>'+
        '<span class="budget-fix-toggle'+(isOpen?' open':'')+'" id="'+bodyId+'Arrow">&#9660;</span>'+
      '</div>'+
      '<div class="budget-fix-body'+(isOpen?' open':'')+'" id="'+bodyId+'">'+items+'</div>';
  }

  buildCollapsibleBlock(document.getElementById('budgetVariable'), varCats, 'Variable Kosten', 'varBody', 'toggleVarBudget');
  var fixEl = document.getElementById('budgetFixed');
  if (fixCats.length > 0) {
    fixEl.classList.add('budget-section-gap');
    buildCollapsibleBlock(fixEl, fixCats, 'Fixkosten', 'fixBody', 'toggleFixBudget');
  } else {
    fixEl.classList.remove('budget-section-gap');
    fixEl.innerHTML = '';
  }
  document.getElementById('budgetEmpty').style.display = (varCats.length + fixCats.length) === 0 ? 'block' : 'none';
}

function calcHaushaltsplan() {
  var templates = data.fixed_templates || [];
  var goals = data.budget_goals || {};
  var cats = data.categories || [];

  // Geplante Einnahmen aus Fixkosten-Vorlagen Typ "in"
  var plannedInc = templates
    .filter(function(t){ return t.type === 'in'; })
    .reduce(function(s,t){ return s + parseFloat(t.amount||0); }, 0);

  // Geplante Ausgaben: Summe aller Budgetziele (nur Ausgabe-Kategorien)
  var incomeNames = templates.filter(function(t){return t.type==='in';}).map(function(t){return t.category;});
  var plannedOut = 0;
  cats.forEach(function(cat) {
    if (incomeNames.indexOf(cat.name) !== -1) return;
    if (cat.system) return; // Systemkategorien (Rücklagen) nicht zu Ausgaben zählen
    var goal = goals[cat.name] || 0;
    plannedOut += goal;
  });

  // Geplante Ruecklagen-Rate aus Unterpositionen
  var subs = data.reserves_sub || [];
  var plannedRes = subs.reduce(function(s,g){ return s + parseFloat(g.amount||0)/12; }, 0);

  // Saldo
  var plannedSaldo = plannedInc - plannedOut - plannedRes;
  var plannedSQ = plannedInc > 0 ? Math.round((plannedSaldo / plannedInc) * 100) : null;

  return {
    inc: plannedInc,
    out: plannedOut,
    res: plannedRes,
    saldo: plannedSaldo,
    sq: plannedSQ
  };
}

function renderHaushaltsplan() {
  var p = calcHaushaltsplan();
  var el = document.getElementById('haushaltsplan');
  if (!el) return;

  lastSollSq = p.sq; // global merken fuer Ist-Sparquote-Faerbung

  if (p.inc <= 0) {
    el.innerHTML = '<div style="font-size:0.78rem;color:var(--muted);text-align:center;padding:8px 0;">Hinterlege Einnahmen unter Fixkosten um den Haushaltsplan zu sehen.</div>';
    return;
  }

  var saldoOk = p.saldo >= 0;
  var rows = [
    { label: 'Einnahmen', val: p.inc, cls: 'pos', sign: '+' },
    { label: 'Ausgaben (Ziele)', val: p.out, cls: 'neg', sign: '-' },
    { label: 'Rücklagen', val: p.res, cls: 'neg', sign: '-' },
  ];

  var html = '<table style="width:100%;border-collapse:collapse;font-size:0.82rem;">';
  rows.forEach(function(r) {
    html += '<tr>'+
      '<td style="padding:4px 0;color:var(--muted);">'+r.label+'</td>'+
      '<td style="padding:4px 0;text-align:right;font-weight:600;" class="'+r.cls+'">'+
        r.sign+r.val.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g,'.')+' &#8364;'+
      '</td>'+
    '</tr>';
  });

  html +=
    '<tr style="border-top:2px solid var(--border);">'+
      '<td style="padding:6px 0 2px;font-weight:700;">Soll-Saldo</td>'+
      '<td style="padding:6px 0 2px;text-align:right;font-weight:700;" class="'+(saldoOk?'pos':'neg')+'">'+
        (saldoOk?'+':'')+p.saldo.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g,'.')+' &#8364;'+
      '</td>'+
    '</tr>'+
    '</table>';

  if (p.sq !== null) {
    html +=
      '<div style="margin-top:10px;padding:8px 12px;background:#f4f8f5;border-radius:8px;'+
        'display:flex;justify-content:space-between;align-items:center;">'+
        '<span style="font-size:0.75rem;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Soll-Sparquote</span>'+
        '<span style="font-weight:700;font-size:1rem;" class="'+(p.sq>=0?'pos':'neg')+'">'+p.sq+'%</span>'+
      '</div>';
  }

  el.innerHTML = html;
}

function renderAuswertung(trans) {
  renderHaushaltsplan();

  // Sparquote Schnitt: letzten avgRange Kalendermonate
  var allTrans = data.transactions || [];
  var now = new Date();
  var lastNmonths = [];
  for (var i = avgRange; i >= 1; i--) {
    var d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    var ym = d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0');
    lastNmonths.push(ym);
  }

  var sqVals = lastNmonths.map(function(ym) {
    var mTrans = allTrans.filter(function(t){ return t.date && t.date.slice(0,7) === ym; });
    return calcSparquote(mTrans);
  }).filter(function(v){ return v !== null; });

  var sqAvgEl = document.getElementById('sqAvg');
  var sqAvgAbsEl = document.getElementById('sqAvgAbs');
  var sqAvgLblEl = document.getElementById('sqAvgLbl');
  if (sqAvgLblEl) sqAvgLblEl.textContent = 'Schnitt ' + avgRange + ' Mo.';
  if (sqVals.length > 0) {
    var avgPct = Math.round(sqVals.reduce(function(a,b){return a+b.pct;},0)/sqVals.length);
    var avgAbs = sqVals.reduce(function(a,b){return a+b.abs;},0)/sqVals.length;
    sqAvgEl.textContent = avgPct + '%';
    sqAvgEl.className = 'sq-val' + (avgPct < 0 ? ' neg' : (lastSollSq !== null && avgPct >= lastSollSq ? ' good' : ''));
    if (sqAvgAbsEl) sqAvgAbsEl.textContent = fmt(avgAbs);
  } else {
    sqAvgEl.textContent = '\u2013';
    if (sqAvgAbsEl) sqAvgAbsEl.textContent = '';
  }

  // Durchschnittstabelle: variable Kategorien
  var wrap = document.getElementById('monthTableWrap');
  var hasAnyData = lastNmonths.some(function(ym) {
    return allTrans.some(function(t){ return t.date && t.date.slice(0,7) === ym; });
  });
  if (!hasAnyData) {
    wrap.innerHTML = '<div class="no-archive">Noch keine Verlaufsdaten vorhanden.</div>';
    return;
  }
  var cats = data.categories || [];
  var varCats = cats.filter(function(c){ return c.kind === 'variabel' && c.name !== 'Rücklagen'; });
  var goals = data.budget_goals || {};

  function budgetArrow(avg, goal) {
    if (!goal || goal <= 0) return '<span class="trend-eq">\u2192</span>';
    var diff = (avg - goal) / goal;
    if      (diff >  0.15) return '<span class="trend-up">\u2191</span>';
    else if (diff >  0.05) return '<span class="trend-up2">\u2197</span>';
    else if (diff > -0.05) return '<span class="trend-eq">\u2192</span>';
    else if (diff > -0.15) return '<span class="trend-down2">\u2198</span>';
    else                   return '<span class="trend-down">\u2193</span>';
  }

  var html = '<table class="month-table"><colgroup>' +
    '<col class="col-cat"><col class="col-amt"><col class="col-trend">' +
    '</colgroup><thead><tr>' +
    '<th style="text-align:left;">Kategorie</th>' +
    '<th>\u00d8 ' + avgRange + 'M</th>' +
    '<th></th></tr></thead><tbody>';

  var hasRows = false;
  varCats.forEach(function(cat) {
    var avgVals = lastNmonths.map(function(ym) {
      return allTrans.filter(function(t){
        return t.category===cat.name && t.type==='out' && t.date && t.date.slice(0,7)===ym;
      }).reduce(function(s,t){return s+parseFloat(t.amount||0);},0);
    });
    if (!avgVals.some(function(v){return v>0;})) return;
    hasRows = true;
    var avg = avgVals.reduce(function(a,b){return a+b;},0)/avgVals.length;
    var goal = goals[cat.name];
    html += '<tr><td>'+cat.name+'</td>'+
      '<td class="avg-neutral">'+avg.toFixed(0)+' \u20ac</td>'+
      '<td>'+budgetArrow(avg, goal)+'</td></tr>';
  });

  if (!hasRows) {
    wrap.innerHTML = '<div class="no-archive">Noch keine Verlaufsdaten vorhanden.</div>';
    return;
  }
  html += '</tbody></table>';
  wrap.innerHTML = html;
}

function toggleAuswertung() {
  document.getElementById('auswBody').classList.toggle('open');
  document.getElementById('auswArrow').classList.toggle('open');
}

// Buchung
function addTransaction() {
  var desc = document.getElementById('desc').value.trim();
  var amount = parseFloat(document.getElementById('amount').value);
  if (!desc) { alert('Beschreibung fehlt.'); return; }
  if (!amount || amount <= 0) { alert('Betrag ungültig.'); return; }
  if (!data.transactions) data.transactions = [];
  data.transactions.push({
    date: document.getElementById('date').value || todayStr(),
    desc: desc, amount: amount,
    category: document.getElementById('category').value,
    type: document.getElementById('type').value
  });
  document.getElementById('desc').value = '';
  document.getElementById('amount').value = '';
  document.getElementById('date').value = todayStr();
  saveData();
}

function deleteTrans(idx) {
  if (confirm('Buchung löschen?')) { data.transactions.splice(idx,1); saveData(); }
}
function editTrans(idx) {
  var t = data.transactions[idx];
  var names = catNames();
  var row = document.getElementById('trow_'+idx);
  if (!row) return;
  row.innerHTML =
    '<td colspan="4" style="padding:4px 6px;">'+
      '<div style="display:grid;grid-template-columns:90px 1fr 100px 90px 1fr;gap:6px;align-items:center;">'+
        '<input type="date" id="et_date_'+idx+'" value="'+t.date+'" style="margin:0;padding:5px 6px;font-size:12px;">'+
        '<input type="text" id="et_desc_'+idx+'" value="'+t.desc+'" style="margin:0;padding:5px 6px;font-size:12px;" placeholder="Beschreibung">'+
        '<input type="number" id="et_amt_'+idx+'" value="'+t.amount+'" style="margin:0;padding:5px 6px;font-size:12px;" step="0.01">'+
        '<select id="et_type_'+idx+'" style="margin:0;padding:5px 6px;font-size:12px;">'+
          '<option value="out"'+(t.type==='out'?' selected':'')+'>Ausgabe</option>'+
          '<option value="in"'+(t.type==='in'?' selected':'')+'>Einnahme</option>'+
        '</select>'+
        '<select id="et_cat_'+idx+'" style="margin:0;padding:5px 6px;font-size:12px;">'+
          names.map(function(n){return '<option value="'+n+'"'+(n===t.category?' selected':'')+'>'+n+'</option>';}).join('')+
        '</select>'+
      '</div>'+
    '</td>'+
    '<td style="display:flex;gap:4px;padding:4px 6px;">'+
      '<button class="btn-sm" style="background:#d4ecd8;color:var(--green);" onclick="saveTransEdit('+idx+')">&#10003;</button>'+
      '<button class="btn-sm" onclick="renderTransactions()">&#215;</button>'+
    '</td>';
}
function saveTransEdit(idx) {
  var date = document.getElementById('et_date_'+idx).value;
  var desc = document.getElementById('et_desc_'+idx).value.trim();
  var amt = parseFloat(document.getElementById('et_amt_'+idx).value);
  var type = document.getElementById('et_type_'+idx).value;
  var cat = document.getElementById('et_cat_'+idx).value;
  if (!desc || !amt || amt <= 0) return;
  data.transactions[idx] = {date:date||todayStr(), desc:desc, amount:amt, type:type, category:cat};
  saveData();
}

// Einstellungen
function openSettings() {
  document.getElementById('s_initialCash').value = data.initial_cash||0;
  document.getElementById('s_cashMin').value = data.cash_min||2000;
  document.getElementById('s_initialReserves').value = data.initial_reserves||0;
  var autoGoal = calcResGoalFromSubs();
  var resGoalEl = document.getElementById('s_resGoal');
  var resGoalHint = document.getElementById('s_resGoalHint');
  if (autoGoal !== null) {
    resGoalEl.value = autoGoal;
    resGoalEl.readOnly = true;
    resGoalEl.style.background = '#f0f4f2';
    if (resGoalHint) resGoalHint.textContent = '(aus Unterpositionen)';
  } else {
    resGoalEl.value = data.reserves_goal||5000;
    resGoalEl.readOnly = false;
    resGoalEl.style.background = '';
    if (resGoalHint) resGoalHint.textContent = '';
  }
  renderSettingsCats();
  renderSettingsBudget();
  renderSettingsRollover();
  renderSettingsFix();
  renderSettingsResSub();
  populateDelYears();
  switchTab('tabKonten');
  document.getElementById('settingsModal').classList.add('open');
}
function populateDelYears() {
  var years = {};
  (data.transactions||[]).forEach(function(t){ if(t.date) years[t.date.slice(0,4)] = true; });
  (data.monthly_archive||[]).forEach(function(m){ if(m.month) years[m.month.slice(0,4)] = true; });
  var sel = document.getElementById('del_year');
  sel.innerHTML = Object.keys(years).sort().reverse()
    .map(function(y){return '<option value="'+y+'">'+y+'</option>';}).join('');
}
function updateDelScope() {
  var scope = document.getElementById('del_scope').value;
  document.getElementById('del_year_wrap').style.display = (scope==='year'||scope==='month') ? 'block' : 'none';
  document.getElementById('del_month_wrap').style.display = scope==='month' ? 'block' : 'none';
}
function deleteTransactions() {
  var scope = document.getElementById('del_scope').value;
  var year = document.getElementById('del_year').value;
  var month = document.getElementById('del_month').value;
  var label = scope==='all' ? 'ALLE Buchungen' : scope==='year' ? 'alle Buchungen aus '+year : 'alle Buchungen aus '+month+'/'+year;
  if (!confirm('Wirklich '+label+' löschen? Dies kann nicht rückgängig gemacht werden.')) return;
  if (scope === 'all') {
    data.transactions = [];
  } else if (scope === 'year') {
    data.transactions = (data.transactions||[]).filter(function(t){ return !t.date || t.date.slice(0,4) !== year; });
  } else {
    var ym = year+'-'+month;
    data.transactions = (data.transactions||[]).filter(function(t){ return !t.date || t.date.slice(0,7) !== ym; });
  }
  saveData();
  alert('Buchungen gelöscht.');
}
function deleteArchive() {
  if (!confirm('Gesamtes Monatsarchiv löschen?')) return;
  data.monthly_archive = [];
  saveData();
  alert('Archiv gelöscht.');
}
function fullReset() {
  var input = prompt('Zum Bestaetigen bitte "RESET" eingeben:');
  if (input !== 'RESET') { alert('Abgebrochen.'); return; }
  if (!confirm('Wirklich ALLE Daten löschen? Kategorien, Ziele, Buchungen, alles.')) return;
  data = {
    categories: [
      {name:'Gehalt',kind:'fix'},{name:'Miete & Nebenkosten',kind:'fix'},
      {name:'Lebensmittel',kind:'variabel'},{name:'Freizeit & Extras',kind:'variabel'},
      {name:'Kleidung',kind:'variabel'},{name:'Versicherung & Sparen',kind:'fix'},
      {name:'Rücklagen',kind:'fix',system:true}
    ],
    transactions:[],recurring:[],monthly_archive:[],fixed_templates:[],
    initial_cash:0,cash_min:2000,initial_reserves:0,reserves_goal:5000,
    initial_date:new Date().toISOString().slice(0,10),
    budget_goals:{}
  };
  saveData();
  closeSettings();
  alert('Alle Daten zurueckgesetzt.');
}
function closeSettings() { document.getElementById('settingsModal').classList.remove('open'); }
function saveSettings() {
  data.initial_cash = parseFloat(document.getElementById('s_initialCash').value)||0;
  data.cash_min = parseFloat(document.getElementById('s_cashMin').value)||0;
  data.initial_reserves = parseFloat(document.getElementById('s_initialReserves').value)||0;
  var autoG = calcResGoalFromSubs();
  if (autoG === null) {
    data.reserves_goal = parseFloat(document.getElementById('s_resGoal').value)||5000;
  }
  saveData(); closeSettings();
}
function switchTab(id) {
  document.querySelectorAll('.stab-panel').forEach(function(p){p.classList.remove('active');});
  document.querySelectorAll('.stab').forEach(function(b){b.classList.remove('active');});
  document.getElementById(id).classList.add('active');
  var map = {tabKonten:0,tabKategorien:1,tabBudget:2,tabRollover:3,tabFixkosten:4,tabRuecklagen:5,tabVerwaltung:6};
  document.querySelectorAll('.stab')[map[id]].classList.add('active');
}

function renderSettingsCats() {
  var cats = data.categories || [];
  document.getElementById('settingsCatList').innerHTML = cats.length === 0
    ? '<div class="empty-hint">Keine Kategorien.</div>'
    : cats.map(function(cat,i){
        return '<div class="section-row" id="catrow_'+i+'">' +
          '<span style="flex:1;">'+cat.name+' <span style="font-size:0.75rem;color:var(--muted);">('+cat.kind+')</span></span>' +
          '<button class="btn-sm" style="background:#d4ecd8;color:var(--green);margin-right:6px;" onclick="editCategory('+i+')">&#9998;</button>' +
          '<button class="btn-sm" onclick="deleteCategory('+i+')">&#215;</button>' +
          '</div>';
      }).join('');
}
function editCategory(idx) {
  var cat = data.categories[idx];
  var row = document.getElementById('catrow_'+idx);
  row.innerHTML =
    '<input type="text" id="editCatName_'+idx+'" value="'+cat.name+'" style="flex:1;margin:0 6px 0 0;">' +
    '<select id="editCatKind_'+idx+'" style="width:100px;margin:0 6px 0 0;">' +
      '<option value="variabel"'+(cat.kind==='variabel'?' selected':'')+'>Variabel</option>' +
      '<option value="fix"'+(cat.kind==='fix'?' selected':'')+'>Fix</option>' +
    '</select>' +
    '<button class="btn-sm" style="background:#d4ecd8;color:var(--green);margin-right:4px;" onclick="saveCategoryEdit('+idx+')">&#10003;</button>' +
    '<button class="btn-sm" onclick="renderSettingsCats()">&#215;</button>';
}
function saveCategoryEdit(idx) {
  var name = document.getElementById('editCatName_'+idx).value.trim();
  var kind = document.getElementById('editCatKind_'+idx).value;
  if (!name) return;
  var oldName = data.categories[idx].name;
  data.categories[idx] = {name: name, kind: kind};
  if (oldName !== name && data.budget_goals[oldName] !== undefined) {
    data.budget_goals[name] = data.budget_goals[oldName];
    delete data.budget_goals[oldName];
  }
  renderSettingsCats(); renderSettingsBudget(); renderSettingsFix();
  saveData();
}
function renderSettingsBudget() {
  var goals = data.budget_goals || {};
  var cats = data.categories || [];
  document.getElementById('settingsBudgetList').innerHTML = cats.length === 0
    ? '<div class="empty-hint">Keine Kategorien vorhanden.</div>'
    : cats.map(function(cat,i){
        var goalVal = goals[cat.name] || 0;
        var goalDisplay = goalVal > 0 ? goalVal+' &#8364;' : '<span style="color:#bbb;">kein Ziel</span>';
        return '<div class="section-row" id="budrow_'+i+'">' +
          '<span style="flex:1;">'+cat.name+
            ' <span style="font-size:0.72rem;color:var(--muted);">('+cat.kind+')</span></span>' +
          '<span style="display:flex;align-items:center;gap:6px;">' +
            '<span style="color:var(--muted);font-size:0.85rem;">'+goalDisplay+'</span>' +
            '<button class="btn-sm" style="background:#d4ecd8;color:var(--green);" onclick="editBudgetGoal('+i+',\''+cat.name+'\','+goalVal+')">&#9998;</button>' +
            (goalVal > 0 ? '<button class="btn-sm" onclick="deleteBudgetGoal(\''+cat.name+'\')">&#215;</button>' : '') +
          '</span>' +
        '</div>';
      }).join('');
}
function editBudgetGoal(idx, cat, currentVal) {
  var row = document.getElementById('budrow_'+idx);
  row.innerHTML =
    '<span style="flex:1;">'+cat+'</span>'+
    '<span style="display:flex;align-items:center;gap:6px;">'+
      '<input type="number" id="editBudVal_'+idx+'" value="'+currentVal+'" style="width:90px;margin:0;" step="10" min="0">'+
      ' <span style="color:var(--muted);">&#8364;</span>'+
      '<button class="btn-sm" style="background:#d4ecd8;color:var(--green);" onclick="saveBudgetGoalEdit('+idx+',\''+cat+'\')">&#10003;</button>'+
      '<button class="btn-sm" onclick="renderSettingsBudget()">&#215;</button>'+
    '</span>';
}
function saveBudgetGoalEdit(idx, cat) {
  var val = parseFloat(document.getElementById('editBudVal_'+idx).value);
  if (isNaN(val) || val < 0) return;
  if (val === 0) {
    delete data.budget_goals[cat];
  } else {
    data.budget_goals[cat] = val;
  }
  renderSettingsBudget(); saveData();
}
function deleteBudgetGoal(cat) {
  if (confirm('Budgetziel für "'+cat+'" löschen?')) {
    delete data.budget_goals[cat];
    renderSettingsBudget(); saveData();
  }
}
function renderSettingsFix() {
  var templates = data.fixed_templates || [];
  var names = catNames();
  document.getElementById('settingsFixList').innerHTML = templates.length === 0
    ? '<div class="empty-hint">Noch keine Vorlagen.</div>'
    : templates.map(function(tpl,i){
        return '<div class="section-row" id="fixrow_'+i+'">' +
          '<span style="flex:1;">'+tpl.desc+
            ' <span style="color:var(--muted);font-size:0.78rem;">('+tpl.category+
            ', '+(tpl.type==='in'?'+':'-')+tpl.amount+' &#8364;, Tag '+tpl.day+')</span></span>' +
          '<span style="display:flex;gap:6px;">' +
            '<button class="btn-sm" style="background:#d4ecd8;color:var(--green);" onclick="editFixTemplate('+i+')">&#9998;</button>' +
            '<button class="btn-sm" onclick="deleteFixTemplate('+i+')">&#215;</button>' +
          '</span>' +
        '</div>';
      }).join('');
  var fixCatSel = document.getElementById('s_fixCat');
  fixCatSel.innerHTML = names.map(function(n){return '<option value="'+n+'">'+n+'</option>';}).join('');
}
function editFixTemplate(idx) {
  var tpl = data.fixed_templates[idx];
  var names = catNames();
  var row = document.getElementById('fixrow_'+idx);
  row.innerHTML =
    '<div style="display:grid;grid-template-columns:1fr 80px 1fr 80px 50px;gap:6px;align-items:center;width:100%;">'+
      '<input type="text" id="ef_desc_'+idx+'" value="'+tpl.desc+'" style="margin:0;" placeholder="Beschreibung">'+
      '<input type="number" id="ef_amt_'+idx+'" value="'+tpl.amount+'" style="margin:0;" step="0.01">'+
      '<select id="ef_cat_'+idx+'" style="margin:0;">'+
        names.map(function(n){return '<option value="'+n+'"'+(n===tpl.category?' selected':'')+'>'+n+'</option>';}).join('')+
      '</select>'+
      '<select id="ef_type_'+idx+'" style="margin:0;">'+
        '<option value="out"'+(tpl.type==='out'?' selected':'')+'>Ausgabe</option>'+
        '<option value="in"'+(tpl.type==='in'?' selected':'')+'>Einnahme</option>'+
      '</select>'+
      '<input type="number" id="ef_day_'+idx+'" value="'+tpl.day+'" min="1" max="31" style="margin:0;" title="Tag">'+
    '</div>'+
    '<span style="display:flex;gap:6px;margin-left:8px;">'+
      '<button class="btn-sm" style="background:#d4ecd8;color:var(--green);" onclick="saveFixTemplateEdit('+idx+')">&#10003;</button>'+
      '<button class="btn-sm" onclick="renderSettingsFix()">&#215;</button>'+
    '</span>';
}
function saveFixTemplateEdit(idx) {
  var desc = document.getElementById('ef_desc_'+idx).value.trim();
  var amt = parseFloat(document.getElementById('ef_amt_'+idx).value);
  var cat = document.getElementById('ef_cat_'+idx).value;
  var type = document.getElementById('ef_type_'+idx).value;
  var day = parseInt(document.getElementById('ef_day_'+idx).value)||1;
  if (!desc || !amt || amt <= 0) return;
  data.fixed_templates[idx] = {desc:desc, amount:amt, category:cat, type:type, day:day};
  renderSettingsFix(); saveData();
}

function addCategory() {
  var inp = document.getElementById('s_newCat');
  var name = inp.value.trim();
  var kind = document.getElementById('s_newCatKind').value;
  if (!name) return;
  if (!data.categories) data.categories = [];
  if (catNames().includes(name)) { alert('Kategorie existiert bereits.'); return; }
  data.categories.push({name: name, kind: kind});
  inp.value = '';
  renderSettingsCats(); renderSettingsBudget(); renderSettingsFix();
  saveData();
}
function deleteCategory(idx) {
  var cat = data.categories[idx];
  if (cat.system) { alert('Die Kategorie "'+cat.name+'" ist fest verankert und kann nicht gelöscht werden.'); return; }
  if (confirm('Kategorie "'+cat.name+'" entfernen? Bestehende Buchungen bleiben erhalten.')) {
    data.categories.splice(idx,1);
    renderSettingsCats(); renderSettingsBudget(); renderSettingsFix();
    saveData();
  }
}
function addBudgetGoal() {
  var cat = document.getElementById('s_goalCat').value;
  var val = parseFloat(document.getElementById('s_goalVal').value);
  if (!cat) { alert('Bitte Kategorie waehlen.'); return; }
  if (!val || val <= 0) { alert('Betrag ungültig.'); return; }
  if (!data.budget_goals) data.budget_goals = {};
  data.budget_goals[cat] = val;
  document.getElementById('s_goalVal').value = '';
  renderSettingsBudget(); saveData();
}
function deleteBudgetGoal(cat) {
  if (confirm('Budgetziel fuer "'+cat+'" loeschen?')) {
    delete data.budget_goals[cat];
    renderSettingsBudget(); saveData();
  }
}
function addFixTemplate() {
  var desc = document.getElementById('s_fixDesc').value.trim();
  var amt = parseFloat(document.getElementById('s_fixAmt').value);
  var cat = document.getElementById('s_fixCat').value;
  var type = document.getElementById('s_fixType').value;
  var day = parseInt(document.getElementById('s_fixDay').value)||1;
  if (!desc) { alert('Beschreibung fehlt.'); return; }
  if (!amt || amt <= 0) { alert('Betrag ungültig.'); return; }
  if (!data.fixed_templates) data.fixed_templates = [];
  data.fixed_templates.push({desc:desc, amount:amt, category:cat, type:type, day:day});
  document.getElementById('s_fixDesc').value = '';
  document.getElementById('s_fixAmt').value = '';
  renderSettingsFix(); saveData();
}
function deleteFixTemplate(idx) {
  if (confirm('Vorlage löschen?')) {
    data.fixed_templates.splice(idx,1);
    renderSettingsFix(); saveData();
  }
}

// Fixkosten Modal
function openFixModal() {
  var templates = data.fixed_templates || [];
  var trans = data.transactions || [];
  var fm = currentMonth || new Date().toISOString().slice(0,7);
  var missing = templates.filter(function(tpl) {
    return !trans.some(function(t) {
      return t.desc === tpl.desc && t.category === tpl.category
        && t.date && t.date.slice(0,7) === fm;
    });
  });
  if (missing.length === 0) { alert('Alle Fixkosten sind bereits gebucht.'); return; }
  var fmParts = fm.split('-');
  var fmYear = parseInt(fmParts[0]), fmMon = parseInt(fmParts[1]);
  var html = missing.map(function(tpl, i) {
    var day = Math.min(tpl.day, new Date(fmYear, fmMon, 0).getDate());
    var dateVal = fmYear+'-'+String(fmMon).padStart(2,'0')+'-'+String(day).padStart(2,'0');
    return '<div class="fix-item" id="fixrow_'+i+'">'+
      '<span class="fix-item-name">'+tpl.desc+' <span style="color:var(--muted);font-size:0.78rem;">('+tpl.category+')</span></span>'+
      '<span class="fix-item-amt">'+(tpl.type==='in'?'+':'-')+tpl.amount.toFixed(2)+' \u20ac</span>'+
      '<input type="date" id="fixdate_'+i+'" value="'+dateVal+'">'+
      '</div>';
  }).join('');
  document.getElementById('fixModalList').innerHTML = html;
  document.getElementById('fixModal').classList.add('open');
  document.getElementById('fixModal').dataset.missing = JSON.stringify(missing);
}
function closeFixModal() { document.getElementById('fixModal').classList.remove('open'); }
function applyFixTemplates() {
  var missing = JSON.parse(document.getElementById('fixModal').dataset.missing || '[]');
  if (!data.transactions) data.transactions = [];
  missing.forEach(function(tpl, i) {
    var dateEl = document.getElementById('fixdate_'+i);
    var date = dateEl ? dateEl.value : todayStr();
    data.transactions.push({date:date, desc:tpl.desc, amount:tpl.amount, category:tpl.category, type:tpl.type});
  });
  closeFixModal();
  saveData();
}

// Wiederkehrend
var tempRec = null;
function openRecModal() {
  var desc = document.getElementById('desc').value.trim();
  var amount = parseFloat(document.getElementById('amount').value);
  if (!desc) { alert('Zuerst Beschreibung eingeben.'); return; }
  if (!amount || amount <= 0) { alert('Zuerst Betrag eingeben.'); return; }
  tempRec = {desc:desc, amount:amount, category:document.getElementById('category').value, type:document.getElementById('type').value};
  document.getElementById('recModalText').textContent = desc+' - '+amount.toFixed(2).replace('.',',')+' \u20ac';
  document.getElementById('recModal').classList.add('open');
}
function closeRecModal() { document.getElementById('recModal').classList.remove('open'); tempRec=null; }
function saveRecurring() {
  if (!tempRec) return;
  if (!data.recurring) data.recurring = [];
  data.recurring.push({...tempRec, frequency:document.getElementById('recFreq').value, day:parseInt(document.getElementById('recDay').value)||1, lastExecuted:todayStr()});
  closeRecModal(); saveData();
  alert('Wiederkehrende Buchung gespeichert!');
}

function toggleVarBudget() {
  var body = document.getElementById('varBody');
  var arrow = document.getElementById('varBodyArrow');
  if (!body) return;
  body.classList.toggle('open');
  if (arrow) arrow.classList.toggle('open');
}

function toggleFixBudget() {
  var body = document.getElementById('fixBody');
  var arrow = document.getElementById('fixBodyArrow');
  if (!body) return;
  body.classList.toggle('open');
  if (arrow) arrow.classList.toggle('open');
}

function toggleResSub() {
  var body = document.getElementById('resSubBody');
  var arrow = document.getElementById('resSubArrow');
  if (!body) return;
  body.classList.toggle('open');
  if (arrow) arrow.classList.toggle('open');
}

function calcResGoalFromSubs() {
  var subs = data.reserves_sub || [];
  if (subs.length === 0) return null;
  return subs.reduce(function(s,g){ return s + parseFloat(g.amount||0); }, 0);
}

function getDueDateMs(sub) {
  var now = new Date();
  // If explicit due_year is set (from resetResSub), use it
  if (sub.due_year) {
    return new Date(sub.due_year, (sub.due_month||1)-1, sub.due_day||1).getTime();
  }
  // Otherwise: next occurrence from today
  var y = now.getFullYear();
  var d = new Date(y, (sub.due_month||1)-1, sub.due_day||1);
  if (d < now) d.setFullYear(y+1);
  return d.getTime();
}

function renderResSubGoals(totalRes) {
  var subs = data.reserves_sub || [];
  var section = document.getElementById('resSubSection');
  var body = document.getElementById('resSubBody');
  var autoLabel = document.getElementById('resGoalAuto');
  if (!section || !body) return;

  // Auto-goal
  var autoGoal = calcResGoalFromSubs();
  if (autoGoal !== null) {
    if (autoLabel) autoLabel.textContent = '';
    var RMARKER = 75;
    var resPerc = autoGoal > 0
      ? (totalRes <= autoGoal ? (totalRes/autoGoal)*RMARKER : Math.min(RMARKER+((totalRes-autoGoal)/autoGoal)*RMARKER, 100))
      : 0;
    var resOk = totalRes >= autoGoal;
    // Nur Sparziel anzeigen (kein ist/soll)
    document.getElementById('resBarLabel').textContent = autoGoal.toFixed(2).replace('.',',') + ' \u20ac';
    var rf = document.getElementById('resFill');
    rf.style.width = resPerc + '%';
    rf.className = 'budget-bar-fill ' + (resOk ? 'ok' : 'over');
    document.getElementById('resDisplay').className = 'big-val ' + (resOk ? 'good' : 'warn');
  } else {
    if (autoLabel) autoLabel.textContent = '';
  }

  if (subs.length === 0) { section.style.display = 'none'; return; }
  section.style.display = 'block';

  // Sort by due date (ascending = soonest first)
  var sorted = subs.map(function(sub,i){ return {sub:sub, idx:i, due:getDueDateMs(sub)}; });
  sorted.sort(function(a,b){ return a.due - b.due; });

  // Priority allocation: fill in order of due date
  var remaining = totalRes;
  var allocations = {};
  sorted.forEach(function(item) {
    var yearly = parseFloat(item.sub.amount||0);
    var alloc = Math.min(remaining, yearly);
    allocations[item.idx] = alloc;
    remaining = Math.max(0, remaining - yearly);
  });

  var totalYearly = subs.reduce(function(s,g){ return s+parseFloat(g.amount||0); }, 0);
  var totalMonthly = totalYearly / 12;

  var now = new Date();
  var html = '';
  sorted.forEach(function(item) {
    var sub = item.sub;
    var origIdx = item.idx;
    var yearly = parseFloat(sub.amount||0);
    var monthly = yearly / 12;
    var alloc = allocations[origIdx] || 0;
    var perc = yearly > 0 ? Math.min((alloc/yearly)*75, 75) : 0;
    var ok = alloc >= yearly;
    var fillClass = ok ? 'budget-bar-fill at-goal' : 'budget-bar-fill ok';
    var freqLabel = sub.freq==='quarterly'?'4x/Jahr':sub.freq==='halfyear'?'2x/Jahr':'1x/Jahr';

    // Due date display
    var dueDate = new Date(item.due);
    var dueStr = dueDate.getDate()+'.'+(dueDate.getMonth()+1)+'.'+dueDate.getFullYear();
    var daysLeft = Math.ceil((item.due - now.getTime()) / 86400000);
    var dueClass = daysLeft <= 30 ? 'color:var(--red);font-weight:600;' : 'color:var(--muted);';

    // Paid status
    var isPaid = sub.paid === true;

    html +=
      '<div class="sub-goal" style="'+(isPaid?'opacity:0.55;':'')+'">' +
        '<div class="sub-goal-row">'+
          '<span class="sub-goal-name">'+sub.name+'</span>'+
          '<span class="sub-goal-nums">'+alloc.toFixed(0)+' / '+yearly+' &#8364;</span>'+
        '</div>'+
        '<div class="budget-bar-wrap" style="height:7px;margin:4px 0;">'+
          '<div class="'+fillClass+'" style="width:'+perc+'%"></div>'+
          '<div class="budget-goal-marker" style="left:75%"></div>'+
        '</div>'+
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-top:3px;">'+
          '<span class="sub-goal-hint">'+monthly.toFixed(0)+' &#8364;/Mon. ('+freqLabel+')</span>'+
          '<span style="font-size:0.72rem;'+dueClass+'">faellig '+dueStr+'</span>'+
        '</div>'+
        (isPaid
          ? '<div style="font-size:0.72rem;color:var(--green);margin-top:3px;">&#10003; bezahlt &ndash; <button onclick="resetResSub('+origIdx+')" style="background:none;border:none;color:var(--primary);font-size:0.72rem;cursor:pointer;padding:0;">neu anspa­ren</button></div>'
          : '<button onclick="payResSub('+origIdx+')" style="margin-top:6px;background:var(--primary);color:white;border:none;border-radius:6px;padding:4px 12px;font-size:0.75rem;font-weight:600;cursor:pointer;">&#10003; Jetzt bezahlen</button>'
        )+
      '</div>';
  });

  // Summenzeile
  html +=
    '<div style="margin-top:12px;padding-top:10px;border-top:2px solid var(--border);'+
      'display:flex;justify-content:space-between;align-items:center;">'+
      '<span style="font-size:0.78rem;font-weight:700;color:var(--text);">Gesamt</span>'+
      '<span style="font-size:0.88rem;font-weight:700;color:var(--primary);">'+
        totalMonthly.toFixed(0)+' &#8364;/Monat'+
        ' <span style="font-size:0.75rem;color:var(--muted);font-weight:400;">('+totalYearly.toFixed(0)+' &#8364;/Jahr)</span>'+
      '</span>'+
    '</div>';

  body.innerHTML = html;
}

var payModalIdx = null;

function payResSub(idx) {
  var sub = data.reserves_sub[idx];
  payModalIdx = idx;
  document.getElementById('payModalName').textContent = sub.name;
  document.getElementById('payModalHint').textContent =
    'Jahresbetrag: '+parseFloat(sub.amount||0).toFixed(2).replace('.',',')+' €';
  document.getElementById('payModalAmt').value = parseFloat(sub.amount||0).toFixed(2);
  document.getElementById('payModalDate').value = todayStr();
  document.getElementById('payModal').classList.add('open');
}

function closePayModal() {
  document.getElementById('payModal').classList.remove('open');
  payModalIdx = null;
}

function confirmPayResSub() {
  if (payModalIdx === null) return;
  var amt = parseFloat(document.getElementById('payModalAmt').value);
  if (isNaN(amt) || amt <= 0) { alert('Bitte gueltigen Betrag eingeben.'); return; }
  var subName = data.reserves_sub[payModalIdx].name || 'Ruecklage';
  // Ruecklagen-Zahlung = Ausgabe vom Sparkonto, nicht vom Girokonto -> kein Summary-Einfluss
  data.transactions.push({
    date: todayStr(),
    desc: subName + ' \u2014 Zahlung',
    amount: amt,
    category: 'Ruecklagen-Zahlung',
    type: 'out'
  });
  // Mark as paid
  data.reserves_sub[payModalIdx].paid = true;
  data.reserves_sub[payModalIdx].paid_amount = amt;
  closePayModal();
  saveData();
}

function resetResSub(idx) {
  if (!confirm('Neue Ansparphase starten? Fälligkeitsdatum wird ein Jahr weiter gesetzt.')) return;
  var sub = data.reserves_sub[idx];
  sub.paid = false;
  sub.paid_amount = 0;
  // Explicitly advance due_year by 1 from current due date
  sub.due_month = sub.due_month || 1;
  sub.due_day = sub.due_day || 1;
  // Calculate current due year and add 1
  var now = new Date();
  var currentDue = new Date(now.getFullYear(), sub.due_month-1, sub.due_day);
  if (currentDue <= now) currentDue.setFullYear(now.getFullYear()+1);
  sub.due_year = currentDue.getFullYear() + 1;
  saveData();
}
function renderSettingsResSub() {
  var MONTHS_SHORT = ['Jan','Feb','Mrz','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez'];
  var subs = data.reserves_sub || [];
  document.getElementById('settingsResSubList').innerHTML = subs.length === 0
    ? '<div class="empty-hint">Noch keine Unterpositionen.</div>'
    : subs.map(function(sub,i){
        var freqLabel = sub.freq==='quarterly'?'Quartalsw.':sub.freq==='halfyear'?'Halbj.':'Jährl.';
        var dueStr = MONTHS_SHORT[(sub.due_month||1)-1]+' (Tag '+(sub.due_day||1)+')';
        return '<div class="section-row" id="ressubrow_'+i+'">'+
          '<span style="flex:1;">'+sub.name+
            ' <span style="font-size:0.75rem;color:var(--muted);">('+sub.amount+' &#8364;, '+freqLabel+', faellig '+dueStr+')</span></span>'+
          '<span style="display:flex;gap:6px;">'+
            '<button class="btn-sm" style="background:#d4ecd8;color:var(--green);" onclick="editResSub('+i+')">&#9998;</button>'+
            '<button class="btn-sm" onclick="deleteResSub('+i+')">&#215;</button>'+
          '</span>'+
        '</div>';
      }).join('');
}

function addResSub() {
  var name = document.getElementById('s_subName').value.trim();
  var amt = parseFloat(document.getElementById('s_subAmt').value);
  var freq = document.getElementById('s_subFreq').value;
  var day = parseInt(document.getElementById('s_subDay').value)||1;
  var month = parseInt(document.getElementById('s_subMonth').value)||1;
  if (!name) { alert('Name fehlt.'); return; }
  if (!amt || amt <= 0) { alert('Betrag ungültig.'); return; }
  if (!data.reserves_sub) data.reserves_sub = [];
  data.reserves_sub.push({name:name, amount:amt, freq:freq, due_day:day, due_month:month, paid:false});
  document.getElementById('s_subName').value = '';
  document.getElementById('s_subAmt').value = '';
  renderSettingsResSub();
  saveData();
}

function editResSub(idx) {
  var sub = data.reserves_sub[idx];
  var row = document.getElementById('ressubrow_'+idx);
  var mn = ['Jan','Feb','Mrz','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez'];
  var monthOpts = mn.map(function(m,i){
    return '<option value="'+(i+1)+'"'+((sub.due_month||1)===(i+1)?' selected':'')+'>'+m+'</option>';
  }).join('');
  row.innerHTML =
    '<div style="display:grid;grid-template-columns:1fr 70px 1fr 50px 1fr;gap:5px;align-items:center;width:100%;">'+
      '<input type="text" id="es_name_'+idx+'" value="'+sub.name+'" style="margin:0;" placeholder="Name">'+
      '<input type="number" id="es_amt_'+idx+'" value="'+sub.amount+'" style="margin:0;" step="10">'+
      '<select id="es_freq_'+idx+'" style="margin:0;">'+
        '<option value="yearly"'+(sub.freq==='yearly'?' selected':'')+'>Jährl.</option>'+
        '<option value="halfyear"'+(sub.freq==='halfyear'?' selected':'')+'>Halbj.</option>'+
        '<option value="quarterly"'+(sub.freq==='quarterly'?' selected':'')+'>Quart.</option>'+
      '</select>'+
      '<input type="number" id="es_day_'+idx+'" value="'+(sub.due_day||1)+'" min="1" max="31" style="margin:0;" title="Tag">'+
      '<select id="es_month_'+idx+'" style="margin:0;">'+monthOpts+'</select>'+
    '</div>'+
    '<span style="display:flex;gap:4px;margin-left:8px;">'+
      '<button class="btn-sm" style="background:#d4ecd8;color:var(--green);" onclick="saveResSub('+idx+')">&#10003;</button>'+
      '<button class="btn-sm" onclick="renderSettingsResSub()">&#215;</button>'+
    '</span>';
}
function saveResSub(idx) {
  var name = document.getElementById('es_name_'+idx).value.trim();
  var amt = parseFloat(document.getElementById('es_amt_'+idx).value);
  var freq = document.getElementById('es_freq_'+idx).value;
  var day = parseInt(document.getElementById('es_day_'+idx).value)||1;
  var month = parseInt(document.getElementById('es_month_'+idx).value)||1;
  if (!name || !amt || amt <= 0) return;
  var existing = data.reserves_sub[idx];
  data.reserves_sub[idx] = {
    name:name, amount:amt, freq:freq,
    due_day:day, due_month:month,
    paid: existing.paid||false,
    paid_amount: existing.paid_amount||0
  };
  renderSettingsResSub();
  saveData();
}
// ===== ROLLOVER =====
function getRolloverIcon(catName) {
  var info = getRolloverInfo(catName);
  if (!info) return '';
  var cls = info.balance >= 0 ? 'positive' : 'negative';
  var sign = info.balance >= 0 ? '+' : '';
  return '<span class="rollover-info '+cls+'">i'+
    '<span class="rollover-tooltip">Übertrag: '+sign+info.balance.toFixed(0)+' €<br>Verfügbar: '+info.available.toFixed(0)+' €</span>'+
  '</span>';
}

function getRolloverInfo(catName) {
  var config = data.rollover_config || {};
  var cfg = config[catName];
  if (!cfg || !cfg.enabled) return null;
  var goals = data.budget_goals || {};
  var goal = goals[catName] || 0;
  var balance = cfg.current_balance || 0;
  var available = goal + balance;
  return { balance: balance, available: available };
}

function renderSettingsRollover() {
  var goals = data.budget_goals || {};
  var config = data.rollover_config || {};
  var catsWithGoal = (data.categories || []).filter(function(c){ return goals[c.name] > 0; });
  
  if (catsWithGoal.length === 0) {
    document.getElementById('settingsRolloverList').innerHTML = '';
    document.getElementById('rolloverEmpty').style.display = 'block';
    return;
  }
  document.getElementById('rolloverEmpty').style.display = 'none';
  
  var html = catsWithGoal.map(function(cat) {
    var cfg = config[cat.name] || {};
    var enabled = cfg.enabled || false;
    var balance = cfg.current_balance || 0;
    var statusText = enabled 
      ? (balance >= 0 ? '<span style="color:var(--green);">+'+balance.toFixed(2)+' €</span>' : '<span style="color:var(--red);">'+balance.toFixed(2)+' €</span>')
      : '<span style="color:#bbb;">inaktiv</span>';
    
    return '<div class="section-row" style="align-items:center;">'+
      '<span style="flex:1;">'+cat.name+' <span style="font-size:0.72rem;color:var(--muted);">(Ziel: '+goals[cat.name]+' €)</span></span>'+
      '<span style="display:flex;align-items:center;gap:10px;">'+
        '<span style="font-size:0.85rem;">'+statusText+'</span>'+
        '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;margin:0;">'+
          '<input type="checkbox" '+(enabled?'checked':'')+' onchange="toggleRollover(\''+cat.name+'\', this.checked)" style="width:18px;height:18px;cursor:pointer;">'+
          '<span style="font-size:0.82rem;color:var(--muted);">'+(enabled?'aktiv':'aus')+'</span>'+
        '</label>'+
      '</span>'+
    '</div>';
  }).join('');
  
  document.getElementById('settingsRolloverList').innerHTML = html;
}

function toggleRollover(catName, enable) {
  if (!data.rollover_config) data.rollover_config = {};
  
  if (enable) {
    openRolloverSetup(catName);
  } else {
    if (!confirm('Rollover für "'+catName+'" wirklich deaktivieren?')) {
      renderSettingsRollover();
      return;
    }
    data.rollover_config[catName] = { enabled: false };
    saveData();
    renderSettingsRollover();
  }
}
var rolloverSetupCat = null;

function openRolloverSetup(catName) {
  rolloverSetupCat = catName;
  var goals = data.budget_goals || {};
  document.getElementById('rolloverSetupName').textContent = catName + ' (Ziel: ' + (goals[catName]||0) + ' €)';
  document.getElementById('rolloverSetupMonth').value = todayStr().slice(0,7);
  document.getElementById('rolloverSetupBalance').value = '0';
  document.getElementById('rolloverSetupModal').classList.add('open');
}

function closeRolloverSetup() {
  document.getElementById('rolloverSetupModal').classList.remove('open');
  rolloverSetupCat = null;
  renderSettingsRollover();
}

function confirmRolloverSetup() {
  if (!rolloverSetupCat) return;
  var monthVal = document.getElementById('rolloverSetupMonth').value;
  var balanceVal = parseFloat(document.getElementById('rolloverSetupBalance').value) || 0;
  
  if (!monthVal || !/^\d{4}-\d{2}$/.test(monthVal)) {
    alert('Bitte gültigen Monat wählen.');
    return;
  }
  
  data.rollover_config[rolloverSetupCat] = {
    enabled: true,
    start_month: monthVal,
    start_balance: balanceVal,
    current_balance: balanceVal
  };
  
  document.getElementById('rolloverSetupModal').classList.remove('open');
  rolloverSetupCat = null;
  saveData();
  renderSettingsRollover();
}
function processRollover() {
  var config = data.rollover_config || {};
  var goals = data.budget_goals || {};
  var now = new Date();
  var currentMonth = now.toISOString().slice(0,7);
  var lastProcessed = data.last_rollover_month || '';
  
  if (lastProcessed === currentMonth) return;
  
  var y = now.getFullYear();
  var m = now.getMonth();
  if (m === 0) { y--; m = 12; }
  var prevMonth = y + '-' + String(m).padStart(2,'0');
  
  Object.keys(config).forEach(function(catName) {
    var cfg = config[catName];
    if (!cfg.enabled) return;
    if (cfg.start_month > prevMonth) return;
    
    var goal = goals[catName] || 0;
    var spent = (data.transactions || [])
      .filter(function(t){ return t.category === catName && t.type === 'out' && t.date && t.date.slice(0,7) === prevMonth; })
      .reduce(function(s,t){ return s + parseFloat(t.amount||0); }, 0);
    
    var prevBalance = cfg.current_balance || 0;
    var available = goal + prevBalance;
    var newBalance = available - spent;
    
    config[catName].current_balance = Math.round(newBalance * 100) / 100;
  });
  
  data.rollover_config = config;
  data.last_rollover_month = currentMonth;
  saveData();
}
function deleteResSub(idx) {
  if (confirm('Unterposition löschen?')) {
    data.reserves_sub.splice(idx,1);
    renderSettingsResSub();
    saveData();
  }
}

document.getElementById('date').value = todayStr();
loadData();
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return Response(HTML, mimetype='text/html; charset=utf-8')

@app.route('/get_data')
def get_data():
    return Response(json.dumps(load_data(), ensure_ascii=False), mimetype='application/json; charset=utf-8')

@app.route('/save_data', methods=['POST'])
def save_data_route():
    try:
        d = request.get_json(force=True)
        save_data(d)
        return Response('{"ok":true}', mimetype='application/json')
    except Exception as e:
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')

# ── LIZENZ ──────────────────────────────────────────
SECRET_KEY   = "mK9xQ2vL7nP4wR8jT6zH3sY5"   # identisch zum Apps Script Key
LICENSE_FILE = os.path.join(BASE_DIR, 'app.dat')
ACTIVATION_URL = "https://script.google.com/macros/s/AKfycbx_OEPXdoGqJiKgjyW07WY7E08k55A7gM57H62COT3FrxLgS8xNvi2Wqzs0e6V0WptsIQ/exec"

def generate_license_code(buyer_id):
    raw = hmac.new(SECRET_KEY.encode(), buyer_id.encode(), hashlib.sha256).digest()
    hex_str = raw.hex().upper()
    short = hex_str[:16]
    return '-'.join([short[i:i+4] for i in range(0, 16, 4)])

def check_license(code):
    """Prüft ob der eingegebene Code für irgendeinen gültigen buyer_id-Input stimmt.
    Da wir offline arbeiten, prüfen wir das Format und ob der Code selbst-konsistent ist:
    Der Code wird als buyer_id genommen und nochmal gehasht — das reicht für Offline-Schutz.
    Echter Check: Code muss exakt dem HMAC über seinen eigenen Wert entsprechen ODER
    wir speichern den buyer_id-Teil. Einfachste Offline-Lösung: Code in license.txt = Beweis.
    Wir prüfen nur Format + dass er nicht leer ist. Der Code wurde vom Server generiert."""
    import re
    return bool(re.match(r'^[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}$', code.strip().upper()))
def activate_online(license_code, hardware_id):
    """Sendet Lizenz + HWID an Server. Gibt (success, message) zurück."""
    import urllib.request
    import urllib.parse
    
    try:
        url = ACTIVATION_URL + "?" + urllib.parse.urlencode({
            'activate': license_code,
            'hwid': hardware_id
        })
        req = urllib.request.Request(url, headers={'User-Agent': 'KassenwartPro/1.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('status') == 'ok':
                return True, data.get('message', 'Aktiviert')
            else:
                return False, data.get('message', 'Aktivierung fehlgeschlagen')
    except urllib.error.URLError:
        return False, "Keine Internetverbindung. Für die Erstaktivierung wird einmalig Internet benötigt."
    except Exception as e:
        return False, f"Fehler: {str(e)}"


def save_license(license_code, hardware_id):
    """Speichert Lizenz verschlüsselt mit HWID als Schlüssel."""
    key = hashlib.sha256(hardware_id.encode()).digest()
    code_bytes = license_code.encode('utf-8')
    # XOR-Verschlüsselung mit Key (wiederholt bis Länge passt)
    key_extended = (key * ((len(code_bytes) // len(key)) + 1))[:len(code_bytes)]
    encrypted = bytes(a ^ b for a, b in zip(code_bytes, key_extended))
    
    data = {
        "v": 2,
        "hash": hashlib.sha256((license_code + '|' + hardware_id).encode()).hexdigest(),
        "enc": encrypted.hex()
    }
    with open(LICENSE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    
    try:
        import subprocess
        subprocess.run(['attrib', '+H', '+S', LICENSE_FILE], check=False, creationflags=0x08000000)
    except Exception:
        pass


def verify_license():
    """Prüft ob gespeicherte Lizenz zur aktuellen Hardware passt."""
    if not os.path.exists(LICENSE_FILE):
        return False
    
    try:
        with open(LICENSE_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        # Legacy-Format (nur Hash) → Migration nötig
        if __import__('re').match(r'^[0-9a-f]{64}$', content):
            return False  # Alte Lizenz ungültig, Neuaktivierung erforderlich
        
        data = json.loads(content)
        if data.get('v') != 2:
            return False
        
        hwid = get_hardware_id()
        key = hashlib.sha256(hwid.encode()).digest()
        encrypted = bytes.fromhex(data['enc'])
        key_extended = (key * ((len(encrypted) // len(key)) + 1))[:len(encrypted)]
        decrypted = bytes(a ^ b for a, b in zip(encrypted, key_extended)).decode('utf-8')
        
        check_hash = hashlib.sha256((decrypted + '|' + hwid).encode()).hexdigest()
        return check_hash == data['hash']
        
    except Exception:
        return False

# ── Revoke-Check ────────────────────────────────────────────────────────────
CHECK_FILE        = os.path.join(BASE_DIR, 'check.dat')
CHECK_INTERVAL    = 15   # Tage bis zum nächsten Ping
MAX_FAILURES      = 10   # Fehlschläge bis Sperrung (= max. 150 Tage)


def revoke_check_online(license_code):
    """Fragt Apps Script ob Lizenz noch aktiv ist.
    Gibt 'valid', 'revoked' oder 'error' zurück."""
    try:
        url = ACTIVATION_URL + "?" + urllib.parse.urlencode({
            "action": "revoke_check",
            "license": license_code
        })
        with urllib.request.urlopen(url, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            status = data.get("status", "error")
            if status in ("valid", "revoked"):
                return status
            return "error"
    except Exception:
        return "error"


def maybe_run_revoke_check():
    """Entscheidet ob ein Revoke-Ping fällig ist und handelt das Ergebnis."""
    # Lizenzcode aus app.dat lesen (für den Ping benötigt)
    license_code = None
    try:
        with open(LICENSE_FILE, 'r', encoding='utf-8') as f:
            data = json.loads(f.read().strip())
        hwid = get_hardware_id()
        key = hashlib.sha256(hwid.encode()).digest()
        encrypted = bytes.fromhex(data['enc'])
        key_extended = (key * ((len(encrypted) // len(key)) + 1))[:len(encrypted)]
        license_code = bytes(a ^ b for a, b in zip(encrypted, key_extended)).decode('utf-8')
    except Exception:
        return  # app.dat nicht lesbar → verify_license() hätte bereits False zurückgegeben

    # check.dat lesen
    check_data = {"permanently_valid": False, "failures": 0, "last_check": 0}
    if os.path.exists(CHECK_FILE):
        try:
            with open(CHECK_FILE, 'r', encoding='utf-8') as f:
                check_data = json.loads(f.read().strip())
        except Exception:
            pass  # Datei korrupt → Defaults verwenden

    # Dauerhaft freigeschaltet → kein Ping mehr nötig
    if check_data.get("permanently_valid", False):
        return

    # Fehlschlag-Limit erreicht → sperren (kein Ping mehr versuchen)
    if check_data.get("failures", 0) >= MAX_FAILURES:
        revoked_dialog()
        return

    # Intervall prüfen
    last_check = check_data.get("last_check", 0)
    days_since = (time.time() - last_check) / 86400
    if days_since < CHECK_INTERVAL:
        return  # Noch nicht fällig

    # Ping ausführen
    status = revoke_check_online(license_code)

    if status == "valid":
        check_data["permanently_valid"] = True
        check_data["failures"] = 0
        _write_check_dat(check_data)

    elif status == "revoked":
        _write_check_dat(check_data)  # Zustand sichern
        revoked_dialog()

    else:  # "error" — Netzwerkproblem
        check_data["failures"] = check_data.get("failures", 0) + 1
        check_data["last_check"] = time.time()  # Intervall neu starten
        _write_check_dat(check_data)
        # Weitermachen — kein Sperren bei Netzwerkfehler


def _write_check_dat(data):
    """Schreibt check.dat und versteckt sie wie app.dat."""
    try:
        with open(CHECK_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        subprocess.run(['attrib', '+H', '+S', CHECK_FILE],
                       check=False, creationflags=0x08000000)
    except Exception:
        pass


def revoked_dialog():
    """Zeigt Sperr-Dialog und beendet die App."""
    import tkinter as tk
    from tkinter import ttk
    root = tk.Tk()
    root.title("Kassenwart Pro – Lizenz deaktiviert")
    root.resizable(False, False)
    root.geometry("420x180")
    root.configure(bg="#1a2a24")
    root.lift()
    root.focus_force()

    ttk.Label(root, text="Lizenz deaktiviert",
              font=("Segoe UI", 13, "bold"),
              foreground="#e4ebe6", background="#1a2a24").pack(pady=(28, 6))
    ttk.Label(root, text="Diese Lizenz wurde deaktiviert.\n"
              "Bei Fragen wende dich an: info@kassenwartpro.de",
              font=("Segoe UI", 10), foreground="#aac4b8",
              background="#1a2a24", justify="center").pack(pady=(0, 18))
    ttk.Button(root, text="Schließen", command=root.destroy).pack()

    root.mainloop()
    sys.exit(0)
# ── Ende Revoke-Check ────────────────────────────────────────────────────────


def get_hardware_id():
    """Erzeugt anonymen Hardware-Fingerprint aus CPU-ID + Disk-Serial."""
    import subprocess
    parts = []
    
    try:
        result = subprocess.run(
            ['wmic', 'cpu', 'get', 'ProcessorId'],
            capture_output=True, text=True, creationflags=0x08000000
        )
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if line and line != 'ProcessorId':
                parts.append(line)
                break
    except Exception:
        pass
    
    try:
        result = subprocess.run(
            ['wmic', 'diskdrive', 'get', 'SerialNumber'],
            capture_output=True, text=True, creationflags=0x08000000
        )
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if line and line != 'SerialNumber':
                parts.append(line)
                break
    except Exception:
        pass
    
    if not parts:
        import getpass, socket
        parts = [getpass.getuser(), socket.gethostname()]
    
    raw = '|'.join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]

def activation_dialog():
    """Tkinter-Dialog zur Lizenzaktivierung. Gibt True zurück wenn aktiviert."""
    import tkinter as tk
    from tkinter import messagebox

    activated = [False]

    root = tk.Tk()
    root.title("Kassenwart Pro — Aktivierung")
    root.resizable(False, False)
    root.configure(bg='#e4ebe6')

    # Fenster zentrieren
    w, h = 420, 280
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f'{w}x{h}+{(sw-w)//2}+{(sh-h)//2}')

    # Header
    tk.Label(root, text="Kassenwart Pro", font=('Segoe UI', 16, 'bold'),
             bg='#e4ebe6', fg='#1a2a24').pack(pady=(28, 2))
    tk.Label(root, text="Bitte gib deinen Lizenzcode ein.",
             font=('Segoe UI', 10), bg='#e4ebe6', fg='#6b8278').pack(pady=(0, 20))

    # Code-Eingabe
    frame = tk.Frame(root, bg='#e4ebe6')
    frame.pack(padx=40, fill='x')

    tk.Label(frame, text="Lizenzcode", font=('Segoe UI', 9, 'bold'),
             bg='#e4ebe6', fg='#6b8278').pack(anchor='w')

    entry_var = tk.StringVar()
    entry = tk.Entry(frame, textvariable=entry_var, font=('Courier New', 13, 'bold'),
                     relief='flat', bg='#ffffff', fg='#1a2a24',
                     insertbackground='#4a7c68', bd=0, highlightthickness=2,
                     highlightcolor='#4a7c68', highlightbackground='#cdd8d2')
    entry.pack(fill='x', ipady=8, pady=(4, 0))
    entry.focus()

    # Fehlermeldung (zunächst leer)
    error_lbl = tk.Label(frame, text="", font=('Segoe UI', 9),
                         bg='#e4ebe6', fg='#a83a3f')
    error_lbl.pack(anchor='w', pady=(4, 0))

    def do_activate(event=None):
        code = entry_var.get().strip().upper()
        # Auto-Format: Bindestriche einfügen wenn der Nutzer ohne tippt
        clean = code.replace('-', '')
        if len(clean) == 16:
            code = '-'.join([clean[i:i+4] for i in range(0, 16, 4)])
            entry_var.set(code)
        if not check_license(code):
            error_lbl.config(text="Ungültiger Code. Format: XXXX-XXXX-XXXX-XXXX")
            entry.config(highlightbackground='#a83a3f', highlightcolor='#a83a3f')
            return
        
        # Hardware-ID ermitteln
        hwid = get_hardware_id()
        
        # Online-Aktivierung
        error_lbl.config(text="Aktivierung läuft...", fg='#4a7c68')
        root.update()
        
        success, message = activate_online(code, hwid)
        
        if not success:
            error_lbl.config(text=message, fg='#a83a3f')
            entry.config(highlightbackground='#a83a3f', highlightcolor='#a83a3f')
            return
        
       # Erfolg — verschlüsselt speichern
        save_license(code, hwid)
        activated[0] = True
        root.destroy()

    # Button
    btn = tk.Button(frame, text="Aktivieren", command=do_activate,
                    font=('Segoe UI', 10, 'bold'), bg='#4a7c68', fg='white',
                    relief='flat', cursor='hand2', pady=8)
    btn.pack(fill='x', pady=(14, 0))
    entry.bind('<Return>', do_activate)

    root.mainloop()
    return activated[0]

def is_licensed():
    return verify_license()

def create_desktop_shortcut(exe_path):
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    shortcut_path = os.path.join(desktop, "Kassenwart Pro.lnk")
    shell = win32com.client.Dispatch("WScript.Shell")
    sc = shell.CreateShortCut(shortcut_path)
    sc.Targetpath = exe_path
    sc.WorkingDirectory = os.path.dirname(exe_path)
    sc.IconLocation = exe_path
    sc.save()

def installation_dialog():
    import tkinter as tk
    from tkinter import filedialog
    import shutil
    chosen = [None]
    root = tk.Tk()
    root.title("Kassenwart Pro — Installation")
    root.resizable(False, False)
    root.configure(bg='#e4ebe6')
    w, h = 460, 340
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f'{w}x{h}+{(sw-w)//2}+{(sh-h)//2}')
    tk.Label(root, text="Kassenwart Pro", font=('Segoe UI', 16, 'bold'),
             bg='#e4ebe6', fg='#1a2a24').pack(pady=(28, 2))
    tk.Label(root, text="Waehle einen Installationsordner.",
             font=('Segoe UI', 10), bg='#e4ebe6', fg='#6b8278').pack(pady=(0, 16))
    frame = tk.Frame(root, bg='#e4ebe6')
    frame.pack(padx=40, fill='x')
    tk.Label(frame, text="Installationsordner", font=('Segoe UI', 9, 'bold'),
             bg='#e4ebe6', fg='#6b8278').pack(anchor='w')
    import os as _os
    path_var = tk.StringVar(value=_os.path.expanduser('~\\KassenwartPro'))
    path_frame = tk.Frame(frame, bg='#e4ebe6')
    path_frame.pack(fill='x', pady=(4, 0))
    path_entry = tk.Entry(path_frame, textvariable=path_var, font=('Segoe UI', 10),
                          relief='flat', bg='#ffffff', fg='#1a2a24', bd=0,
                          highlightthickness=2, highlightcolor='#4a7c68',
                          highlightbackground='#cdd8d2')
    path_entry.pack(side='left', fill='x', expand=True, ipady=7)
    def browse():
        folder = filedialog.askdirectory(title="Installationsordner waehlen")
        if folder:
            path_var.set(_os.path.join(folder, 'KassenwartPro'))
    tk.Button(path_frame, text="...", command=browse,
              font=('Segoe UI', 9), bg='#cdd8d2', fg='#1a2a24',
              relief='flat', cursor='hand2', padx=8, pady=7, bd=0).pack(side='left', padx=(4,0))
    error_lbl = tk.Label(frame, text="", font=('Segoe UI', 9),
                         bg='#e4ebe6', fg='#a83a3f')
    error_lbl.pack(anchor='w', pady=(4, 0))
    shortcut_var = tk.BooleanVar(value=True)
    tk.Checkbutton(frame, text="Desktop-Verknüpfung erstellen",
                   variable=shortcut_var,
                   font=('Segoe UI', 9), bg='#e4ebe6', fg='#1a2a24',
                   activebackground='#e4ebe6', selectcolor='#ffffff',
                   cursor='hand2').pack(anchor='w', pady=(8, 0))
    def do_install():
        target = path_var.get().strip()
        if not target:
            error_lbl.config(text="Bitte einen Ordner waehlen.")
            return
        try:
            _os.makedirs(target, exist_ok=True)
            import sys as _sys2
            src_exe = _sys2.executable
            dst_exe = _os.path.join(target, _os.path.basename(src_exe))
            shutil.copy2(src_exe, dst_exe)
            # install.dat in den Zielordner (neben die installierte .exe)
            marker = _os.path.join(target, 'install.dat')
            with open(marker, 'w', encoding='utf-8') as mf:
                mf.write(target)
            # Desktop-Shortcut erstellen (falls Checkbox aktiv)
            if shortcut_var.get():
                try:
                    create_desktop_shortcut(dst_exe)
                except Exception:
                    pass
            chosen[0] = target
            root.destroy()
        except Exception as e:
            error_lbl.config(text=f"Fehler: {e}")
    tk.Button(frame, text="Installieren & starten", command=do_install,
              font=('Segoe UI', 10, 'bold'), bg='#4a7c68', fg='white',
              relief='flat', cursor='hand2', pady=8, bd=0).pack(fill='x', pady=(14, 0))
    root.mainloop()
    return chosen[0]

def is_installed():
    # install.dat liegt im selben Ordner wie die laufende .exe (= Zielordner nach Installation)
    if getattr(_sys, 'frozen', False):
        marker = os.path.join(os.path.dirname(_sys.executable), 'install.dat')
        return os.path.exists(marker)
    return True

if __name__ == '__main__':
    import webbrowser, threading, time, sys, traceback

    # Schritt 1: Installation (nur beim allerersten Start)
    if not is_installed():
        install_dir = installation_dialog()
        if not install_dir:
            sys.exit(0)
        BASE_DIR          = install_dir
        SETTINGS_FILE     = os.path.join(BASE_DIR, 'config.dat')
        TRANSACTIONS_FILE = os.path.join(BASE_DIR, 'data.dat')
        LICENSE_FILE      = os.path.join(BASE_DIR, 'app.dat')
    else:
        BASE_DIR          = _get_base_dir()
        SETTINGS_FILE     = os.path.join(BASE_DIR, 'config.dat')
        TRANSACTIONS_FILE = os.path.join(BASE_DIR, 'data.dat')
        LICENSE_FILE      = os.path.join(BASE_DIR, 'app.dat')

    # Schritt 2: Lizenzpruefung
    if not is_licensed():
        try:
            ok = activation_dialog()
        except Exception as e:
            err_path = os.path.join(BASE_DIR, 'activation_error.txt')
            with open(err_path, 'w', encoding='utf-8') as ef:
                ef.write(traceback.format_exc())
            ok = False
        if not ok:
            sys.exit(0)

    maybe_run_revoke_check()

    # Schritt 3: Flask starten
    def open_browser():
        time.sleep(1)
        webbrowser.open('http://localhost:8084')
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(port=8084, debug=False)