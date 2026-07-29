# Retirement Planning Application

A free desktop app that helps you plan your savings and retirement. No spreadsheet, no sign-up — just fill in your numbers and see the results.

It has three calculators:
- **Future Value** — "If I save this much, with this interest rate, for this many years, how much will I have?"
- **Target Plan** — "I want to reach a specific amount — how much do I need to save each month?"
- **Retirement Drawdown** — "Once I retire and start spending my savings, how long will the money last?"

Every tab accounts for inflation and shows what your money is actually worth in today's terms, plus a growth chart and a year-by-year (or month-by-month) breakdown table.

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

**Future Value tab:** enter your starting balance, interest rate, how often it compounds, the inflation rate, how long you're investing, and how much you'll add regularly. Click **Calculate**. The summary shows your projected balance (both as a raw number and in today's money), total interest earned, effective annual rate (APY), the real rate after inflation, overall return, and how long it takes to double your money.

**Target Plan tab:** enter your goal amount, current savings, interest rate, and timeframe. Click **Calculate** to see the monthly contribution required to get there — plus what that goal will actually be worth in today's money once you reach it.

**Retirement Drawdown tab:** enter your retirement pot and how much you plan to withdraw each month. Click **Calculate** to see how many years it lasts before running out. It also tells you the *sustainable* withdrawal — the monthly amount you could take forever without ever touching the principal. Use **Use Future Value result** to pull your projected balance straight from the Future Value tab.

Every tab: switch between the **Chart** and **Table** view, toggle **Yearly**/**Monthly** detail, use **Export to CSV** to save your results, and **View → Toggle Dark Mode** in the menu if you prefer a dark theme. The currency you pick applies across all three tabs.

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
