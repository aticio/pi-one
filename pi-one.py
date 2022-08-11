import logging
import websocket
import json
import logging.handlers
import schedule
import time
import os
from datetime import datetime


cwd = os.path.dirname(os.path.realpath(__file__))
os.chdir(cwd)

SYMBOL = "MASKBUSD"
QUOTE = "BUSD"

def main():
    configure_logs()


    now = datetime.now()

    current_time = now.strftime("%H:%M:%S")
    logging.info(current_time)
    schedule.every().day.at("00:00").do(job)

    while True:
        schedule.run_pending()
        time.sleep(1)


def job():
    # BUY
    
    # TRACK
    # SELL


def enter_long(brick):
    logging.info("Opening long position.")

    logging.info("Getting spot account balance")
    balance = get_spot_balance(QUOTE)

    if not balance:
        return

    logging.info(f"Quote balance: {balance} {QUOTE}")

    share = (balance * POSITION_RISK) / (BRICK_SIZE * 2)

    if share * brick["close"] > balance:
        order_amount = balance
    else:
        order_amount = share * brick["close"]

    order_response = spot_order_quote(
        SYMBOL,
        "BUY",
        "MARKET",
        algoutils.truncate_ceil(order_amount, 6))

    if not order_response:
        return



# Spot account trade functions
def get_spot_balance(asset):
    timestamp = algoutils.get_current_timestamp()

    params = {"timestamp": timestamp, "recvWindow": 5000}
    query_string = urlencode(params)
    params["signature"] = hmac.new(SECRET.encode(
        "utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {"X-MBX-APIKEY": API_KEY}

    try:
        response = requests.get(
            url=f"{BINANCE_URL}{SPOT_ACCOUNT_PATH}",
            params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

        for _, balance in enumerate(data["balances"]):
            if balance["asset"] == asset:
                return float(balance["free"])
    except requests.exceptions.RequestException as err:
        logging.error(err)
        return None


# Preperation functions
def configure_logs():
    handler = logging.handlers.RotatingFileHandler(
        cwd + "/logs/" + SYMBOL + "_pos_tracker.log",
        maxBytes=10000000, backupCount=5)

    formatter = logging.Formatter(
        "%(asctime)s %(message)s", "%Y-%m-%d_%H:%M:%S")
    handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


if __name__ == "__main__":
    main()