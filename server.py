import os
import json
from flask import Flask, request, jsonify
import anthropic

app = Flask(__name__)
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Opslag voor laatste bekende trend per symbool+timeframe
trend_cache = {}

SYSTEM_PROMPT = """Je bent een market structure analyst. Je krijgt OHLC candlestick data en bepaalt de huidige trend.

Jouw regels:
- Een swing high is het HOOGSTE punt (wick) van een volledige bullish beweging, gevolgd door een neerwaartse beweging
- Een swing low is het LAAGSTE punt (wick) van een volledige bearish beweging, gevolgd door een opwaartse beweging
- BULLISH: een candle sluit met zijn BODY (close) BOVEN de laatste swing high → uptrend
- BEARISH: een candle sluit met zijn BODY (close) ONDER de laatste swing low → downtrend
- Wicks tellen NIET voor BOS confirmatie, alleen de close
- Trend verandert ALLEEN bij een echte break of structure in de tegenovergestelde richting
- Een retrace zonder BOS verandert de trend NIET

Antwoord ALLEEN met een JSON object, niets anders:
{"trend": "up"} of {"trend": "down"} of {"trend": "neutral"}"""


def analyse_trend(candles: list, current_trend: str) -> str:
    # Formatteer candles als leesbare tekst
    candle_text = "Laatste candles (oudste eerst) — open, high, low, close:\n"
    for c in candles[-50:]:  # max 50 candles meesturen
        candle_text += f"O:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']}\n"

    user_msg = f"{candle_text}\nHuidige trend: {current_trend}\nBepaal de trend op basis van market structure (BOS)."

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=50,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}]
    )

    text = response.content[0].text.strip()
    data = json.loads(text)
    return data.get("trend", "neutral")


@app.route("/trend", methods=["POST"])
def get_trend():
    """
    Verwacht JSON body:
    {
      "symbol": "NASDAQ:NQ1!",
      "timeframe": "240",
      "candles": [
        {"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05},
        ...
      ]
    }
    """
    try:
        body = request.get_json()
        symbol = body.get("symbol", "unknown")
        timeframe = body.get("timeframe", "unknown")
        candles = body.get("candles", [])

        if len(candles) < 5:
            return jsonify({"error": "Te weinig candles"}), 400

        cache_key = f"{symbol}_{timeframe}"
        current_trend = trend_cache.get(cache_key, "neutral")

        trend = analyse_trend(candles, current_trend)
        trend_cache[cache_key] = trend

        return jsonify({"trend": trend, "symbol": symbol, "timeframe": timeframe})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
