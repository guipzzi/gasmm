"""Configuração do paper bot de MM no gás AAA."""
import os

STRATEGY = "gasmm"
SERIES = "KXAAAGASD"
BANKROLL = 5000.0                 # banca de paper (referência p/ equity)

# Cotação / inventário (espelha o backtest validado: 1 ctr/fill, cap ±20)
QUOTE_SIZE = float(os.getenv("GASMM_QUOTE_SIZE", "1"))
INV_CAP = float(os.getenv("GASMM_INV_CAP", "20"))
N_STRIKES = int(os.getenv("GASMM_N_STRIKES", "6"))     # strikes centrais por evento
ATM_LO = float(os.getenv("GASMM_ATM_LO", "0.12"))      # só cota strike ATM (sem hindsight:
ATM_HI = float(os.getenv("GASMM_ATM_HI", "0.88"))      #   usa o mid ATUAL na hora de cotar)
QUOTE_UNTIL_S = int(os.getenv("GASMM_QUOTE_UNTIL_S", "1800"))  # para de cotar 30min do fim

# Loop
STEP_SECONDS = int(os.getenv("GASMM_STEP_SECONDS", "60"))
LOOP_MAX_MINUTES = int(os.getenv("LOOP_MAX_MINUTES", "240"))

# Kalshi público (somente leitura — sem auth)
KALSHI_HOST = os.getenv("KALSHI_HOST", "https://external-api.kalshi.com")
KALSHI_PREFIX = "/trade-api/v2"

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# taxa Kalshi por contrato (limite pessimista: e se cobrarem maker como taker)
def fee(p: float) -> float:
    return 0.07 * p * (1 - p)
