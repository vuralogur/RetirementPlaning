# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Retirement Planning Application — single-file desktop GUI tool (Tkinter/ttkbootstrap) with two calculators:
- **Future Value Calculation**: a full compound-interest calculator — currency, interest rate (annual or monthly, independent compounding frequency), duration in years+months, optional recurring deposits/withdrawals with an annual step-up. Reports Future Value, Initial Balance, Total Interest Earned, Compounded Rate (APY), All-time Rate of Return, and Time to Double, plus a chart and a Yearly/Monthly breakdown table.
- **Target-Based Savings Plan**: back-solves the required monthly contribution to hit a target amount within a given number of years. Simpler/older-style tab (single monthly rate, no currency/compounding options) — was deliberately left untouched during the Future Value rebuild.

## Tech Stack

- Python 3 (no venv is checked into the repo; create your own with `python -m venv venv`, gitignored — `py -3` on this dev machine resolves to Python 3.14.0)
- [`ttkbootstrap`](https://ttkbootstrap.readthedocs.io/) (>=2.0.1) for themed `ttk` widgets, light/dark theming, and dialogs — the whole UI is built with `ttkbootstrap` widget classes (`tb.Window`, `tb.Frame`, `tb.Entry`, etc.), not plain `tkinter.ttk`
- `matplotlib` (>=3.10.8) embedded via `FigureCanvasTkAgg` for the Future Value growth chart
- `pyinstaller` for packaging into a standalone `.exe` (dev-only, see `requirements-dev.txt`). No test framework — there is no automated test suite in this repo (see Testing).
- No web framework, no database, no external network services
- Note: ttkbootstrap 2.x's built-in theme names (`bootstrap-light` / `bootstrap-dark`, `nord-light`/`dark`, etc.) are **not** the classic 1.x names (`flatly`/`darkly`/`cosmo`) — check `Style().theme_names()` before assuming a theme name exists.

## Architecture

`RetirementPlanning.py` is a flat, procedural script with no classes, split into two layers:

- **Pure calculation layer** (fully unit-testable, no Tkinter/ttkbootstrap dependency):
  - `compute_investment_growth(initial_balance, nominal_rate_pct, rate_period, compounds_per_year, duration_years, duration_months, contribution_type, contribution_amount, contribution_frequency, increase_mode, increase_value)` is the Future Value engine. It normalizes the nominal rate + compounding frequency into an **effective annual rate (APY)** and an **effective monthly rate** (`(1+periodic_rate)**compounds_per_year - 1`, then `(1+EAR)**(1/12) - 1`), then simulates **month-by-month** regardless of the chosen compound frequency — daily/quarterly/etc. compounding is folded into the effective rate rather than literally simulated day-by-day. This is a deliberate simplification, documented in a code comment; don't "fix" it into a day-level simulation without checking with the user first, since it would multiply the loop's complexity for output that's already correct at the month/year granularity the UI reports.
    - Returns a dict: `initial_balance`, `future_value`, `total_contributed`, `total_interest`, `effective_annual_rate_pct`, `all_time_ror_pct` (`None` when `initial_balance == 0`, division-by-zero guard), `doubling_time_months` (`None` when the effective annual rate is ≤ 0, log-domain guard), `monthly_rows`/`yearly_rows` (each row: `year`, `month` (monthly only), `interest`, `accrued_interest`, `balance`), `depleted` (`True` if withdrawals clamped the balance to 0 before the end of the term).
    - Contribution step-up (`increase_mode` "Percent"/"Fixed Amount") is applied once per year, at the start of year 2 onward, to a running `current_contribution` — not recomputed from scratch each year.
  - `format_years_months(total_months)` → `"X years, Y months"`, reused for both the duration display and the doubling-time stat.
  - `compute_target_plan(target_amount, current_savings, monthly_return_rate_pct, years_to_target)` is the Target Plan tab's closed-form back-solve — unrelated to `compute_investment_growth`, untouched by the Future Value rebuild.
- **UI layer**: a single `tb.Window` (`app`), built once by `build_app()` — no destroy/rebuild navigation. A `tb.Notebook` holds two permanent tabs ("Future Value", "Target Plan"), each built once by `build_future_value_tab(notebook)` / `build_target_plan_tab(notebook)`.
  - **Numeric Entry widgets live in module-level dicts**: `entries_main` / `entries_target` map a short key (e.g. `"initial_balance"`, `"duration_years"`) to its `tb.Entry`. `add_input_row(parent, row, key, label_text, entries_dict)` is the shared helper that creates a label+entry row and registers it in the dict.
  - **Dropdown/segmented-button selections live in plain module-level `tb.StringVar` globals**, not `entries_main` (they're never passed through `parse_field` since a readonly `Combobox`/`Radiobutton` can't hold invalid text): `currency_var`, `rate_period_var`, `compound_frequency_var`, `contribution_type_var`, `contribution_frequency_var`, `increase_mode_var`, `view_mode_var` (Chart/Table), `breakdown_mode_var` (Yearly/Monthly). `add_combobox_row(parent, row, label_text, values, variable)` is the shared helper for the `Combobox` rows.
  - **Result stats live in a dict**: `result_vars_main` maps a stat key (`"future_value"`, `"apy"`, `"ror"`, `"doubling_time"`, etc.) to its `tb.StringVar`, populated via `add_stat_row(parent, row, key, label_text, stat_vars_dict)`.
  - Other per-tab state (`error_message_main`, `chart_axes_main`, `chart_canvas_main`, `export_button_main`, `growth_result_main` (the last raw `compute_investment_growth` result dict, kept for redrawing the table on a breakdown-mode toggle without recalculating), `tree_main`, `chart_container_main`/`table_container_main`, and the `*_target` equivalents) are plain module-level globals declared via `global` inside the `build_*_tab` functions.
  - **Calculation callbacks** (`calculate_future_value`, `calculate_target_plan`) parse each Entry field individually via `parse_field(entry, cast, label)` (raises `FieldError` carrying the offending widget), read the selector `StringVar`s directly (no parsing needed), call the corresponding pure `compute_*` function, write results into `result_vars_main`/`result_var_target`, redraw the chart, repopulate the table (Future Value tab only), and cache a flat summary dict in `last_result_main` / `last_result_target` for CSV export.
- **Chart/Table toggle**: `chart_container_main` and `table_container_main` are two `tb.Frame`s gridded into the *same* cell of `view_area`; `switch_future_value_view()` calls `.tkraise()` on whichever one `view_mode_var` selects — no widget destruction. The chart is a single `matplotlib.figure.Figure` + `FigureCanvasTkAgg` created once; `calculate_future_value` clears and redraws `chart_axes_main` rather than recreating the canvas. The table is a `tb.Treeview` (`tree_main`); `populate_future_value_table()` reads `breakdown_mode_var` and repopulates from `growth_result_main["yearly_rows"]` or `["monthly_rows"]`, toggling the `Month` column via `tree.configure(displaycolumns=...)` rather than rebuilding the widget.
- **CSV export**: `export_result_to_csv(result, error_var, default_filename)` is the shared implementation (stdlib `csv` + `tkinter.filedialog.asksaveasfilename`) — `export_future_value()`/`export_target_plan()` just supply the right `last_result_*` flat dict (summary stats only, not the full monthly/yearly table — table export isn't implemented). If `last_result_*` is `None` (no successful calculation yet), it reports an inline error instead of opening the file dialog.
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
- Naming: `snake_case` for functions and variables, `entries_*` for the per-tab Entry-widget dict, `result_vars_main`/`result_var_target`/`feedback_var_target`/`error_message_*` for `StringVar`s, `last_result_*` for the flat cached dict used by CSV export, `growth_result_main` for the raw `compute_investment_growth` result dict kept for chart/table redraws.
- Numeric results are formatted with `f"{value:,.2f}"` (thousands separator, 2 decimal places), or via the `format_money(value, symbol)` helper when a currency prefix applies, before being placed into a `StringVar`.
- **Two different rate conventions coexist by design**: the Target Plan tab's `monthly_return_rate_pct` is always a **monthly** rate (divided by 100, no period conversion — do not change this tab's convention). The Future Value tab's `compute_investment_growth` takes a **nominal rate + an explicit `rate_period` ("Annual"/"Monthly") + an explicit `compounds_per_year`**, and internally derives the effective monthly rate — see Architecture. Don't conflate the two when touching either tab.

## UI Conventions

- All widgets are created via the `tb` (`ttkbootstrap`) namespace, not `tkinter.ttk` directly — plain `ttk` widgets don't accept the `bootstyle=` keyword used throughout for theming (`PRIMARY`, `SECONDARY`, `SUCCESS`, `DANGER`, `DEFAULT` from `ttkbootstrap.constants`).
- Layout uses `.grid()` for structural layout (tabs, cards, chart area) and `.pack(side="left"/anchor=...)` for simple button rows/result-panel content — both are used in this codebase depending on context, unlike the old pure-`.grid()` convention.
- Two permanent `tb.Notebook` tabs, not destroy/rebuild frames — see Architecture. Don't reintroduce a `switch_frame`-style destroy/rebuild pattern.
- Inputs are grouped in a `tb.Labelframe(text="Your Details", bootstyle=PRIMARY)` "card"; results in a `tb.Labelframe(text="Summary"/"Result", bootstyle=SUCCESS)` card.
- The Future Value tab's input panel is wrapped in a scrollable `tb.Canvas` + `tb.Scrollbar` (the `Labelframe` is the canvas's embedded window, resized to the canvas width on `<Configure>`) since it has ~11 fields — this is the pattern to extend if more fields are added; don't let the panel silently overflow the window instead.
- Segmented choices (Currency, Chart/Table, Yearly/Monthly) use `tb.Radiobutton(bootstyle="toolbutton")` groups sharing one `tb.StringVar`, each button's `command=` re-running the relevant "apply" function (`switch_future_value_view`, `populate_future_value_table`). Free-choice-from-a-list fields (Rate Period, Compound Frequency, Contribution Type/Frequency, Annual Increase mode) use `tb.Combobox(state="readonly")` via `add_combobox_row` so the value is always one of the valid options — never a free-typed `Entry` for these.
- `<Return>` is bound once on `app` (`handle_return` in `build_app`) and dispatches to whichever tab is currently selected (`notebook.index(notebook.select())`) — don't bind per-tab `<Return>` handlers, they'd stomp on each other since there's one shared root.
- Inline error `Label` (`bootstyle=DANGER`) below the buttons for validation/domain errors — there is no `messagebox` popup for these.
- Entries with a field-specific parse error get `bootstyle=DANGER`; `clear_entry_errors(...)` resets them to `bootstyle=DEFAULT` at the start of each `calculate_*` call. This uses ttkbootstrap's semantic bootstyle keyword, not a hand-registered custom ttk style.
- The Future Value tab prefixes money outputs with the selected `currency_var` symbol (`format_money`); the Target Plan tab still shows plain numbers with no currency symbol — don't invent one there without a product decision, and don't silently drop the currency prefix from the Future Value tab either.

