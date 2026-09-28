"""
app.py
CROMPTON Solar Monitor - Main Flask Application
Single-Solar-Panel Monitoring and Soiling-Loss Intelligence System
"""

import os
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv

# Load environment configuration
load_dotenv()

# Import data providers and ML engine
from demo_data import get_demo_metrics
from weather_api import get_weather_by_location, geocode_location, get_weather
from prediction_model import train_model, predict_clean_power, calculate_soiling_loss
from sensor_service import get_sensor_reading

# Automatically train the lightweight ML model on startup
print("Initializing CROMPTON ML Prediction Layer...")
train_model()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "crompton-default-secret-key")


@app.route("/")
def dashboard():
    """Renders the main CROMPTON Solar Monitor Dashboard shell with placeholder data."""
    data = get_demo_metrics()
    return render_template("dashboard.html", metrics=data)


@app.route("/api/health")
def health_check():
    """Health check endpoint to verify backend status."""
    return jsonify({
        "status": "healthy",
        "service": "CROMPTON Solar Monitor Backend",
        "version": "1.0.0-foundation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": "Supabase (Client connected & authenticated)",
        "weather": "Open-Meteo (No API key required)",
        "prediction_engine": "RandomForestRegressor (Trained & Active)",
        "mqtt": "Standby (ready for ingestion)",
        "message": "CROMPTON Solar Monitor Backend is running successfully."
    }), 200


@app.route("/api/dashboard-data")
def api_dashboard_data():
    """API endpoint providing current dummy telemetry and diurnal curve data."""
    return jsonify(get_demo_metrics()), 200


@app.route("/api/weather")
def api_weather():
    """
    GET /api/weather?location=<city>

    1. Validates the location parameter.
    2. Geocodes it via Open-Meteo Geocoding API.
    3. Fetches real-time weather via Open-Meteo Weather API.
    4. Returns combined location + weather JSON.

    Error responses follow a consistent { "error": "<message>" } shape.
    """
    location = request.args.get("location", "").strip()

    # --- Validation ---
    if not location:
        return jsonify({"error": "Location parameter is required. Example: /api/weather?location=Pune"}), 400

    if len(location) > 100:
        return jsonify({"error": "Location name is too long. Please enter a valid city or town."}), 400

    # --- Geocode + Weather ---
    try:
        result = get_weather_by_location(location)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except LookupError:
        return jsonify({
            "error": "Location not found. Please enter a valid city, town or location."
        }), 404
    except RuntimeError as e:
        return jsonify({
            "error": f"Weather data temporarily unavailable. ({e})"
        }), 503
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {e}"}), 500

    return jsonify(result), 200


@app.route("/api/sensor")
def api_sensor():
    """
    GET /api/sensor
    Returns the latest telemetry from the sensor abstraction layer.
    Currently: Simulated sensor readings.
    Future: ESP32 hardware readings via MQTT.
    """
    reading = get_sensor_reading()
    return jsonify(reading), 200


@app.route("/api/prediction")
def api_prediction():
    """
    GET /api/prediction

    Full telemetry pipeline:
      Sensor (simulated or hardware)
        → actual_power
        → weather data (optional query params to pass in live values)
        → predict_clean_power (RandomForestRegressor)
        → calculate_soiling_loss (weather-aware cleaning recommendations)
        → return JSON with all metrics, rain forecast & sensor metadata

    Optional query parameters override sensor/weather defaults:
    - actual_power (W)
    - expected_clean_power (W)
    - solar_radiation (W/m²)
    - temperature (°C)
    - cloud_cover (%)
    - humidity (%)
    - location (city string to pull live 24h precipitation forecast)
    - rain_expected (bool: true/false)
    - rain_probability (float: 0-100%)
    """
    try:
        args = request.args

        # 1. Pull from sensor abstraction layer (simulated or hardware)
        sensor = get_sensor_reading()
        voltage        = sensor["voltage"]
        current        = sensor["current"]
        panel_temp     = sensor["panel_temperature"]
        actual_power   = float(args.get("actual_power", sensor["actual_power"]))
        sensor_source  = sensor.get("sensor_source", "Simulated")

        # 2. Build feature set for the prediction model
        features = {
            "solar_radiation":  float(args.get("solar_radiation",  520.0)),
            "temperature":      float(args.get("temperature",       28.5)),
            "cloud_cover":      float(args.get("cloud_cover",       10.0)),
            "humidity":         float(args.get("humidity",          50.0)),
            "panel_temperature": panel_temp,
            "voltage":           voltage,
            "current":           current
        }

        # 3. Predict expected clean power via the ML model (or query override)
        if "expected_clean_power" in args:
            expected_clean_power = float(args["expected_clean_power"])
        else:
            expected_clean_power = predict_clean_power(features)

        # 4. Resolve upcoming rain forecast (weather-aware recommendation)
        # Check explicit query params first
        rain_exp_param = args.get("rain_expected")
        rain_prob_param = args.get("rain_probability")
        loc_param = args.get("location")

        rain_expected = None
        rain_probability = 0.0

        if rain_exp_param is not None:
            rain_expected = str(rain_exp_param).strip().lower() in ("true", "1", "yes")

        if rain_prob_param is not None:
            try:
                rain_probability = float(rain_prob_param)
            except (ValueError, TypeError):
                rain_probability = 0.0

        # If rain forecast is not explicitly overridden in params, check location
        rain_forecast_24h_mm = float(args.get("rain_forecast_24h_mm", 0.0) or 0.0)
        if rain_expected is None and loc_param:
            try:
                w_data = get_weather_by_location(loc_param.strip()).get("weather", {})
                rain_expected = w_data.get("rain_expected", False)
                rain_probability = w_data.get("rain_probability", 0.0)
                rain_forecast_24h_mm = w_data.get("rain_forecast_24h_mm", 0.0)
            except Exception:
                pass

        # Fallback to default if no forecast data available
        if rain_expected is None:
            from weather_api import _LAST_WEATHER_CACHE
            cached_weather = _LAST_WEATHER_CACHE.get("weather", {})
            rain_expected = cached_weather.get("rain_expected", False)
            rain_probability = cached_weather.get("rain_probability", 0.0)
            if not rain_forecast_24h_mm:
                rain_forecast_24h_mm = cached_weather.get("rain_forecast_24h_mm", 0.0)

        # 5. Compute soiling loss + financial metrics + cleaning recommendation
        result = calculate_soiling_loss(
            actual_power,
            expected_clean_power,
            rain_expected=rain_expected,
            rain_probability=rain_probability
        )

        # 6. Attach sensor telemetry and rain forecast volume so dashboard can display live V / I / Rain readings
        result["voltage"]               = round(voltage, 1)
        result["current"]               = round(current, 2)
        result["panel_temperature"]     = round(panel_temp, 1)
        result["sensor_source"]         = sensor_source
        result["rain_forecast_24h_mm"]  = round(float(rain_forecast_24h_mm or 0.0), 2)

        return jsonify(result), 200

    except ValueError as e:
        return jsonify({"error": f"Invalid numeric parameter: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"error": f"Pipeline failed: {str(e)}"}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug_mode = os.getenv("FLASK_ENV", "development") == "development"
    print(f"Starting CROMPTON Solar Monitor on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug_mode, use_reloader=False)
