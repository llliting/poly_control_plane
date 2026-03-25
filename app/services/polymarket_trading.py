"""Polymarket CLOB trading service — place limit orders and close positions.

Requires POLYMARKET_PRIVATE_KEY in env. Lazily initialises the ClobClient
on first use so the app still starts even if the key is missing.
"""

from __future__ import annotations

import logging
from threading import Lock

from app.core.config import settings

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
            from py_clob_client.client import ClobClient

            client = ClobClient(
                host="https://clob.polymarket.com",
                chain_id=settings.polymarket_chain_id,
                key=pk,
                signature_type=2,
                funder=settings.polymarket_funder or None,
            )
            creds = client.derive_api_key()
            client.set_api_creds(creds)
            logger.info("polymarket trading: CLOB client initialised")
            _client = client
        except Exception as exc:
            logger.exception("polymarket trading: failed to init CLOB client: %s", exc)
            _client = None

        return _client


def is_enabled() -> bool:
    return _get_client() is not None


def get_open_orders() -> list[dict]:
    """Fetch all open orders from the CLOB."""
    client = _get_client()
    if not client:
        return []
    try:
        resp = client.get_orders()
        orders = resp if isinstance(resp, list) else []
        return orders
    except Exception as exc:
        logger.exception("get_open_orders failed: %s", exc)
        return []


def place_limit_order(
    token_id: str,
    side: str,
    price: float,
    size: float,
) -> dict:
    """Place a GTC limit order on the CLOB.

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
        from py_clob_client.order_builder.constants import BUY, SELL

        clob_side = BUY if side.upper() == "BUY" else SELL

        order = client.create_order(
            order_args={
                "token_id": token_id,
                "price": price,
                "size": size,
                "side": clob_side,
            },
        )
        resp = client.post_order(order)
        return {"success": True, "order": resp}
    except Exception as exc:
        logger.exception("place_limit_order failed: %s", exc)
        return {"success": False, "error": str(exc)}


def cancel_order(order_id: str) -> dict:
    """Cancel a single open order."""
    client = _get_client()
    if not client:
        return {"success": False, "error": "trading not configured"}
    try:
        resp = client.cancel(order_id=order_id)
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
    )
