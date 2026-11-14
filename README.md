# FactoryFlow — Manufacturing Material Planning Simulator (Phase 1)

A beginner-friendly **manufacturing supply chain portfolio project** that uses **100% fictional electronics factory data**. It runs locally, without ERP accounts, company systems, commercial APIs, or confidential records.

![Status](https://img.shields.io/badge/status-learning%20prototype-blue)

## What this version does

- Simulates production demand for a smart desk lamp and a wireless charger.
- Uses a **one-level Bill of Materials (BOM)** to calculate component requirements.
- Accounts for on-hand inventory, reserved stock, safety stock, and dated incoming receipts.
- Identifies material shortages and rounds suggested purchase quantities up to supplier pack sizes.
- Calculates theoretical latest order dates from the production start and lead times.
- Offers four scenarios: baseline, demand surge, supplier delays, and additional stock.
- Contains automated tests for key supply planning calculations.

**Important:** This is a single-date, one-bucket *MRP learning simulator*, not an enterprise-grade MRP/ERP system. It does **not** create purchase orders or check factory capacity.

## Requirements

- Python **3.11+** recommended
- VS Code (optional) and a terminal

## How to run on Windows (VS Code PowerShell terminal)

1. Download/extract the starter ZIP and open its folder in VS Code (`File` → `Open Folder`).
2. Open `Terminal` → `New Terminal`.
3. Run these commands **one at a time**:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m streamlit run app.py
```

The app should open in a browser tab. To stop it, press `Ctrl+C` in the terminal.

If the `py` launcher is unavailable, substitute `python` for `py` on the first line. If Python is missing altogether, install Python 3.11 or newer first.

**Why use `.venv\Scripts\python.exe` directly?** It avoids PowerShell script-activation policy issues.

## Folder guide

| File | Beginner explanation |
|---|---|
| `app.py` | What you see and click: dashboard, scenario controls, tables. |
| `factoryflow/data.py` | Fictional finished products, BOM, inventory, and expected receipts. |
| `factoryflow/planning.py` | The actual planning calculations and business rules. |
| `tests/test_planning.py` | Tests to check whether the calculations produce correct answers. |
| `requirements.txt` | The software packages the project needs. |
| `CODEX_NEXT_STEPS.md` | Your next instruction for Codex after confirming Phase 1 works. |

## Example calculation

Default plan: 200 smart desk lamps + 100 wireless chargers, production date December 1, 2026; snapshot November 14, 2026.

**LED boards:** demand 200; 120 usable on hand; 40 incoming on time. Shortage = `max(0, 200 - 120 - 40) = 40`. Supplier packs = 20; order suggestion = 40.

**Screws:** 4 × 200 + 2 × 100 = 1,000 gross required. On-hand = 1,000; safety stock = 100, so usable = 900; net shortage = 100. Supplier packs = 200; purchase suggestion rounds up to 200.

**Power adapters:** 200 gross required, 150 on hand. The additional 20 arrive December 3, **after** production start and cannot cover December 1 demand. Net shortage = 50.

## Key assumptions / limitations

- One level of BOM only; components are not expanded into subassemblies.
- All products require components on the **same** user-selected production start date.
- Inventory is a fictional snapshot. Receipts on/before the snapshot are assumed already reflected in on-hand, avoiding double counting.
- Supplier lead times are calendar days, with no holiday or business-day logic.
- Suggestions reflect pack multiples only (no minimum order quantity rules yet).
- No yield loss, scrap, quality holds, existing reservations by order, capacity constraints, routing, machine schedules, or actual procurement transactions.
- Sufficient material does **not** guarantee an achievable production schedule.
- Simulated supplier delivery dates are assumptions, not actual delivery promises.
- The scenario controls change the displayed planning result, but **do not save** edits to an external system.

## Learning challenge

Before asking Codex to change the app, try to explain why the screws have a 100-unit shortage even when there are 1,000 screws on hand. If you can explain the safety-stock rule and the pack-size rounding, you understand a crucial part of the first version.

## Publishing

Publish only after running the tests, verifying the demo locally, and adding your own screenshots. Be transparent that this is an **AI-assisted learning project using synthetic data**.
