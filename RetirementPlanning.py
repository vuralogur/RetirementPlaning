import csv
import math
import os

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import ttkbootstrap as tb
from tkinter import filedialog
from ttkbootstrap.constants import BOTH, DANGER, DEFAULT, EW, PRIMARY, SECONDARY, SUCCESS, W


LIGHT_THEME = "bootstrap-light"
DARK_THEME = "bootstrap-dark"

CURRENCY_SYMBOLS = ["$", "€", "£", "₺"]
RATE_PERIODS = ["Annual", "Monthly"]
COMPOUND_FREQUENCIES = {
    "Annually": 1,
    "Semi-Annually": 2,
    "Quarterly": 4,
    "Monthly": 12,
    "Daily": 365,
}
CONTRIBUTION_TYPES = ["None", "Deposit", "Withdrawal"]
CONTRIBUTION_FREQUENCIES = ["Monthly", "Yearly"]
INCREASE_MODES = ["None", "Percent", "Fixed Amount"]
YES_NO = ["Yes", "No"]

# Hard cap on the drawdown simulation so a withdrawal that is fully covered by
# interest can never loop forever.
MAX_DRAWDOWN_YEARS = 100


def format_years_months(total_months):
    years, months = divmod(max(total_months, 0), 12)
    return f"{years} years, {months} months"


def normalize_rates(nominal_rate_pct, rate_period, compounds_per_year):
    """Nominal rate + compounding frequency -> (effective annual, effective monthly).

    The simulations always step month-by-month regardless of the chosen compound
    frequency; compounding literally at that frequency (e.g. daily) is folded into
    the effective annual/monthly rate instead of simulating day-by-day. That keeps
    one simulation loop while still reporting the mathematically correct APY.
    """
    if not -100 <= nominal_rate_pct <= 100:
        raise ValueError("Interest rate must be between -100 and 100.")

    annual_nominal = nominal_rate_pct * (12 if rate_period == "Monthly" else 1) / 100
    periodic_rate = annual_nominal / compounds_per_year
    effective_annual_rate = (1 + periodic_rate) ** compounds_per_year - 1
    effective_monthly_rate = (1 + effective_annual_rate) ** (1 / 12) - 1
    return effective_annual_rate, effective_monthly_rate


def validate_inflation(inflation_rate_pct):
    # -100% inflation is excluded: it would make the deflator zero (division by zero
    # when converting to today's money).
    if not -100 < inflation_rate_pct <= 100:
        raise ValueError("Inflation rate must be above -100 and at most 100.")
    return inflation_rate_pct / 100


def real_rate(effective_annual_rate, annual_inflation):
    """Inflation-adjusted ("real") annual return, via the Fisher relation."""
    return (1 + effective_annual_rate) / (1 + annual_inflation) - 1


def compute_investment_growth(
    initial_balance,
    nominal_rate_pct,
    rate_period,
    compounds_per_year,
    duration_years,
    duration_months,
    contribution_type,
    contribution_amount,
    contribution_frequency,
    increase_mode,
    increase_value,
    inflation_rate_pct=0,
):
    if initial_balance < 0:
        raise ValueError("Initial balance cannot be negative.")

    if duration_years < 0:
        raise ValueError("Duration years cannot be negative.")

    if not 0 <= duration_months <= 11:
        raise ValueError("Months must be between 0 and 11.")

    total_months = duration_years * 12 + duration_months
    if total_months <= 0:
        raise ValueError("Investment duration must be greater than zero.")

    if contribution_amount < 0:
        raise ValueError("Contribution amount cannot be negative.")

    if increase_value < 0:
        raise ValueError("Annual contribution increase cannot be negative.")

    effective_annual_rate, effective_monthly_rate = normalize_rates(
        nominal_rate_pct, rate_period, compounds_per_year
    )
    annual_inflation = validate_inflation(inflation_rate_pct)

    sign = {"None": 0, "Deposit": 1, "Withdrawal": -1}[contribution_type]
    current_contribution = contribution_amount

    balance = initial_balance
    cumulative_interest = 0.0
    total_contributed = 0.0
    year_interest_accum = 0.0
    depleted = False

    monthly_rows = []
    yearly_rows = []

    for month in range(1, total_months + 1):
        year_index = (month - 1) // 12 + 1
        month_in_year = (month - 1) % 12 + 1

        if month_in_year == 1 and year_index > 1 and increase_mode != "None":
            if increase_mode == "Percent":
                current_contribution *= 1 + increase_value / 100
            else:
                current_contribution += increase_value

        interest_this_month = balance * effective_monthly_rate
        balance += interest_this_month
        cumulative_interest += interest_this_month
        year_interest_accum += interest_this_month

        if not depleted and sign != 0:
            applies = contribution_frequency == "Monthly" or (
                contribution_frequency == "Yearly" and month_in_year == 12
            )
            if applies:
                delta = sign * current_contribution
                balance += delta
                total_contributed += delta
                if balance < 0:
                    total_contributed -= balance
                    balance = 0.0
                    depleted = True

        # Purchasing-power deflator: divide a nominal amount by this to express it
        # in today's money.
        deflator = (1 + annual_inflation) ** (month / 12)

        monthly_rows.append(
            {
                "year": year_index,
                "month": month_in_year,
                "interest": interest_this_month,
                "accrued_interest": cumulative_interest,
                "balance": balance,
                "deflator": deflator,
            }
        )

        if month_in_year == 12 or month == total_months:
            yearly_rows.append(
                {
                    "year": year_index,
                    "interest": year_interest_accum,
                    "accrued_interest": cumulative_interest,
                    "balance": balance,
                    "deflator": deflator,
                }
            )
            year_interest_accum = 0.0

    future_value = balance
    total_interest = future_value - initial_balance - total_contributed
    final_deflator = (1 + annual_inflation) ** (total_months / 12)

    all_time_ror_pct = (future_value - initial_balance) / initial_balance * 100 if initial_balance > 0 else None

    if effective_annual_rate > 0:
        doubling_time_months = round(math.log(2) / math.log(1 + effective_annual_rate) * 12)
    else:
        doubling_time_months = None

    return {
        "initial_balance": initial_balance,
        "future_value": future_value,
        "future_value_real": future_value / final_deflator,
        "total_contributed": total_contributed,
        "total_interest": total_interest,
        "total_interest_real": total_interest / final_deflator,
        "effective_annual_rate_pct": effective_annual_rate * 100,
        "real_annual_rate_pct": real_rate(effective_annual_rate, annual_inflation) * 100,
        "all_time_ror_pct": all_time_ror_pct,
        "doubling_time_months": doubling_time_months,
        "total_months": total_months,
        "final_deflator": final_deflator,
        "monthly_rows": monthly_rows,
        "yearly_rows": yearly_rows,
        "depleted": depleted,
    }


