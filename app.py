from flask import Flask, render_template, jsonify
import os
import time
import atexit
import requests
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
FMP_API_KEY = os.getenv("FMP_API_KEY")

TICKERS = [
    "NVDA", "TSM", "AMD", "MSFT", "GOOGL", "GLD", "HOOD", "AMZN",
    "ACHR", "BABA", "NIO", "QS", "DIS", "HUYA", "CRSR", "EVGO"
]

TICKER_SET = set(TICKERS)

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
FMP_DCF_BULK_URL = "https://financialmodelingprep.com/stable/dcf-bulk"

QUOTE_TTL = 60 * 60
TARGET_TTL = 24 * 60 * 60
FAIR_VALUE_TTL = 24 * 60 * 60
NEWS_TTL = 30 * 60

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


def fmp_get_dcf_bulk():
    if not FMP_API_KEY:
        raise RuntimeError("Missing FMP_API_KEY")

    response = requests.get(
        FMP_DCF_BULK_URL,
        params={"apikey": FMP_API_KEY},
        timeout=60
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
    cache[key] = {"timestamp": time.time(), "value": value}


def fetch_current_price(symbol):
    data = alpha_get({"function": "GLOBAL_QUOTE", "symbol": symbol})
    quote = data.get("Global Quote", {})
    return quote.get("05. price")


def fetch_price_target(symbol):
    data = alpha_get({"function": "OVERVIEW", "symbol": symbol})
    return data.get("AnalystTargetPrice")


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

        # Per your naming:
        # Headwinds = positive momentum news
        # Tailwinds = negative momentum news
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


def refresh_quotes():
    results = {}
    for symbol in TICKERS:
        try:
            set_cached(QUOTE_CACHE, symbol, fetch_current_price(symbol))
            results[symbol] = "ok"
        except Exception as e:
            results[symbol] = f"error: {e}"
    LAST_REFRESH["quotes"] = int(time.time())
    return results


def refresh_targets():
    results = {}
    for symbol in TICKERS:
        try:
            set_cached(TARGET_CACHE, symbol, fetch_price_target(symbol))
            results[symbol] = "ok"
        except Exception as e:
            results[symbol] = f"error: {e}"
    LAST_REFRESH["targets"] = int(time.time())
    return results


def refresh_fair_values_bulk():
    results = {}
    try:
        data = fmp_get_dcf_bulk()
        seen = set()

        for row in data if isinstance(data, list) else []:
            symbol = row.get("symbol")
            if symbol not in TICKER_SET:
                continue

            value = None
            for key in ("dcf", "DCF", "fairValue", "fair_value"):
                if key in row:
                    value = row[key]
                    break

            set_cached(FAIR_VALUE_CACHE, symbol, value)
            results[symbol] = "ok"
            seen.add(symbol)

        for symbol in TICKERS:
            if symbol not in seen:
                set_cached(FAIR_VALUE_CACHE, symbol, None)
                results[symbol] = "missing"

    except Exception as e:
        for symbol in TICKERS:
            results[symbol] = f"error: {e}"

    LAST_REFRESH["fair_values"] = int(time.time())
    return results


def refresh_news():
    results = {}
    for symbol in TICKERS:
        try:
            set_cached(NEWS_CACHE, symbol, fetch_news(symbol))
            results[symbol] = "ok"
        except Exception as e:
            results[symbol] = f"error: {e}"
    LAST_REFRESH["news"] = int(time.time())
    return results


def prime_caches():
    # initial load on startup
    try:
        refresh_quotes()
    except Exception:
        pass

    try:
        refresh_targets()
    except Exception:
        pass

    try:
        refresh_fair_values_bulk()
    except Exception:
        pass

    try:
        refresh_news()
    except Exception:
        pass


def build_row(symbol):
    current_price = get_cached(QUOTE_CACHE, symbol, QUOTE_TTL)
    price_target = get_cached(TARGET_CACHE, symbol, TARGET_TTL)
    fair_value = get_cached(FAIR_VALUE_CACHE, symbol, FAIR_VALUE_TTL)
    news_summary = get_cached(NEWS_CACHE, symbol, NEWS_TTL)

    if current_price is None:
        try:
            current_price = fetch_current_price(symbol)
            set_cached(QUOTE_CACHE, symbol, current_price)
        except Exception:
            current_price = None

    if price_target is None:
        try:
            price_target = fetch_price_target(symbol)
            set_cached(TARGET_CACHE, symbol, price_target)
        except Exception:
            price_target = None

    if fair_value is None:
        try:
            refresh_fair_values_bulk()
            fair_value = get_cached(FAIR_VALUE_CACHE, symbol, FAIR_VALUE_TTL)
        except Exception:
            fair_value = None

    if news_summary is None:
        try:
            news_summary = fetch_news(symbol)
            set_cached(NEWS_CACHE, symbol, news_summary)
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
        refresh_fair_values_bulk,
        trigger="interval",
        hours=24,
        id="refresh_fair_values",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        refresh_news,
        trigger="interval",
        minutes=30,
        id="refresh_news",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    atexit.register(lambda: scheduler.shutdown(wait=False))


# start once on process startup
prime_caches()
start_scheduler()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/portfolio")
def portfolio_api():
    return jsonify({
        "updated_at": int(time.time()),
        "refresh_windows": {
            "quotes_minutes": 60,
            "price_targets_hours": 24,
            "fair_values_hours": 24,
            "news_minutes": 30,
        },
        "last_refresh": LAST_REFRESH,
        "rows": get_portfolio_rows(),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True, use_reloader=False)
