from flask import Flask, render_template, jsonify, request
import os
import time
import atexit
import requests
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
FMP_API_KEY = os.getenv("FMP_API_KEY")

OWNED_TICKERS = [
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

QUOTE_CACHE = {}
TARGET_CACHE = {}
FAIR_VALUE_CACHE = {}
NEWS_CACHE = {}

LAST_REFRESH = {
    "quotes": None,
    "targets": None,
    "fair_values": None,
    "news": None,
}

scheduler = BackgroundScheduler(timezone="America/New_York")


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
    return data


def set_cached(cache, key, value):
    cache[key] = {"timestamp": int(time.time()), "value": value}


def get_cached_value(cache, key):
    item = cache.get(key)
    return item["value"] if item else None


def fetch_current_price(symbol):
    data = alpha_get({"function": "GLOBAL_QUOTE", "symbol": symbol})
    quote = data.get("Global Quote", {})
    return quote.get("05. price")


def fetch_price_target(symbol):
    data = alpha_get({"function": "OVERVIEW", "symbol": symbol})
    return data.get("AnalystTargetPrice")


def fetch_fair_value(symbol):
    data = fmp_get_dcf(symbol)

    if isinstance(data, list) and data:
        row = data[0]
    elif isinstance(data, dict):
        row = data
    else:
        row = {}

    for key in ("dcf", "DCF", "fairValue", "fair_value"):
        if key in row:
            return row[key]
    return None


def summarize_news(feed, symbol):
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

        # per your naming:
        # Headwinds = positive momentum
        # Tailwinds = negative momentum
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
    data = alpha_get({
        "function": "NEWS_SENTIMENT",
        "tickers": symbol,
        "sort": "LATEST",
        "limit": 5,
    })
    feed = data.get("feed", [])[:5]
    return summarize_news(feed, symbol)


def refresh_symbol(symbol):
    try:
        set_cached(QUOTE_CACHE, symbol, fetch_current_price(symbol))
    except Exception:
        pass

    try:
        set_cached(TARGET_CACHE, symbol, fetch_price_target(symbol))
    except Exception:
        pass

    try:
        set_cached(FAIR_VALUE_CACHE, symbol, fetch_fair_value(symbol))
    except Exception:
        pass

    try:
        set_cached(NEWS_CACHE, symbol, fetch_news(symbol))
    except Exception:
        pass


def refresh_quotes():
    for symbol in OWNED_TICKERS:
        try:
            set_cached(QUOTE_CACHE, symbol, fetch_current_price(symbol))
        except Exception:
            pass
    LAST_REFRESH["quotes"] = int(time.time())


def refresh_targets():
    for symbol in OWNED_TICKERS:
        try:
            set_cached(TARGET_CACHE, symbol, fetch_price_target(symbol))
        except Exception:
            pass
    LAST_REFRESH["targets"] = int(time.time())


def refresh_fair_values():
    for symbol in OWNED_TICKERS:
        try:
            set_cached(FAIR_VALUE_CACHE, symbol, fetch_fair_value(symbol))
        except Exception:
            pass
    LAST_REFRESH["fair_values"] = int(time.time())


def refresh_news_all():
    for symbol in OWNED_TICKERS:
        try:
            set_cached(NEWS_CACHE, symbol, fetch_news(symbol))
        except Exception:
            pass
    LAST_REFRESH["news"] = int(time.time())


def prime_caches():
    refresh_quotes()
    refresh_targets()
    refresh_fair_values()
    refresh_news_all()


def start_scheduler():
    if scheduler.running:
        return

    scheduler.add_job(
        refresh_quotes,
        trigger="interval",
        minutes=60,
        id="refresh_quotes",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        refresh_targets,
        trigger="interval",
        hours=24,
        id="refresh_targets",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        refresh_fair_values,
        trigger="interval",
        hours=24,
        id="refresh_fair_values",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        refresh_news_all,
        trigger="interval",
        minutes=30,
        id="refresh_news",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    atexit.register(lambda: scheduler.shutdown(wait=False))


def build_row(symbol):
    symbol = symbol.upper()

    if get_cached_value(QUOTE_CACHE, symbol) is None:
        try:
            set_cached(QUOTE_CACHE, symbol, fetch_current_price(symbol))
        except Exception:
            pass

    if get_cached_value(TARGET_CACHE, symbol) is None:
        try:
            set_cached(TARGET_CACHE, symbol, fetch_price_target(symbol))
        except Exception:
            pass

    if get_cached_value(FAIR_VALUE_CACHE, symbol) is None:
        try:
            set_cached(FAIR_VALUE_CACHE, symbol, fetch_fair_value(symbol))
        except Exception:
            pass

    if get_cached_value(NEWS_CACHE, symbol) is None:
        try:
            set_cached(NEWS_CACHE, symbol, fetch_news(symbol))
        except Exception as e:
            set_cached(NEWS_CACHE, symbol, {
                "headwinds": [f"Error loading news: {e}"],
                "tailwinds": ["—"],
                "recent_headlines": [],
            })

    news_summary = get_cached_value(NEWS_CACHE, symbol) or {
        "headwinds": ["—"],
        "tailwinds": ["—"],
        "recent_headlines": [],
    }

    return {
        "ticker": symbol,
        "acquisition_cost": format_money(ACQUISITION_COSTS.get(symbol)) if symbol in ACQUISITION_COSTS else "—",
        "current_price": format_money(get_cached_value(QUOTE_CACHE, symbol)),
        "price_target": format_money(get_cached_value(TARGET_CACHE, symbol)),
        "fair_value": format_money(get_cached_value(FAIR_VALUE_CACHE, symbol)),
        "headwinds": news_summary["headwinds"],
        "tailwinds": news_summary["tailwinds"],
        "recent_headlines": news_summary["recent_headlines"],
        "is_owned": symbol in OWNED_TICKERS,
    }


# start once
prime_caches()
start_scheduler()


@app.route("/")
def index():
    return render_template("index.html", owned_tickers=OWNED_TICKERS)


@app.route("/api/ticker")
def ticker_api():
    symbol = request.args.get("symbol", OWNED_TICKERS[0]).upper()
    row = build_row(symbol)

    return jsonify({
        "updated_at": int(time.time()),
        "refresh_windows": {
            "quotes_minutes": 60,
            "price_targets_hours": 24,
            "fair_values_hours": 24,
            "news_minutes": 30,
        },
        "last_refresh": LAST_REFRESH,
        "row": row,
        "owned_tickers": OWNED_TICKERS,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True, use_reloader=False)
