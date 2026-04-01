import threading

from app.services import binance


def test_get_binance_price_cache_hit_does_not_block(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_fetch(symbol: str, timeout: float = 3.0) -> float:
        calls["count"] += 1
        return 100000.0

    monkeypatch.setattr(binance, "_fetch_price", fake_fetch)
    with binance._lock:
        binance._price_cache.clear()
        binance._price_history.clear()

    first = binance.get_binance_price("BTC")
    assert first["price"] == 100000.0
    assert calls["count"] == 1

    result: dict[str, object] = {}
    err: dict[str, BaseException] = {}

    def target() -> None:
        try:
            result["value"] = binance.get_binance_price("BTC")
        except BaseException as exc:  # pragma: no cover
            err["value"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=0.5)

    assert not thread.is_alive(), "cached Binance price lookup blocked under lock"
    assert "value" not in err
    assert result["value"]["price"] == 100000.0
    assert calls["count"] == 1
