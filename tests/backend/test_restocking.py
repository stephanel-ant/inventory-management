"""
Tests for restocking recommendations and purchase-order API endpoints.
"""
import pytest
from mock_data import purchase_orders


@pytest.fixture(autouse=True)
def reset_purchase_orders():
    """Purchase orders are appended to a module-level list; clear it around
    each test so POST tests don't leak state into one another."""
    purchase_orders.clear()
    yield
    purchase_orders.clear()


class TestRestockingRecommendations:
    """Test suite for GET /api/restocking/recommendations."""

    def test_returns_200_with_envelope(self, client):
        """Test the response envelope has all top-level keys."""
        response = client.get("/api/restocking/recommendations?budget=50000")
        assert response.status_code == 200

        body = response.json()
        assert set(body) == {
            "budget", "recommendations", "total_selected_cost", "remaining_budget"
        }
        assert isinstance(body["recommendations"], list)

    def test_recommendation_structure(self, client):
        """Test that each recommendation has all required fields."""
        response = client.get("/api/restocking/recommendations?budget=999999")
        recs = response.json()["recommendations"]
        assert len(recs) > 0

        first = recs[0]
        for field in [
            "item_sku", "item_name", "warehouse", "category", "unit_cost",
            "quantity_on_hand", "reorder_point", "forecasted_demand", "trend",
            "shortfall", "recommended_quantity", "line_cost",
            "priority_score", "selected",
        ]:
            assert field in first

    def test_selected_cost_within_budget(self, client):
        """Test that greedy selection never exceeds the budget."""
        response = client.get("/api/restocking/recommendations?budget=10000")
        body = response.json()

        assert body["total_selected_cost"] <= 10000
        assert abs(body["total_selected_cost"] + body["remaining_budget"] - 10000) < 0.01

        selected_sum = sum(
            r["line_cost"] for r in body["recommendations"] if r["selected"]
        )
        assert abs(selected_sum - body["total_selected_cost"]) < 0.01

    def test_only_positive_shortfall(self, client):
        """Test that items with no shortfall are excluded entirely."""
        response = client.get("/api/restocking/recommendations?budget=999999")
        recs = response.json()["recommendations"]

        for rec in recs:
            assert rec["shortfall"] > 0
            assert rec["recommended_quantity"] == rec["shortfall"]

    def test_sorted_by_priority_desc(self, client):
        """Test that recommendations are ranked highest-priority first."""
        response = client.get("/api/restocking/recommendations?budget=999999")
        recs = response.json()["recommendations"]

        scores = [r["priority_score"] for r in recs]
        assert scores == sorted(scores, reverse=True)

    def test_warehouse_filter(self, client):
        """Test filtering recommendations by warehouse."""
        response = client.get(
            "/api/restocking/recommendations?budget=999999&warehouse=Tokyo"
        )
        recs = response.json()["recommendations"]

        for rec in recs:
            assert rec["warehouse"] == "Tokyo"

    def test_zero_budget_selects_nothing(self, client):
        """Test that a $0 budget yields no selected items."""
        response = client.get("/api/restocking/recommendations?budget=0")
        body = response.json()

        assert body["total_selected_cost"] == 0
        for rec in body["recommendations"]:
            assert rec["selected"] is False


class TestPurchaseOrders:
    """Test suite for POST/GET /api/purchase-orders."""

    def test_create_returns_201_and_enriches(self, client):
        """Test that POST enriches the line with inventory data."""
        response = client.post(
            "/api/purchase-orders",
            json={"items": [{"sku": "PCB-001", "quantity": 100}]},
        )
        assert response.status_code == 201

        created = response.json()
        assert isinstance(created, list)
        assert len(created) == 1

        po = created[0]
        assert po["item_sku"] == "PCB-001"
        assert po["warehouse"] == "San Francisco"
        assert po["status"] == "Submitted"
        assert po["order_number"].startswith("PO-")
        assert abs(po["total_cost"] - 100 * 24.99) < 0.01

    def test_lead_time_per_warehouse(self, client):
        """Test that lead time is looked up from the warehouse map."""
        response = client.post(
            "/api/purchase-orders",
            json={"items": [{"sku": "PCB-001", "quantity": 1}]},
        )
        po = response.json()[0]

        assert po["lead_time_days"] == 5  # San Francisco
        assert "expected_delivery_date" in po
        assert "-" in po["expected_delivery_date"]

    def test_unknown_sku_returns_400(self, client):
        """Test that an unknown SKU is rejected."""
        response = client.post(
            "/api/purchase-orders",
            json={"items": [{"sku": "NOPE-999", "quantity": 1}]},
        )
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data
        assert "NOPE-999" in data["detail"]

    def test_empty_items_returns_400(self, client):
        """Test that an empty items list is rejected."""
        response = client.post("/api/purchase-orders", json={"items": []})
        assert response.status_code == 400

    def test_get_lists_created_orders(self, client):
        """Test that GET returns POs created in the same process."""
        client.post(
            "/api/purchase-orders",
            json={"items": [{"sku": "PCB-001", "quantity": 10}]},
        )
        response = client.get("/api/purchase-orders")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["item_sku"] == "PCB-001"
