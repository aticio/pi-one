import websocket
import json
from datetime import datetime
import requests
import time
import algoutils
import os
import configparser

cwd = os.path.dirname(os.path.realpath(__file__))
os.chdir(cwd)

# Configparser init
cp = configparser.ConfigParser()
cp.read(cwd + "/config.ini")

BINANCE_URL = cp["context"]["BinanceUrl"]
BINANCE_WEBSOCKET_ADDRESS = cp["context"]["BinanceWebSocketAddress"]
EXCHANGE_INFO = cp["context"]["ExchangeInfo"]

WATCHLIST = []
PRICE_DATA = {}

def main():
    init_stream()



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
    global WATCHLIST
    ticker_data = json.loads(message)

    for t in ticker_data:
        if "BUSD" in t["s"] and "USDT" not in t["s"]:
            if len(PRICE_DATA[t["s"]]) == 180:
                PRICE_DATA[t["s"]].pop(0)
            PRICE_DATA[t["s"]].append(t["c"])
            if t['s'] not in WATCHLIST:
                anomaly = check_anomaly(PRICE_DATA[t["s"]])
                if anomaly:
                    print("open pos")


def check_anomaly(prices):
    anomaly = False
    for p in prices[60:]:
        if float(prices[-1]) > (float(p) + (float(p) * 0.1)):
            anomaly = True
            break
    return anomaly


if __name__ == "__main__":
    main()