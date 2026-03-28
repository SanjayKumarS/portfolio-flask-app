from flask import Flask, render_template, jsonify
import os
import time
import requests

app = Flask(__name__)

API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

HOLDINGS = [
    {
        "ticker": "NVDA",
        "market_ticker": "NVDA",
        "market_value": "$80,679.31",
        "price_target": "$268.22",
        "fair_value": "$260.00",
        "corr_gold": "0.01 to -0.03",
        "corr_bitcoin": "0.11 to 0.15",
        "corr_oil": "~0.07",
    },
    {
        "ticker": "TSM",
        "market_ticker": "TSM",
        "market_value": "$20,382.04",
        "price_target": "$430.65",
        "fair_value": "$400.00",
        "corr_gold": "0.02",
        "corr_bitcoin": "0.10",
        "corr_oil": "Low",
    },
    {
        "ticker": "AMD",
        "market_ticker": "AMD",
        "market_value": "$18,179.10",
        "price_target": "$289.61",
        "fair_value": "$270.00",
        "corr_gold": "Low",
        "corr_bitcoin": "~0.09",
        "corr_oil": "Low",
    },
    {
        "ticker": "MSFT",
        "market_ticker": "MSFT",
        "market_value": "$10,703.10",
        "price_target": "$589.90",
        "fair_value": "$420.00",
        "corr_gold": "0.01",
        "corr_bitcoin": "0.09",
        "corr_oil": "Low",
    },
    {
        "ticker": "GOOGL",
        "market_ticker": "GOOGL",
        "market_value": "$5,486.80",
        "price_target": "$376.75",
        "fair_value": "$340.00",
        "corr_gold": "Low",
        "corr_bitcoin": "Low",
        "corr_oil": "Low",
    },
    {
        "ticker": "GLD",
        "market_ticker": "GLD",
        "market_value": "$10,367.50",
        "price_target": "—",
        "fair_value": "—",
        "corr_gold": "1.00",
        "corr_bitcoin": "0.07",
        "corr_oil": "Low / Moderate",
    },
    {
        "ticker": "HOOD",
        "market_ticker": "HOOD",
        "market_value": "$3,301.00",
        "price_target": "$122.23",
        "fair_value": "$194.61",
        "corr_gold": "Low",
        "corr_bitcoin": "Moderate",
        "corr_oil": "Low",
    },
    {
        "ticker": "AMZN",
        "market_ticker": "AMZN",
        "market_value": "$19,934.00",
        "price_target": "$280.80",
        "fair_value": "$281.46",
        "corr_gold": "-0.00",
        "corr_bitcoin": "0.09",
        "corr_oil": "Low",
    },
    {
        "ticker": "ACHR",
        "market_ticker": "ACHR",
        "market_value": "$509.00",
        "price_target": "$11.06",
        "fair_value": "—",
        "corr_gold": "Low",
        "corr_bitcoin": "Low / Moderate",
        "corr_oil": "Low",
    },
    {
        "ticker": "BABA",
        "market_ticker": "BABA",
        "market_value": "$3,176.44",
        "price_target": "$188.46",
        "fair_value": "$189.58",
        "corr_gold": "Low",
        "corr_bitcoin": "Low",
        "corr_oil": "Low",
    },
    {
        "ticker": "NIO",
        "market_ticker": "NIO",
        "market_value": "$531.00",
        "price_target": "$6.52",
        "fair_value": "$6.49",
        "corr_gold": "Low",
        "corr_bitcoin": "Low / Moderate",
        "corr_oil": "Low / Moderate",
    },
    {
        "ticker": "QS",
        "market_ticker": "QS",
        "market_value": "$323.70",
        "price_target": "$7.91",
        "fair_value": "$25.00",
        "corr_gold": "Low",
        "corr_bitcoin": "Low / Moderate",
        "corr_oil": "Low / Moderate",
    },
    {
        "ticker": "DIS",
        "market_ticker": "DIS",
        "market_value": "$5,591.41",
        "price_target": "$129.30",
        "fair_value": "$131.50",
        "corr_gold": "Low",
        "corr_bitcoin": "Low",
        "corr_oil": "Low",
    },
    {
        "ticker": "HUYA",
        "market_ticker": "HUYA",
        "market_value": "$672.83",
        "price_target": "$4.01",
        "fair_value": "$5.44",
        "corr_gold": "Low",
        "corr_bitcoin": "Low",
        "corr_oil": "Low",
    },
    {
        "ticker": "CRSR",
        "market_ticker": "CRSR",
        "market_value": "$532.00",
        "price_target": "$5.00",
        "fair_value": "$8.75 to $9.06",
        "corr_gold": "Low",
        "corr_bitcoin": "Low / Moderate",
        "corr_oil": "Low",
    },
    {
        "ticker": "EVGO",
        "market_ticker": "EVGO",
        "market_value": "$344.00",
        "price_target": "$5.06",
        "fair_value": "$5.27",
        "corr_gold": "Low",
        "corr_bitcoin": "Low / Moderate",
        "corr_oil": "Low / Moderate",
    },
]

CACHE = {"timestamp": 0, "data": None}
CACHE_TTL_SECONDS = 300


def format_money(value):
    return f"${value:,.2f}" if value is not None else "—"


def fetch_quote(symbol):
    if not API_KEY:
        return None

    url = "https://www.alphavantage.co/query"
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": symbol,
        "apikey": API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        payload = response.json()
        quote = payload.get("Global Quote", {})
        price = quote.get("05. price")
        return float(price) if price else None
    except Exception:
        return None


def build_portfolio_rows():
    rows = []

    for holding in HOLDINGS:
        live_price = fetch_quote(holding["market_ticker"])
        rows.append({
            "ticker": holding["ticker"],
            "current_price": format_money(live_price),
            "current_market_value": holding["market_value"],
            "price_target": holding["price_target"],
            "fair_value": holding["fair_value"],
            "corr_gold": holding["corr_gold"],
            "corr_bitcoin": holding["corr_bitcoin"],
            "corr_oil": holding["corr_oil"],
        })

    return rows


def get_cached_portfolio():
    now = time.time()

    if CACHE["data"] is not None and now - CACHE["timestamp"] < CACHE_TTL_SECONDS:
        return CACHE["data"]

    data = build_portfolio_rows()
    CACHE["data"] = data
    CACHE["timestamp"] = now
    return data


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/portfolio")
def portfolio_api():
    return jsonify({
        "updated_at": int(time.time()),
        "rows": get_cached_portfolio()
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