def compute_target_plan(
    target_amount,
    initial_balance,
    nominal_rate_pct,
    rate_period,
    compounds_per_year,
    duration_years,
    duration_months,
    inflation_rate_pct=0,
):
    """Solve for the monthly deposit needed to reach `target_amount`.

    Deposits are treated as end-of-month (ordinary annuity), matching the order
    `compute_investment_growth` applies interest and contributions, so the closed
    form below and the simulation it feeds agree.
    """
    if target_amount < 0:
        raise ValueError("Target savings amount cannot be negative.")

    if initial_balance < 0:
        raise ValueError("Current savings cannot be negative.")

    if duration_years < 0:
        raise ValueError("Duration years cannot be negative.")

    if not 0 <= duration_months <= 11:
        raise ValueError("Months must be between 0 and 11.")

    total_months = duration_years * 12 + duration_months
    if total_months <= 0:
        raise ValueError("Time to reach the target must be greater than zero.")

    _, effective_monthly_rate = normalize_rates(nominal_rate_pct, rate_period, compounds_per_year)
    annual_inflation = validate_inflation(inflation_rate_pct)

    if abs(effective_monthly_rate) < 1e-12:
        required = (target_amount - initial_balance) / total_months
    else:
        growth = (1 + effective_monthly_rate) ** total_months
        annuity_factor = (growth - 1) / effective_monthly_rate
        required = (target_amount - initial_balance * growth) / annuity_factor

    already_reached = required <= 0
    if already_reached:
        required = 0.0

    growth_result = compute_investment_growth(
        initial_balance=initial_balance,
        nominal_rate_pct=nominal_rate_pct,
        rate_period=rate_period,
        compounds_per_year=compounds_per_year,
        duration_years=duration_years,
        duration_months=duration_months,
        contribution_type="Deposit",
        contribution_amount=required,
        contribution_frequency="Monthly",
        increase_mode="None",
        increase_value=0,
        inflation_rate_pct=inflation_rate_pct,
    )

    final_deflator = (1 + annual_inflation) ** (total_months / 12)

    return {
        "required_monthly_contribution": required,
        "already_reached": already_reached,
        "target_amount": target_amount,
        "target_amount_real": target_amount / final_deflator,
        "total_months": total_months,
        "growth": growth_result,
    }


