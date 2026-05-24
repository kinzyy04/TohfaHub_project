from prometheus_client import Counter, Gauge

# Counter for total orders created, labelled by status
craftnest_orders_total = Counter(
    "craftnest_orders_total",
    "Total number of orders created, labeled by status",
    ["status"],
)

# Gauge for active sellers count (non‑banned)
craftnest_active_sellers = Gauge(
    "craftnest_active_sellers",
    "Current number of active (non‑banned) sellers",
)
