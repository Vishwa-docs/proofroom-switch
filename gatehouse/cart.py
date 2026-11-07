"""Small, deterministic checkout service used as the incident target."""

from decimal import Decimal


CASES = [
    {"id": "regular", "price": "24.00", "discount": "0.00"},
    {"id": "member", "price": "50.00", "discount": "5.00"},
    {"id": "guest", "price": "18.00", "discount": None},
    {"id": "gift", "price": "34.00", "discount": None},
    {"id": "promo", "price": "70.00", "discount": "10.00"},
]

RELEASES = {
    "v2.14.0": {"schema": "checkout-v1", "artifact": "checkout-2.14.0"},
    "v2.13.2": {"schema": "checkout-v1", "artifact": "checkout-2.13.2"},
}


def checkout(version: str, cart: dict) -> dict:
    """Return the response from an executable release, with no network mocks."""
    if version not in {"v2.14.0", "v2.13.2"}:
        raise ValueError("release is not in the allowlist")
    discount = cart["discount"]
    if version == "v2.13.2" and discount is None:
        discount = "0.00"
    # v2.14.0 contains the real regression: Decimal(None) raises TypeError.
    total = Decimal(cart["price"]) - Decimal(discount)
    return {"cart_id": cart["id"], "total": str(total.quantize(Decimal("0.01")))}


def replay(version: str) -> list[dict]:
    results = []
    for case in CASES:
        try:
            results.append({"case": case["id"], "ok": True, "response": checkout(version, case)})
        except (TypeError, ValueError) as exc:
            results.append({"case": case["id"], "ok": False, "error": type(exc).__name__})
    return results

