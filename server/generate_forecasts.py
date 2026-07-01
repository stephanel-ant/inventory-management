"""Regenerate demand_forecasts.json with SKUs that match inventory.json.

The original fixture used SKUs that don't exist in inventory.json, which
made it impossible to join forecast → inventory to get unit_cost for
budget-aware restocking recommendations. This script rebuilds the file
with one forecast per real inventory SKU.
"""
import json
import random
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
random.seed(42)

with open(DATA_DIR / "inventory.json") as f:
    inventory = json.load(f)

# (trend_name, forecast_multiplier_low, forecast_multiplier_high)
TRENDS = [
    ("increasing", 1.15, 1.45),
    ("stable", 0.98, 1.02),
    ("decreasing", 0.70, 0.90),
]
TREND_WEIGHTS = [45, 30, 25]

forecasts = []
for idx, item in enumerate(inventory, 1):
    trend, lo, hi = random.choices(TRENDS, weights=TREND_WEIGHTS)[0]
    qoh = item["quantity_on_hand"]
    # Bias current_demand around quantity_on_hand so a realistic ~60% of
    # items end up with forecasted_demand > qoh (positive shortfall).
    current = max(1, random.randint(int(qoh * 0.7), int(qoh * 1.3)))
    forecasted = int(current * random.uniform(lo, hi))
    forecasts.append({
        "id": str(idx),
        "item_sku": item["sku"],
        "item_name": item["name"],
        "current_demand": current,
        "forecasted_demand": forecasted,
        "trend": trend,
        "period": "Next 30 days",
    })

with open(DATA_DIR / "demand_forecasts.json", "w") as f:
    json.dump(forecasts, f, indent=2)

print(f"Wrote {len(forecasts)} forecasts to {DATA_DIR / 'demand_forecasts.json'}")
