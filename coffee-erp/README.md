# Coffee Shop ERP Simulation & Working Capital Optimizer

A simulated ERP system — items, formulas/BOM, routings, inventory, costing, and
financials — for a fictional coffee shop, built to demonstrate manufacturing
and supply chain data modeling paired with AI-driven optimization.

## Problem Statement

Manufacturing and retail operations tie up significant working capital in
inventory while trying to balance service level, cost, and margin. This
project simulates a small production/retail operation end-to-end and applies
optimization and machine learning to two decisions operators face daily:

1. **How much inventory should we hold, of what, to minimize working capital
   while avoiding stockouts?**
2. **Which items should we prioritize/promote to maximize margin?**

## Architecture

*(diagram goes here — data flow: seed data → simulator → SQLite → costing
engine → optimization layer → dashboard)*

## Tech Stack

- **SQLite** — item master, BOM/formulas, routings, inventory, orders, financials
- **Python (pandas)** — order simulation, costing rollup
- **OR-Tools** — working capital / inventory optimization (LP)
- **scikit-learn** — margin driver analysis / promotion ranking
- **Streamlit** — interactive dashboard

## Project Structure

See repo layout below. `sql/schema.sql` defines the data model;
`src/` contains the simulation, costing, and dashboard code.

## Setup

```bash
git clone https://github.com/<your-username>/coffee-erp.git
cd coffee-erp
python -m venv venv
source venv/bin/activate  # venv\Scripts\activate on Windows
pip install -r requirements.txt

# Build the database
sqlite3 coffee_shop.db < sql/schema.sql

# Run the simulator to generate sample data
python src/simulate_orders.py

# Launch the dashboard
streamlit run src/dashboard.py
```

## Results / Screenshots

*(add once Phase 5-6 are built — margin dashboard, inventory optimization
output, before/after working capital comparison)*

## Background

Built by Kerry Hall to apply manufacturing operations and quality engineering
experience (Goodyear, Morgan Advanced Materials) to a generalized, public
version of the kinds of costing, scheduling, and inventory problems found in
industrial settings.

## License

MIT
