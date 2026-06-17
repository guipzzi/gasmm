"""CLI do paper MM do gás.

  --once    : um ciclo (fills desde o último poll + settle + snapshot). Cron barato.
  --loop    : loop de LOOP_MAX_MINUTES re-cotando a cada STEP_SECONDS (fiel ao backtest
              de 1-min). Roda na nuvem cobrindo o horário do mercado.
  --settle  : reconcilia mercados liquidados (marca inventário no resultado).
  --report  : curva de equity, PnL por dia, fills vs volume real (a métrica que valida).

Backend: SQLite local por padrão; Supabase se SUPABASE_URL + SUPABASE_SERVICE_KEY no env.
"""
from __future__ import annotations
import argparse
import time
from collections import defaultdict

from . import config, engine, ledger


def _now():
    return int(time.time())


def cmd_once():
    ledger.init()
    n = engine.step(_now())
    s = engine.settle_finished(_now())
    snap = engine.equity_snapshot(_now())
    print(f"[once|{ledger.backend_name()}] strikes_ativos={n} liquidados={s} "
          f"equity=${snap['equity']:,.2f} realized=${snap['realized']:+,.2f} "
          f"fills={snap['fills']} n_ativos={snap['n_active']}")


def cmd_loop():
    ledger.init()
    deadline = time.time() + config.LOOP_MAX_MINUTES * 60
    print(f"[loop|{ledger.backend_name()}] início | até {config.LOOP_MAX_MINUTES}min | "
          f"passo {config.STEP_SECONDS}s | série {config.SERIES}")
    i = 0
    while time.time() < deadline:
        now = _now()
        try:
            n = engine.step(now)
            liq = engine.settle_finished(now) if i % 10 == 0 else 0
            if i % 10 == 0 or liq:
                snap = engine.equity_snapshot(now)
                print(f"  t+{i:04d} ativos={n} liq={liq} equity=${snap['equity']:,.2f} "
                      f"realized=${snap['realized']:+,.2f} fills={snap['fills']}",
                      flush=True)
        except Exception as e:
            print(f"  ! step err: {e}", flush=True)
        i += 1
        time.sleep(config.STEP_SECONDS)
    engine.equity_snapshot(_now())
    print("[loop] fim")


def cmd_settle():
    ledger.init()
    n = engine.settle_finished(_now())
    engine.equity_snapshot(_now())
    print(f"[settle] {n} mercado(s) liquidado(s)")


def cmd_report():
    ledger.init()
    rows = ledger.all_strikes()
    settled = [r for r in rows if r.get("status") == "settled"]
    realized = sum(float(r.get("pnl") or 0) for r in settled)
    fills = sum(int(r.get("fills") or 0) for r in rows)
    vol = sum(float(r.get("vol_seen") or 0) for r in rows)
    wins = sum(1 for r in settled if float(r.get("pnl") or 0) > 0)
    # PnL por dia (evento = dia)
    byday = defaultdict(float)
    for r in settled:
        day = (r.get("event") or "")[-8:]
        byday[day] += float(r.get("pnl") or 0)
    print("=" * 56)
    print(f"GASMM paper — backend {ledger.backend_name()}")
    print("=" * 56)
    print(f"  strikes liquidados: {len(settled)} | ativos: {len(rows)-len(settled)}")
    print(f"  PnL realizado: ${realized:+,.2f} | equity ${config.BANKROLL+realized:,.2f}")
    if settled:
        print(f"  dias+: {wins}/{len(settled)} = {wins/len(settled)*100:.0f}%")
    print(f"  fills totais: {fills} | volume real visto: {vol:,.0f} contratos"
          + (f" | captura {fills/vol*100:.2f}% do fluxo" if vol else ""))
    if byday:
        print("  PnL por dia:")
        for d in sorted(byday):
            print(f"    {d}: ${byday[d]:+.2f}")
    print("\n  validação: o PnL realizado deve seguir ~$11/dia (backtest de-viesado).")
    print("  se fills_reais << backtest ou PnL≤0 → o cron é lento demais / sem edge ao vivo.")


def main():
    ap = argparse.ArgumentParser(prog="gasmm")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--once", action="store_true")
    g.add_argument("--loop", action="store_true")
    g.add_argument("--settle", action="store_true")
    g.add_argument("--report", action="store_true")
    a = ap.parse_args()
    if a.once:
        cmd_once()
    elif a.loop:
        cmd_loop()
    elif a.settle:
        cmd_settle()
    elif a.report:
        cmd_report()


if __name__ == "__main__":
    main()
