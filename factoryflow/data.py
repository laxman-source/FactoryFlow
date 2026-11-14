"""Fictional demonstration data for FactoryFlow Phase 1.

No customer, employer, or supplier information is included.
All stock quantities and lead times are invented for the simulation.
"""

from datetime import date

DEMO_AS_OF = date(2026, 11, 14)
DEMO_PRODUCTION_DATE = date(2026, 12, 1)

PRODUCTS = [
    {"sku": "FG-LAMP-01", "name": "Smart Desk Lamp"},
    {"sku": "FG-CHARGER-02", "name": "Wireless Charger"},
]

# A ONE-LEVEL BOM: required components for one finished product.
BOM = [
    {"finished_sku": "FG-LAMP-01", "component_sku": "LED-100", "qty_per_unit": 1},
    {"finished_sku": "FG-LAMP-01", "component_sku": "LAM-HSG-110", "qty_per_unit": 1},
    {"finished_sku": "FG-LAMP-01", "component_sku": "SCR-120", "qty_per_unit": 4},
    {"finished_sku": "FG-LAMP-01", "component_sku": "ADP-130", "qty_per_unit": 1},
    {"finished_sku": "FG-CHARGER-02", "component_sku": "PCB-200", "qty_per_unit": 1},
    {"finished_sku": "FG-CHARGER-02", "component_sku": "CHG-HSG-210", "qty_per_unit": 1},
    {"finished_sku": "FG-CHARGER-02", "component_sku": "SCR-120", "qty_per_unit": 2},
    {"finished_sku": "FG-CHARGER-02", "component_sku": "USB-220", "qty_per_unit": 1},
]

INVENTORY = [
    {"sku": "LED-100", "name": "LED circuit board", "on_hand": 120, "reserved": 0, "safety_stock": 0, "lead_days": 7, "pack_size": 20},
    {"sku": "LAM-HSG-110", "name": "Lamp housing", "on_hand": 240, "reserved": 0, "safety_stock": 0, "lead_days": 5, "pack_size": 10},
    {"sku": "SCR-120", "name": "Assembly screws", "on_hand": 1000, "reserved": 0, "safety_stock": 100, "lead_days": 5, "pack_size": 200},
    {"sku": "ADP-130", "name": "Power adapter", "on_hand": 150, "reserved": 0, "safety_stock": 0, "lead_days": 12, "pack_size": 25},
    {"sku": "PCB-200", "name": "Charging PCB", "on_hand": 90, "reserved": 0, "safety_stock": 0, "lead_days": 10, "pack_size": 10},
    {"sku": "CHG-HSG-210", "name": "Charger housing", "on_hand": 110, "reserved": 0, "safety_stock": 0, "lead_days": 6, "pack_size": 10},
    {"sku": "USB-220", "name": "USB-C cable", "on_hand": 60, "reserved": 0, "safety_stock": 0, "lead_days": 6, "pack_size": 10},
]

# Incoming stock is counted ONLY when due after the simulation snapshot
# and on/before the planned production date.
RECEIPTS = [
    {"component_sku": "LED-100", "qty": 40, "due_date": date(2026, 11, 27)},
    {"component_sku": "ADP-130", "qty": 20, "due_date": date(2026, 12, 3)},
    {"component_sku": "PCB-200", "qty": 20, "due_date": date(2026, 11, 25)},
    {"component_sku": "USB-220", "qty": 50, "due_date": date(2026, 11, 30)},
]

DEFAULT_DEMAND = {"FG-LAMP-01": 200, "FG-CHARGER-02": 100}