def compute_retirement_drawdown(
    starting_balance,
    monthly_withdrawal,
    nominal_rate_pct,
    rate_period,
    compounds_per_year,
    inflation_rate_pct=0,
    index_withdrawal_to_inflation=True,
    max_years=MAX_DRAWDOWN_YEARS,
):
    """Simulate spending down a balance: how long does the money last?

    Each month interest is credited first, then the withdrawal is taken. If the
    withdrawal is indexed to inflation it steps up once per year, mirroring the
    annual step-up convention used in the accumulation simulation.
    """
    if starting_balance < 0:
        raise ValueError("Starting balance cannot be negative.")

    if monthly_withdrawal < 0:
        raise ValueError("Monthly withdrawal cannot be negative.")

    if max_years <= 0:
        raise ValueError("Maximum horizon must be greater than zero.")

    effective_annual_rate, effective_monthly_rate = normalize_rates(
        nominal_rate_pct, rate_period, compounds_per_year
    )
    annual_inflation = validate_inflation(inflation_rate_pct)

    max_months = int(max_years) * 12
    balance = starting_balance
    total_withdrawn = 0.0
    cumulative_interest = 0.0
    year_interest_accum = 0.0
    year_withdrawal_accum = 0.0
    depleted = False
    months_lasted = 0

    monthly_rows = []
    yearly_rows = []

    for month in range(1, max_months + 1):
        year_index = (month - 1) // 12 + 1
        month_in_year = (month - 1) % 12 + 1

        interest_this_month = balance * effective_monthly_rate
        balance += interest_this_month
        cumulative_interest += interest_this_month
        year_interest_accum += interest_this_month

        if index_withdrawal_to_inflation:
            withdrawal = monthly_withdrawal * (1 + annual_inflation) ** ((month - 1) // 12)
        else:
            withdrawal = monthly_withdrawal

        if withdrawal >= balance:
            withdrawal = max(balance, 0.0)
            depleted = True

        balance -= withdrawal
        total_withdrawn += withdrawal
        year_withdrawal_accum += withdrawal
        months_lasted = month

        deflator = (1 + annual_inflation) ** (month / 12)

        monthly_rows.append(
            {
                "year": year_index,
                "month": month_in_year,
                "interest": interest_this_month,
                "withdrawal": withdrawal,
                "balance": balance,
                "deflator": deflator,
            }
        )

        if month_in_year == 12 or depleted or month == max_months:
            yearly_rows.append(
                {
                    "year": year_index,
                    "interest": year_interest_accum,
                    "withdrawal": year_withdrawal_accum,
                    "balance": balance,
                    "deflator": deflator,
                }
            )
            year_interest_accum = 0.0
            year_withdrawal_accum = 0.0

        if depleted:
            break

    final_deflator = (1 + annual_inflation) ** (months_lasted / 12) if months_lasted else 1.0

    return {
        "starting_balance": starting_balance,
        "months_lasted": months_lasted,
        "depleted": depleted,
        "final_balance": balance,
        "total_withdrawn": total_withdrawn,
        "total_withdrawn_real": total_withdrawn / final_deflator,
        "total_interest": cumulative_interest,
        # Withdrawing only the interest leaves the principal untouched forever.
        "sustainable_monthly_withdrawal": starting_balance * effective_monthly_rate,
        "effective_annual_rate_pct": effective_annual_rate * 100,
        "real_annual_rate_pct": real_rate(effective_annual_rate, annual_inflation) * 100,
        "max_months": max_months,
        "monthly_rows": monthly_rows,
        "yearly_rows": yearly_rows,
    }


class FieldError(Exception):
    def __init__(self, entry, message):
        super().__init__(message)
        self.entry = entry


def parse_field(entry, cast, field_label):
    try:
        return cast(entry.get())
    except ValueError:
        raise FieldError(entry, f"{field_label} must be a valid number.")


def mark_entry_error(entry):
    entry.configure(bootstyle=DANGER)


def clear_entry_errors(entries):
    for entry in entries:
        entry.configure(bootstyle=DEFAULT)


def report_field_error(entry, message, error_var):
    if entry is not None:
        mark_entry_error(entry)
    error_var.set(message)


entries_main = {}
entries_target = {}
entries_drawdown = {}
last_result_main = None
last_result_target = None
last_result_drawdown = None
views = {}


def add_input_row(parent, row, key, label_text, entries_dict):
    tb.Label(parent, text=label_text).grid(row=row, column=0, sticky=W, padx=(0, 10), pady=4)
    entry = tb.Entry(parent)
    entry.grid(row=row, column=1, sticky=EW, pady=4)
    entries_dict[key] = entry
    return entry


def add_combobox_row(parent, row, label_text, values, variable, width=16, state="readonly"):
    tb.Label(parent, text=label_text).grid(row=row, column=0, sticky=W, padx=(0, 10), pady=4)
    combo = tb.Combobox(parent, values=values, textvariable=variable, state=state, width=width)
    combo.grid(row=row, column=1, sticky=EW, pady=4)
    return combo


def add_duration_row(parent, row, entries_dict, label_text="Duration"):
    tb.Label(parent, text=label_text).grid(row=row, column=0, sticky=W, pady=4)
    duration_frame = tb.Frame(parent)
    duration_frame.grid(row=row, column=1, sticky=EW, pady=4)
    entry_years = tb.Entry(duration_frame, width=6)
    entry_years.pack(side="left")
    tb.Label(duration_frame, text="yrs").pack(side="left", padx=(4, 10))
    entry_months = tb.Entry(duration_frame, width=6)
    entry_months.pack(side="left")
    tb.Label(duration_frame, text="mos").pack(side="left", padx=(4, 0))
    entries_dict["duration_years"] = entry_years
    entries_dict["duration_months"] = entry_months


def add_stat_row(parent, row, key, label_text, stat_vars_dict):
    tb.Label(parent, text=label_text, font=("Segoe UI", 9)).grid(row=row, column=0, sticky=W, pady=3)
    var = tb.StringVar(value="—")
    tb.Label(parent, textvariable=var, font=("Segoe UI", 11, "bold")).grid(row=row, column=1, sticky=W, padx=(10, 0), pady=3)
    stat_vars_dict[key] = var
    return var


def add_stat_rows(parent, specs, stat_vars_dict):
    for row, (key, label_text) in enumerate(specs):
        add_stat_row(parent, row, key, label_text, stat_vars_dict)


def format_money(value, symbol):
    return f"{symbol}{value:,.2f}"


def format_pct(value):
    return "N/A" if value is None else f"{value:.2f}%"


def build_scrollable_panel(parent, title):
    """Left-hand input card that scrolls when it outgrows the window."""
    outer = tb.Frame(parent)
    canvas = tb.Canvas(outer, width=320, highlightthickness=0)
    scrollbar = tb.Scrollbar(outer, orient="vertical", command=canvas.yview)
    inner = tb.Labelframe(canvas, text=title, padding=12, bootstyle=PRIMARY)
    inner.columnconfigure(1, weight=1)

    canvas_window = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    return outer, inner


def build_result_view(parent, name, columns, chart_title, x_label):
    """Chart/Table pair with Chart|Table and Yearly|Monthly toggles.

    `columns` is a tuple of (row key, heading, width, "int"|"money"). Both frames
    are gridded into the same cell and swapped with tkraise(), so nothing is ever
    destroyed and rebuilt.
    """
    view = {
        "name": name,
        "columns": columns,
        "chart_title": chart_title,
        "x_label": x_label,
        "result": None,
    }

    toggles = tb.Frame(parent)
    toggles.grid(row=0, column=0, sticky="ew")
    toggles.columnconfigure(0, weight=1)

    view_mode_var = tb.StringVar(value="Chart")
    breakdown_mode_var = tb.StringVar(value="Yearly")
    view["view_mode_var"] = view_mode_var
    view["breakdown_mode_var"] = breakdown_mode_var

    left_toggle = tb.Frame(toggles)
    left_toggle.grid(row=0, column=0, sticky="w")
    for label in ("Chart", "Table"):
        tb.Radiobutton(
            left_toggle, text=label, variable=view_mode_var, value=label, bootstyle="toolbutton",
            command=lambda v=view: switch_view(v),
        ).pack(side="left", padx=(0, 4))

    right_toggle = tb.Frame(toggles)
    right_toggle.grid(row=0, column=1, sticky="e")
    for label in ("Yearly", "Monthly"):
        tb.Radiobutton(
            right_toggle, text=label, variable=breakdown_mode_var, value=label, bootstyle="toolbutton",
            command=lambda v=view: populate_view_table(v),
        ).pack(side="left", padx=(4, 0))

    view_area = tb.Frame(parent)
    view_area.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
    view_area.columnconfigure(0, weight=1)
    view_area.rowconfigure(0, weight=1)
    parent.rowconfigure(1, weight=1)

    chart_container = tb.Frame(view_area)
    chart_container.grid(row=0, column=0, sticky="nsew")
    table_container = tb.Frame(view_area)
    table_container.grid(row=0, column=0, sticky="nsew")
    view["chart_container"] = chart_container
    view["table_container"] = table_container

    figure = Figure(figsize=(5, 2.6), dpi=100)
    axes = figure.add_subplot(111)
    axes.set_title(chart_title)
    axes.set_xlabel(x_label)
    axes.set_ylabel("Balance")
    figure.tight_layout()
    canvas = FigureCanvasTkAgg(figure, master=chart_container)
    canvas.get_tk_widget().pack(fill=BOTH, expand=True)
    canvas.draw()
    view["axes"] = axes
    view["canvas"] = canvas

    tree = tb.Treeview(
        table_container,
        columns=tuple(col[0] for col in columns),
        show="headings",
        bootstyle=PRIMARY,
    )
    for key, heading, width, kind in columns:
        tree.heading(key, text=heading)
        tree.column(key, width=width, anchor="center" if kind == "int" else "e")
    tree_scroll = tb.Scrollbar(table_container, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=tree_scroll.set)
    tree.pack(side="left", fill=BOTH, expand=True)
    tree_scroll.pack(side="right", fill="y")
    view["tree"] = tree

    views[name] = view
    switch_view(view)
    return view


def switch_view(view):
    if view["view_mode_var"].get() == "Chart":
        view["chart_container"].tkraise()
    else:
        view["table_container"].tkraise()


def populate_view_table(view):
    tree = view["tree"]
    tree.delete(*tree.get_children())
    result = view["result"]
    if result is None:
        return

    symbol = currency_var.get()
    yearly = view["breakdown_mode_var"].get() == "Yearly"
    rows = result["yearly_rows"] if yearly else result["monthly_rows"]

    # Yearly rows have no month number, so hide that column rather than showing a
    # blank one.
    tree.configure(displaycolumns=tuple(c[0] for c in view["columns"] if not (yearly and c[0] == "month")))

    for row in rows:
        values = []
        for key, _heading, _width, kind in view["columns"]:
            if key not in row:
                values.append("")
            elif kind == "money":
                values.append(format_money(row[key], symbol))
            else:
                values.append(row[key])
        tree.insert("", "end", values=values)


def redraw_view_chart(view):
    result = view["result"]
    axes = view["axes"]
    axes.clear()

    if result is not None:
        symbol = currency_var.get()
        rows = result["yearly_rows"]
        x = [row["year"] for row in rows]
        nominal = [row["balance"] for row in rows]
        real = [row["balance"] / row["deflator"] for row in rows]

        axes.plot(x, nominal, marker="o", linewidth=2, label="Nominal")
        # Only draw the second line when inflation actually moves it, otherwise it
        # sits exactly on top of the first one.
        if any(abs(n - r) > 1e-9 for n, r in zip(nominal, real)):
            axes.plot(x, real, marker="o", linewidth=2, linestyle="--", label="Today's money")
            axes.legend(fontsize=8)
        axes.set_ylabel(f"Balance ({symbol})")
    else:
        axes.set_ylabel("Balance")

    axes.set_title(view["chart_title"])
    axes.set_xlabel(view["x_label"])
    axes.figure.tight_layout()
    view["canvas"].draw()


def show_result(view, result):
    view["result"] = result
    redraw_view_chart(view)
    populate_view_table(view)


def add_currency_row(parent, row):
    tb.Label(parent, text="Currency").grid(row=row, column=0, sticky=W, pady=4)
    currency_buttons = tb.Frame(parent)
    currency_buttons.grid(row=row, column=1, sticky=W, pady=4)
    for symbol in CURRENCY_SYMBOLS:
        tb.Radiobutton(
            currency_buttons, text=symbol, variable=currency_var, value=symbol, bootstyle="toolbutton",
            command=refresh_currency,
        ).pack(side="left", padx=(0, 2))


def refresh_currency():
    """Currency is app-wide: re-render every tab that already has a result."""
    for recalc in (calculate_future_value, calculate_target_plan, calculate_drawdown):
        recalc(silent=True)
    for view in views.values():
        if view["result"] is not None:
            redraw_view_chart(view)
            populate_view_table(view)


def build_future_value_tab(notebook):
    global error_message_main, export_button_main, result_vars_main
    global rate_period_var, compound_frequency_var
    global contribution_type_var, contribution_frequency_var, increase_mode_var

    result_vars_main = {}

    tab = tb.Frame(notebook, padding=16)
    tab.columnconfigure(0, weight=0)
    tab.columnconfigure(1, weight=1)
    tab.rowconfigure(0, weight=1)
    notebook.add(tab, text="Future Value")

    left_outer, details = build_scrollable_panel(tab, "Your Details")
    left_outer.grid(row=0, column=0, sticky="ns", padx=(0, 16))

    row = 0
    add_currency_row(details, row)
    row += 1

    add_input_row(details, row, "initial_balance", "Initial Balance", entries_main)
    row += 1

    add_input_row(details, row, "rate", "Interest Rate (%)", entries_main)
    row += 1

    rate_period_var = tb.StringVar(value=RATE_PERIODS[0])
    add_combobox_row(details, row, "Rate Period", RATE_PERIODS, rate_period_var)
    row += 1

    compound_frequency_var = tb.StringVar(value="Monthly")
    add_combobox_row(details, row, "Compound Frequency", list(COMPOUND_FREQUENCIES.keys()), compound_frequency_var)
    row += 1

    add_input_row(details, row, "inflation", "Inflation Rate (%/yr)", entries_main)
    row += 1

    add_duration_row(details, row, entries_main)
    row += 1

    contribution_type_var = tb.StringVar(value="Deposit")
    add_combobox_row(details, row, "Contribution Type", CONTRIBUTION_TYPES, contribution_type_var, state="disabled")
    row += 1

    add_input_row(details, row, "contribution_amount", "Contribution Amount", entries_main)
    row += 1

    contribution_frequency_var = tb.StringVar(value=CONTRIBUTION_FREQUENCIES[0])
    add_combobox_row(details, row, "Contribution Frequency", CONTRIBUTION_FREQUENCIES, contribution_frequency_var)
    row += 1

    increase_mode_var = tb.StringVar(value="Percent")
    add_combobox_row(details, row, "Annual Increase", INCREASE_MODES, increase_mode_var, state="disabled")
    row += 1

    add_input_row(details, row, "increase_value", "Increase Value (% or amount)", entries_main)
    row += 1

    buttons = tb.Frame(details)
    buttons.grid(row=row, column=0, columnspan=2, sticky=EW, pady=(12, 4))
    tb.Button(buttons, text="Calculate", bootstyle=PRIMARY, command=calculate_future_value).pack(side="left")
    export_button_main = tb.Button(buttons, text="Export to CSV", bootstyle=SECONDARY, command=export_future_value)
    export_button_main.pack(side="left", padx=(8, 0))
    row += 1

    error_message_main = tb.StringVar()
    tb.Label(details, textvariable=error_message_main, bootstyle=DANGER, wraplength=280).grid(
        row=row, column=0, columnspan=2, sticky=W
    )

    right = tb.Frame(tab)
    right.grid(row=0, column=1, sticky="nsew")
    right.columnconfigure(0, weight=1)

    result_panel = tb.Labelframe(right, text="Summary", padding=12, bootstyle=SUCCESS)
    result_panel.grid(row=0, column=0, sticky=EW, pady=(0, 12))
    result_panel.columnconfigure(1, weight=1)
    add_stat_rows(
        result_panel,
        (
            ("future_value", "Future Value"),
            ("future_value_real", "Future Value (today's money)"),
            ("initial_balance", "Initial Balance"),
            ("total_interest", "Total Interest Earned"),
            ("apy", "Compounded Rate (APY)"),
            ("real_rate", "Real Rate (after inflation)"),
            ("ror", "All-time Rate of Return"),
            ("doubling_time", "Time to Double"),
        ),
        result_vars_main,
    )

    view_host = tb.Frame(right)
    view_host.grid(row=1, column=0, sticky="nsew")
    view_host.columnconfigure(0, weight=1)
    right.rowconfigure(1, weight=1)

    build_result_view(
        view_host,
        "main",
        (
            ("year", "Year", 55, "int"),
            ("month", "Month", 55, "int"),
            ("interest", "Interest", 110, "money"),
            ("accrued_interest", "Accrued Interest", 130, "money"),
            ("balance", "Balance", 115, "money"),
        ),
        "Projected Growth",
        "Year",
    )


def build_target_plan_tab(notebook):
    global error_message_target, export_button_target, result_vars_target
    global target_rate_period_var, target_compound_frequency_var

    result_vars_target = {}

    tab = tb.Frame(notebook, padding=16)
    tab.columnconfigure(0, weight=0)
    tab.columnconfigure(1, weight=1)
    tab.rowconfigure(0, weight=1)
    notebook.add(tab, text="Target Plan")

    left_outer, details = build_scrollable_panel(tab, "Your Details")
    left_outer.grid(row=0, column=0, sticky="ns", padx=(0, 16))

    row = 0
    add_currency_row(details, row)
    row += 1

    add_input_row(details, row, "target_amount", "Target Savings Amount", entries_target)
    row += 1

    add_input_row(details, row, "initial_balance", "Current Savings", entries_target)
    row += 1

    add_input_row(details, row, "rate", "Interest Rate (%)", entries_target)
    row += 1

    target_rate_period_var = tb.StringVar(value=RATE_PERIODS[0])
    add_combobox_row(details, row, "Rate Period", RATE_PERIODS, target_rate_period_var)
    row += 1

    target_compound_frequency_var = tb.StringVar(value="Monthly")
    add_combobox_row(
        details, row, "Compound Frequency", list(COMPOUND_FREQUENCIES.keys()), target_compound_frequency_var
    )
    row += 1

    add_input_row(details, row, "inflation", "Inflation Rate (%/yr)", entries_target)
    row += 1

    add_duration_row(details, row, entries_target, label_text="Time to Target")
    row += 1

    buttons = tb.Frame(details)
    buttons.grid(row=row, column=0, columnspan=2, sticky=EW, pady=(12, 4))
    tb.Button(buttons, text="Calculate", bootstyle=PRIMARY, command=calculate_target_plan).pack(side="left")
    export_button_target = tb.Button(buttons, text="Export to CSV", bootstyle=SECONDARY, command=export_target_plan)
    export_button_target.pack(side="left", padx=(8, 0))
    row += 1

    error_message_target = tb.StringVar()
    tb.Label(details, textvariable=error_message_target, bootstyle=DANGER, wraplength=280).grid(
        row=row, column=0, columnspan=2, sticky=W
    )

    right = tb.Frame(tab)
    right.grid(row=0, column=1, sticky="nsew")
    right.columnconfigure(0, weight=1)

    result_panel = tb.Labelframe(right, text="Summary", padding=12, bootstyle=SUCCESS)
    result_panel.grid(row=0, column=0, sticky=EW, pady=(0, 12))
    result_panel.columnconfigure(1, weight=1)
    add_stat_rows(
        result_panel,
        (
            ("required", "Required Monthly Contribution"),
            ("total_contributed", "Total Contributions"),
            ("total_interest", "Total Interest Earned"),
            ("final_balance", "Projected Final Balance"),
            ("target_real", "Target in Today's Money"),
            ("apy", "Compounded Rate (APY)"),
        ),
        result_vars_target,
    )

    view_host = tb.Frame(right)
    view_host.grid(row=1, column=0, sticky="nsew")
    view_host.columnconfigure(0, weight=1)
    right.rowconfigure(1, weight=1)

    build_result_view(
        view_host,
        "target",
        (
            ("year", "Year", 55, "int"),
            ("month", "Month", 55, "int"),
            ("interest", "Interest", 110, "money"),
            ("accrued_interest", "Accrued Interest", 130, "money"),
            ("balance", "Balance", 115, "money"),
        ),
        "Path to Target",
        "Year",
    )


def build_drawdown_tab(notebook):
    global error_message_drawdown, export_button_drawdown, result_vars_drawdown
    global drawdown_rate_period_var, drawdown_compound_frequency_var, index_withdrawal_var

    result_vars_drawdown = {}

    tab = tb.Frame(notebook, padding=16)
    tab.columnconfigure(0, weight=0)
    tab.columnconfigure(1, weight=1)
    tab.rowconfigure(0, weight=1)
    notebook.add(tab, text="Retirement Drawdown")

    left_outer, details = build_scrollable_panel(tab, "Your Details")
    left_outer.grid(row=0, column=0, sticky="ns", padx=(0, 16))

    row = 0
    add_currency_row(details, row)
    row += 1

    add_input_row(details, row, "starting_balance", "Starting Balance", entries_drawdown)
    row += 1

    tb.Button(
        details, text="Use Future Value result", bootstyle=SECONDARY, command=copy_future_value_to_drawdown
    ).grid(row=row, column=0, columnspan=2, sticky=W, pady=(0, 6))
    row += 1

    add_input_row(details, row, "monthly_withdrawal", "Monthly Withdrawal", entries_drawdown)
    row += 1

    add_input_row(details, row, "rate", "Interest Rate (%)", entries_drawdown)
    row += 1

    drawdown_rate_period_var = tb.StringVar(value=RATE_PERIODS[0])
    add_combobox_row(details, row, "Rate Period", RATE_PERIODS, drawdown_rate_period_var)
    row += 1

    drawdown_compound_frequency_var = tb.StringVar(value="Monthly")
    add_combobox_row(
        details, row, "Compound Frequency", list(COMPOUND_FREQUENCIES.keys()), drawdown_compound_frequency_var
    )
    row += 1

    add_input_row(details, row, "inflation", "Inflation Rate (%/yr)", entries_drawdown)
    row += 1

    index_withdrawal_var = tb.StringVar(value="Yes")
    add_combobox_row(details, row, "Raise Withdrawal With Inflation", YES_NO, index_withdrawal_var)
    row += 1

    buttons = tb.Frame(details)
    buttons.grid(row=row, column=0, columnspan=2, sticky=EW, pady=(12, 4))
    tb.Button(buttons, text="Calculate", bootstyle=PRIMARY, command=calculate_drawdown).pack(side="left")
    export_button_drawdown = tb.Button(
        buttons, text="Export to CSV", bootstyle=SECONDARY, command=export_drawdown
    )
    export_button_drawdown.pack(side="left", padx=(8, 0))
    row += 1

    error_message_drawdown = tb.StringVar()
    tb.Label(details, textvariable=error_message_drawdown, bootstyle=DANGER, wraplength=280).grid(
        row=row, column=0, columnspan=2, sticky=W
    )

    right = tb.Frame(tab)
    right.grid(row=0, column=1, sticky="nsew")
    right.columnconfigure(0, weight=1)

    result_panel = tb.Labelframe(right, text="Summary", padding=12, bootstyle=SUCCESS)
    result_panel.grid(row=0, column=0, sticky=EW, pady=(0, 12))
    result_panel.columnconfigure(1, weight=1)
    add_stat_rows(
        result_panel,
        (
            ("lasts", "Money Lasts"),
            ("final_balance", "Final Balance"),
            ("total_withdrawn", "Total Withdrawn"),
            ("total_withdrawn_real", "Total Withdrawn (today's money)"),
            ("sustainable", "Sustainable Monthly Withdrawal"),
            ("apy", "Compounded Rate (APY)"),
        ),
        result_vars_drawdown,
    )

    view_host = tb.Frame(right)
    view_host.grid(row=1, column=0, sticky="nsew")
    view_host.columnconfigure(0, weight=1)
    right.rowconfigure(1, weight=1)

    build_result_view(
        view_host,
        "drawdown",
        (
            ("year", "Year", 55, "int"),
            ("month", "Month", 55, "int"),
            ("interest", "Interest", 110, "money"),
            ("withdrawal", "Withdrawal", 115, "money"),
            ("balance", "Balance", 115, "money"),
        ),
        "Balance During Retirement",
        "Year",
    )


def calculate_future_value(silent=False):
    if not entries_main:
        return
    if not silent:
        clear_entry_errors(list(entries_main.values()))
        error_message_main.set("")

    try:
        initial_balance = parse_field(entries_main["initial_balance"], float, "Initial balance")
        rate = parse_field(entries_main["rate"], float, "Interest rate")
        inflation = parse_field(entries_main["inflation"], float, "Inflation rate")
        duration_years = parse_field(entries_main["duration_years"], int, "Duration years")
        duration_months = parse_field(entries_main["duration_months"], int, "Duration months")
        contribution_amount = parse_field(entries_main["contribution_amount"], float, "Contribution amount")
        increase_value = parse_field(entries_main["increase_value"], float, "Increase value")
    except FieldError as e:
        if not silent:
            report_field_error(e.entry, str(e), error_message_main)
        return

    try:
        result = compute_investment_growth(
            initial_balance=initial_balance,
            nominal_rate_pct=rate,
            rate_period=rate_period_var.get(),
            compounds_per_year=COMPOUND_FREQUENCIES[compound_frequency_var.get()],
            duration_years=duration_years,
            duration_months=duration_months,
            contribution_type=contribution_type_var.get(),
            contribution_amount=contribution_amount,
            contribution_frequency=contribution_frequency_var.get(),
            increase_mode=increase_mode_var.get(),
            increase_value=increase_value,
            inflation_rate_pct=inflation,
        )
    except ValueError as e:
        if not silent:
            report_field_error(None, str(e), error_message_main)
        return

    symbol = currency_var.get()
    result_vars_main["future_value"].set(format_money(result["future_value"], symbol))
    result_vars_main["future_value_real"].set(format_money(result["future_value_real"], symbol))
    result_vars_main["initial_balance"].set(format_money(result["initial_balance"], symbol))
    result_vars_main["total_interest"].set(format_money(result["total_interest"], symbol))
    result_vars_main["apy"].set(format_pct(result["effective_annual_rate_pct"]))
    result_vars_main["real_rate"].set(format_pct(result["real_annual_rate_pct"]))
    result_vars_main["ror"].set(format_pct(result["all_time_ror_pct"]))
    result_vars_main["doubling_time"].set(
        "N/A" if result["doubling_time_months"] is None else format_years_months(result["doubling_time_months"])
    )

    if result["depleted"] and not silent:
        error_message_main.set("Note: balance was fully depleted by withdrawals before the end of the term.")

    global last_result_main
    last_result_main = {
        "Currency": symbol,
        "Initial Balance": initial_balance,
        "Interest Rate (%)": rate,
        "Rate Period": rate_period_var.get(),
        "Compound Frequency": compound_frequency_var.get(),
        "Inflation Rate (%/yr)": inflation,
        "Duration": format_years_months(result["total_months"]),
        "Contribution Type": contribution_type_var.get(),
        "Contribution Amount": contribution_amount,
        "Contribution Frequency": contribution_frequency_var.get(),
        "Annual Increase Mode": increase_mode_var.get(),
        "Annual Increase Value": increase_value,
        "Future Value": result["future_value"],
        "Future Value (today's money)": result["future_value_real"],
        "Total Interest Earned": result["total_interest"],
        "Compounded Rate (APY %)": result["effective_annual_rate_pct"],
        "Real Rate (%)": result["real_annual_rate_pct"],
        "All-time Rate of Return (%)": result["all_time_ror_pct"],
        "Time to Double": (
            "N/A" if result["doubling_time_months"] is None else format_years_months(result["doubling_time_months"])
        ),
    }

    show_result(views["main"], result)


def calculate_target_plan(silent=False):
    if not entries_target:
        return
    if not silent:
        clear_entry_errors(list(entries_target.values()))
        error_message_target.set("")

    try:
        target_amount = parse_field(entries_target["target_amount"], float, "Target savings amount")
        initial_balance = parse_field(entries_target["initial_balance"], float, "Current savings")
        rate = parse_field(entries_target["rate"], float, "Interest rate")
        inflation = parse_field(entries_target["inflation"], float, "Inflation rate")
        duration_years = parse_field(entries_target["duration_years"], int, "Duration years")
        duration_months = parse_field(entries_target["duration_months"], int, "Duration months")
    except FieldError as e:
        if not silent:
            report_field_error(e.entry, str(e), error_message_target)
        return

    try:
        plan = compute_target_plan(
            target_amount=target_amount,
            initial_balance=initial_balance,
            nominal_rate_pct=rate,
            rate_period=target_rate_period_var.get(),
            compounds_per_year=COMPOUND_FREQUENCIES[target_compound_frequency_var.get()],
            duration_years=duration_years,
            duration_months=duration_months,
            inflation_rate_pct=inflation,
        )
    except ValueError as e:
        if not silent:
            report_field_error(None, str(e), error_message_target)
        return

    growth = plan["growth"]
    symbol = currency_var.get()
    result_vars_target["required"].set(format_money(plan["required_monthly_contribution"], symbol))
    result_vars_target["total_contributed"].set(format_money(growth["total_contributed"], symbol))
    result_vars_target["total_interest"].set(format_money(growth["total_interest"], symbol))
    result_vars_target["final_balance"].set(format_money(growth["future_value"], symbol))
    result_vars_target["target_real"].set(format_money(plan["target_amount_real"], symbol))
    result_vars_target["apy"].set(format_pct(growth["effective_annual_rate_pct"]))

    if plan["already_reached"] and not silent:
        error_message_target.set(
            "Your current savings already reach the target — no monthly contribution needed."
        )

    global last_result_target
    last_result_target = {
        "Currency": symbol,
        "Target Savings Amount": target_amount,
        "Current Savings": initial_balance,
        "Interest Rate (%)": rate,
        "Rate Period": target_rate_period_var.get(),
        "Compound Frequency": target_compound_frequency_var.get(),
        "Inflation Rate (%/yr)": inflation,
        "Time to Target": format_years_months(plan["total_months"]),
        "Required Monthly Contribution": plan["required_monthly_contribution"],
        "Total Contributions": growth["total_contributed"],
        "Total Interest Earned": growth["total_interest"],
        "Projected Final Balance": growth["future_value"],
        "Target in Today's Money": plan["target_amount_real"],
        "Compounded Rate (APY %)": growth["effective_annual_rate_pct"],
    }

    show_result(views["target"], growth)


def calculate_drawdown(silent=False):
    if not entries_drawdown:
        return
    if not silent:
        clear_entry_errors(list(entries_drawdown.values()))
        error_message_drawdown.set("")

    try:
        starting_balance = parse_field(entries_drawdown["starting_balance"], float, "Starting balance")
        monthly_withdrawal = parse_field(entries_drawdown["monthly_withdrawal"], float, "Monthly withdrawal")
        rate = parse_field(entries_drawdown["rate"], float, "Interest rate")
        inflation = parse_field(entries_drawdown["inflation"], float, "Inflation rate")
    except FieldError as e:
        if not silent:
            report_field_error(e.entry, str(e), error_message_drawdown)
        return

    try:
        result = compute_retirement_drawdown(
            starting_balance=starting_balance,
            monthly_withdrawal=monthly_withdrawal,
            nominal_rate_pct=rate,
            rate_period=drawdown_rate_period_var.get(),
            compounds_per_year=COMPOUND_FREQUENCIES[drawdown_compound_frequency_var.get()],
            inflation_rate_pct=inflation,
            index_withdrawal_to_inflation=index_withdrawal_var.get() == "Yes",
        )
    except ValueError as e:
        if not silent:
            report_field_error(None, str(e), error_message_drawdown)
        return

    symbol = currency_var.get()
    if result["depleted"]:
        lasts_text = format_years_months(result["months_lasted"])
    else:
        lasts_text = f"{MAX_DRAWDOWN_YEARS}+ years (never depletes)"

    result_vars_drawdown["lasts"].set(lasts_text)
    result_vars_drawdown["final_balance"].set(format_money(result["final_balance"], symbol))
    result_vars_drawdown["total_withdrawn"].set(format_money(result["total_withdrawn"], symbol))
    result_vars_drawdown["total_withdrawn_real"].set(format_money(result["total_withdrawn_real"], symbol))
    result_vars_drawdown["sustainable"].set(format_money(result["sustainable_monthly_withdrawal"], symbol))
    result_vars_drawdown["apy"].set(format_pct(result["effective_annual_rate_pct"]))

    if result["depleted"] and not silent:
        error_message_drawdown.set(
            f"Your money runs out after {lasts_text}. "
            f"Withdrawing {format_money(result['sustainable_monthly_withdrawal'], symbol)}/month would last indefinitely."
        )

    global last_result_drawdown
    last_result_drawdown = {
        "Currency": symbol,
        "Starting Balance": starting_balance,
        "Monthly Withdrawal": monthly_withdrawal,
        "Interest Rate (%)": rate,
        "Rate Period": drawdown_rate_period_var.get(),
        "Compound Frequency": drawdown_compound_frequency_var.get(),
        "Inflation Rate (%/yr)": inflation,
        "Raise Withdrawal With Inflation": index_withdrawal_var.get(),
        "Money Lasts": lasts_text,
        "Final Balance": result["final_balance"],
        "Total Withdrawn": result["total_withdrawn"],
        "Total Withdrawn (today's money)": result["total_withdrawn_real"],
        "Sustainable Monthly Withdrawal": result["sustainable_monthly_withdrawal"],
        "Compounded Rate (APY %)": result["effective_annual_rate_pct"],
    }

    show_result(views["drawdown"], result)


def copy_future_value_to_drawdown():
    if last_result_main is None:
        error_message_drawdown.set("Calculate a Future Value result first.")
        return
    entry = entries_drawdown["starting_balance"]
    entry.delete(0, "end")
    entry.insert(0, f"{last_result_main['Future Value']:.2f}")
    error_message_drawdown.set("")


def export_result_to_csv(result, error_var, default_filename):
    if result is None:
        error_var.set("Calculate a result before exporting.")
        return

    path = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv")],
        initialfile=default_filename,
    )
    if not path:
        return

    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["Field", "Value"])
        for field, value in result.items():
            writer.writerow([field, value])


