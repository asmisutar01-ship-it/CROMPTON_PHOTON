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
from prediction_model import (
    train_model,
    predict_clean_power,
    calculate_soiling_loss,
    get_model_metrics,
    ldr_to_irradiance,
    cross_check_irradiance,
    LDR_RAW_MIN,
    LDR_RAW_MAX,
    LDR_MAX_IRRAD,
    LDR_GAMMA
)
from sensor_service import get_sensor_reading, sensor_service
from mqtt_ingestion import mqtt_service

# Automatically train the lightweight ML model on startup
print("Initializing CROMPTON ML Prediction Layer...")
train_model()

# Start background MQTT ingestion service for ESP32 hardware telemetry
print("Starting CROMPTON MQTT Ingestion Service...")
mqtt_service.connect()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "crompton-default-secret-key")


def format_recent_reading(r: dict, reference_expected_power: float = 19.8) -> dict:
    """Format a Supabase solar reading for dashboard table display."""
    raw_ts = r.get("timestamp", "")
    try:
        dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        ts_str = dt.strftime("%H:%M:%S")
    except Exception:
        ts_str = str(raw_ts)[11:19] if len(str(raw_ts)) >= 19 else str(raw_ts)

    v = float(r.get("voltage", 0.0) or 0.0)
    c = float(r.get("current", 0.0) or 0.0)
    p = float(r.get("actual_power_w", r.get("power", 0.0)) or 0.0)
    if p <= 0 and v > 0 and c > 0:
        p = v * c
    actual_power = round(max(0.0, min(p, 3000.0)), 2)

    ldr = float(r.get("ldr_value", 0.0) or 0.0)
    if ldr > 0:
        irradiance = round(ldr_to_irradiance(ldr), 1)
    else:
        irradiance = 785.0

    expected_power = round(min(3000.0, max(0.0, 3000.0 * (irradiance / 1000.0))), 2) if irradiance > 0 else reference_expected_power
    if expected_power < 0.1:
        expected_power = reference_expected_power

    if expected_power > 0:
        loss_val = max(0.0, expected_power - actual_power)
        loss_pct = round((loss_val / expected_power) * 100.0, 1)
    else:
        loss_pct = 0.0

    if loss_pct < 5.0:
        status = "Clean"
    elif loss_pct < 15.0:
        status = "Normal"
    else:
        status = "Soiled"

    return {
        "timestamp": ts_str,
        "irradiance": irradiance,
        "ambient_temp": 30.5,
        "panel_temp": round(float(r.get("panel_temperature", 28.0) or 28.0), 1),
        "actual_power": actual_power,
        "expected_power": expected_power,
        "loss_percent": loss_pct,
        "status": status,
        "voltage": round(v, 2),
        "current": round(c, 2)
    }


def build_dashboard_metrics() -> dict:
    """
    Constructs live dashboard metrics integrating real hardware telemetry from
    sensor_service (ESP32) and Supabase database records.
    Falls back gracefully to demo defaults if sensors/database are empty.
    """
    demo = get_demo_metrics()
    try:
        sensor = get_sensor_reading()
        sensor_source = sensor.get("sensor_source", "Simulated")
        v = float(sensor.get("voltage", 4.8))
        c = float(sensor.get("current", 3.2))
        p_raw = sensor.get("actual_power_mw", v * c)
        actual_power = round(max(0.0, min(float(p_raw), 3000.0)), 2)
        panel_temp = round(float(sensor.get("panel_temperature", 42.5)), 1)
        ldr = float(sensor.get("ldr_value", 0.0))

        irrad_check = cross_check_irradiance(None, ldr)
        effective_irrad = irrad_check["resolved_irradiance"]
        if effective_irrad <= 0:
            effective_irrad = 785.0

        features = {
            "solar_radiation": effective_irrad,
            "cloud_cover": 15.0,
            "ambient_temperature": 30.0,
            "panel_temperature": panel_temp,
            "humidity": 50.0,
            "ldr_value": ldr,
            "time_of_day": datetime.now().hour + datetime.now().minute / 60.0
        }
        expected_clean_power = predict_clean_power(features)
        loss_calc = calculate_soiling_loss(actual_power, expected_clean_power)

        recent_rows = []
        try:
            from supabase_db import get_recent_solar_readings
            db_readings = get_recent_solar_readings(limit=8)
            if db_readings and len(db_readings) > 0:
                for row in db_readings:
                    recent_rows.append(format_recent_reading(row, expected_clean_power))
        except Exception:
            pass

        if not recent_rows:
            recent_rows = demo["recent_readings"]

        demo["power_metrics"]["actual_power_mw"] = actual_power
        demo["power_metrics"]["actual_power_w"] = actual_power
        demo["power_metrics"]["expected_clean_power_mw"] = expected_clean_power
        demo["power_metrics"]["expected_clean_power_w"] = expected_clean_power
        demo["power_metrics"]["power_loss_mw"] = loss_calc["power_loss_w"]
        demo["power_metrics"]["soiling_loss_percent"] = loss_calc["soiling_loss_percent"]
        demo["power_metrics"]["energy_loss_kwh"] = loss_calc["energy_loss_kwh"]
        demo["power_metrics"]["estimated_financial_loss_inr"] = loss_calc["estimated_future_savings"]
        demo["power_metrics"]["panel_voltage_v"] = round(v, 2)
        demo["power_metrics"]["panel_current_ma"] = round(c, 2)

        demo["weather_conditions"]["solar_irradiance_wm2"] = round(effective_irrad, 1)
        demo["weather_conditions"]["panel_temp_c"] = panel_temp

        demo["recent_readings"] = recent_rows
        demo["system_status"]["last_updated"] = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        demo["system_status"]["mqtt_status"] = f"Connected ({mqtt_service.topic})" if mqtt_service.is_connected else "Connecting..."
        demo["system_status"]["telemetry_source"] = sensor_source

    except Exception as e:
        print(f"[build_dashboard_metrics] Fallback to demo due to: {e}")

    return demo


