"""Polymarket CLOB trading service — place limit orders and close positions.

Requires POLYMARKET_PRIVATE_KEY in env. Lazily initialises the ClobClient
on first use so the app still starts even if the key is missing.
"""

from __future__ import annotations

import logging
import time
from threading import Lock

from app.core.config import settings
from app.services.orderbook import fetch_book

logger = logging.getLogger(__name__)

_lock = Lock()
_client = None
_client_init_attempted = False


def _get_client():
    """Return a configured ClobClient, or None if credentials are missing."""
    global _client, _client_init_attempted
    with _lock:
        if _client_init_attempted:
            return _client
        _client_init_attempted = True

        pk = (settings.polymarket_private_key or "").strip()
        if not pk:
            logger.warning("polymarket trading: no POLYMARKET_PRIVATE_KEY, trading disabled")
            return None

        try:
            from py_clob_client_v2 import ApiCreds, BuilderConfig, ClobClient

            builder_code = (settings.poly_builder_code or "").strip()
            builder_config = BuilderConfig(builder_code=builder_code) if builder_code else None
            creds = None
            if settings.clob_api_key and settings.clob_secret and settings.clob_pass_phrase:
                creds = ApiCreds(
                    api_key=settings.clob_api_key,
                    api_secret=settings.clob_secret,
                    api_passphrase=settings.clob_pass_phrase,
                )
            client = ClobClient(
                host="https://clob.polymarket.com",
                chain_id=settings.polymarket_chain_id,
                key=pk,
                creds=creds,
                signature_type=settings.polymarket_signature_type,
                funder=settings.polymarket_funder or None,
                builder_config=builder_config,
            )
            if creds is None:
                client.set_api_creds(client.create_or_derive_api_key())
            logger.info("polymarket trading: CLOB client initialised")
            _client = client
        except Exception as exc:
            logger.exception("polymarket trading: failed to init CLOB client: %s", exc)
            _client = None

        return _client


def is_enabled() -> bool:
    return _get_client() is not None


def _sleep_before_retry(attempt: int, max_attempts: int) -> None:
    if attempt >= max_attempts:
        return
    time.sleep(max(settings.polymarket_trade_retry_sleep_ms, 0) / 1000.0)


def _extract_order_rows(resp) -> list[dict]:
    if isinstance(resp, list):
        return [row for row in resp if isinstance(row, dict)]
    if isinstance(resp, dict):
        data = resp.get("data")
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
    return []


def _response_success(resp) -> bool:
    if isinstance(resp, dict):
        success = resp.get("success")
        if success is not None:
            return bool(success)
        status = str(resp.get("status") or "").lower()
        if status in {"live", "matched", "delayed"}:
            return True
    return False


def _response_order_id(resp) -> str:
    if not isinstance(resp, dict):
        return ""
    return str(resp.get("orderID") or resp.get("order_id") or resp.get("id") or "")


def _response_error(resp) -> str:
    if not isinstance(resp, dict):
        return ""
    return str(resp.get("errorMsg") or resp.get("error") or resp.get("message") or "")


def _submit_order_with_retries(submit_order, *, label: str, context: str) -> dict:
    last_error = "trade retries exhausted"
    for attempt in range(1, settings.polymarket_trade_retry_attempts + 1):
        try:
            resp = submit_order()
            if _response_success(resp):
                return {"success": True, "order": resp, "order_id": _response_order_id(resp)}
            last_error = _response_error(resp) or f"{label} order not successful"
            logger.warning(
                "%s order rejected attempt=%s/%s context=%s error=%s",
                label,
                attempt,
                settings.polymarket_trade_retry_attempts,
                context,
                last_error,
            )
        except Exception as exc:
            last_error = str(exc)
            logger.warning(
                "%s order failed attempt=%s/%s context=%s error=%s",
                label,
                attempt,
                settings.polymarket_trade_retry_attempts,
                context,
                exc,
            )
        _sleep_before_retry(attempt, settings.polymarket_trade_retry_attempts)
    return {"success": False, "error": last_error}


def _create_limit_order_args(token_id: str, side: str, price: float, size: float):
    from py_clob_client_v2 import OrderArgs, Side

    clob_side = Side.BUY if side.upper() == "BUY" else Side.SELL
    return OrderArgs(token_id=token_id, price=price, size=size, side=clob_side)


def _marketable_limit_price(book: dict, side: str, size: float) -> float | None:
    levels = book.get("asks") if side.upper() == "BUY" else book.get("bids")
    if not levels:
        return None
    cumulative = 0.0
    chosen = None
    for level in levels:
        px = float(level.get("price") or 0)
        qty = float(level.get("size") or 0)
        if px <= 0 or qty <= 0:
            continue
        cumulative += qty
        chosen = px
        if cumulative + 1e-9 >= size:
            break
    if chosen is None:
        return None
    if side.upper() == "BUY":
        return min(chosen, 0.99)
    return max(chosen, 0.01)