def export_future_value():
    export_result_to_csv(last_result_main, error_message_main, "future_value_result.csv")


def export_target_plan():
    export_result_to_csv(last_result_target, error_message_target, "target_plan_result.csv")


def export_drawdown():
    export_result_to_csv(last_result_drawdown, error_message_drawdown, "retirement_drawdown_result.csv")


def toggle_dark_mode():
    current = app.style.theme.name
    app.style.theme_use(DARK_THEME if current == LIGHT_THEME else LIGHT_THEME)


def show_about():
    tb.Messagebox.show_info(
        "Retirement Planning\n\n"
        "Future Value — project how your savings grow.\n"
        "Target Plan — find the monthly contribution to reach a goal.\n"
        "Retirement Drawdown — see how long your money lasts.\n\n"
        "All tabs account for inflation and show results in today's money.",
        title="About",
    )


def build_menu():
    menu = tb.Menu(app)
    app.config(menu=menu)

    file_menu = tb.Menu(menu, tearoff=False)
    file_menu.add_command(label="Exit", command=app.destroy)
    menu.add_cascade(label="File", menu=file_menu)

    view_menu = tb.Menu(menu, tearoff=False)
    view_menu.add_command(label="Toggle Dark Mode", command=toggle_dark_mode)
    menu.add_cascade(label="View", menu=view_menu)

    help_menu = tb.Menu(menu, tearoff=False)
    help_menu.add_command(label="About", command=show_about)
    menu.add_cascade(label="Help", menu=help_menu)


def build_app():
    global app, currency_var

    app = tb.Window(themename=LIGHT_THEME, title="Retirement Planning")
    app.geometry("1040x760")
    app.minsize(900, 640)
    app.columnconfigure(0, weight=1)
    app.rowconfigure(0, weight=1)

    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.ico")
    if os.path.exists(icon_path):
        try:
            app.iconbitmap(icon_path)
        except Exception:
            pass

    build_menu()

    # Currency is shared by every tab, so it must exist before any tab is built.
    currency_var = tb.StringVar(value=CURRENCY_SYMBOLS[0])

    notebook = tb.Notebook(app)
    notebook.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

    build_future_value_tab(notebook)
    build_target_plan_tab(notebook)
    build_drawdown_tab(notebook)

    tab_callbacks = (calculate_future_value, calculate_target_plan, calculate_drawdown)

    def handle_return(event):
        index = notebook.index(notebook.select())
        if 0 <= index < len(tab_callbacks):
            tab_callbacks[index]()

    app.bind("<Return>", handle_return)

    return app


if __name__ == "__main__":
    build_app()
    app.mainloop()
