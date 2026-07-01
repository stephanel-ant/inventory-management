from datetime import date, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
from mock_data import inventory_items, orders, demand_forecasts, backlog_items, spending_summary, monthly_spending, category_spending, recent_transactions, purchase_orders

app = FastAPI(title="Factory Inventory Management System")

# Quarter mapping for date filtering
QUARTER_MAP = {
    'Q1-2025': ['2025-01', '2025-02', '2025-03'],
    'Q2-2025': ['2025-04', '2025-05', '2025-06'],
    'Q3-2025': ['2025-07', '2025-08', '2025-09'],
    'Q4-2025': ['2025-10', '2025-11', '2025-12']
}

# Per-warehouse restocking lead times (days). Used to compute
# expected_delivery_date on submitted purchase orders. Unknown
# warehouses fall back to 7 days.
WAREHOUSE_LEAD_TIME_DAYS = {
    "San Francisco": 5,
    "London": 10,
    "Tokyo": 14,
}

# Heuristic weight applied to shortfall when ranking restocking
# candidates — boosts items with rising demand so they win budget
# allocation ahead of stable/declining ones. Not a business rule,
# just a demo prioritization knob.
TREND_MULTIPLIER = {
    "increasing": 1.5,
    "stable": 1.0,
    "decreasing": 0.7,
}

def filter_by_month(items: list, month: Optional[str]) -> list:
    """Filter items by month/quarter based on order_date field"""
    if not month or month == 'all':
        return items

    if month.startswith('Q'):
        # Handle quarters
        if month in QUARTER_MAP:
            months = QUARTER_MAP[month]
            return [item for item in items if any(m in item.get('order_date', '') for m in months)]
    else:
        # Direct month match
        return [item for item in items if month in item.get('order_date', '')]

    return items

def apply_filters(items: list, warehouse: Optional[str] = None, category: Optional[str] = None,
                 status: Optional[str] = None) -> list:
    """Apply common filters to a list of items"""
    filtered = items

    if warehouse and warehouse != 'all':
        filtered = [item for item in filtered if item.get('warehouse') == warehouse]

    if category and category != 'all':
        filtered = [item for item in filtered if item.get('category', '').lower() == category.lower()]

    if status and status != 'all':
        filtered = [item for item in filtered if item.get('status', '').lower() == status.lower()]

    return filtered

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class InventoryItem(BaseModel):
    id: str
    sku: str
    name: str
    category: str
    warehouse: str
    quantity_on_hand: int
    reorder_point: int
    unit_cost: float
    location: str
    last_updated: str

class Order(BaseModel):
    id: str
    order_number: str
    customer: str
    items: List[dict]
    status: str
    order_date: str
    expected_delivery: str
    total_value: float
    actual_delivery: Optional[str] = None
    warehouse: Optional[str] = None
    category: Optional[str] = None

class DemandForecast(BaseModel):
    id: str
    item_sku: str
    item_name: str
    current_demand: int
    forecasted_demand: int
    trend: str
    period: str

class BacklogItem(BaseModel):
    id: str
    order_id: str
    item_sku: str
    item_name: str
    quantity_needed: int
    quantity_available: int
    days_delayed: int
    priority: str
    has_purchase_order: Optional[bool] = False

class PurchaseOrder(BaseModel):
    id: str
    order_number: str
    item_sku: str
    item_name: str
    warehouse: str
    quantity: int
    unit_cost: float
    total_cost: float
    status: str
    created_date: str
    lead_time_days: int
    expected_delivery_date: str

class PurchaseOrderLineItem(BaseModel):
    sku: str
    quantity: int

class CreatePurchaseOrderRequest(BaseModel):
    items: List[PurchaseOrderLineItem]

class RestockingRecommendation(BaseModel):
    item_sku: str
    item_name: str
    warehouse: str
    category: str
    unit_cost: float
    quantity_on_hand: int
    reorder_point: int
    forecasted_demand: int
    trend: str
    shortfall: int
    recommended_quantity: int
    line_cost: float
    priority_score: float
    selected: bool

class RestockingRecommendationsResponse(BaseModel):
    budget: float
    recommendations: List[RestockingRecommendation]
    total_selected_cost: float
    remaining_budget: float

# API endpoints
@app.get("/")
def root():
    return {"message": "Factory Inventory Management System API", "version": "1.0.0"}

