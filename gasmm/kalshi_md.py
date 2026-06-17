"""Cliente PÚBLICO mínimo da Kalshi (somente market data — sem auth/RSA).

Dados de mercado da Kalshi são públicos; este bot nunca envia ordens, então não
precisa de chave. Mantém o pacote auto-contido p/ deploy (não puxa progno_bot
nem cryptography). Endpoints usados: /markets, /markets/{t}/orderbook,
/series/{s}/markets/{t}/candlesticks.
"""
from __future__ import annotations
import requests
from . import config

_S = requests.Session()
_S.headers.update({"User-Agent": "gasmm-paper/1.0"})


def _get(path: str, params: dict | None = None) -> dict:
    url = config.KALSHI_HOST + config.KALSHI_PREFIX + path
    try:
        r = _S.get(url, params=params, timeout=15)
        r.raise_for_status()
        return r.json() if r.content else {}
    except requests.RequestException as e:
        return {"_error": str(e)}


def markets(*, series_ticker=None, event_ticker=None, status=None,
            limit=200, cursor=None) -> dict:
    p = {"limit": limit}
    if series_ticker:
        p["series_ticker"] = series_ticker
    if event_ticker:
        p["event_ticker"] = event_ticker
    if status:
        p["status"] = status
    if cursor:
        p["cursor"] = cursor
    return _get("/markets", p)


def market(ticker: str) -> dict:
    return _get(f"/markets/{ticker}")


def orderbook(ticker: str, depth: int = 5) -> dict:
    return _get(f"/markets/{ticker}/orderbook", {"depth": depth})


def candlesticks(series_ticker: str, ticker: str, *, start_ts: int,
                 end_ts: int, period_interval: int = 1) -> dict:
    return _get(f"/series/{series_ticker}/markets/{ticker}/candlesticks",
                {"start_ts": int(start_ts), "end_ts": int(end_ts),
                 "period_interval": period_interval})


def all_markets(series_ticker: str, status: str) -> list[dict]:
    """Pagina /markets até o fim."""
    out, cur = [], None
    for _ in range(15):
        r = markets(series_ticker=series_ticker, status=status, limit=200, cursor=cur)
        if not isinstance(r, dict) or not r.get("markets"):
            break
        out += r["markets"]
        cur = r.get("cursor")
        if not cur:
            break
    return out


def best_quotes(ticker: str):
    """(best_bid, best_ask) em dólar a partir do orderbook público (yes side).
    orderbook_fp.yes_dollars/no_dollars = [[preço,size]…]. Melhor bid YES = maior
    preço do lado yes; melhor ask YES = 1 − (maior preço do lado no)."""
    ob = orderbook(ticker)
    book = ob.get("orderbook_fp") or ob.get("orderbook") or {}
    yes = book.get("yes_dollars") or book.get("yes") or []
    no = book.get("no_dollars") or book.get("no") or []

    def _px(arr):
        vals = []
        for row in arr:
            try:
                vals.append((float(row[0]), float(row[1])))
            except (TypeError, ValueError, IndexError):
                continue
        return vals
    yv, nv = _px(yes), _px(no)
    best_bid = max((p for p, _ in yv), default=None)
    best_no = max((p for p, _ in nv), default=None)
    best_ask = (1.0 - best_no) if best_no is not None else None
    return best_bid, best_ask