@app.route("/")
def dashboard():
    """Renders the main CROMPTON Solar Monitor Dashboard shell with live telemetry."""
    data = build_dashboard_metrics()
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
        "model_metrics": get_model_metrics(),
        "mqtt": f"Connected ({mqtt_service.topic})" if mqtt_service.is_connected else "Connecting...",
        "message": "CROMPTON Solar Monitor Backend is running successfully."
    }), 200


@app.route("/api/dashboard-data")
def api_dashboard_data():
    """API endpoint providing current live telemetry and diurnal curve data."""
    return jsonify(build_dashboard_metrics()), 200


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
    - expected_clean_power (mW)
    - voltage (V), current (mA), ldr_value (raw light level)
    - solar_radiation (W/m²)
    - ambient_temperature (°C)
    - cloud_cover (%)
    - humidity (%)
    - location (city string to pull live weather and four-hour precipitation forecast)
    - rain_expected_next_4h (bool: true/false)
    - rain_probability_next_4h (float: 0-100%)
    """
    try:
        args = request.args

        # 1. Pull from sensor abstraction layer (simulated or hardware)
        sensor = get_sensor_reading()
        voltage        = float(args.get("voltage", sensor["voltage"]))
        current        = float(args.get("current", sensor["current"]))
        panel_temp     = float(args.get("panel_temperature", sensor["panel_temperature"]))
        ldr_value      = float(args.get("ldr_value", sensor.get("ldr_value", 0.0)))
        actual_power   = round(max(0.0, min(float(sensor.get("actual_power_mw", float(voltage) * float(current))), 3000.0)), 4)  # mW = V × mA (clamped [0, 3000.0] / 3W)
        sensor_source  = sensor.get("sensor_source", "Simulated")

        # 2. Irradiance resolution: Calibrate ESP32 LDR and cross-check with weather API
        weather_rad_param = args.get("solar_radiation")
        weather_rad = float(weather_rad_param) if weather_rad_param is not None else None
        irrad_check = cross_check_irradiance(weather_rad, ldr_value)
        effective_solar_radiation = irrad_check["resolved_irradiance"]

        # 3. Build feature set for the prediction model (all environmental + LDR)
        features = {
            "solar_radiation":     effective_solar_radiation,
            "cloud_cover":         float(args.get("cloud_cover", 10.0)),
            "ambient_temperature": float(args.get("ambient_temperature", args.get("temperature", 28.5))),
            "panel_temperature":   panel_temp,
            "humidity":            float(args.get("humidity", 50.0)),
            "ldr_value":           ldr_value,
            "time_of_day":         float(args.get("time_of_day", datetime.now().hour + datetime.now().minute / 60.0))
        }

        # 4. Predict expected clean power via the ML model (or query override)
        if "expected_clean_power" in args:
            expected_clean_power = float(args["expected_clean_power"])
        else:
            expected_clean_power = predict_clean_power(features)

        # 5. Resolve precipitation only for the next four hours.
        rain_exp_param = args.get("rain_expected_next_4h")
        rain_prob_param = args.get("rain_probability_next_4h")
        loc_param = args.get("location")
        rain_expected_next_4h = None
        rain_probability_next_4h = float(rain_prob_param or 0.0)
        rain_next_4h_mm = float(args.get("rain_next_4h_mm", 0.0) or 0.0)
        rain_forecast_24h_mm = 0.0

        if rain_exp_param is not None:
            rain_expected_next_4h = str(rain_exp_param).strip().lower() in ("true", "1", "yes")

        if rain_expected_next_4h is None and loc_param:
            try:
                w_data = get_weather_by_location(loc_param.strip()).get("weather", {})
                rain_expected_next_4h = w_data.get("rain_expected_next_4h", False)
                rain_probability_next_4h = w_data.get("rain_probability_next_4h", 0.0)
                rain_next_4h_mm = w_data.get("rain_next_4h_mm", 0.0)
                rain_forecast_24h_mm = w_data.get("rain_forecast_24h_mm", 0.0)
            except Exception:
                pass

        if rain_expected_next_4h is None:
            from weather_api import _LAST_WEATHER_CACHE
            cached_weather = _LAST_WEATHER_CACHE.get("weather", {})
            rain_expected_next_4h = cached_weather.get("rain_expected_next_4h", False)
            rain_probability_next_4h = cached_weather.get("rain_probability_next_4h", 0.0)
            rain_next_4h_mm = cached_weather.get("rain_next_4h_mm", 0.0)
            rain_forecast_24h_mm = cached_weather.get("rain_forecast_24h_mm", 0.0)

        # 6. Compute soiling loss + financial metrics + cleaning recommendation
        result = calculate_soiling_loss(
            actual_power,
            expected_clean_power,
            rain_expected_next_4h=rain_expected_next_4h,
            rain_probability_next_4h=rain_probability_next_4h,
            rain_next_4h_mm=rain_next_4h_mm,
            cloud_cover=features["cloud_cover"]
        )

        # 7. Attach sensor telemetry, LDR calibration info & rain forecast volume
        result["voltage"]                   = round(voltage, 2)
        result["current"]                   = round(current, 2)
        result["ldr_value"]                 = round(ldr_value, 1)
        result["calibrated_ldr_irradiance"] = irrad_check["ldr_irradiance"]
        result["effective_solar_radiation"] = round(effective_solar_radiation, 1)
        result["irradiance_source"]         = irrad_check["source"]
        result["irradiance_cross_check"]    = irrad_check
        result["panel_temperature"]         = round(panel_temp, 1)
        result["sensor_source"]             = sensor_source
        result["mqtt_status"]               = f"Connected ({mqtt_service.topic})" if mqtt_service.is_connected else "Connecting..."
        result["rain_forecast_24h_mm"]      = round(float(rain_forecast_24h_mm or 0.0), 2)

        # Attach real recent readings for live table auto-refresh
        recent_rows = []
        try:
            from supabase_db import get_recent_solar_readings
            db_readings = get_recent_solar_readings(limit=8)
            if db_readings:
                for row in db_readings:
                    recent_rows.append(format_recent_reading(row, expected_clean_power))
        except Exception:
            pass
        result["recent_readings"] = recent_rows

        # 8. Persist AI prediction and soiling loss analysis to Supabase
        try:
            from supabase_db import insert_prediction
            insert_prediction(result)
        except Exception as pred_db_err:
            pass  # Non-blocking for live polling endpoint

        return jsonify(result), 200

    except ValueError as e:
        return jsonify({"error": f"Invalid numeric parameter: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"error": f"Pipeline failed: {str(e)}"}), 500


@app.route("/api/recent-readings")
def api_recent_readings():
    """Returns recent solar readings from Supabase formatted for the dashboard table."""
    try:
        from supabase_db import get_recent_solar_readings
        db_readings = get_recent_solar_readings(limit=10)
        formatted = [format_recent_reading(r) for r in db_readings]
        return jsonify({"status": "success", "readings": formatted}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug_mode = os.getenv("FLASK_ENV", "development") == "development"
    print(f"Starting CROMPTON Solar Monitor on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug_mode, use_reloader=False)
