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


def format_years_months(total_months):
    years, months = divmod(max(total_months, 0), 12)
    return f"{years} years, {months} months"


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
):
    if initial_balance < 0:
        raise ValueError("Initial balance cannot be negative.")

    if not -100 <= nominal_rate_pct <= 100:
        raise ValueError("Interest rate must be between -100 and 100.")

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

    # Nominal rate -> effective annual rate (APY) -> effective monthly rate.
    # The simulation always steps month-by-month regardless of compound
    # frequency; compounding literally at the chosen frequency (e.g. daily)
    # is folded into the effective annual/monthly rate instead of simulating
    # day-by-day, which keeps one simulation loop while still reporting the
    # mathematically correct APY for any compounding frequency.
    annual_nominal = nominal_rate_pct * (12 if rate_period == "Monthly" else 1) / 100
    periodic_rate = annual_nominal / compounds_per_year
    effective_annual_rate = (1 + periodic_rate) ** compounds_per_year - 1
    effective_monthly_rate = (1 + effective_annual_rate) ** (1 / 12) - 1

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

        monthly_rows.append(
            {
                "year": year_index,
                "month": month_in_year,
                "interest": interest_this_month,
                "accrued_interest": cumulative_interest,
                "balance": balance,
            }
        )

        if month_in_year == 12 or month == total_months:
            yearly_rows.append(
                {
                    "year": year_index,
                    "interest": year_interest_accum,
                    "accrued_interest": cumulative_interest,
                    "balance": balance,
                }
            )
            year_interest_accum = 0.0

    future_value = balance
    total_interest = future_value - initial_balance - total_contributed

    all_time_ror_pct = (future_value - initial_balance) / initial_balance * 100 if initial_balance > 0 else None

    if effective_annual_rate > 0:
        doubling_time_months = round(math.log(2) / math.log(1 + effective_annual_rate) * 12)
    else:
        doubling_time_months = None

    return {
        "initial_balance": initial_balance,
        "future_value": future_value,
        "total_contributed": total_contributed,
        "total_interest": total_interest,
        "effective_annual_rate_pct": effective_annual_rate * 100,
        "all_time_ror_pct": all_time_ror_pct,
        "doubling_time_months": doubling_time_months,
        "monthly_rows": monthly_rows,
        "yearly_rows": yearly_rows,
        "depleted": depleted,
    }


def compute_target_plan(target_amount, current_savings, monthly_return_rate_pct, years_to_target):
    if years_to_target <= 0:
        raise ValueError("Years to reach target must be greater than zero.")

    if target_amount < 0:
        raise ValueError("Target savings amount cannot be negative.")

    if current_savings < 0:
        raise ValueError("Current savings cannot be negative.")

    if not -100 <= monthly_return_rate_pct <= 100:
        raise ValueError("Monthly return rate must be between -100 and 100.")

    monthly_return_rate = monthly_return_rate_pct / 100
    months = years_to_target * 12
    required_monthly_contribution = (target_amount - current_savings * (1 + monthly_return_rate) ** months) / months
    distance_to_target = target_amount - (current_savings * (1 + monthly_return_rate) ** months + required_monthly_contribution * months)

    return required_monthly_contribution, distance_to_target


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
last_result_main = None
last_result_target = None


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


def add_stat_row(parent, row, key, label_text, stat_vars_dict):
    tb.Label(parent, text=label_text, font=("Segoe UI", 9)).grid(row=row, column=0, sticky=W, pady=3)
    var = tb.StringVar(value="—")
    tb.Label(parent, textvariable=var, font=("Segoe UI", 11, "bold")).grid(row=row, column=1, sticky=W, padx=(10, 0), pady=3)
    stat_vars_dict[key] = var
    return var


def format_money(value, symbol):
    return f"{symbol}{value:,.2f}"


