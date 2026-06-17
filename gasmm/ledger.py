"""Ledger do paper MM (backend duplo, espelha poly5m/ledger.py):
  - SQLite local (gasmm/data/gasmm.db) p/ teste.
  - Supabase (PostgREST) quando SUPABASE_URL + SUPABASE_SERVICE_KEY no env —
    backend do GitHub Actions (runner efêmero; estado sobrevive entre runs).
    Schema: gasmm/schema.sql.

Tabelas:
  gasmm_strikes — 1 linha por strike cotado: inventário, caixa, cotações postadas,
     último candle processado, fills, status (active/settled), pnl.
  gasmm_equity  — snapshots de equity p/ monitorar a curva ao vivo.
"""
from __future__ import annotations
import os
import sqlite3
import time
import requests
from . import config

STRIKE_COLS = ("ticker", "event", "strike", "opened_ts", "close_ts", "last_ts",
               "posted_bid", "posted_ask", "inv", "cash", "gross", "fills",
               "vol_seen", "status", "settle_value", "pnl", "updated_ts")
EQUITY_COLS = ("ts", "realized", "open_mtm", "equity", "n_active",
               "total_fills", "total_vol")


class SqliteStore:
    def __init__(self):
        self.path = os.path.join(config.DATA_DIR, "gasmm.db")

    def _c(self):
        os.makedirs(config.DATA_DIR, exist_ok=True)
        c = sqlite3.connect(self.path, timeout=10)
        c.execute("PRAGMA journal_mode=WAL")
        c.row_factory = sqlite3.Row
        return c

    def init(self):
        with self._c() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS gasmm_strikes(
                ticker TEXT PRIMARY KEY, event TEXT, strike REAL,
                opened_ts INTEGER, close_ts INTEGER, last_ts INTEGER,
                posted_bid REAL, posted_ask REAL, inv REAL DEFAULT 0,
                cash REAL DEFAULT 0, gross REAL DEFAULT 0, fills INTEGER DEFAULT 0,
                vol_seen REAL DEFAULT 0, status TEXT DEFAULT 'active',
                settle_value REAL, pnl REAL, updated_ts INTEGER)""")
            c.execute("""CREATE TABLE IF NOT EXISTS gasmm_equity(
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, realized REAL,
                open_mtm REAL, equity REAL, n_active INTEGER,
                total_fills INTEGER, total_vol REAL)""")

    def upsert_strike(self, **kw):
        kw["updated_ts"] = int(time.time())
        cols = [k for k in STRIKE_COLS if k in kw]
        with self._c() as c:
            sets = ",".join(f"{k}=excluded.{k}" for k in cols if k != "ticker")
            c.execute(
                f"INSERT INTO gasmm_strikes ({','.join(cols)}) "
                f"VALUES ({','.join('?'*len(cols))}) "
                f"ON CONFLICT(ticker) DO UPDATE SET {sets}",
                tuple(kw[k] for k in cols))

    def get_strike(self, ticker):
        with self._c() as c:
            r = c.execute("SELECT * FROM gasmm_strikes WHERE ticker=?",
                          (ticker,)).fetchone()
            return dict(r) if r else None

    def active_strikes(self):
        with self._c() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM gasmm_strikes WHERE status='active'").fetchall()]

    def settle_strike(self, ticker, settle_value, pnl):
        with self._c() as c:
            c.execute("UPDATE gasmm_strikes SET status='settled',settle_value=?,"
                      "pnl=?,updated_ts=? WHERE ticker=?",
                      (settle_value, pnl, int(time.time()), ticker))

    def log_equity(self, **kw):
        with self._c() as c:
            c.execute(f"INSERT INTO gasmm_equity ({','.join(EQUITY_COLS)}) "
                      f"VALUES ({','.join('?'*len(EQUITY_COLS))})",
                      tuple(kw.get(k) for k in EQUITY_COLS))

    def all_strikes(self):
        with self._c() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM gasmm_strikes ORDER BY opened_ts").fetchall()]


class SupabaseStore:
    def __init__(self, url, key):
        self.base = url.rstrip("/") + "/rest/v1"
        self._s = requests.Session()
        self._s.headers.update({"apikey": key, "Authorization": f"Bearer {key}",
                                "Content-Type": "application/json"})

    def _get(self, table, params):
        r = self._s.get(f"{self.base}/{table}", params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    def init(self):
        self._get("gasmm_strikes", {"select": "ticker", "limit": "1"})

    def upsert_strike(self, **kw):
        kw["updated_ts"] = int(time.time())
        row = {k: kw[k] for k in STRIKE_COLS if k in kw}
        self._s.post(f"{self.base}/gasmm_strikes",
                     params={"on_conflict": "ticker"},
                     headers={"Prefer": "resolution=merge-duplicates"},
                     json=row, timeout=15).raise_for_status()

    def get_strike(self, ticker):
        rows = self._get("gasmm_strikes", {"select": "*", "ticker": f"eq.{ticker}",
                                           "limit": "1"})
        return rows[0] if rows else None

    def active_strikes(self):
        return self._get("gasmm_strikes", {"select": "*", "status": "eq.active"})

    def settle_strike(self, ticker, settle_value, pnl):
        self._s.patch(f"{self.base}/gasmm_strikes", params={"ticker": f"eq.{ticker}"},
                      json={"status": "settled", "settle_value": settle_value,
                            "pnl": pnl, "updated_ts": int(time.time())},
                      timeout=15).raise_for_status()

    def log_equity(self, **kw):
        self._s.post(f"{self.base}/gasmm_equity",
                     json={k: kw.get(k) for k in EQUITY_COLS},
                     timeout=15).raise_for_status()

    def all_strikes(self):
        return self._get("gasmm_strikes", {"select": "*", "order": "opened_ts.asc"})


_store = None


def get_store():
    global _store
    if _store is None:
        url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY")
        _store = SupabaseStore(url, key) if url and key else SqliteStore()
    return _store


def backend_name():
    return "supabase" if isinstance(get_store(), SupabaseStore) else "sqlite"


def init(): get_store().init()
def upsert_strike(**kw): get_store().upsert_strike(**kw)
def get_strike(t): return get_store().get_strike(t)
def active_strikes(): return get_store().active_strikes()
def settle_strike(t, sv, pnl): get_store().settle_strike(t, sv, pnl)
def log_equity(**kw): get_store().log_equity(**kw)
def all_strikes(): return get_store().all_strikes()
