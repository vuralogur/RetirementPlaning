# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Retirement Planning Application — single-file desktop GUI tool (Tkinter/ttkbootstrap) with three calculators, all sharing one currency selector, one rate engine, and one inflation model:
- **Future Value** (accumulation): compound-interest projection from an initial balance plus recurring deposits/withdrawals with an annual step-up. Reports Future Value (nominal and in today's money), Initial Balance, Total Interest, APY, real rate after inflation, All-time Rate of Return, Time to Double.
- **Target Plan**: back-solves the monthly deposit needed to reach a target within a given time, then runs that plan through the accumulation engine so the chart/table show the actual path.
- **Retirement Drawdown** (decumulation): spends a balance down and reports how long the money lasts, plus the *sustainable* withdrawal (interest-only) that never touches principal.

Each tab has a Summary panel and a Chart/Table view with a Yearly/Monthly breakdown.

## Tech Stack

- Python 3 (no venv is checked into the repo; create your own with `python -m venv venv`, gitignored — `py -3` on this dev machine resolves to Python 3.14.0)
- [`ttkbootstrap`](https://ttkbootstrap.readthedocs.io/) (>=2.0.1) for themed `ttk` widgets, light/dark theming, and dialogs — the whole UI is built with `ttkbootstrap` widget classes (`tb.Window`, `tb.Frame`, `tb.Entry`, etc.), not plain `tkinter.ttk`
- `matplotlib` (>=3.10.8) embedded via `FigureCanvasTkAgg` for the Future Value growth chart
- `pyinstaller` for packaging into a standalone `.exe` (dev-only, see `requirements-dev.txt`). No test framework — there is no automated test suite in this repo (see Testing).
- No web framework, no database, no external network services
- Note: ttkbootstrap 2.x's built-in theme names (`bootstrap-light` / `bootstrap-dark`, `nord-light`/`dark`, etc.) are **not** the classic 1.x names (`flatly`/`darkly`/`cosmo`) — check `Style().theme_names()` before assuming a theme name exists.

## Architecture

`RetirementPlanning.py` is a flat, procedural script with no classes, split into two layers:

- **Pure calculation layer** (no Tkinter/ttkbootstrap dependency, no globals — safe to call from a headless script):
  - `normalize_rates(nominal_rate_pct, rate_period, compounds_per_year)` → `(effective_annual_rate, effective_monthly_rate)` is the **single rate engine all three calculators go through**. It folds the compounding frequency into an effective annual rate (`(1+periodic)**compounds_per_year - 1`) and derives a monthly rate from it (`(1+EAR)**(1/12) - 1`). Every simulation then steps **month-by-month** regardless of the chosen frequency — daily/quarterly compounding is represented by the effective rate rather than literally simulated day-by-day. Deliberate simplification, documented in the docstring; don't "fix" it into a day-level loop without asking, and never re-derive rates locally in a new function — call this.
  - `validate_inflation(pct)` → annual inflation as a fraction. **-100 is excluded** (it would make the deflator zero and divide-by-zero every "today's money" conversion).
  - `real_rate(effective_annual_rate, annual_inflation)` — Fisher relation `(1+r)/(1+i)-1`, not the naive `r - i` subtraction.
  - `compute_investment_growth(...)` — accumulation engine. Returns `future_value`, `future_value_real`, `total_contributed`, `total_interest`(`_real`), `effective_annual_rate_pct`, `real_annual_rate_pct`, `all_time_ror_pct` (`None` when `initial_balance == 0`, division guard), `doubling_time_months` (`None` when EAR ≤ 0, log-domain guard), `total_months`, `final_deflator`, `monthly_rows`/`yearly_rows`, `depleted`. Contribution step-up applies once per year from year 2 onward to a running `current_contribution`.
  - `compute_target_plan(...)` — solves for the monthly deposit with the **ordinary-annuity closed form** `d = (target - P·(1+r)^n) / (((1+r)^n - 1)/r)`, falling back to `(target - P)/n` when `|r| < 1e-12`. This matches the accumulation loop's order (interest credited *then* contribution added = end-of-month deposit), so the closed form and the simulation agree exactly — a smoke test asserts the simulated final balance lands on the target. **This replaced an earlier buggy version that divided by `n` instead of the annuity factor**, which under-counted the interest contributions themselves earn; don't reintroduce that. When the initial balance alone already exceeds the target it returns `required = 0` with `already_reached = True` rather than a confusing negative number. It calls `compute_investment_growth` internally and returns it under `"growth"`, which is what the tab's chart/table render.
  - `compute_retirement_drawdown(...)` — decumulation. Credits interest, then withdraws; the withdrawal steps up once a year when `index_withdrawal_to_inflation` is on. Returns `months_lasted`, `depleted`, `final_balance`, `total_withdrawn`(`_real`), `sustainable_monthly_withdrawal` (= `starting_balance * effective_monthly_rate`, i.e. interest-only, principal untouched forever), and rows. **The `max_years=MAX_DRAWDOWN_YEARS` (100) cap is a required infinite-loop guard** — when interest covers the withdrawal the balance never falls, so the loop must be bounded; the UI renders that case as "100+ years (never depletes)". Never remove the cap.
  - `format_years_months(total_months)` → `"X years, Y months"`, reused for durations and the doubling-time/lasts stats.
  - **Inflation convention**: every simulation stores a per-row `deflator = (1+annual_inflation)**(month/12)`. "Today's money" is always `nominal / deflator` — computed once at display time, never by re-running the simulation at a real rate. That keeps one simulation and makes nominal/real trivially consistent.
- **UI layer**: a single `tb.Window` (`app`), built once by `build_app()` — no destroy/rebuild navigation. A `tb.Notebook` holds three permanent tabs built by `build_future_value_tab` / `build_target_plan_tab` / `build_drawdown_tab`.
  - **Numeric Entry widgets live in per-tab module-level dicts**: `entries_main` / `entries_target` / `entries_drawdown`, keyed by short names (`"initial_balance"`, `"duration_years"`, …). `add_input_row(...)` and `add_duration_row(...)` create and register them.
  - **Dropdown/segmented selections live in module-level `tb.StringVar` globals** (never in the `entries_*` dicts — a readonly `Combobox`/`Radiobutton` can't hold invalid text, so they never go through `parse_field`): `currency_var` plus per-tab `*_rate_period_var`, `*_compound_frequency_var`, `contribution_*_var`, `increase_mode_var`, `index_withdrawal_var`.
  - **`currency_var` is app-wide and must be created in `build_app()` before any tab is built**, since all three tabs' `add_currency_row(...)` bind to it. Changing it calls `refresh_currency()`, which silently re-runs all three calculators (`calculate_*(silent=True)`) and redraws every view so the new symbol reaches summary stats, chart labels *and* table cells.
  - **`silent=True`** on the calculate functions means "recompute for a re-render, don't touch error state" — it skips clearing/setting `error_message_*` and skips entry highlighting, so a currency change can't wipe or invent an error message. Keep that contract if you add another caller.
  - **Result stats live in per-tab dicts**: `result_vars_main` / `result_vars_target` / `result_vars_drawdown` map a stat key to its `tb.StringVar`, declared as a block via `add_stat_rows(parent, specs, dict)`.
- **The Chart/Table component is shared**: `build_result_view(parent, name, columns, chart_title, x_label)` builds the Chart|Table + Yearly|Monthly toggles, a matplotlib `Figure`/`FigureCanvasTkAgg`, and a `tb.Treeview`, then stores everything in a dict registered in the module-level `views` dict under `name` (`"main"`, `"target"`, `"drawdown"`). `columns` is a tuple of `(row key, heading, width, "int"|"money")`, so a tab only declares its columns rather than duplicating table code.
  - `switch_view(view)` `.tkraise()`s the chart or table frame — both are gridded into the same cell, nothing is destroyed.
  - `populate_view_table(view)` maps row dict keys to columns via the `columns` spec, and hides the `month` column with `displaycolumns` in Yearly mode instead of showing blanks.
  - `redraw_view_chart(view)` plots the nominal balance and, **only when inflation actually separates them**, a dashed "today's money" line plus a legend (otherwise the second line would sit exactly on the first).
  - `show_result(view, result)` = store result + redraw chart + repopulate table. Calculation callbacks end with this.
- **CSV export**: `export_result_to_csv(result, error_var, default_filename)` is shared (stdlib `csv` + `filedialog.asksaveasfilename`); `export_future_value()` / `export_target_plan()` / `export_drawdown()` supply the matching `last_result_*` flat summary dict. Summary stats only — the full breakdown table is still not exported. `None` (nothing calculated yet) reports an inline error instead of opening the dialog.
- **Cross-tab link**: `copy_future_value_to_drawdown()` fills the drawdown tab's starting balance from `last_result_main["Future Value"]`, guarded with an inline error when no Future Value result exists yet.
- **Menu bar** (`build_menu`): File → Exit, View → Toggle Dark Mode (`toggle_dark_mode()` flips between `LIGHT_THEME`/`DARK_THEME` via `app.style.theme_use(...)`), Help → About (`tb.Messagebox.show_info`).
- **App icon**: `assets/icon.ico` (a generated placeholder — coin + growth-bars glyph, not a real brand asset) is set via `app.iconbitmap(...)`, wrapped in `try/except` since `.ico` icons aren't supported on every platform.
- Entry point is guarded: `if __name__ == "__main__": build_app(); app.mainloop()`. Importing the module (e.g. from tests) does **not** launch the GUI — `build_app()` must be called explicitly to construct widgets.

## Directory Structure

```
RetirementPlanning.py   # entire application (pure calc functions + ttkbootstrap UI)
assets/icon.ico          # generated placeholder window/taskbar icon
requirements.txt        # runtime deps: ttkbootstrap, matplotlib
requirements-dev.txt    # dev-only deps: pyinstaller (packaging)
README.md               # usage/setup/packaging instructions
```

There are no subpackages and no CI config (no `pyproject.toml`, `setup.py`, linter config, or CI config) anywhere in the repo. `build/`, `dist/`, and `*.spec` (PyInstaller output) are gitignored by the standard Python `.gitignore` template — don't commit them.

## Commands

```bash
pip install -r requirements.txt && python RetirementPlanning.py     # run the app
pip install -r requirements-dev.txt && pyinstaller --onefile --windowed --icon assets/icon.ico --collect-all ttkbootstrap --name RetirementPlanning RetirementPlanning.py   # build standalone .exe
```

On Linux, Tkinter may need a separate system package: `sudo apt-get install python3-tk` (per README.md). On this Windows dev machine, `python` is not on PATH but `py -3` works. **The `--collect-all ttkbootstrap` PyInstaller flag is required** — without it the built exe crashes on startup (`FileNotFoundError` for `ttkbootstrap/assets/icons/bootstrap.ttf`) because ttkbootstrap's non-Python asset files aren't picked up automatically; this was verified by actually building and launching the exe.

## Coding Standards / Conventions (as established by the existing code)

- Procedural style, no classes — keep new code consistent with this unless a refactor is explicitly requested.
- Keep new calculation logic in a pure `compute_*` function (no Tkinter/ttkbootstrap access, raises `ValueError` for invalid domain input) so it stays unit-testable; keep the matching `calculate_*` UI callback as a thin wrapper that parses fields, calls `compute_*`, and writes results/errors back to widgets.
- New numeric input fields go through `add_input_row(...)` into the tab's `entries_*` dict; new dropdown/segmented-button fields go through `add_combobox_row(...)`/a `tb.Radiobutton(bootstyle="toolbutton")` group backed by a module-level `tb.StringVar`, not a hand-declared `global entry_*` variable.
- Naming: `snake_case` for functions and variables, `entries_*` for the per-tab Entry-widget dict, `result_vars_*` for the per-tab stat `StringVar` dict, `error_message_*` for the inline error `StringVar`, `last_result_*` for the flat cached dict used by CSV export, `views[<name>]` for the shared chart/table component state.
- Money is formatted through `format_money(value, symbol)` and percentages through `format_pct(value)` (which renders `None` as `"N/A"`) — don't hand-roll `f"{v:,.2f}"` at call sites when a helper already covers it.
- **One rate convention across the whole app**: every calculator takes a *nominal* rate plus an explicit `rate_period` ("Annual"/"Monthly") and `compounds_per_year`, and derives effective rates via `normalize_rates(...)`. The old Target Plan "raw monthly rate" convention is gone — don't reintroduce a second convention.

## UI Conventions

- All widgets are created via the `tb` (`ttkbootstrap`) namespace, not `tkinter.ttk` directly — plain `ttk` widgets don't accept the `bootstyle=` keyword used throughout for theming (`PRIMARY`, `SECONDARY`, `SUCCESS`, `DANGER`, `DEFAULT` from `ttkbootstrap.constants`).
- Layout uses `.grid()` for structural layout (tabs, cards, chart area) and `.pack(side="left"/anchor=...)` for simple button rows/result-panel content — both are used in this codebase depending on context, unlike the old pure-`.grid()` convention.
- Three permanent `tb.Notebook` tabs, not destroy/rebuild frames — see Architecture. Don't reintroduce a `switch_frame`-style destroy/rebuild pattern.
- **Every tab follows the same two-column shape**: a scrollable input card on the left (`build_scrollable_panel(parent, title)`), and on the right a `Summary` `Labelframe` above a shared chart/table component (`build_result_view(...)`). Build a new tab out of those helpers rather than hand-rolling a fourth layout.
- The input panels are scrollable `tb.Canvas` + `tb.Scrollbar` wrappers (the `Labelframe` is the canvas's embedded window, resized to canvas width on `<Configure>`) because the field lists are long — keep adding fields there rather than letting a panel silently overflow the window.
- Segmented choices (Currency, Chart/Table, Yearly/Monthly) use `tb.Radiobutton(bootstyle="toolbutton")` groups sharing one `tb.StringVar`, each button's `command=` re-running the relevant apply function (`switch_view`, `populate_view_table`, `refresh_currency`). **Bind loop variables explicitly** (`command=lambda v=view: switch_view(v)`) — the toggles are built in `for` loops and late binding would wire every button to the last view.
- Free-choice-from-a-list fields (Rate Period, Compound Frequency, Contribution Type/Frequency, Annual Increase mode, Raise-With-Inflation) use `tb.Combobox(state="readonly")` via `add_combobox_row` so the value is always valid — never a free-typed `Entry` for these. `add_combobox_row(..., state="disabled")` is used to pin Contribution Type = "Deposit" and Annual Increase = "Percent" (a deliberate product decision — those two are fixed, not user-selectable).
- `<Return>` is bound once on `app` (`handle_return` in `build_app`) and dispatches through the `tab_callbacks` tuple by selected tab index — don't bind per-tab `<Return>` handlers, they'd stomp on each other since there's one shared root. If you add a tab, add its callback to that tuple in the same order.
- Inline error `Label` (`bootstyle=DANGER`, `wraplength` set) below the buttons for validation/domain errors — there is no `messagebox` popup for these.
- Entries with a field-specific parse error get `bootstyle=DANGER`; `clear_entry_errors(...)` resets them to `bootstyle=DEFAULT` at the start of each non-silent `calculate_*` call. This uses ttkbootstrap's semantic bootstyle keyword, not a hand-registered custom ttk style.
- All three tabs prefix money with the shared `currency_var` symbol via `format_money` — summary stats, chart y-axis label, and table cells alike. If you add a money output anywhere, route it through `format_money`.

## Error Handling

- Per-field parsing goes through `parse_field(entry, cast, field_label)`, which raises `FieldError(entry, message)` on a bad `float()`/`int()` conversion — the UI callback catches `FieldError`, highlights that specific `Entry` (`bootstyle=DANGER`), and sets the frame's inline error `StringVar`.
- Domain validation (duration out of range, negative amounts, inflation ≤ -100, …) lives inside the pure `compute_*`/`normalize_rates`/`validate_inflation` functions and raises a plain `ValueError(message)`; the UI callback catches it and sets the inline error `StringVar` (no specific entry is highlighted since these errors can span multiple fields).
- **Non-fatal conditions are reported through the same inline `StringVar`, not raised**, because the calculation still produced valid results: `depleted` on the accumulation tab, `already_reached` on Target Plan, and the "money runs out after X / sustainable amount is Y" note on Drawdown. All are suppressed when `silent=True`.
- `report_field_error(entry_or_none, message, error_var)` is the single place that applies an error to the UI — reuse it for any new validation rather than calling `messagebox` or setting the `StringVar` directly.
- CSV export guards the "nothing calculated yet" case via `export_result_to_csv` checking `result is None` and reporting through the same `error_var` mechanism — don't let the file dialog open with nothing to write.
- There is no `messagebox` import/usage for validation; `tb.Messagebox.show_info` is used only for the non-error "About" dialog.

## Logging

None. The application has no logging framework or print-based diagnostics; errors are surfaced through the inline `error_message_*` labels described above.

## Planning Rules

Before implementing any feature:

1. Analyze the existing implementation.
2. Identify affected files.
3. Explain the proposed solution.
4. Wait for user approval.
5. Implement in small, reviewable steps.
6. Run or update tests if applicable.
7. Summarize the changes and any follow-up work.

Never make large, repository-wide changes without an approved plan.

## Testing

- There is no automated test suite in this repo (removed by user request — the app is meant to stay a minimal, no-test-infrastructure personal utility). Don't add `pytest`/`tests/`/`conftest.py` back unless explicitly asked.
- Verify changes manually instead: `py -3 -m py_compile RetirementPlanning.py` for a syntax check, then a headless smoke script — `build_app()` without calling `app.mainloop()`, drive `calculate_*`/`export_*`/`toggle_dark_mode`/`switch_view`/`populate_view_table`/`refresh_currency`, and assert on `result_vars_*` `StringVar`s, entry `style`, `views[name]["axes"].lines`, and `views[name]["tree"].get_children()`, mocking `tkinter.filedialog.asksaveasfilename` for the export path. This is how every change in this app has been verified so far since there's no display automation available.
- **Known reference values to check the math against** (all verified by hand and by smoke script):
  - 5% annual compounded monthly → APY `5.11619%`, doubling time `13 years, 11 months`.
  - 12% annual compounded monthly → effective monthly rate exactly `0.01` (the nominal→EAR→monthly round-trip is lossless).
  - 10% nominal with 5% inflation → real rate `4.7619%` (Fisher, not `10-5=5`).
  - Target: 10 000 goal, 0 start, 12% annual/monthly compounding, 1 year → required `788.487887`/month, and the simulation's final balance must land on `10 000.00` exactly. (The old buggy formula gave `833.33`.)
  - 1 000 nominal with 5% inflation over 10 years → `613.913254` in today's money.
- Turkish console note: `py -3` on this machine writes to a `cp1254` console, so `print()`ing the `₺` symbol from a smoke script raises `UnicodeEncodeError`. That's a harness limitation, not an app bug — set `PYTHONIOENCODING=utf-8` or print `.encode("unicode_escape")`.
- The PyInstaller build itself was verified by actually building `dist/RetirementPlanning.exe` and launching it to confirm it starts without crashing — don't assume a documented build command works without doing this if you change packaging-related code.

## Database

Not applicable — the application holds no persistent state and uses no database.

## Security

- The app takes no network input and makes no network calls; all input comes from local Tkinter Entry widgets.
- No secrets, credentials, or API keys are used anywhere in this codebase.

## Performance

- `compute_investment_growth` and `compute_retirement_drawdown` run a Python `for` loop over months doing simple arithmetic — intentionally simulated month-by-month rather than closed-form, since contributions/step-ups/depletion need per-period state. Preserve this.
- `compute_target_plan` solves in closed form and then runs *one* simulation to produce the chart/table. Don't turn the solve itself into a search loop.
- The chart redraws by clearing and re-plotting the axes on every Calculate; don't recreate the `Figure`/`FigureCanvasTkAgg`, only update the axes.
- `populate_view_table()` deletes and re-inserts every row. Measured worst case (the 100-year drawdown horizon, 1 200 monthly rows) is ~8 ms, and a 50-year accumulation with a 600-row monthly table is ~80 ms end to end — comfortably fast. Don't add Treeview virtualization speculatively.

## Dependency Management

Runtime dependencies (`ttkbootstrap`, `matplotlib`) are pinned in `requirements.txt`; dev-only tools (`pyinstaller`) are in `requirements-dev.txt`. Keep this split — don't add dev tooling to `requirements.txt` or vice versa. If a new dependency is genuinely needed, add it to the appropriate file with a `>=` lower bound matching what was actually tested, not an unpinned or overly strict `==` pin.

## Git Commit Messages

Recent history (`git log`) shows short, plain-language, non-conventional-commit messages (e.g. "README.md", "proje kodları eklendi") with no enforced format (no Conventional Commits prefix, no issue linking convention). Match this existing informal style unless the user requests otherwise.

## Instructions for Future Contributors

- This is a small teaching/personal-utility project, not a packaged distributable — there's no `setup.py`/`pyproject.toml` to register entry points against; PyInstaller (see Commands) is how it's shipped as an executable.
- No venv is checked into the repo. `myenv/` was tracked by mistake early in the project's history and was later removed from git and deleted from disk — that history isn't rewritten, just stopped going forward. Create your own venv locally; it's covered by `.gitignore`.
- `assets/icon.ico` is a generic generated placeholder (coin + growth-bars glyph), not a real brand/logo asset — feel free to swap it for a real one, no need to preserve its exact appearance.
- README's setup/run/test/packaging instructions match the real filenames and the `requirements.txt` / `requirements-dev.txt` split — keep it that way if you touch setup steps.

## Do's and Don'ts for AI Assistants

**Do:**
- Keep new features inside `RetirementPlanning.py` unless the user asks for a restructure — the whole app is intentionally one file today, split into a pure calc layer and a ttkbootstrap UI layer.
- Add new calculation logic as a pure `compute_*` function (raise `ValueError` for invalid input) that gets its rates from `normalize_rates(...)` — no test suite exists, so verify by hand against the reference values in Testing.
- Build new UI out of the existing helpers: `build_scrollable_panel`, `add_input_row`, `add_duration_row`, `add_combobox_row`, `add_currency_row`, `add_stat_rows`, `build_result_view`. A fourth tab should be almost entirely helper calls.
- Use `parse_field` / `report_field_error` / the `error_message_*` `StringVar` + `bootstyle=DANGER`/`DEFAULT` for any new input validation, consistent with the three existing calculators.
- Preserve the `silent=True` contract on `calculate_*` (recompute without touching error state) — `refresh_currency` depends on it.
- If you change anything PyInstaller-related, actually rebuild and launch the exe to confirm it still starts (see Testing) — this app already broke once from a missing `--collect-all ttkbootstrap` flag.

**Don't:**
- Don't remove the `MAX_DRAWDOWN_YEARS` cap in `compute_retirement_drawdown` — it's the only thing stopping an infinite loop when interest fully covers the withdrawal.
- Don't re-derive interest rates inline in a new function; go through `normalize_rates` so all three tabs stay consistent.
- Don't reintroduce the old Target Plan formula that divided by the month count instead of the annuity factor — it silently under-counts interest on contributions.
- Don't invent a CI config unless the user explicitly asks — none currently exists.
- Don't introduce a different GUI framework, ORM, or state-management library beyond what's already here (ttkbootstrap, matplotlib) — don't add more UI dependencies without checking with the user first.
- Don't reintroduce `messagebox` popups for validation errors — the app intentionally uses inline per-field errors now.
- Don't reintroduce destroy/rebuild frame-swapping navigation (`switch_frame`) — the app uses permanent `Notebook` tabs.
- Don't commit files under a local venv, `build/`, `dist/`, or `*.spec` — all gitignored, not part of the app source.
