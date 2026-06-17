"""Motor do paper MM: descoberta de strikes ATM, fills incrementais (mesmo modelo
do backtest validado, mas FORWARD e honesto à cadência de poll), re-cotação com
guarda anti-seleção-adversa, e liquidação no resultado.

Honestidade dos fills: a cada poll, processamos os candlesticks de 1-min DESDE o
último poll usando a cotação que DE FATO mantivemos (posted_bid/ask) — fill quando
um trade real tocou o nível. Quanto mais raro o poll, mais estática (conservadora)
a cotação. NENHUMA ordem real; os fills vêm de trades que aconteceram.
"""
from __future__ import annotations
import datetime as dt
import statistics as st
from collections import defaultdict

from . import config, kalshi_md, ledger

SERIES = config.SERIES


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _ts(iso):
    try:
        return int(dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())
    except Exception:
        return None


def _strike_row(s):
    return {k: s.get(k) for k in ledger.STRIKE_COLS if k in s}


def discover(now):
    """Strikes centrais ATM (mid ATUAL em [ATM_LO,ATM_HI]) dos eventos abertos.
    Sem hindsight: usa o preço corrente na hora de cotar."""
    mk = kalshi_md.all_markets(SERIES, "open")
    by = defaultdict(list)
    for m in mk:
        if _f(m.get("floor_strike")) is not None and m.get("close_time"):
            by[m.get("event_ticker", "")].append(m)
    cands = []
    for ev, strikes in by.items():
        med = st.median([_f(m["floor_strike"]) for m in strikes])
        central = sorted(strikes, key=lambda m: abs(_f(m["floor_strike"]) - med))[:config.N_STRIKES]
        for m in central:
            close_ts = _ts(m["close_time"])
            if close_ts is None or close_ts - now < config.QUOTE_UNTIL_S:
                continue
            bid = _f(m.get("yes_bid_dollars"))
            ask = _f(m.get("yes_ask_dollars"))
            if bid is None or ask is None or not (0 < bid < ask < 1):
                continue
            mid = (bid + ask) / 2
            if not (config.ATM_LO <= mid <= config.ATM_HI):
                continue
            cands.append({"ticker": m["ticker"], "event": ev,
                          "strike": _f(m["floor_strike"]), "close_ts": close_ts,
                          "bid": bid, "ask": ask})
    return cands


def _apply_candle(s, v):
    """Aplica fills de UM candle de 1-min com a cotação postada que está em s."""
    pr = v.get("price", {})
    if _f(pr.get("close_dollars")) is None:        # nenhum trade neste minuto
        return
    lo, hi = _f(pr.get("low_dollars")), _f(pr.get("high_dollars"))
    bid, ask = s.get("posted_bid"), s.get("posted_ask")
    s["vol_seen"] = (s.get("vol_seen") or 0) + (_f(v.get("volume_fp")) or 0)
    if bid is None or ask is None:
        return
    mid = (bid + ask) / 2
    sz = config.QUOTE_SIZE
    if lo is not None and lo <= bid and s["inv"] < config.INV_CAP and 0 < bid < 1:
        s["inv"] += sz; s["cash"] -= bid * sz
        s["fills"] += 1; s["gross"] += (mid - bid) * sz
    if hi is not None and hi >= ask and s["inv"] > -config.INV_CAP and 0 < ask < 1:
        s["inv"] -= sz; s["cash"] += ask * sz
        s["fills"] += 1; s["gross"] += (ask - mid) * sz


def _process_fills(s, now):
    """Puxa candles de 1-min desde last_ts e aplica fills com a cotação mantida."""
    last = int(s.get("last_ts") or (now - 60))
    if now - last < 60:
        return s
    cs = kalshi_md.candlesticks(SERIES, s["ticker"], start_ts=last, end_ts=now,
                                period_interval=1)
    cands = sorted((cs.get("candlesticks", []) if isinstance(cs, dict) else []),
                   key=lambda v: v.get("end_period_ts", 0))
    for v in cands:
        ts = v.get("end_period_ts", 0)
        if ts <= last:
            continue
        _apply_candle(s, v)
        s["last_ts"] = ts
    return s


