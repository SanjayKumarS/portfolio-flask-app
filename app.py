from flask import Flask, render_template, jsonify
import os
import time
import requests

app = Flask(__name__)

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
FMP_API_KEY = os.getenv("FMP_API_KEY")

TICKERS = [
    "NVDA", "TSM", "AMD", "MSFT", "GOOGL", "GLD", "HOOD", "AMZN",
    "ACHR", "BABA", "NIO", "QS", "DIS", "HUYA", "CRSR", "EVGO"
]

ACQUISITION_COSTS = {
    "NVDA": 7.19,
    "TSM": 112.56,
    "AMD": 77.87,
    "MSFT": 232.61,
    "GOOGL": 148.00,
    "GLD": 414.01,
    "HOOD": 99.38,
    "AMZN": 242.43,
    "ACHR": 8.91,
    "BABA": 211.77,
    "NIO": 19.04,
    "QS": 46.49,
    "DIS": 158.09,
    "HUYA": 16.05,
    "CRSR": 38.50,
    "EVGO": 1.71,
}

ALPHA_BASE_URL = "https://www.alphavantage.co/query"
FMP_DCF_URL = "https://financialmodelingprep.com/stable/discounted-cash-flow"

QUOTE_TTL = 60 * 60          # 60 minutes
TARGET_TTL = 24 * 60 * 60    # 24 hours
FAIR_VALUE_TTL = 24 * 60 * 60
NEWS_TTL = 30 * 60           # 30 minutes

# Per-symbol caches
QUOTE_CACHE = {}       # {symbol: {"timestamp": ..., "value": ...}}
TARGET_CACHE = {}
FAIR_VALUE_CACHE = {}
NEWS_CACHE = {}


def format_money(value):
    if value in (None, "", "None", "—"):
        return "—"
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return str(value)


def alpha_get(params):
    if not ALPHA_VANTAGE_API_KEY:
        raise RuntimeError("Missing ALPHA_VANTAGE_API_KEY")

    merged = dict(params)
    merged["apikey"] = ALPHA_VANTAGE_API_KEY

    response = requests.get(ALPHA_BASE_URL, params=merged, timeout=30)
    response.raise_for_status()
    data = response.json()

    if isinstance(data, dict):
        if data.get("Note"):
            raise RuntimeError(data["Note"])
        if data.get("Information"):
            raise RuntimeError(data["Information"])
        if data.get("Error Message"):
            raise RuntimeError(data["Error Message"])

    return data


def fmp_get_dcf(symbol):
    if not FMP_API_KEY:
        raise RuntimeError("Missing FMP_API_KEY")

    response = requests.get(
        FMP_DCF_URL,
        params={"symbol": symbol, "apikey": FMP_API_KEY},
        timeout=30
    )
    response.raise_for_status()
    data = response.json()

    if isinstance(data, dict) and data.get("Error Message"):
        raise RuntimeError(data["Error Message"])

    return data


def get_cached(cache, key, ttl):
    item = cache.get(key)
    if not item:
        return None
    if time.time() - item["timestamp"] < ttl:
        return item["value"]
    return None


def set_cached(cache, key, value):
    cache[key] = {
        "timestamp": time.time(),
        "value": value
    }


def fetch_current_price(symbol):
    cached = get_cached(QUOTE_CACHE, symbol, QUOTE_TTL)
    if cached is not None:
        return cached

    data = alpha_get({
        "function": "GLOBAL_QUOTE",
        "symbol": symbol,
    })
    quote = data.get("Global Quote", {})
    value = quote.get("05. price")
    set_cached(QUOTE_CACHE, symbol, value)
    return value


def fetch_price_target(symbol):
    cached = get_cached(TARGET_CACHE, symbol, TARGET_TTL)
    if cached is not None:
        return cached

    data = alpha_get({
        "function": "OVERVIEW",
        "symbol": symbol,
    })
    value = data.get("AnalystTargetPrice")
    set_cached(TARGET_CACHE, symbol, value)
    return value


def fetch_fair_value(symbol):
    cached = get_cached(FAIR_VALUE_CACHE, symbol, FAIR_VALUE_TTL)
    if cached is not None:
        return cached

    data = fmp_get_dcf(symbol)

    if isinstance(data, list) and data:
        row = data[0]
    elif isinstance(data, dict):
        row = data
    else:
        row = {}

    value = None
    for key in ("dcf", "DCF", "fairValue", "fair_value"):
        if key in row:
            value = row[key]
            break

    set_cached(FAIR_VALUE_CACHE, symbol, value)
    return value


def summarize_news(feed, symbol):
    # Per your naming:
    # Headwinds = positive momentum news
    # Tailwinds = negative momentum news
    positive = []
    negative = []
    recent_headlines = []

    for item in feed[:5]:
        title = (item.get("title") or "").strip()
        if title:
            recent_headlines.append(title)

        score_value = None

        for ts in item.get("ticker_sentiment", []):
            if ts.get("ticker") == symbol:
                try:
                    score_value = float(ts.get("ticker_sentiment_score"))
                except Exception:
                    score_value = None
                break

        if score_value is None:
            try:
                score_value = float(item.get("overall_sentiment_score"))
            except Exception:
                score_value = None

        label = (item.get("overall_sentiment_label") or "").lower()

        if score_value is not None:
            if score_value > 0.15 and title:
                positive.append(title)
            elif score_value < -0.15 and title:
                negative.append(title)
        else:
            if "bullish" in label and title:
                positive.append(title)
            elif "bearish" in label and title:
                negative.append(title)

    if not positive:
        positive = ["No clearly positive recent catalyst detected."]
    if not negative:
        negative = ["No clearly negative recent catalyst detected."]

    return {
        "headwinds": positive[:3],
        "tailwinds": negative[:3],
        "recent_headlines": recent_headlines[:5],
    }


def fetch_news(symbol):
    cached = get_cached(NEWS_CACHE, symbol, NEWS_TTL)
    if cached is not None:
        return cached

    data = alpha_get({
        "function": "NEWS_SENTIMENT",
        "tickers": symbol,
        "sort": "LATEST",
        "limit": 5,
    })
    feed = data.get("feed", [])[:5]
    summary = summarize_news(feed, symbol)
    set_cached(NEWS_CACHE, symbol, summary)
    return summary


def build_row(symbol):
    try:
        current_price = fetch_current_price(symbol)
    except Exception as e:
        current_price = None

    try:
        price_target = fetch_price_target(symbol)
    except Exception:
        price_target = None

    try:
        fair_value = fetch_fair_value(symbol)
    except Exception:
        fair_value = None

    try:
        news_summary = fetch_news(symbol)
    except Exception as e:
        news_summary = {
            "headwinds": [f"Error loading news: {e}"],
            "tailwinds": ["—"],
            "recent_headlines": [],
        }

    return {
        "ticker": symbol,
        "acquisition_cost": format_money(ACQUISITION_COSTS.get(symbol)),
        "current_price": format_money(current_price),
        "price_target": format_money(price_target),
        "fair_value": format_money(fair_value),
        "headwinds": news_summary["headwinds"],
        "tailwinds": news_summary["tailwinds"],
        "recent_headlines": news_summary["recent_headlines"],
    }


def get_portfolio_rows():
    return [build_row(symbol) for symbol in TICKERS]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/portfolio")
def portfolio_api():
    rows = get_portfolio_rows()
    return jsonify({
        "updated_at": int(time.time()),
        "refresh_windows": {
            "quotes_minutes": 60,
            "price_targets_hours": 24,
            "fair_values_hours": 24,
            "news_minutes": 30
        },
        "rows": rows,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
