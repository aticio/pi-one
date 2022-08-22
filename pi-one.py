import websocket
import json
import hmac
import hashlib
import requests
import algoutils
from urllib.parse import urlencode
import os
import configparser
import logging
import logging.handlers

cwd = os.path.dirname(os.path.realpath(__file__))
os.chdir(cwd)

# Configparser init
cp = configparser.ConfigParser()
cp.read(cwd + "/config.ini")


BINANCE_URL = cp["context"]["BinanceUrl"]
BINANCE_WEBSOCKET_ADDRESS = cp["context"]["BinanceWebSocketAddress"]
EXCHANGE_INFO = cp["context"]["ExchangeInfo"]
SPOT_ORDER_PATH = cp["context"]["SpotOrderPath"]
SPOT_ACCOUNT_PATH = cp["context"]["SpotAccountPath"]

QUOTE = cp["data"]["Quote"]
BASE = ""

# Auth
API_KEY = os.getenv("BINANCE_API_KEY")
SECRET = os.getenv("BINANCE_API_SECRET")

PRICE_DATA = {}
STEP_SIZES = {}

POS_PRICE = 0.0
EXIT_PRICE = 0.0
IN_POSITION = False
SELECTED_PAIR = ""


def main():
    configure_logs()
    logging.info("Happy trading.")

    logging.info("Getting pairs")
    exchange_info = get_exchange_info()
    pairs = get_busd_pairs(exchange_info)
    for pair in pairs:
        PRICE_DATA[pair] = []
        STEP_SIZES[pair] = 0

    collect_step_sizes(exchange_info, pairs)

    logging.info("Initiating websocket stream")
    init_stream()


def get_busd_pairs(exchange_info):
    pairs = []
    for symbol in exchange_info["symbols"]:
        if "BUSD" in symbol["symbol"] and "USDT" not in symbol["symbol"]:
            pairs.append(symbol["symbol"])
    return pairs


def collect_step_sizes(exchange_info, pairs):
    global STEP_SIZES

    symbols = exchange_info["symbols"]
    for symbol in symbols:
        if "BUSD" in symbol["symbol"] and "USDT" not in symbol["symbol"]:
            for filter in symbol["filters"]:
                if filter["filterType"] == "LOT_SIZE":
                    step = 0
                    split_steps = filter["stepSize"].split(".")
                    if split_steps[0] == "1":
                        step = 0
                    else:
                        split_decimal = split_steps[1].find("1")
                        step = split_decimal + 1
                    STEP_SIZES[symbol["symbol"]] = step                


def get_exchange_info():
    response = requests.get(BINANCE_URL + EXCHANGE_INFO)
    exchange_info = response.json()
    return exchange_info


# Websocket functions
def init_stream():
    w_s = websocket.WebSocketApp(
        BINANCE_WEBSOCKET_ADDRESS,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
        )
    w_s.on_open = on_open
    w_s.run_forever()


def on_error(w_s, error):
    print(error)


def on_close(w_s, close_status_code, close_msg):
    print("closing websocket connection, initiating again...")
    init_stream()


def on_open(w_s):
    print("websocket connection opened...")


def on_message(w_s, message):
    global PRICE_DATA
    global SELECTED_PAIR

    ticker_data = json.loads(message)

    for t in ticker_data:
        if "BUSD" in t["s"] and "USDT" not in t["s"]:
            PRICE_DATA[t["s"]].append(t["c"])
            if len(PRICE_DATA[t["s"]]) == 600:
                PRICE_DATA[t["s"]].pop(0)

            anomaly = check_anomaly(PRICE_DATA[t["s"]])
            if anomaly:
                logging.info(f"Anomaly detected: {t['s']}: {t['c']}")
                if IN_POSITION is False:
                    SELECTED_PAIR = t["s"]
                    enter_long(t["s"], t["c"])

            if IN_POSITION is True:
                if t["s"] == SELECTED_PAIR:
                    if float(t["c"]) >= EXIT_PRICE:
                        exit_long(t["s"], t["c"])
                    

def enter_long(symbol, price):
    global POS_PRICE
    global EXIT_PRICE
    global IN_POSITION
    global BASE

    BASE = symbol[:-4]
    IN_POSITION = True
    POS_PRICE = price
    EXIT_PRICE = price + (price * 0.01)

    logging.info("Opening long position.")

    logging.info("Getting spot account balance")
    balance = get_spot_balance(QUOTE)

    if not balance:
        return

    logging.info(f"Quote balance: {balance} {QUOTE}")

    order_response = spot_order_quote(
        symbol,
        "BUY",
        "MARKET",
        algoutils.truncate_floor(balance, 6))

    if not order_response:
        return


def exit_long(symbol, price):
    global POS_PRICE
    global EXIT_PRICE
    global IN_POSITION
    global BASE

    logging.info("Closing long position")

    logging.info("Getting spot account balance")
    balance = get_spot_balance(BASE)

    if not balance:
        return

    amount_to_sell = algoutils.truncate_floor(balance, STEP_SIZES[symbol])
    if STEP_SIZES[symbol] == 0:
        amount_to_sell = int(amount_to_sell)
    logging.info("Amount to sell %f %s", amount_to_sell, BASE)

    spot_order_response = spot_order(symbol, "SELL", "MARKET", amount_to_sell)

    if not spot_order_response:
        return

    logging.info("Sell order has been filled")

    POS_PRICE = 0.0
    EXIT_PRICE = 0.0
    IN_POSITION = False
    BASE = ""


def check_anomaly(prices):
    anomaly = False
    for p in prices[420:540]:
        if float(prices[-1]) > (float(p) + (float(p) * 0.1)):
            for p2 in prices[:540]:
                if float(prices[-1]) < (float(p2) + (float(p2) * 0.2)):
                    anomaly = True
                    break
    return anomaly


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


def spot_order(order_symbol, side, type, quantity):
    timestamp = algoutils.get_current_timestamp()

    params = {
        "symbol": order_symbol, "side": side, "type": type,
        "quantity": quantity, "timestamp": timestamp, "recvWindow": 5000
    }
    query_string = urlencode(params)
    params["signature"] = hmac.new(SECRET.encode(
        "utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {"X-MBX-APIKEY": API_KEY}

    try:
        response = requests.post(
            url=f"{BINANCE_URL}{SPOT_ORDER_PATH}",
            params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as err:
        logging.error(err)
        logging.error(response.json())
        return None


def spot_order_quote(order_symbol, side, type, quote_quantity):
    timestamp = algoutils.get_current_timestamp()

    params = {
        "symbol": order_symbol, "side": side,
        "type": type, "quoteOrderQty": quote_quantity,
        "timestamp": timestamp, "recvWindow": 5000
    }
    query_string = urlencode(params)
    params["signature"] = hmac.new(SECRET.encode(
        "utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {"X-MBX-APIKEY": API_KEY}

    try:
        response = requests.post(
            url=f"{BINANCE_URL}{SPOT_ORDER_PATH}",
            params=params,
            headers=headers)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as err:
        logging.error(err)
        logging.error(response.json())
        return None


# Preperation functions
def configure_logs():
    handler = logging.handlers.RotatingFileHandler(
        cwd + "/logs/pi_one.log",
        maxBytes=10000000, backupCount=5)

    formatter = logging.Formatter(
        "%(asctime)s %(message)s", "%Y-%m-%d_%H:%M:%S")
    handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


if __name__ == "__main__":
    main()