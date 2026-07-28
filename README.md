# Retirement Planning Application

A free desktop app that helps you plan your savings and retirement. No spreadsheet, no sign-up — just fill in your numbers and see the results.

It has two calculators:
- **Future Value** — "If I save this much, with this interest rate, for this many years, how much will I have?" Also shows a growth chart and a year-by-year (or month-by-month) breakdown table.
- **Target Plan** — "I want to reach a specific amount — how much do I need to save each month?"

## Quick Start

You need [Python 3](https://www.python.org/downloads/) installed on your computer (any recent version works). If you're not sure whether you have it, open a terminal and type `python --version` — if you see a version number, you're set.

**1. Get the code**

```bash
git clone https://github.com/vuralogur/retirement-planning-app.git
cd retirement-planning-app
```

(No git? Click the green "Code" button on the GitHub page → "Download ZIP", then unzip it and open a terminal in that folder.)

**2. Install what the app needs**

```bash
pip install -r requirements.txt
```

**3. Run it**

```bash
python RetirementPlanning.py
```

A window should open. That's it — no setup, no accounts, no configuration.

> **Windows note:** if `python` isn't recognized, try `py` instead (e.g. `py -m pip install -r requirements.txt` and `py RetirementPlanning.py`).
>
> **Linux note:** if the window fails to open with a Tkinter-related error, install it first: `sudo apt-get install python3-tk`, then try again.

## How to use it

**Future Value tab:** enter your starting balance, interest rate, how often it compounds, how long you're investing, and (optionally) how much you'll add regularly. Click **Calculate**. The summary panel shows your projected balance, total interest earned, effective annual rate (APY), overall return, and how long it takes to double your money. Switch between the **Chart** and **Table** view to see the year-by-year (or month-by-month) numbers.

**Target Plan tab:** enter your goal amount, current savings, interest rate, and timeframe. Click **Calculate** to see the monthly contribution required to get there.

Either tab: use **Export to CSV** to save your results to a file, and **View → Toggle Dark Mode** in the menu if you prefer a dark theme.

## Optional: keep things tidy with a virtual environment

Not required, but recommended if you have other Python projects on your machine — it keeps this app's packages separate from everything else.

```bash
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # macOS / Linux

pip install -r requirements.txt
python RetirementPlanning.py
```

---

## For developers

### Building a standalone .exe

```bash
pip install -r requirements-dev.txt
pyinstaller --onefile --windowed --icon assets/icon.ico --collect-all ttkbootstrap --name RetirementPlanning RetirementPlanning.py
```

The `--collect-all ttkbootstrap` flag is required — without it, the built .exe crashes on startup because ttkbootstrap's font/icon asset files aren't picked up automatically. The result is written to `dist/RetirementPlanning.exe`.
