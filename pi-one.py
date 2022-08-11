import websocket
import json
from datetime import datetime
import requests
import time
from multiprocessing import Process
from legitindicators import super_smoother

EXCHANGE_INFO = "https://api.binance.com/api/v3/exchangeInfo"
KLINE_URL = "https://api.binance.com/api/v3/klines"

KLINE_INTERVAL = "1d"
KLINE_LIMIT = 30


def main():
    exchange_info = get_exchange_info()
    pairs = get_pairs(exchange_info)
    busd_pairs = filter_busd_pairs(pairs)
    for bp in busd_pairs:
        p = Process(target=init_ops, args=(bp,))
        p.start() 


def init_ops(pair):
    klines = get_kline(pair, KLINE_INTERVAL, KLINE_LIMIT)
    open, high, _, close = get_ohlc(klines)
    fall_short = 0
    for i, _ in enumerate(klines):
        if high[i] - open[i] < open[i] * 0.01:
            fall_short = fall_short + 1
    
    if fall_short == 0:
        ss = super_smoother(close, 20)
        if close[-1] > ss[-1]:
            print(pair)




def get_ohlc(klines):
    open = [float(o[1]) for o in klines]
    high = [float(h[2]) for h in klines]
    low = [float(l[3]) for l in klines]
    close = [float(c[4]) for c in klines]
    return open, high, low, close


def get_high(klines):
    high = [float(d[2]) for d in klines]
    return high

def get_kline(kline_symbol, kline_interval, kline_limit):
    try:
        params = {"symbol": kline_symbol, "interval": kline_interval, "limit": kline_limit}
        response = requests.get(
            url=f"{KLINE_URL}", params=params)
        response.raise_for_status()
        kline = response.json()
        # kline = kline[:-1]
        return kline
    except requests.exceptions.RequestException as err:
        print(err)
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