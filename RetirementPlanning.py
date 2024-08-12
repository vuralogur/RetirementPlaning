import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

def calculate_future_value():
    try:
        current_savings = float(entry_current_savings.get())
        monthly_contribution = float(entry_monthly_contribution.get())
        monthly_return_rate = float(entry_annual_return_rate.get()) / 100
        retirement_age = int(entry_retirement_age.get())
        current_age = int(entry_current_age.get())
        
        if current_age >= retirement_age:
            messagebox.showerror("Error", "Current age must be less than retirement age.")
            return

        months = (retirement_age - current_age) * 12
        future_value = current_savings

        for _ in range(months):
            future_value += future_value * monthly_return_rate
            future_value += monthly_contribution

        result.set(f"{future_value:,.2f}")

    except ValueError:
        messagebox.showerror("Error", "Please enter valid numerical values.")

def calculate_target_plan():
    try:
        target_amount = float(entry_target_amount.get())
        current_savings = float(entry_current_savings_target.get())
        monthly_return_rate = float(entry_annual_return_rate_target.get()) / 100
        years_to_target = int(entry_years_to_target.get())
        
        months = years_to_target * 12
        required_monthly_contribution = (target_amount - current_savings * (1 + monthly_return_rate) ** months) / months
        
        result_target.set(f"{required_monthly_contribution:,.2f}")

        distance_to_target = target_amount - (current_savings * (1 + monthly_return_rate) ** months + required_monthly_contribution * months)
        feedback.set(f"You are {distance_to_target:,.2f} units away from your target.")

    except ValueError:
        messagebox.showerror("Error", "Please enter valid numerical values.")

def switch_frame(frame_name):
    if frame_name == "target_plan":
        for widget in app.winfo_children():
            widget.destroy()
        setup_target_plan_frame()
    elif frame_name == "main":
        for widget in app.winfo_children():
            widget.destroy()
        setup_main_frame()

def setup_main_frame():
    global entry_current_savings, entry_monthly_contribution, entry_annual_return_rate, entry_retirement_age, entry_current_age, result

    app.title("Retirement Planning")

    frame_inputs = ttk.Frame(app, padding="10")
    frame_inputs.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    labels = ["Current Savings", "Monthly Contribution", "Monthly Return Rate (%)", "Retirement Age", "Current Age"]
    for i, label in enumerate(labels):
        ttk.Label(frame_inputs, text=label).grid(row=i, column=0, sticky=tk.W, pady=2)

    entry_current_savings = ttk.Entry(frame_inputs)
    entry_current_savings.grid(row=0, column=1, padx=5, pady=2)

    entry_monthly_contribution = ttk.Entry(frame_inputs)
    entry_monthly_contribution.grid(row=1, column=1, padx=5, pady=2)

    entry_annual_return_rate = ttk.Entry(frame_inputs)
    entry_annual_return_rate.grid(row=2, column=1, padx=5, pady=2)

    entry_retirement_age = ttk.Entry(frame_inputs)
    entry_retirement_age.grid(row=3, column=1, padx=5, pady=2)

    entry_current_age = ttk.Entry(frame_inputs)
    entry_current_age.grid(row=4, column=1, padx=5, pady=2)

    result = tk.StringVar()
    ttk.Label(frame_inputs, text="Future Value:").grid(row=5, column=0, sticky=tk.W, pady=2)
    ttk.Label(frame_inputs, textvariable=result).grid(row=5, column=1, sticky=tk.W, pady=2)

    button_calculate = ttk.Button(frame_inputs, text="Calculate", command=calculate_future_value)
    button_calculate.grid(row=6, columnspan=2, pady=10)

    button_target_plan = ttk.Button(frame_inputs, text="Target-Based Plan", command=lambda: switch_frame("target_plan"))
    button_target_plan.grid(row=7, columnspan=2, pady=10)

def setup_target_plan_frame():
    global entry_target_amount, entry_current_savings_target, entry_annual_return_rate_target, entry_years_to_target, result_target, feedback

    app.title("Target-Based Savings Plan")

    frame_inputs = ttk.Frame(app, padding="10")
    frame_inputs.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    labels = ["Target Savings Amount", "Current Savings", "Monthly Return Rate (%)", "Years to Reach Target"]
    for i, label in enumerate(labels):
        ttk.Label(frame_inputs, text=label).grid(row=i, column=0, sticky=tk.W, pady=2)

    entry_target_amount = ttk.Entry(frame_inputs)
    entry_target_amount.grid(row=0, column=1, padx=5, pady=2)

    entry_current_savings_target = ttk.Entry(frame_inputs)
    entry_current_savings_target.grid(row=1, column=1, padx=5, pady=2)

    entry_annual_return_rate_target = ttk.Entry(frame_inputs)
    entry_annual_return_rate_target.grid(row=2, column=1, padx=5, pady=2)

    entry_years_to_target = ttk.Entry(frame_inputs)
    entry_years_to_target.grid(row=3, column=1, padx=5, pady=2)

    result_target = tk.StringVar()
    feedback = tk.StringVar()

    ttk.Label(frame_inputs, text="Required Monthly Contribution:").grid(row=4, column=0, sticky=tk.W, pady=2)
    ttk.Label(frame_inputs, textvariable=result_target).grid(row=4, column=1, sticky=tk.W, pady=2)

    ttk.Label(frame_inputs, text="Feedback:").grid(row=5, column=0, sticky=tk.W, pady=2)
    ttk.Label(frame_inputs, textvariable=feedback).grid(row=5, column=1, sticky=tk.W, pady=2)

    button_calculate = ttk.Button(frame_inputs, text="Calculate", command=calculate_target_plan)
    button_calculate.grid(row=6, columnspan=2, pady=10)

    button_back = ttk.Button(frame_inputs, text="Back", command=lambda: switch_frame("main"))
    button_back.grid(row=7, columnspan=2, pady=10)

app = tk.Tk()
setup_main_frame()
app.mainloop()
