# Prometheus Instrumentation Completion Plan

## Goal Description
We need to finish the Prometheus instrumentation for CraftNest backend:
- Restrict `/metrics` endpoint to localhost only.
- Increment `craftnest_orders_total` counter on every order creation and status change.
- Update `craftnest_active_sellers` gauge when sellers are banned/unbanned.
- Document the setup in `README.md`.

## User Review Required
- Confirm that the IP restriction should return `403` for non‑localhost requests.
- Approve the exact places where we will increment the order counter (order creation and admin status overrides).

## Open Questions
- Should the order counter also be incremented on order status changes that result in a new order (e.g., refund)?
- Do we need to expose the gauge value at server start (initial count of active sellers)?

## Proposed Changes
---
### [MODIFY] [app/main.py](file:///c:/Users/ACER/OneDrive/Desktop/antigravity_workspace/TohfaHub_project-2/craftnest-backend/app/main.py)
Add a new middleware before the existing ones to block `/metrics` requests from non‑127.0.0.1 IPs.
---
### [MODIFY] [app/services/order_service.py](file:///c:/Users/ACER/OneDrive/Desktop/antigravity_workspace/TohfaHub_project-2/craftnest-backend/app/services/order_service.py)
Import `craftnest_orders_total` and increment it after successful order creation and after admin forced status changes.
---
### [MODIFY] [app/services/admin_service.py](file:///c:/Users/ACER/OneDrive/Desktop/antigravity_workspace/TohfaHub_project-2/craftnest-backend/app/services/admin_service.py)
Import `craftnest_active_sellers` and adjust its value in `ban_seller` and `unban_seller`.
---
### [MODIFY] [README.md](file:///c:/Users/ACER/OneDrive/Desktop/antigravity_workspace/TohfaHub_project-2/craftnest-backend/README.md)
Add a section describing Prometheus endpoint, Grafana installation, and metric meanings.
---
## Verification Plan
- Run the server locally and `curl http://127.0.0.1:8443/metrics` – should succeed.
- `curl http://<LAN_IP>:8443/metrics` – should return `403`.
- Create an order via API and verify that `craftnest_orders_total` increases (check `/metrics`).
- Ban and unban a seller and verify that `craftnest_active_sellers` gauge updates.
- Review README for correct instructions.