## Error Handling

- Per-field parsing goes through `parse_field(entry, cast, field_label)`, which raises `FieldError(entry, message)` on a bad `float()`/`int()` conversion — the UI callback catches `FieldError`, highlights that specific `Entry` (`bootstyle=DANGER`), and sets the frame's inline error `StringVar`.
- Domain validation (e.g. `duration_months` out of 0..11, `years_to_target <= 0`) lives inside the pure `compute_*` functions and raises a plain `ValueError(message)`; the UI callback catches it and sets the inline error `StringVar` (no specific entry is highlighted since these errors can span multiple fields).
- `compute_investment_growth` also reports a non-fatal condition — `depleted: True` when withdrawals clamp the balance to 0 before the term ends — via the same inline `error_message_main` `StringVar` (not raised as an exception, since the calculation still completed and returned valid results).
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
- Verify changes manually instead: `py -3 -m py_compile RetirementPlanning.py` for a syntax check, then a headless smoke script — `build_app()` without calling `app.mainloop()`, drive `calculate_*`/`export_*`/`toggle_dark_mode`/`switch_future_value_view`/`populate_future_value_table`, and assert on `StringVar`/widget `style`/`chart_axes_main.lines`/`tree_main.get_children()` state, mocking `tkinter.filedialog.asksaveasfilename` for the export path. This is how every change in this app has been verified so far since there's no display automation available.
- If you touch `compute_investment_growth`'s math, sanity-check it by hand (e.g. the "5% annual, monthly compounding → ~5.116% APY" example, or a 100%-annual-rate case where doubling time should be exactly 12 months) rather than trusting a refactor blind — there's no regression suite to catch a mistake.
- The PyInstaller build itself was verified by actually building `dist/RetirementPlanning.exe` and launching it to confirm it starts without crashing — don't assume a documented build command works without doing this if you change packaging-related code.

