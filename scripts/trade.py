#!/usr/bin/env python3
"""CLI tool for Polymarket liquidity rewards trading.

Usage:
  # View orderbook for a market
  python scripts/trade.py book wta-shymano-vekic-2026-04-06

  # Place a limit order (BUY 100 shares of outcome 0 at 0.45)
  python scripts/trade.py buy wta-shymano-vekic-2026-04-06 0.45 100
  python scripts/trade.py buy wta-shymano-vekic-2026-04-06 0.45 100 --outcome 1

  # Place a SELL limit order
  python scripts/trade.py sell wta-shymano-vekic-2026-04-06 0.80 50

  # List open orders for a market
  python scripts/trade.py orders wta-shymano-vekic-2026-04-06

  # Cancel an order by ID
  python scripts/trade.py cancel <order-id>

  # Cancel all open orders
  python scripts/trade.py cancel-all

Requires POLYMARKET_PRIVATE_KEY in .env or environment.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import ssl
import time
import urllib.parse
import urllib.request

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "WARNING").upper(),
    format="%(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("trade")

# ---------------------------------------------------------------------------
# SSL + HTTP
# ---------------------------------------------------------------------------
try:
    import certifi
    _ssl_ctx = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _ssl_ctx = ssl.create_default_context()


def _get_json(url: str, timeout: float = 10.0) -> dict | list:
    req = urllib.request.Request(url, headers={"User-Agent": "poly-trade-cli/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Market resolution
# ---------------------------------------------------------------------------
CLOB_HOST = "https://clob.polymarket.com"
GAMMA_HOST = "https://gamma-api.polymarket.com"


def _parse_market_item(match: dict) -> dict:
    # Parse outcomes and token IDs
    outcomes = match.get("outcomes")
    prices = match.get("outcomePrices")
    clob_ids = match.get("clobTokenIds")
    try:
        if isinstance(outcomes, str):
            outcomes = json.loads(outcomes)
        if isinstance(prices, str):
            prices = json.loads(prices)
        if isinstance(clob_ids, str):
            clob_ids = json.loads(clob_ids)
    except Exception:
        sys.exit(f"Failed to parse market token data for {slug}")

    if not isinstance(clob_ids, list) or len(clob_ids) < 2:
        sys.exit(f"Market {slug} has no CLOB token IDs")

    tokens = []
    for i, token_id in enumerate(clob_ids):
        outcome = outcomes[i] if isinstance(outcomes, list) and i < len(outcomes) else f"Outcome {i}"
        price = float(prices[i]) if isinstance(prices, list) and i < len(prices) else None
        tokens.append({"token_id": str(token_id), "outcome": str(outcome), "price": price})

    return {
        "slug": match.get("slug") or "",
        "question": match.get("question") or match.get("title") or (match.get("slug") or ""),
        "condition_id": match.get("conditionId") or "",
        "tokens": tokens,
        "sports_market_type": match.get("sportsMarketType"),
        "group_item_title": match.get("groupItemTitle"),
        "event_slug": None,
        "event_title": None,
    }


def _fetch_market_by_slug(slug: str) -> dict | None:
    url = f"{GAMMA_HOST}/markets?slug={urllib.parse.quote(slug)}"
    items = _get_json(url)
    if not isinstance(items, list) or not items:
        return None
    match = next((m for m in items if m.get("slug") == slug), None)
    if not match:
        return None
    market = _parse_market_item(match)
    market["event_slug"] = slug
    return market


def _fetch_event_markets(slug: str) -> dict | None:
    url = f"{GAMMA_HOST}/events?slug={urllib.parse.quote(slug)}"
    items = _get_json(url)
    if not isinstance(items, list) or not items:
        return None
    event = next((e for e in items if e.get("slug") == slug), None)
    if not event:
        return None

    raw_markets = event.get("markets") or []
    markets = []
    for raw_market in raw_markets:
        try:
            market = _parse_market_item(raw_market)
        except SystemExit:
            continue
        market["event_slug"] = slug
        market["event_title"] = event.get("title") or slug
        markets.append(market)

    if not markets:
        return None

    return {
        "slug": slug,
        "title": event.get("title") or slug,
        "markets": markets,
    }


def _choose_event_market(event_data: dict, selector: str | None) -> dict:
    markets = event_data["markets"]
    if selector:
        selector = selector.strip().lower()
        for market in markets:
            candidates = [
                market["slug"].lower(),
                (market.get("sports_market_type") or "").lower(),
                (market.get("group_item_title") or "").lower(),
                market["slug"].split("-")[-1].lower(),
            ]
            if selector in [c for c in candidates if c]:
                return market
    if len(markets) == 1:
        return markets[0]

    choices = ", ".join(m["slug"].split("-")[-1] for m in markets)
    if selector:
        sys.exit(f"Submarket not found for {event_data['slug']}: {selector}. Choices: {choices}")
    sys.exit(f"{event_data['slug']} is a sports event slug, not a single market. Use --market. Choices: {choices}")


def resolve_market(slug: str, selector: str | None = None) -> dict:
    """Resolve a market slug or sports event slug to market metadata via Gamma API."""
    market = _fetch_market_by_slug(slug)
    if market:
        return market

    event_data = _fetch_event_markets(slug)
    if event_data:
        return _choose_event_market(event_data, selector)

    sys.exit(f"Market not found: {slug}")


def resolve_market_group(slug: str) -> list[dict]:
    """Resolve a market slug to one market, or an event slug to all of its markets."""
    market = _fetch_market_by_slug(slug)
    if market:
        return [market]

    event_data = _fetch_event_markets(slug)
    if event_data:
        return event_data["markets"]

    sys.exit(f"Market not found: {slug}")


# ---------------------------------------------------------------------------
# Orderbook
# ---------------------------------------------------------------------------
def fetch_book(token_id: str) -> dict:
    url = f"{CLOB_HOST}/book?token_id={urllib.parse.quote(token_id)}"
    data = _get_json(url)
    bids = sorted(
        [{"price": float(b.get("price", 0)), "size": float(b.get("size", 0))} for b in (data.get("bids") or [])],
        key=lambda x: -x["price"],
    )
    asks = sorted(
        [{"price": float(a.get("price", 0)), "size": float(a.get("size", 0))} for a in (data.get("asks") or [])],
        key=lambda x: x["price"],
    )
    best_bid = bids[0]["price"] if bids else None
    best_ask = asks[0]["price"] if asks else None
    mid = round((best_bid + best_ask) / 2, 4) if best_bid is not None and best_ask is not None else None
    spread = round(best_ask - best_bid, 4) if best_bid is not None and best_ask is not None else None
    return {
        "best_bid": best_bid, "best_ask": best_ask, "mid": mid, "spread": spread,
        "bids": bids[:15], "asks": asks[:15],
        "min_tick_size": data.get("min_tick_size"),
        "min_order_size": data.get("min_order_size"),
    }


def cmd_book(args):
    markets = [resolve_market(args.slug, args.market)] if args.market else resolve_market_group(args.slug)
    if len(markets) > 1:
        print(f"\n  Event: {args.slug}")
        print(f"  Submarkets: {len(markets)}")
        print()

    for idx, market in enumerate(markets):
        print(f"  {market['question']}")
        print(f"  slug: {market['slug']}")
        print()

        for token in market["tokens"]:
            book = fetch_book(token["token_id"])
            label = token["outcome"]
            price_str = f" (last: {token['price']:.3f})" if token["price"] is not None else ""
            print(f"  [{label}]{price_str}  bid {book['best_bid'] or '--'} / ask {book['best_ask'] or '--'}  spread {book['spread'] or '--'}  mid {book['mid'] or '--'}")
            if book.get("min_order_size"):
                print(f"    min_order_size: {book['min_order_size']}  min_tick_size: {book.get('min_tick_size')}")

            # Print asks (reversed so lowest is closest to spread)
            asks_display = list(reversed(book["asks"][:10]))
            if asks_display:
                print(f"    {'ASKS':>8}  {'Price':>8}  {'Size':>10}  {'Cumul':>10}")
                cum = sum(a["size"] for a in asks_display)
                for a in asks_display:
                    print(f"    {'':>8}  {a['price']:>8.3f}  {a['size']:>10.1f}  {cum:>10.1f}")
                    cum -= a["size"]
            print(f"    {'---':>8}  {'---':>8}  {'---':>10}  {'---':>10}")
            if book["bids"]:
                print(f"    {'BIDS':>8}  {'Price':>8}  {'Size':>10}  {'Cumul':>10}")
                cum = 0
                for b in book["bids"][:10]:
                    cum += b["size"]
                    print(f"    {'':>8}  {b['price']:>8.3f}  {b['size']:>10.1f}  {cum:>10.1f}")
            print()

        if idx != len(markets) - 1:
            print()


# ---------------------------------------------------------------------------
# CLOB client (lazy init)
# ---------------------------------------------------------------------------
_clob_client = None


def get_clob_client():
    global _clob_client
    if _clob_client is not None:
        return _clob_client

    # Load .env if present
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value

    pk = os.environ.get("POLYMARKET_PRIVATE_KEY", "").strip()
    if not pk:
        sys.exit("POLYMARKET_PRIVATE_KEY not set in .env or environment")

    chain_id = int(os.environ.get("POLYMARKET_CHAIN_ID", "137"))
    sig_type = int(os.environ.get("POLYMARKET_SIGNATURE_TYPE", "2"))
    funder = os.environ.get("POLYMARKET_FUNDER", "").strip() or None

    try:
        from py_clob_client.client import ClobClient
    except ImportError:
        sys.exit("py_clob_client not installed. Run: pip install py-clob-client")

    client = ClobClient(
        host=CLOB_HOST,
        chain_id=chain_id,
        key=pk,
        signature_type=sig_type,
        funder=funder,
    )
    creds = client.create_or_derive_api_creds()
    client.set_api_creds(creds)
    _clob_client = client
    return client


# ---------------------------------------------------------------------------
# Place order
# ---------------------------------------------------------------------------
def cmd_order(args):
    side = args.command.upper()  # "buy" or "sell"
    market = resolve_market(args.slug, args.market)
    outcome_idx = args.outcome
    if outcome_idx >= len(market["tokens"]):
        sys.exit(f"Outcome index {outcome_idx} out of range (market has {len(market['tokens'])} outcomes)")

    token = market["tokens"][outcome_idx]
    price = args.price
    size = args.size

    print(f"\n  Market:  {market['question']}")
    print(f"  Slug:    {market['slug']}")
    print(f"  Action:  {side} {size} shares of [{token['outcome']}] at {price:.3f}")
    print(f"  Token:   {token['token_id'][:20]}...")

    # Show current book for context
    book = fetch_book(token["token_id"])
    print(f"  Book:    bid {book['best_bid'] or '--'} / ask {book['best_ask'] or '--'}  spread {book['spread'] or '--'}")

    if not args.yes:
        confirm = input("\n  Confirm? [y/N] ").strip().lower()
        if confirm != "y":
            print("  Aborted.")
            return

    client = get_clob_client()

    from py_clob_client.clob_types import OrderArgs, OrderType
    from py_clob_client.order_builder.constants import BUY, SELL

    clob_side = BUY if side == "BUY" else SELL
    order_type = OrderType.GTC

    order = client.create_order(OrderArgs(
        token_id=token["token_id"],
        price=price,
        size=size,
        side=clob_side,
    ))

    resp = client.post_order(order, order_type)
    print(f"\n  Response: {json.dumps(resp, indent=2, default=str)}")

    if isinstance(resp, dict):
        if resp.get("success"):
            print(f"\n  Order placed: {resp.get('orderID', 'unknown')}")
        else:
            print(f"\n  Order failed: {resp.get('errorMsg') or resp.get('error') or 'unknown error'}")


# ---------------------------------------------------------------------------
# Open orders
# ---------------------------------------------------------------------------
def cmd_orders(args):
    market = resolve_market(args.slug, args.market)
    client = get_clob_client()

    token_ids = {t["token_id"] for t in market["tokens"]}
    outcome_map = {t["token_id"]: t["outcome"] for t in market["tokens"]}

    print(f"\n  {market['question']}")
    print(f"  slug: {market['slug']}")

    try:
        from py_clob_client.clob_types import OpenOrderParams
        resp = client.get_orders(OpenOrderParams())
    except Exception:
        resp = client.get_orders()

    orders = []
    if isinstance(resp, list):
        orders = resp
    elif isinstance(resp, dict) and isinstance(resp.get("data"), list):
        orders = resp["data"]

    matched = [o for o in orders if isinstance(o, dict) and str(o.get("asset_id") or o.get("token_id") or "") in token_ids]

    if not matched:
        print("\n  No open orders for this market.")
        return

    print(f"\n  {'Outcome':<20} {'Side':<6} {'Price':>8} {'Size':>10} {'Remaining':>10} {'Order ID'}")
    print(f"  {'-'*20} {'-'*6} {'-'*8} {'-'*10} {'-'*10} {'-'*36}")
    for o in matched:
        asset = str(o.get("asset_id") or o.get("token_id") or "")
        outcome = outcome_map.get(asset, asset[:12])
        side = o.get("side", "?")
        price = float(o.get("price", 0))
        orig = float(o.get("original_size") or o.get("size") or 0)
        remain = float(o.get("size_matched") or o.get("remaining_size") or orig)
        oid = str(o.get("id") or o.get("order_id") or o.get("orderID") or "")
        print(f"  {outcome:<20} {side:<6} {price:>8.3f} {orig:>10.1f} {remain:>10.1f} {oid}")


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------
def cmd_cancel(args):
    client = get_clob_client()
    order_id = args.order_id

    print(f"\n  Canceling order: {order_id}")
    if not args.yes:
        confirm = input("  Confirm? [y/N] ").strip().lower()
        if confirm != "y":
            print("  Aborted.")
            return

    resp = client.cancel(order_id=order_id)
    print(f"  Result: {json.dumps(resp, indent=2, default=str)}")


def cmd_cancel_all(args):
    client = get_clob_client()
    print("\n  Canceling ALL open orders.")
    if not args.yes:
        confirm = input("  Confirm? [y/N] ").strip().lower()
        if confirm != "y":
            print("  Aborted.")
            return

    resp = client.cancel_all()
    print(f"  Result: {json.dumps(resp, indent=2, default=str)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Polymarket liquidity rewards trading CLI")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompts")
    sub = parser.add_subparsers(dest="command", required=True)

    # book
    p_book = sub.add_parser("book", help="Show orderbook for a market")
    p_book.add_argument("slug", help="Market slug")
    p_book.add_argument("--market", help="Submarket for sports event slugs, e.g. draw or team code")

    # buy
    p_buy = sub.add_parser("buy", help="Place a BUY limit order")
    p_buy.add_argument("slug", help="Market slug")
    p_buy.add_argument("price", type=float, help="Limit price (0-1)")
    p_buy.add_argument("size", type=float, help="Number of shares")
    p_buy.add_argument("--outcome", type=int, default=0, help="Outcome index (0=first, 1=second)")
    p_buy.add_argument("--market", help="Submarket for sports event slugs, e.g. draw or team code")

    # sell
    p_sell = sub.add_parser("sell", help="Place a SELL limit order")
    p_sell.add_argument("slug", help="Market slug")
    p_sell.add_argument("price", type=float, help="Limit price (0-1)")
    p_sell.add_argument("size", type=float, help="Number of shares")
    p_sell.add_argument("--outcome", type=int, default=0, help="Outcome index (0=first, 1=second)")
    p_sell.add_argument("--market", help="Submarket for sports event slugs, e.g. draw or team code")

    # orders
    p_orders = sub.add_parser("orders", help="List open orders for a market")
    p_orders.add_argument("slug", help="Market slug")
    p_orders.add_argument("--market", help="Submarket for sports event slugs, e.g. draw or team code")

    # cancel
    p_cancel = sub.add_parser("cancel", help="Cancel an order by ID")
    p_cancel.add_argument("order_id", help="Order ID to cancel")

    # cancel-all
    sub.add_parser("cancel-all", help="Cancel all open orders")

    args = parser.parse_args()

    if args.command == "book":
        cmd_book(args)
    elif args.command in ("buy", "sell"):
        cmd_order(args)
    elif args.command == "orders":
        cmd_orders(args)
    elif args.command == "cancel":
        cmd_cancel(args)
    elif args.command == "cancel-all":
        cmd_cancel_all(args)


if __name__ == "__main__":
    main()
