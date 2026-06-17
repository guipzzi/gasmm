"""
gasmm — paper bot de MARKET-MAKING no mercado KXAAAGASD (gás AAA) da Kalshi.

É a ÚNICA estratégia que sobreviveu à bateria de honestidade completa (direcional,
ladder-arb e MM nos 7 mercados): MM no gás de-viesado deu +$632 (maker0) / +$399
(taker fee) / +$378 (strict), OOS replicando, bootstrap P(≤0)=0%. Funciona porque
o underlying (índice AAA de varejo) é LENTO — não há futuro rápido pra te pegar
(seleção adversa positiva). Nos outros 6 mercados o MM morre atropelado.

OBJETIVO deste bot: VALIDAR ao vivo se a taxa de fill real bate com o backtest —
o único risco que o backtest não consegue provar. NENHUMA ordem real: os fills são
derivados dos trades que DE FATO aconteceram (candlesticks de 1-min), com o mesmo
modelo conservador do backtest. Roda na nuvem (GitHub Actions) e persiste no
Supabase entre runs — independe do PC do usuário.

Dados de mercado da Kalshi são PÚBLICOS: o bot não usa chave/auth da Kalshi.
Único secret necessário: SUPABASE_URL + SUPABASE_SERVICE_KEY.
"""
