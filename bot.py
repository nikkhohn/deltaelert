"""
Delta Exchange BTC Option Price Alert Bot
-------------------------------------------
Monitors ALL BTC option contracts (daily + weekly + monthly expiries) on
Delta Exchange and sends a Telegram alert every time an option's price
drops through a new threshold: 5, 4, 3, 2, 1 (USD).

- Uses Delta Exchange's PUBLIC ticker endpoint (no API key needed).
- Sends ONE alert per new threshold crossed per symbol (not spammy).
- If price goes back above 5, that symbol "resets" so future drops alert again.

CONFIG: fill in the values directly below (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID).

⚠️ IMPORTANT: this repo MUST be PRIVATE on GitHub if you hardcode the token
here. Anyone who can read this file can control your Telegram bot.
"""

import time
import logging
import requests

# ---------- Config (fill these in) ----------
TELEGRAM_BOT_TOKEN = "PASTE_YOUR_BOT_TOKEN_HERE"      # from BotFather
TELEGRAM_CHAT_ID = "PASTE_YOUR_CHAT_ID_HERE"           # your chat/group id

POLL_INTERVAL_SEC = 3        # seconds between checks
UNDERLYING = "BTC"           # change to "ETH" if needed
PRICE_FIELD = "mark_price"   # or "close"

DELTA_TICKERS_URL = "https://api.delta.exchange/v2/tickers"
TELEGRAM_SEND_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

THRESHOLDS = [5, 4, 3, 2, 1]  # highest -> lowest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("delta-alert-bot")

# symbol -> last threshold already alerted on (6 = none crossed yet / reset state)
last_alert_state: dict[str, int] = {}


def fetch_option_tickers():
    params = {
        "contract_types": "call_options,put_options",
        "underlying_asset_symbols": UNDERLYING,
    }
    resp = requests.get(DELTA_TICKERS_URL, params=params, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"Delta API returned success=false: {data}")
    return data["result"]


def send_telegram_alert(text: str):
    try:
        r = requests.post(
            TELEGRAM_SEND_URL,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
        if not r.ok:
            log.error(f"Telegram send failed: {r.status_code} {r.text}")
    except Exception as e:
        log.error(f"Telegram send exception: {e}")


def crossed_threshold(price: float) -> int | None:
    """Return the lowest threshold the price has dropped to/below, else None."""
    hit = None
    for t in THRESHOLDS:
        if price <= t:
            hit = t
    return hit


def process_ticker(t: dict):
    symbol = t.get("symbol")
    price_raw = t.get(PRICE_FIELD)
    if symbol is None or price_raw is None:
        return
    try:
        price = float(price_raw)
    except (TypeError, ValueError):
        return

    prev_state = last_alert_state.get(symbol, 6)  # 6 = "above all thresholds"

    hit = crossed_threshold(price)

    if hit is None:
        # price is back above 5 -> reset so future drops alert again
        if prev_state != 6:
            last_alert_state[symbol] = 6
        return

    if hit < prev_state:
        # crossed a new (lower) threshold since last alert -> notify
        last_alert_state[symbol] = hit
        msg = (
            f"🔻 <b>{symbol}</b>\n"
            f"Price dropped ≤ ${hit}\n"
            f"Current {PRICE_FIELD}: ${price:.2f}"
        )
        log.info(f"ALERT: {symbol} hit ${hit} (price={price:.2f})")
        send_telegram_alert(msg)


def main():
    log.info(
        f"Starting Delta Exchange option alert bot | underlying={UNDERLYING} "
        f"| poll_interval={POLL_INTERVAL_SEC}s | price_field={PRICE_FIELD}"
    )
    send_telegram_alert(f"✅ Bot started. Monitoring {UNDERLYING} options for price drops.")

    while True:
        start = time.time()
        try:
            tickers = fetch_option_tickers()
            for t in tickers:
                process_ticker(t)
        except Exception as e:
            log.error(f"Poll error: {e}")

        elapsed = time.time() - start
        sleep_for = max(0.0, POLL_INTERVAL_SEC - elapsed)
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