def _new_state(c, now):
    return {"ticker": c["ticker"], "event": c["event"], "strike": c["strike"],
            "opened_ts": now, "close_ts": c["close_ts"], "last_ts": now,
            "posted_bid": None, "posted_ask": None, "inv": 0.0, "cash": 0.0,
            "gross": 0.0, "fills": 0, "vol_seen": 0.0, "status": "active"}


def step(now):
    """Um ciclo: fills desde o último poll + re-cotação. Retorna nº de strikes ativos."""
    cands = {c["ticker"]: c for c in discover(now)}
    active = {r["ticker"]: dict(r) for r in ledger.active_strikes()}
    seen = set()
    for ticker, c in cands.items():
        s = active.get(ticker) or _new_state(c, now)
        for k in ("inv", "cash", "gross", "vol_seen"):
            s[k] = float(s.get(k) or 0)
        s["fills"] = int(s.get("fills") or 0)
        if active.get(ticker):
            _process_fills(s, now)
        # re-cota (guarda anti-seleção-adversa perto do fechamento)
        if now < s["close_ts"] - config.QUOTE_UNTIL_S:
            s["posted_bid"], s["posted_ask"] = c["bid"], c["ask"]
        else:
            s["posted_bid"] = s["posted_ask"] = None
        ledger.upsert_strike(**_strike_row(s))
        seen.add(ticker)
    # ativos que sairam da janela ATM/abriram: processa fills finais, para de cotar
    for ticker, s in active.items():
        if ticker in seen:
            continue
        for k in ("inv", "cash", "gross", "vol_seen"):
            s[k] = float(s.get(k) or 0)
        s["fills"] = int(s.get("fills") or 0)
        _process_fills(s, now)
        s["posted_bid"] = s["posted_ask"] = None
        ledger.upsert_strike(**_strike_row(s))
    return len(cands)


def settle_finished(now):
    """Marca no resultado os strikes cujo mercado liquidou. Retorna nº liquidados."""
    n = 0
    for r in ledger.active_strikes():
        m = kalshi_md.market(r["ticker"])
        mk = m.get("market", m) if isinstance(m, dict) else {}
        status, result = mk.get("status"), mk.get("result")
        if status in ("settled", "finalized") and result in ("yes", "no"):
            s = dict(r)
            for k in ("inv", "cash", "gross", "vol_seen"):
                s[k] = float(s.get(k) or 0)
            s["fills"] = int(s.get("fills") or 0)
            _process_fills(s, now)
            sv = 1.0 if result == "yes" else 0.0
            pnl = s["cash"] + s["inv"] * sv
            ledger.settle_strike(r["ticker"], sv, pnl)
            n += 1
    return n


def equity_snapshot(now):
    rows = ledger.all_strikes()
    realized = sum(float(r.get("pnl") or 0) for r in rows if r.get("status") == "settled")
    open_mtm = 0.0
    n_active = fills = 0
    vol = 0.0
    for r in rows:
        fills += int(r.get("fills") or 0)
        vol += float(r.get("vol_seen") or 0)
        if r.get("status") == "active":
            n_active += 1
            b, a = r.get("posted_bid"), r.get("posted_ask")
            mid = (b + a) / 2 if (b is not None and a is not None) else 0.5
            open_mtm += float(r.get("cash") or 0) + float(r.get("inv") or 0) * mid
    equity = config.BANKROLL + realized + open_mtm
    ledger.log_equity(ts=now, realized=realized, open_mtm=open_mtm, equity=equity,
                      n_active=n_active, total_fills=fills, total_vol=vol)
    return {"realized": realized, "open_mtm": open_mtm, "equity": equity,
            "n_active": n_active, "fills": fills, "vol": vol}
