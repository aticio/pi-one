import websocket
import json
from datetime import datetime
import requests
import time

EXCHANGE_INFO = "https://api.binance.com/api/v3/exchangeInfo"
KLINE_URL = "https://api.binance.com/api/v3/klines"

KLINE_INTERVAL = "1d"

def main():
    exchange_info = get_exchange_info()
    pairs = get_pairs(exchange_info)
    busd_pairs = filter_busd_pairs(pairs)
    


def get_kline(kline_symbol, kline_interval):
    try:
        params = {"symbol": kline_symbol, "interval": kline_interval, "limit": 720}
        response = requests.get(
            url=f"{KLINE_URL}", params=params)
        response.raise_for_status()
        kline = response.json()
        kline = kline[:-1]
        return kline
    except requests.exceptions.RequestException as err:
        logging.error(err)
        return None


def filter_busd_pairs(pairs):
    busd_paris = []
    for pair in pairs:
        if "BUSD" in pair and "USDT" not in pair:
            busd_paris.append(pair)
    return busd_paris


def get_pairs(exchange_info):
    pairs = []
    for symbol in exchange_info["symbols"]:
        pairs.append(symbol["symbol"])
    return pairs


def get_exchange_info():
    response = requests.get(EXCHANGE_INFO)
    exchange_info = response.json()
    return exchange_info


if __name__ == "__main__":
    main()