def get_open_orders(token_ids: list[str] | None = None) -> list[dict]:
    """Fetch all open orders from the CLOB."""
    client = _get_client()
    if not client:
        return []
    try:
        try:
            from py_clob_client_v2 import OpenOrderParams

            resp = client.get_open_orders(OpenOrderParams())
        except Exception:
            resp = client.get_open_orders()
        orders = _extract_order_rows(resp)
        if token_ids:
            allowed = {str(token_id) for token_id in token_ids if token_id}
            filtered = []
            for order in orders:
                if not isinstance(order, dict):
                    continue
                asset_id = str(
                    order.get("asset_id")
                    or order.get("assetId")
                    or order.get("token_id")
                    or order.get("tokenId")
                    or ""
                )
                if asset_id in allowed:
                    filtered.append(order)
            orders = filtered
        return orders
    except Exception as exc:
        logger.exception("get_open_orders failed: %s", exc)
        return []


def place_limit_order(
    token_id: str,
    side: str,
    price: float,
    size: float,
    order_type: str = "GTC",
    post_only: bool = True,
) -> dict:
    """Place a limit order on the CLOB.

    Args:
        token_id: The CLOB token ID for the outcome.
        side: "BUY" or "SELL".
        price: Limit price (0-1 for binary markets).
        size: Number of contracts.

    Returns:
        dict with order result or error.
    """
    client = _get_client()
    if not client:
        return {"success": False, "error": "trading not configured (no private key)"}

    try:
        from py_clob_client_v2 import OrderType

        tif = getattr(OrderType, order_type.upper(), OrderType.GTC)
        order_args = _create_limit_order_args(
            token_id=token_id,
            side=side,
            price=price,
            size=size,
        )
        submit_post_only = post_only and order_type.upper() == "GTC"
        return _submit_order_with_retries(
            lambda: client.create_and_post_order(order_args, order_type=tif, post_only=submit_post_only),
            label="maker" if post_only and order_type.upper() == "GTC" else "limit",
            context=f"token_id={token_id} side={side} price={price} size={size}",
        )
    except Exception as exc:
        logger.exception("place_limit_order failed: %s", exc)
        return {"success": False, "error": str(exc)}


def place_taker_order(token_id: str, side: str, size: float, order_type: str = "FAK") -> dict:
    client = _get_client()
    if not client:
        return {"success": False, "error": "trading not configured (no private key)"}

    try:
        from py_clob_client_v2 import OrderType

        book = fetch_book(token_id)
        price = _marketable_limit_price(book, side=side, size=size)
        if price is None:
            return {"success": False, "error": "no resting liquidity available"}
        tif = getattr(OrderType, order_type.upper(), OrderType.FAK)
        order_args = _create_limit_order_args(
            token_id=token_id,
            side=side,
            price=price,
            size=size,
        )
        result = _submit_order_with_retries(
            lambda: client.create_and_post_order(order_args, order_type=tif, post_only=False),
            label="taker",
            context=f"token_id={token_id} side={side} size={size} marketable_price={price}",
        )
        if result.get("success"):
            result["price"] = price
        return result
    except Exception as exc:
        logger.exception("place_taker_order failed: %s", exc)
        return {"success": False, "error": str(exc)}


def cancel_order(order_id: str) -> dict:
    """Cancel a single open order."""
    client = _get_client()
    if not client:
        return {"success": False, "error": "trading not configured"}
    try:
        from py_clob_client_v2 import OrderPayload

        resp = client.cancel_order(OrderPayload(orderID=order_id))
        return {"success": True, "result": resp}
    except Exception as exc:
        logger.exception("cancel_order failed: %s", exc)
        return {"success": False, "error": str(exc)}


def cancel_all_orders() -> dict:
    """Cancel all open orders."""
    client = _get_client()
    if not client:
        return {"success": False, "error": "trading not configured"}
    try:
        resp = client.cancel_all()
        return {"success": True, "result": resp}
    except Exception as exc:
        logger.exception("cancel_all_orders failed: %s", exc)
        return {"success": False, "error": str(exc)}


def close_position(token_id: str, size: float, current_price: float) -> dict:
    """Close a position by placing a sell order at or near current price.

    For a long position (owns YES tokens), we sell YES.
    We place the order at the current best bid to get filled as maker.

    Args:
        token_id: The CLOB token ID for the outcome we hold.
        size: Number of contracts to sell.
        current_price: Price to place the sell order at (best bid).

    Returns:
        dict with order result or error.
    """
    return place_limit_order(
        token_id=token_id,
        side="SELL",
        price=current_price,
        size=size,
        post_only=False,
    )
