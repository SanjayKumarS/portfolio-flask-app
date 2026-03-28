from flask import Flask, render_template

app = Flask(__name__)

portfolio = [
    {"ticker": "NVDA", "shares": 481.61, "current_price": 167.52, "market_value": 80679.31, "price_target": "$268.22", "fair_value": "$260.00", "corr_gold": "0.01 to -0.03", "corr_btc": "0.11 to 0.15", "corr_oil": "~0.07"},
    {"ticker": "TSM", "shares": 62.38, "current_price": 326.74, "market_value": 20382.04, "price_target": "$430.65", "fair_value": "$400.00", "corr_gold": "0.02", "corr_btc": "0.10", "corr_oil": "Low"},
    {"ticker": "AMD", "shares": 90.00, "current_price": 201.99, "market_value": 18179.10, "price_target": "$289.61", "fair_value": "$270.00", "corr_gold": "Low", "corr_btc": "~0.09", "corr_oil": "Low"},
    {"ticker": "MSFT", "shares": 30.00, "current_price": 356.77, "market_value": 10703.10, "price_target": "$589.90", "fair_value": "$420.00", "corr_gold": "0.01", "corr_btc": "0.09", "corr_oil": "Low"},
    {"ticker": "GOOGL", "shares": 20.00, "current_price": 274.34, "market_value": 5486.80, "price_target": "$376.75", "fair_value": "$340.00", "corr_gold": "Low", "corr_btc": "Low", "corr_oil": "Low"},
    {"ticker": "GLD", "shares": 25.00, "current_price": 414.70, "market_value": 10367.50, "price_target": "—", "fair_value": "—", "corr_gold": "1.00", "corr_btc": "0.07", "corr_oil": "Low / Moderate"},
    {"ticker": "HOOD", "shares": 50.00, "current_price": 66.02, "market_value": 3301.00, "price_target": "$122.23", "fair_value": "$194.61", "corr_gold": "Low", "corr_btc": "Moderate", "corr_oil": "Low"},
    {"ticker": "AMZN", "shares": 100.00, "current_price": 199.34, "market_value": 19934.00, "price_target": "$280.80", "fair_value": "$281.46", "corr_gold": "-0.00", "corr_btc": "0.09", "corr_oil": "Low"},
    {"ticker": "ACHR", "shares": 100.00, "current_price": 5.09, "market_value": 509.00, "price_target": "$11.06", "fair_value": "—", "corr_gold": "Low", "corr_btc": "Low / Moderate", "corr_oil": "Low"},
    {"ticker": "BABA", "shares": 25.89, "current_price": 122.69, "market_value": 3176.44, "price_target": "$188.46", "fair_value": "$189.58", "corr_gold": "Low", "corr_btc": "Low", "corr_oil": "Low"},
    {"ticker": "NIO", "shares": 100.00, "current_price": 5.31, "market_value": 531.00, "price_target": "$6.52", "fair_value": "$6.49", "corr_gold": "Low", "corr_btc": "Low / Moderate", "corr_oil": "Low / Moderate"},
    {"ticker": "QS", "shares": 51.71, "current_price": 6.26, "market_value": 323.70, "price_target": "$7.91", "fair_value": "$25.00", "corr_gold": "Low", "corr_btc": "Low / Moderate", "corr_oil": "Low / Moderate"},
    {"ticker": "DIS", "shares": 60.50, "current_price": 92.42, "market_value": 5591.41, "price_target": "$129.30", "fair_value": "$131.50", "corr_gold": "Low", "corr_btc": "Low", "corr_oil": "Low"},
    {"ticker": "HUYA", "shares": 223.53, "current_price": 3.01, "market_value": 672.83, "price_target": "$4.01", "fair_value": "$5.44", "corr_gold": "Low", "corr_btc": "Low", "corr_oil": "Low"},
    {"ticker": "CRSR", "shares": 100.00, "current_price": 5.32, "market_value": 532.00, "price_target": "$5.00", "fair_value": "$8.75 to $9.06", "corr_gold": "Low", "corr_btc": "Low / Moderate", "corr_oil": "Low"},
    {"ticker": "EVGO", "shares": 200.00, "current_price": 1.72, "market_value": 344.00, "price_target": "$5.06", "fair_value": "$5.27", "corr_gold": "Low", "corr_btc": "Low / Moderate", "corr_oil": "Low / Moderate"},
]

def fmt_money(v):
    return f"${v:,.2f}"

@app.route('/')
def index():
    total_value = sum(x['market_value'] for x in portfolio)
    enriched = []
    for row in portfolio:
        upside = None
        target_num = None
        if row['price_target'].startswith('$'):
            try:
                target_num = float(row['price_target'].replace('$', '').replace(',', ''))
                upside = (target_num / row['current_price'] - 1) * 100
            except ValueError:
                upside = None
        enriched.append({
            **row,
            'current_price_fmt': fmt_money(row['current_price']),
            'market_value_fmt': fmt_money(row['market_value']),
            'upside_pct': upside,
        })
    return render_template('index.html', portfolio=enriched, total_value=fmt_money(total_value), count=len(portfolio))

if __name__ == '__main__':
    app.run(debug=True)