@app.get("/api/inventory", response_model=List[InventoryItem])
def get_inventory(
    warehouse: Optional[str] = None,
    category: Optional[str] = None
):
    """Get all inventory items with optional filtering"""
    return apply_filters(inventory_items, warehouse, category)

@app.get("/api/inventory/{item_id}", response_model=InventoryItem)
def get_inventory_item(item_id: str):
    """Get a specific inventory item"""
    item = next((item for item in inventory_items if item["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.get("/api/orders", response_model=List[Order])
def get_orders(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get all orders with optional filtering"""
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)
    return filtered_orders

@app.get("/api/orders/{order_id}", response_model=Order)
def get_order(order_id: str):
    """Get a specific order"""
    order = next((order for order in orders if order["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/api/demand", response_model=List[DemandForecast])
def get_demand_forecasts():
    """Get demand forecasts"""
    return demand_forecasts

@app.get("/api/backlog", response_model=List[BacklogItem])
def get_backlog():
    """Get backlog items with purchase order status"""
    # Add has_purchase_order flag to each backlog item
    result = []
    for item in backlog_items:
        item_dict = dict(item)
        # Check if this backlog item has a purchase order
        # Restocking POs don't carry backlog_item_id, so use .get() to
        # avoid KeyError when the list contains SKU-based purchase orders.
        has_po = any(po.get("backlog_item_id") == item["id"] for po in purchase_orders)
        item_dict["has_purchase_order"] = has_po
        result.append(item_dict)
    return result

@app.get("/api/dashboard/summary")
def get_dashboard_summary(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get summary statistics for dashboard with optional filtering"""
    # Filter inventory
    filtered_inventory = apply_filters(inventory_items, warehouse, category)

    # Filter orders
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)

    total_inventory_value = sum(item["quantity_on_hand"] * item["unit_cost"] for item in filtered_inventory)
    low_stock_items = len([item for item in filtered_inventory if item["quantity_on_hand"] <= item["reorder_point"]])
    pending_orders = len([order for order in filtered_orders if order["status"] in ["Processing", "Backordered"]])
    total_backlog_items = len(backlog_items)

    return {
        "total_inventory_value": round(total_inventory_value, 2),
        "low_stock_items": low_stock_items,
        "pending_orders": pending_orders,
        "total_backlog_items": total_backlog_items,
        "total_orders_value": sum(order["total_value"] for order in filtered_orders)
    }

@app.get("/api/spending/summary")
def get_spending_summary():
    """Get spending summary statistics"""
    return spending_summary

@app.get("/api/spending/monthly")
def get_monthly_spending():
    """Get monthly spending breakdown"""
    return monthly_spending

@app.get("/api/spending/categories")
def get_category_spending():
    """Get spending by category"""
    return category_spending

@app.get("/api/spending/transactions")
def get_recent_transactions():
    """Get recent transactions"""
    return recent_transactions

@app.get("/api/reports/quarterly")
def get_quarterly_reports():
    """Get quarterly performance reports"""
    # Calculate quarterly statistics from orders
    quarters = {}

    for order in orders:
        order_date = order.get('order_date', '')
        # Determine quarter
        if '2025-01' in order_date or '2025-02' in order_date or '2025-03' in order_date:
            quarter = 'Q1-2025'
        elif '2025-04' in order_date or '2025-05' in order_date or '2025-06' in order_date:
            quarter = 'Q2-2025'
        elif '2025-07' in order_date or '2025-08' in order_date or '2025-09' in order_date:
            quarter = 'Q3-2025'
        elif '2025-10' in order_date or '2025-11' in order_date or '2025-12' in order_date:
            quarter = 'Q4-2025'
        else:
            continue

        if quarter not in quarters:
            quarters[quarter] = {
                'quarter': quarter,
                'total_orders': 0,
                'total_revenue': 0,
                'delivered_orders': 0,
                'avg_order_value': 0
            }

        quarters[quarter]['total_orders'] += 1
        quarters[quarter]['total_revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            quarters[quarter]['delivered_orders'] += 1

    # Calculate averages and fulfillment rate
    result = []
    for q, data in quarters.items():
        if data['total_orders'] > 0:
            data['avg_order_value'] = round(data['total_revenue'] / data['total_orders'], 2)
            data['fulfillment_rate'] = round((data['delivered_orders'] / data['total_orders']) * 100, 1)
        result.append(data)

    # Sort by quarter
    result.sort(key=lambda x: x['quarter'])
    return result

@app.get("/api/reports/monthly-trends")
def get_monthly_trends():
    """Get month-over-month trends"""
    months = {}

    for order in orders:
        order_date = order.get('order_date', '')
        if not order_date:
            continue

        # Extract month (format: YYYY-MM-DD)
        month = order_date[:7]  # Gets YYYY-MM

        if month not in months:
            months[month] = {
                'month': month,
                'order_count': 0,
                'revenue': 0,
                'delivered_count': 0
            }

        months[month]['order_count'] += 1
        months[month]['revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            months[month]['delivered_count'] += 1

    # Convert to list and sort
    result = list(months.values())
    result.sort(key=lambda x: x['month'])
    return result

@app.get("/api/restocking/recommendations", response_model=RestockingRecommendationsResponse)
def get_restocking_recommendations(
    budget: float = 25000,
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
):
    """Rank forecast shortfalls and greedily select items within budget."""
    inv_by_sku = {i["sku"]: i for i in inventory_items}
    candidates = []
    for f in demand_forecasts:
        inv = inv_by_sku.get(f["item_sku"])
        if not inv:
            continue
        if warehouse and warehouse != "all" and inv["warehouse"] != warehouse:
            continue
        if category and category != "all" and inv["category"].lower() != category.lower():
            continue
        shortfall = f["forecasted_demand"] - inv["quantity_on_hand"]
        if shortfall <= 0:
            continue
        line_cost = round(shortfall * inv["unit_cost"], 2)
        priority = round(shortfall * TREND_MULTIPLIER.get(f["trend"], 1.0), 2)
        candidates.append({
            "item_sku": f["item_sku"],
            "item_name": f["item_name"],
            "warehouse": inv["warehouse"],
            "category": inv["category"],
            "unit_cost": inv["unit_cost"],
            "quantity_on_hand": inv["quantity_on_hand"],
            "reorder_point": inv["reorder_point"],
            "forecasted_demand": f["forecasted_demand"],
            "trend": f["trend"],
            "shortfall": shortfall,
            "recommended_quantity": shortfall,
            "line_cost": line_cost,
            "priority_score": priority,
            "selected": False,
        })

    candidates.sort(key=lambda c: c["priority_score"], reverse=True)

    # Greedy fill: walk the priority-sorted list and mark items selected
    # while they fit. Items that don't fit are skipped (not a hard stop),
    # so a cheap low-priority item can still fill leftover budget.
    remaining = budget
    for c in candidates:
        if c["line_cost"] <= remaining:
            c["selected"] = True
            remaining -= c["line_cost"]

    return {
        "budget": budget,
        "recommendations": candidates,
        "total_selected_cost": round(budget - remaining, 2),
        "remaining_budget": round(remaining, 2),
    }

@app.get("/api/purchase-orders", response_model=List[PurchaseOrder])
def get_purchase_orders():
    """List submitted purchase orders (newest first)."""
    return sorted(purchase_orders, key=lambda p: p["created_date"], reverse=True)

@app.post("/api/purchase-orders", response_model=List[PurchaseOrder], status_code=201)
def create_purchase_orders(req: CreatePurchaseOrderRequest):
    """Create one PO per line item, enriched from inventory with lead time."""
    if not req.items:
        raise HTTPException(status_code=400, detail="items cannot be empty")

    inv_by_sku = {i["sku"]: i for i in inventory_items}
    today = date.today()
    created = []
    for line in req.items:
        inv = inv_by_sku.get(line.sku)
        if not inv:
            raise HTTPException(status_code=400, detail=f"Unknown SKU: {line.sku}")
        lead = WAREHOUSE_LEAD_TIME_DAYS.get(inv["warehouse"], 7)
        po_id = str(len(purchase_orders) + 1)
        po = {
            "id": po_id,
            "order_number": f"PO-{today.year}-{int(po_id):04d}",
            "item_sku": line.sku,
            "item_name": inv["name"],
            "warehouse": inv["warehouse"],
            "quantity": line.quantity,
            "unit_cost": inv["unit_cost"],
            "total_cost": round(line.quantity * inv["unit_cost"], 2),
            "status": "Submitted",
            "created_date": today.isoformat(),
            "lead_time_days": lead,
            "expected_delivery_date": (today + timedelta(days=lead)).isoformat(),
        }
        purchase_orders.append(po)
        created.append(po)
    return created

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