def build_future_value_tab(notebook):
    global error_message_main, chart_canvas_main, chart_axes_main, export_button_main
    global currency_var, rate_period_var, compound_frequency_var
    global contribution_type_var, contribution_frequency_var, increase_mode_var
    global result_vars_main, view_mode_var, breakdown_mode_var
    global chart_container_main, table_container_main, tree_main, growth_result_main

    growth_result_main = None
    result_vars_main = {}

    tab = tb.Frame(notebook, padding=16)
    tab.columnconfigure(0, weight=0)
    tab.columnconfigure(1, weight=1)
    tab.rowconfigure(0, weight=1)
    notebook.add(tab, text="Future Value")

    # ---- Left: scrollable input panel ----
    left_outer = tb.Frame(tab)
    left_outer.grid(row=0, column=0, sticky="ns", padx=(0, 16))

    canvas = tb.Canvas(left_outer, width=300, highlightthickness=0)
    scrollbar = tb.Scrollbar(left_outer, orient="vertical", command=canvas.yview)
    details = tb.Labelframe(canvas, text="Your Details", padding=12, bootstyle=PRIMARY)
    details.columnconfigure(1, weight=1)

    canvas_window = canvas.create_window((0, 0), window=details, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    details.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    row = 0
    tb.Label(details, text="Currency").grid(row=row, column=0, sticky=W, pady=4)
    currency_var = tb.StringVar(value=CURRENCY_SYMBOLS[0])
    currency_buttons = tb.Frame(details)
    currency_buttons.grid(row=row, column=1, sticky=W, pady=4)
    for symbol in CURRENCY_SYMBOLS:
        tb.Radiobutton(
            currency_buttons, text=symbol, variable=currency_var, value=symbol, bootstyle="toolbutton"
        ).pack(side="left", padx=(0, 2))
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

    tb.Label(details, text="Duration").grid(row=row, column=0, sticky=W, pady=4)
    duration_frame = tb.Frame(details)
    duration_frame.grid(row=row, column=1, sticky=EW, pady=4)
    entry_years = tb.Entry(duration_frame, width=6)
    entry_years.pack(side="left")
    tb.Label(duration_frame, text="yrs").pack(side="left", padx=(4, 10))
    entry_months = tb.Entry(duration_frame, width=6)
    entry_months.pack(side="left")
    tb.Label(duration_frame, text="mos").pack(side="left", padx=(4, 0))
    entries_main["duration_years"] = entry_years
    entries_main["duration_months"] = entry_months
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
    tb.Label(details, textvariable=error_message_main, bootstyle=DANGER, wraplength=260).grid(
        row=row, column=0, columnspan=2, sticky=W
    )

    # ---- Right: summary + chart/table ----
    right = tb.Frame(tab)
    right.grid(row=0, column=1, sticky="nsew")
    right.columnconfigure(0, weight=1)
    right.rowconfigure(1, weight=1)

    result_panel = tb.Labelframe(right, text="Summary", padding=12, bootstyle=SUCCESS)
    result_panel.grid(row=0, column=0, sticky=EW, pady=(0, 12))
    result_panel.columnconfigure(1, weight=1)

    add_stat_row(result_panel, 0, "future_value", "Future Value", result_vars_main)
    add_stat_row(result_panel, 1, "initial_balance", "Initial Balance", result_vars_main)
    add_stat_row(result_panel, 2, "total_interest", "Total Interest Earned", result_vars_main)
    add_stat_row(result_panel, 3, "apy", "Compounded Rate (APY)", result_vars_main)
    add_stat_row(result_panel, 4, "ror", "All-time Rate of Return", result_vars_main)
    add_stat_row(result_panel, 5, "doubling_time", "Time to Double", result_vars_main)

    view_toggle = tb.Frame(right)
    view_toggle.grid(row=1, column=0, sticky="ew")
    view_mode_var = tb.StringVar(value="Chart")
    for label in ("Chart", "Table"):
        tb.Radiobutton(
            view_toggle, text=label, variable=view_mode_var, value=label, bootstyle="toolbutton",
            command=lambda: switch_future_value_view(),
        ).pack(side="left", padx=(0, 4))

    breakdown_toggle = tb.Frame(right)
    breakdown_toggle.grid(row=1, column=0, sticky="e")
    breakdown_mode_var = tb.StringVar(value="Yearly")
    for label in ("Yearly", "Monthly"):
        tb.Radiobutton(
            breakdown_toggle, text=label, variable=breakdown_mode_var, value=label, bootstyle="toolbutton",
            command=lambda: populate_future_value_table(),
        ).pack(side="left", padx=(4, 0))

    view_area = tb.Frame(right)
    view_area.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
    view_area.columnconfigure(0, weight=1)
    view_area.rowconfigure(0, weight=1)
    right.rowconfigure(2, weight=1)

    chart_container_main = tb.Frame(view_area)
    chart_container_main.grid(row=0, column=0, sticky="nsew")

    table_container_main = tb.Frame(view_area)
    table_container_main.grid(row=0, column=0, sticky="nsew")

    figure = Figure(figsize=(5, 2.6), dpi=100)
    chart_axes_main = figure.add_subplot(111)
    chart_axes_main.set_title("Projected Growth")
    chart_axes_main.set_xlabel("Year")
    chart_axes_main.set_ylabel("Balance")
    figure.tight_layout()

    chart_canvas_main = FigureCanvasTkAgg(figure, master=chart_container_main)
    chart_canvas_main.get_tk_widget().pack(fill=BOTH, expand=True)
    chart_canvas_main.draw()

    tree_main = tb.Treeview(
        table_container_main,
        columns=("year", "month", "interest", "accrued_interest", "balance"),
        show="headings",
        bootstyle=PRIMARY,
    )
    for col, heading, width in (
        ("year", "Year", 60),
        ("month", "Month", 60),
        ("interest", "Interest", 120),
        ("accrued_interest", "Accrued Interest", 140),
        ("balance", "Balance", 120),
    ):
        tree_main.heading(col, text=heading)
        tree_main.column(col, width=width, anchor="e" if col != "year" and col != "month" else "center")
    tree_scroll = tb.Scrollbar(table_container_main, orient="vertical", command=tree_main.yview)
    tree_main.configure(yscrollcommand=tree_scroll.set)
    tree_main.pack(side="left", fill=BOTH, expand=True)
    tree_scroll.pack(side="right", fill="y")

    switch_future_value_view()


def switch_future_value_view():
    if view_mode_var.get() == "Chart":
        chart_container_main.tkraise()
    else:
        table_container_main.tkraise()


def populate_future_value_table():
    tree_main.delete(*tree_main.get_children())
    if growth_result_main is None:
        return

    symbol = currency_var.get()
    if breakdown_mode_var.get() == "Yearly":
        tree_main.configure(displaycolumns=("year", "interest", "accrued_interest", "balance"))
        for row in growth_result_main["yearly_rows"]:
            tree_main.insert(
                "",
                "end",
                values=(
                    row["year"],
                    "",
                    format_money(row["interest"], symbol),
                    format_money(row["accrued_interest"], symbol),
                    format_money(row["balance"], symbol),
                ),
            )
    else:
        tree_main.configure(displaycolumns=("year", "month", "interest", "accrued_interest", "balance"))
        for row in growth_result_main["monthly_rows"]:
            tree_main.insert(
                "",
                "end",
                values=(
                    row["year"],
                    row["month"],
                    format_money(row["interest"], symbol),
                    format_money(row["accrued_interest"], symbol),
                    format_money(row["balance"], symbol),
                ),
            )


def build_target_plan_tab(notebook):
    global result_var_target, feedback_var_target, error_message_target, export_button_target

    tab = tb.Frame(notebook, padding=16)
    tab.columnconfigure(0, weight=1)
    notebook.add(tab, text="Target Plan")

    details = tb.Labelframe(tab, text="Your Details", padding=12, bootstyle=PRIMARY)
    details.grid(row=0, column=0, sticky=EW)
    details.columnconfigure(1, weight=1)

    add_input_row(details, 0, "target_amount", "Target Savings Amount", entries_target)
    add_input_row(details, 1, "current_savings", "Current Savings", entries_target)
    add_input_row(details, 2, "monthly_return_rate", "Monthly Return Rate (%)", entries_target)
    add_input_row(details, 3, "years_to_target", "Years to Reach Target", entries_target)

    buttons = tb.Frame(tab)
    buttons.grid(row=1, column=0, sticky=EW, pady=12)
    tb.Button(buttons, text="Calculate", bootstyle=PRIMARY, command=calculate_target_plan).pack(side="left")
    export_button_target = tb.Button(buttons, text="Export to CSV", bootstyle=SECONDARY, command=export_target_plan)
    export_button_target.pack(side="left", padx=(8, 0))

    error_message_target = tb.StringVar()
    tb.Label(tab, textvariable=error_message_target, bootstyle=DANGER).grid(row=2, column=0, sticky=W)

    result_panel = tb.Labelframe(tab, text="Result", padding=12, bootstyle=SUCCESS)
    result_panel.grid(row=3, column=0, sticky=EW, pady=(4, 12))
    result_var_target = tb.StringVar(value="—")
    feedback_var_target = tb.StringVar(value="")
    tb.Label(result_panel, text="Required Monthly Contribution", font=("Segoe UI", 10)).pack(anchor=W)
    tb.Label(result_panel, textvariable=result_var_target, font=("Segoe UI", 22, "bold"), bootstyle=SUCCESS).pack(anchor=W)
    tb.Label(result_panel, textvariable=feedback_var_target, font=("Segoe UI", 10)).pack(anchor=W, pady=(6, 0))


def calculate_future_value():
    entries = list(entries_main.values())
    clear_entry_errors(entries)
    error_message_main.set("")

    try:
        initial_balance = parse_field(entries_main["initial_balance"], float, "Initial balance")
        rate = parse_field(entries_main["rate"], float, "Interest rate")
        duration_years = parse_field(entries_main["duration_years"], int, "Duration years")
        duration_months = parse_field(entries_main["duration_months"], int, "Duration months")
        contribution_amount = parse_field(entries_main["contribution_amount"], float, "Contribution amount")
        increase_value = parse_field(entries_main["increase_value"], float, "Increase value")
    except FieldError as e:
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
        )
    except ValueError as e:
        report_field_error(None, str(e), error_message_main)
        return

    symbol = currency_var.get()
    result_vars_main["future_value"].set(format_money(result["future_value"], symbol))
    result_vars_main["initial_balance"].set(format_money(result["initial_balance"], symbol))
    result_vars_main["total_interest"].set(format_money(result["total_interest"], symbol))
    result_vars_main["apy"].set(f"{result['effective_annual_rate_pct']:.2f}%")
    result_vars_main["ror"].set(
        "N/A" if result["all_time_ror_pct"] is None else f"{result['all_time_ror_pct']:.2f}%"
    )
    result_vars_main["doubling_time"].set(
        "N/A" if result["doubling_time_months"] is None else format_years_months(result["doubling_time_months"])
    )

    if result["depleted"]:
        error_message_main.set("Note: balance was fully depleted by withdrawals before the end of the term.")

    global last_result_main, growth_result_main
    growth_result_main = result
    last_result_main = {
        "Currency": symbol,
        "Initial Balance": initial_balance,
        "Interest Rate (%)": rate,
        "Rate Period": rate_period_var.get(),
        "Compound Frequency": compound_frequency_var.get(),
        "Duration": format_years_months(duration_years * 12 + duration_months),
        "Contribution Type": contribution_type_var.get(),
        "Contribution Amount": contribution_amount,
        "Contribution Frequency": contribution_frequency_var.get(),
        "Annual Increase Mode": increase_mode_var.get(),
        "Annual Increase Value": increase_value,
        "Future Value": result["future_value"],
        "Total Interest Earned": result["total_interest"],
        "Compounded Rate (APY %)": result["effective_annual_rate_pct"],
        "All-time Rate of Return (%)": result["all_time_ror_pct"],
        "Time to Double": (
            "N/A" if result["doubling_time_months"] is None else format_years_months(result["doubling_time_months"])
        ),
    }

    years = [row["year"] for row in result["yearly_rows"]]
    balances = [row["balance"] for row in result["yearly_rows"]]
    chart_axes_main.clear()
    chart_axes_main.plot(years, balances, marker="o", linewidth=2)
    chart_axes_main.set_title("Projected Growth")
    chart_axes_main.set_xlabel("Year")
    chart_axes_main.set_ylabel(f"Balance ({symbol})")
    chart_axes_main.figure.tight_layout()
    chart_canvas_main.draw()

    populate_future_value_table()


