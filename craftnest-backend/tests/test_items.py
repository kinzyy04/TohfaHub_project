import pytest
from httpx import AsyncClient
from tests.conftest import create_user_token_helper

@pytest.mark.asyncio
async def test_cases_for_items_endpoint(client: AsyncClient, buyer_token: str, seller_token: str):
    # ==========================================
    # Case 1: Happy path (200/201)
    # ==========================================
    # Create item (Seller creates a product)
    headers_seller = {"Authorization": f"Bearer {seller_token}"}
    item_payload = {
        "name": "Handmade Wooden Chair",
        "description": "A premium oak wooden chair made by local artisans.",
        "price": 149.99
    }
    
    create_response = await client.post("/api/v1/items", json=item_payload, headers=headers_seller)
    assert create_response.status_code == 201
    created_item = create_response.json()
    assert created_item["name"] == item_payload["name"]
    assert created_item["price"] == item_payload["price"]
    assert "id" in created_item
    item_id = created_item["id"]
    
    # Read item (Buyer reads the product)
    headers_buyer = {"Authorization": f"Bearer {buyer_token}"}
    read_response = await client.get(f"/api/v1/items/{item_id}", headers=headers_buyer)
    assert read_response.status_code == 200
    assert read_response.json()["name"] == item_payload["name"]

    # ==========================================
    # Case 2: No Authorization header -> 401
    # ==========================================
    no_auth_response = await client.get(f"/api/v1/items/{item_id}")
    assert no_auth_response.status_code == 401
    assert no_auth_response.json()["detail"] == "Not authenticated"

    # ==========================================
    # Case 3: Wrong role -> 403
    # ==========================================
    # Buyer tries to create a product (buyers do not have permission to sell/create products)
    wrong_role_response = await client.post("/api/v1/items", json=item_payload, headers=headers_buyer)
    assert wrong_role_response.status_code == 403
    assert wrong_role_response.json()["detail"] == "Operation not permitted for this role"

    # ==========================================
    # Case 4: Invalid body -> 422
    # ==========================================
    # 4a) Missing required field ('name' is missing)
    invalid_body_1 = {
        "description": "No name here",
        "price": 10.0
    }
    invalid_resp_1 = await client.post("/api/v1/items", json=invalid_body_1, headers=headers_seller)
    assert invalid_resp_1.status_code == 422
    
    # 4b) Invalid data type (price is an invalid string)
    invalid_body_2 = {
        "name": "Invalid price item",
        "price": "not-a-number"
    }
    invalid_resp_2 = await client.post("/api/v1/items", json=invalid_body_2, headers=headers_seller)
    assert invalid_resp_2.status_code == 422

    # 4c) Business logic invalid input validation (price <= 0)
    invalid_body_3 = {
        "name": "Free item",
        "price": 0.0
    }
    invalid_resp_3 = await client.post("/api/v1/items", json=invalid_body_3, headers=headers_seller)
    assert invalid_resp_3.status_code == 422
    assert invalid_resp_3.json()["detail"] == "Price must be greater than zero"

    # ==========================================
    # Case 5: Non-existent resource id -> 404
    # ==========================================
    not_found_response = await client.get("/api/v1/items/99999", headers=headers_buyer)
    assert not_found_response.status_code == 404
    assert not_found_response.json()["detail"] == "Item not found"

    # ==========================================
    # Case 6: Cross-user access (unauthorized write/delete)
    # ==========================================
    # Create Seller B and obtain token
    seller_b_token = await create_user_token_helper(client, "seller")
    headers_seller_b = {"Authorization": f"Bearer {seller_b_token}"}
    
    # Seller B tries to edit Seller A's item -> 403
    update_payload = {
        "name": "Chair Edited by Hackers",
        "description": "Should fail",
        "price": 999.0
    }
    cross_edit_response = await client.put(f"/api/v1/items/{item_id}", json=update_payload, headers=headers_seller_b)
    assert cross_edit_response.status_code == 403
    assert cross_edit_response.json()["detail"] == "Not enough permissions to access this resource"
    
    # Seller B tries to delete Seller A's item -> 403
    cross_delete_response = await client.delete(f"/api/v1/items/{item_id}", headers=headers_seller_b)
    assert cross_delete_response.status_code == 403
    assert cross_delete_response.json()["detail"] == "Not enough permissions to access this resource"

    # Verify Seller A can successfully delete their own item -> Happy path 204
    delete_response = await client.delete(f"/api/v1/items/{item_id}", headers=headers_seller)
    assert delete_response.status_code == 204