## Database

Not applicable — the application holds no persistent state and uses no database.

## Security

- The app takes no network input and makes no network calls; all input comes from local Tkinter Entry widgets.
- No secrets, credentials, or API keys are used anywhere in this codebase.

## Performance

- `compute_investment_growth` runs a Python `for` loop over `total_months` (years×12 + months) doing simple arithmetic — intentionally simulated month-by-month rather than a closed-form formula, since contributions/step-ups/withdrawal-depletion need per-period state. Preserve this behavior unless explicitly asked to optimize.
- The target-plan calculation uses a closed-form formula (no loop). Do not introduce unnecessary loops there.
- The chart redraws by clearing and re-plotting `chart_axes_main` on every Calculate — fine at this data size (one point per year, max a few hundred); don't recreate the `Figure`/`FigureCanvasTkAgg` on every calculation, only update the axes.
- `populate_future_value_table()` calls `tree_main.delete(*tree_main.get_children())` then re-inserts all rows — fine up to a few hundred monthly rows (a multi-decade Monthly breakdown); if very long durations become common, consider whether the Treeview needs virtualization, but don't add that speculatively.

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
- Add new calculation logic as a pure `compute_*` function (raise `ValueError` for invalid input), mirroring `compute_investment_growth`/`compute_target_plan` — no test suite exists, so verify by hand (see Testing).
- Use `add_input_row(...)` + `entries_main`/`entries_target` for numeric fields, `add_combobox_row(...)`/`toolbutton` Radiobutton groups + a module-level `StringVar` for selection fields; use `tb` (ttkbootstrap) widget classes with `bootstyle=` for anything new, not plain `tkinter.ttk`.
- Use `parse_field` / `report_field_error` / the `error_message_*` `StringVar` + `bootstyle=DANGER`/`DEFAULT` for any new input validation, consistent with the two existing calculators.
- If you change anything PyInstaller-related, actually rebuild and launch the exe to confirm it still starts (see Testing) — this app already broke once from a missing `--collect-all ttkbootstrap` flag.
- If you touch `compute_investment_growth`'s math, re-verify the "5% annual, monthly compounding → ~5.116% APY" example and the doubling-time example by hand or against the existing tests before trusting a refactor.

**Don't:**
- Don't invent a CI config unless the user explicitly asks — none currently exists.
- Don't introduce a different GUI framework, ORM, or state-management library beyond what's already here (ttkbootstrap, matplotlib) — don't add more UI dependencies without checking with the user first.
- Don't reintroduce `messagebox` popups for validation errors — the app intentionally uses inline per-field errors now.
- Don't reintroduce destroy/rebuild frame-swapping navigation (`switch_frame`) — the app now uses permanent `Notebook` tabs.
- Don't commit files under a local venv, `build/`, `dist/`, or `*.spec` — all gitignored, not part of the app source.
