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
import schedule
import time

cwd = os.path.dirname(os.path.realpath(__file__))
os.chdir(cwd)

# Configparser init.
cp = configparser.ConfigParser()
cp.read(cwd + "/config.ini")


BINANCE_URL = cp["context"]["BinanceUrl"]
BINANCE_WEBSOCKET_ADDRESS = cp["context"]["BinanceWebSocketAddress"]
KLINE_PATH = cp["context"]["KlinePath"]
EXCHANGE_INFO = cp["context"]["ExchangeInfo"]
SPOT_ORDER_PATH = cp["context"]["SpotOrderPath"]
SPOT_ACCOUNT_PATH = cp["context"]["SpotAccountPath"]

SYMBOL = ""
BASE = ""
QUOTE = ""
STEP_SIZE = 0

# Auth
API_KEY = os.getenv("BINANCE_API_KEY")
SECRET = os.getenv("BINANCE_API_SECRET")

EXIT_PRICE = 0.0
STOP_PRICE = 0.0
IN_STREAM = False

W_S = None


def main():
    configure_logs()
    logging.info("Happy trading.")

    schedule.every().day.at("00:00").do(init_ops)
    while True:
        schedule.run_pending()
        time.sleep(1)


def init_ops():
    logging.info("------------")
    global cp
    global EXIT_PRICE
    global STOP_PRICE
    global BINANCE_WEBSOCKET_ADDRESS
    global IN_STREAM
    global SYMBOL
    global BASE
    global QUOTE
    global STEP_SIZE

    logging.info("Reading config")
    cp.read(cwd + "/config.ini")

    QUOTE = cp["data"]["Quote"]
    SYMBOL = cp["data"]["Symbol"]
    BASE = cp["data"]["Base"]
    exit_ratio = float(cp["data"]["ExitRatio"])
    stop_ratio = float(cp["data"]["StopRatio"])

    logging.info(f"Symbol: {SYMBOL}")
    logging.info(f"Base: {BASE}")
    logging.info(f"Quote: {QUOTE}")

    BINANCE_WEBSOCKET_ADDRESS = BINANCE_WEBSOCKET_ADDRESS.replace("symbol", str.lower(SYMBOL))
    logging.info(f"Websocket: {BINANCE_WEBSOCKET_ADDRESS}")

    if SYMBOL != "":
        enter_long()

        klines = get_klines(SYMBOL, "1d", 20)
        _, _, _, close = get_ohlc(klines)
        EXIT_PRICE = float(close[-1]) + (float(close[-1]) * exit_ratio)
        STOP_PRICE = float(close[-1]) - (float(close[-1]) * stop_ratio)

        exchange_info = get_exchange_info(SYMBOL)
        STEP_SIZE = get_step_size(exchange_info)

        logging.info(f"Last close: {close[-1]}")
        logging.info(f"Exit price: {EXIT_PRICE}")
        logging.info(f"Stop price: {STOP_PRICE}")
        logging.info(f"Step size: {STEP_SIZE}")

        if IN_STREAM is False:
            IN_STREAM = True
            init_stream()        
    else:
        logging.info("NO GO")


def get_ohlc(klines):
    open = [float(o[1]) for o in klines]
    high = [float(h[2]) for h in klines]
    low = [float(l[3]) for l in klines]
    close = [float(c[4]) for c in klines]
    return open, high, low, close


def get_klines(kline_symbol, kline_interval, kline_limit):
    try:
        params = {"symbol": kline_symbol, "interval": kline_interval, "limit": kline_limit}
        response = requests.get(
            url=f"{BINANCE_URL}{KLINE_PATH}", params=params)
        response.raise_for_status()
        kline = response.json()
        return kline
    except requests.exceptions.RequestException as err:
        print(err)
        return None


def get_exchange_info(symbol):
    response = requests.get(BINANCE_URL + EXCHANGE_INFO + f"?symbol={symbol}")
    exchange_info = response.json()
    return exchange_info


def get_step_size(exchange_info):
    step = 0
    for filter in exchange_info["symbols"][0]["filters"]:
        if filter["filterType"] == "LOT_SIZE":
            split_steps = filter["stepSize"].split(".")
            if split_steps[0] == "1":
                step = 0
            else:
                split_decimal = split_steps[1].find("1")
                step = split_decimal + 1
            break         
    return step


# Websocket functions
def init_stream():
    global W_S
    W_S = websocket.WebSocketApp(
        BINANCE_WEBSOCKET_ADDRESS,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
        )
    W_S.on_open = on_open
    W_S.run_forever()


def on_error(w_s, error):
    print(error)


def on_close(w_s, close_status_code, close_msg):
    if IN_STREAM is True:
        print("closing websocket connection, initiating again...")
        init_stream()


def on_open(w_s):
    print("websocket connection opened...")


def on_message(w_s, message):
    global W_S
    global IN_STREAM

    t = json.loads(message)

    if float(t["c"]) >= EXIT_PRICE:
        exit_long()
        logging.info("Profit gained")
        
        IN_STREAM = False
        W_S.close()
    
    if float(t["c"]) <= STOP_PRICE:
        exit_long()
        logging.info("Stop level reached")
        
        IN_STREAM = False
        W_S.close()         


def enter_long():
    global IN_POSITION

    IN_POSITION = True

    logging.info("Opening long position.")

    logging.info("Getting spot account balance")
    balance = get_spot_balance(QUOTE)

    if not balance:
        return

    logging.info(f"Quote balance: {balance} {QUOTE}")

    order_response = spot_order_quote(
        SYMBOL,
        "BUY",
        "MARKET",
        algoutils.truncate_floor(balance, 6))

    if not order_response:
        return
    
    logging.info(json.dumps(order_response, sort_keys=True, indent=4))


def exit_long():
    global EXIT_PRICE
    global BASE
    global SYMBOL
    global QUOTE
    global IN_STREAM
    global STEP_SIZE

    logging.info("Closing long position")

    logging.info("Getting spot account balance")
    balance = get_spot_balance(BASE)

    if not balance:
        return

    amount_to_sell = algoutils.truncate_floor(balance, STEP_SIZE)
    if STEP_SIZE == 0:
        amount_to_sell = int(amount_to_sell)
    logging.info("Amount to sell %f %s", amount_to_sell, BASE)

    spot_order_response = spot_order(SYMBOL, "SELL", "MARKET", amount_to_sell)

    if not spot_order_response:
        return

    logging.info("Sell order has been filled")

    STEP_SIZE = 0
    SYMBOL = ""
    BASE = ""
    QUOTE = ""
    EXIT_PRICE = 0.0
    IN_STREAM = False


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