def calculate_target_plan():
    entries = list(entries_target.values())
    clear_entry_errors(entries)
    error_message_target.set("")

    try:
        target_amount = parse_field(entries_target["target_amount"], float, "Target savings amount")
        current_savings = parse_field(entries_target["current_savings"], float, "Current savings")
        monthly_return_rate_pct = parse_field(entries_target["monthly_return_rate"], float, "Monthly return rate")
        years_to_target = parse_field(entries_target["years_to_target"], int, "Years to reach target")
    except FieldError as e:
        report_field_error(e.entry, str(e), error_message_target)
        return

    try:
        required_monthly_contribution, distance_to_target = compute_target_plan(
            target_amount, current_savings, monthly_return_rate_pct, years_to_target
        )
    except ValueError as e:
        report_field_error(None, str(e), error_message_target)
        return

    result_var_target.set(f"{required_monthly_contribution:,.2f}")
    feedback_var_target.set(f"You are {distance_to_target:,.2f} away from your target.")

    global last_result_target
    last_result_target = {
        "Target Savings Amount": target_amount,
        "Current Savings": current_savings,
        "Monthly Return Rate (%)": monthly_return_rate_pct,
        "Years to Reach Target": years_to_target,
        "Required Monthly Contribution": required_monthly_contribution,
        "Distance to Target": distance_to_target,
    }


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


def toggle_dark_mode():
    current = app.style.theme.name
    app.style.theme_use(DARK_THEME if current == LIGHT_THEME else LIGHT_THEME)


def show_about():
    tb.Messagebox.show_info(
        "Retirement Planning\n\nCalculate future savings value or the monthly contribution needed to reach a savings target.",
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
    global app

    app = tb.Window(themename=LIGHT_THEME, title="Retirement Planning")
    app.geometry("980x720")
    app.minsize(880, 620)
    app.columnconfigure(0, weight=1)
    app.rowconfigure(0, weight=1)

    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.ico")
    if os.path.exists(icon_path):
        try:
            app.iconbitmap(icon_path)
        except Exception:
            pass

    build_menu()

    notebook = tb.Notebook(app)
    notebook.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

    build_future_value_tab(notebook)
    build_target_plan_tab(notebook)

    def handle_return(event):
        if notebook.index(notebook.select()) == 0:
            calculate_future_value()
        else:
            calculate_target_plan()

    app.bind("<Return>", handle_return)

    return app


if __name__ == "__main__":
    build_app()
    app.mainloop()
