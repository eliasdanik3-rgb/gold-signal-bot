import os
import sqlite3
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")

DATABASE = "signals.db"


def init_db():
    with sqlite3.connect(DATABASE) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                signal_id TEXT PRIMARY KEY,
                action TEXT,
                entry REAL,
                stop_loss REAL,
                take_profit REAL,
                strength INTEGER
            )
        """)


init_db()


@app.get("/health")
def health():
    return jsonify({"status": "running"})


@app.post("/webhook")
def webhook():
    if request.headers.get("X-Bot-Secret") != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON"}), 400

    try:
        action = data["action"]
        entry = float(data["entry"])
        stop = float(data["stop_loss"])
        target = float(data["take_profit"])
        strength = int(data["strength"])
        signal_id = str(data["signal_id"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Missing or invalid values"}), 400

    if action not in ("BUY", "SELL"):
        return jsonify({"error": "Invalid action"}), 400

    if not 75 <= strength <= 100:
        return jsonify({"status": "ignored", "reason": "Weak signal"})

    if action == "BUY" and not stop < entry < target:
        return jsonify({"error": "Invalid BUY levels"}), 400

    if action == "SELL" and not target < entry < stop:
        return jsonify({"error": "Invalid SELL levels"}), 400

    try:
        with sqlite3.connect(DATABASE) as db:
            db.execute(
                """INSERT INTO signals
                VALUES (?, ?, ?, ?, ?, ?)""",
                (signal_id, action, entry, stop, target, strength)
            )
    except sqlite3.IntegrityError:
        return jsonify({"status": "duplicate signal"})

    if not BOT_TOKEN or not CHAT_ID:
        return jsonify({"error": "Telegram settings missing"}), 500

    message = (
        f"XAU/USD {action} SIGNAL\\n"
        f"Entry reference: {entry}\\n"
        f"Stop reference: {stop}\\n"
        f"Target reference: {target}\\n"
        f"Strength score: {strength}/100\\n"
        "Paper signal only."
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            json={"chat_id": CHAT_ID, "text": message},
            timeout=2
        )
        response.raise_for_status()
    except requests.RequestException:
        app.logger.exception("Telegram notification failed")
        return jsonify({"error": "Telegram notification failed"}), 502

    return jsonify({"status": "sent"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
