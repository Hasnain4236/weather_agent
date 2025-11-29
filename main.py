import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from tools import get_current_weather, get_current_weather_summary

load_dotenv()

APP_HOST = os.getenv("WEATHER_APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("WEATHER_APP_PORT", "5000"))

app = Flask(__name__, template_folder="templates", static_folder="static")


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/weather")
def api_weather():
    payload = request.get_json(force=True, silent=True) or {}
    location = (payload.get("location") or "").strip()
    if not location:
        return jsonify({"error": "Please enter a location."}), 400

    try:
        summary = get_current_weather_summary(location)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 502

    return jsonify(summary)


def main():
    debug = os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes", "on"}
    app.run(host=APP_HOST, port=APP_PORT, debug=debug)


if __name__ == "__main__":
    main()
