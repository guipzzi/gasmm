# gasmm — paper bot de market-making (underlying lento / Kalshi)

Paper trading autônomo de **market-making** em mercados Kalshi de **underlying lento**
(`config.SERIES`): **KXAAAGASD** (gás AAA — validado e robusto) e **KXHIGHNY** (temp
máx NYC — único do clima que sobreviveu ao backtest de-viesado, em paper p/ confirmar
ao vivo). MM só funciona onde o underlying é lento (sem instrumento rápido que te
pega na cotação parada → seleção adversa baixa); em underlying rápido (WTI/FX/crypto)
o MM morre atropelado. Cada strike é rastreado por ticker; a série é derivada dele,
então é só adicionar tickers em `config.SERIES`. Ver `progno_bot_2/mm_debiased.py`.

**Objetivo deste bot:** validar AO VIVO se a taxa de fill real bate com o backtest
de-viesado (+$632 maker0 / +$399 com taker fee / +$378 strict, OOS replicando,
bootstrap P(≤0)=0%). A taxa de fill é o único risco que o backtest não prova.

## Como funciona (honesto)

- **Nenhuma ordem real.** Os fills são derivados dos trades que DE FATO aconteceram,
  lidos dos candlesticks de 1-min. A cada poll, processa os candles desde o último
  poll usando a cotação que mantivemos (`posted_bid/ask`) — fill quando um trade real
  tocou o nível, com cap de inventário. Mesmo modelo conservador do backtest.
- **Sem hindsight:** escolhe os strikes ATM pelo mid ATUAL na hora de cotar.
- **Defesa anti-seleção-adversa:** para de cotar nos últimos 30min antes do close.
- **Estado no Supabase:** sobrevive entre runs (runner do GitHub Actions é efêmero) →
  independe do seu PC.
- **Dados da Kalshi são públicos:** o bot NÃO usa chave/auth da Kalshi.

## Arquivos

| arquivo | papel |
|---|---|
| `config.py` | parâmetros (série, banca, tamanho, cap, banda ATM, cadência) |
| `kalshi_md.py` | cliente público mínimo (markets/orderbook/candlesticks) — sem auth |
| `engine.py` | descoberta de strikes, fills incrementais, re-cotação, liquidação |
| `ledger.py` | backend duplo SQLite (local) / Supabase (nuvem) |
| `run.py` | CLI: `--once` / `--loop` / `--settle` / `--report` |
| `schema.sql` | tabelas do Supabase (`gasmm_strikes`, `gasmm_equity`) |

## Uso local (SQLite)

```bash
python -m gasmm.run --once      # um ciclo
python -m gasmm.run --report    # curva de equity, PnL/dia, fills vs volume
python -m gasmm.run --settle    # reconcilia mercados liquidados
python -m gasmm.run --loop      # loop 1-min (LOOP_MAX_MINUTES, default 240)
```

## Deploy na nuvem (Supabase + GitHub Actions) — independe do PC

1. **Supabase:** no SQL Editor do projeto (mesmo do progno_bot), rode `gasmm/schema.sql`
   uma vez. Cria `gasmm_strikes` e `gasmm_equity` com RLS (só a service key escreve).
2. **GitHub Secrets** (Settings → Secrets → Actions) no repo onde o Actions roda:
   `SUPABASE_URL` e `SUPABASE_SERVICE_KEY` (a publishable/service key do projeto).
   **Não precisa de secret da Kalshi** (market data é público).
3. **Push** do código (este pacote + `.github/workflows/gasmm-paper.yml`). O workflow:
   - `--once` a cada 10min na janela 12–23 UTC (poll barato, ~30s/run, cabe no free tier);
   - `--settle` + `--report` diário às 01:30 UTC.
   Dá pra disparar manual em Actions → "gasmm paper" → Run (mode: once/loop/settle/report).

### Cadência e custo

O gás é **lento**, então 10min de defasagem de cotação é seguro (foi de onde veio o
edge). `--once`/10min ≈ 1.080 min de runner/mês — dentro do free tier mesmo em repo
privado. Para fidelidade de 1-min (igual ao backtest), use `--loop` via dispatch ou
um VPS; aí o custo de Actions sobe (prefira repo público = minutos ilimitados).

## Validação — o que olhar

No `--report` diário:
- **PnL realizado** deve seguir ~**$11/dia** (tamanho conservador do backtest);
- **fills reais vs volume**: o backtest assumiu ~0,7% do fluxo (conservador). Se os
  fills ao vivo vierem MUITO abaixo → o cron é lento demais / a fila te deixa pra trás;
- **PnL ≤ 0 ao vivo** apesar de fills OK → o edge não existe na prática (mata a tese).

Rode **3–4 semanas** em paper antes de qualquer capital real. Escale o tamanho
(`GASMM_QUOTE_SIZE`, `GASMM_INV_CAP`) só depois que os fills ao vivo confirmarem.

## Segurança

Não commite a service key. As chaves da Kalshi/Synoptic que já passaram por chat em
texto puro **devem ser revogadas/rotacionadas** — este bot não as usa, mas elas seguem
expostas.
