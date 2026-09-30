"""
demo_data.py
CROMPTON Solar Monitor - Mock/Dummy Data Provider
Provides mock telemetry, performance metrics, and diurnal power curves
for single solar panel monitoring (6V, 500mA, 3000mW / 3W max) and soiling loss detection.
"""

from datetime import datetime, timezone

def get_demo_metrics():
    """Return realistic mock telemetry and calculated metrics for 3W solar panel."""
    # 3W panel: max 6V, 500mA, 3000 mW (3 W)
    # Operating example under ~785 W/m²: 4.8V, 400mA -> actual_power = 1920.0 mW (1.92 W)
    # Expected clean power: ~2475.0 mW (2.475 W)
    # Power loss: ~555.0 mW (soiling ~22.4%)
    actual_power_mw = 1920.0
    expected_clean_power_mw = 2475.0
    power_loss_mw = expected_clean_power_mw - actual_power_mw
    soiling_loss_percent = round((power_loss_mw / expected_clean_power_mw) * 100, 2)
    # 555.0 mW * 8h = 4440 mWh = 0.00444 kWh
    energy_loss_kwh = round((power_loss_mw * 8.0) / 1_000_000.0, 6)
    financial_loss_inr = round(energy_loss_kwh * 8.0, 5)

    return {
        "panel_info": {
            "panel_id": "CR-SOLAR-001",
            "model": "Crompton Prototype 3W",
            "rated_capacity_mw": 3000.0,
            "rated_capacity_w": 3.0,
            "max_voltage_v": 6.0,
            "max_current_ma": 500.0,
            "tilt_angle": "22° South",
            "installation_date": "2024-01-15"
        },
        "power_metrics": {
            "actual_power_mw": actual_power_mw,
            "actual_power_w": actual_power_mw,  # legacy alias holding mW value
            "expected_clean_power_mw": expected_clean_power_mw,
            "expected_clean_power_w": expected_clean_power_mw,  # legacy alias holding mW value
            "power_loss_mw": round(power_loss_mw, 4),
            "soiling_loss_percent": soiling_loss_percent,
            "energy_loss_kwh": energy_loss_kwh,
            "energy_loss_mwh": round(power_loss_mw * 8.0, 3),
            "estimated_financial_loss_inr": financial_loss_inr,
            "cumulative_monthly_loss_inr": round(financial_loss_inr * 30.0, 4),
            "panel_voltage_v": 4.8,
            "panel_current_ma": 400.0,
            "panel_current_a": 0.4
        },
        "weather_conditions": {
            "solar_irradiance_wm2": 785.0,
            "ambient_temp_c": 31.5,
            "panel_temp_c": 44.8,
            "air_quality_index": 178,
            "dust_level": "Moderate-High",
            "humidity_percent": 54,
            "wind_speed_kmh": 12.4,
            "cloud_cover_percent": 15
        },
        "ai_prediction_insight": {
            "cleaning_recommended": False,
            "urgency": "Low",
            "projected_weekly_revenue_loss_inr": round(financial_loss_inr * 7.0, 4),
            "optimal_cleaning_window": "Tomorrow morning before 08:30 AM",
            "weather_forecast_note": "Panel capacity is 24mW; financial savings are micro-scale. Automated cleaning advised if maintenance cost is negligible.",
            "confidence_score": 0.91
        },
        "panel_health": {
            "overall_status": "Healthy",
            "efficiency_ratio": round((actual_power_mw / expected_clean_power_mw) * 100, 2),
            "thermal_derating_percent": 3.8,
            "cell_degradation_index": "Normal (< 0.5%/yr)",
            "operating_state": "Active Telemetry"
        },
        "system_status": {
            "backend_state": "Running (Flask)",
            "telemetry_link": "Demo Simulation Mode",
            "supabase_sync": "Standby (Ready)",
            "mqtt_listener": "Pending Configuration",
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "ping_latency_ms": 18
        },
        "graph_data": {
            "labels": [
                "06:00", "07:00", "08:00", "09:00", "10:00", "11:00",
                "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00"
            ],
            "expected_power_mw": [
                0.0, 337.5, 900.0, 1575.0, 2175.0, 2550.0, 2700.0, 2625.0, 2325.0, 1800.0, 1200.0, 450.0, 0.0
            ],
            "expected_power_w": [
                0.0, 0.34, 0.90, 1.58, 2.18, 2.55, 2.70, 2.63, 2.33, 1.80, 1.20, 0.45, 0.0
            ],
            "actual_power_mw": [
                0.0, 237.5, 662.5, 1162.5, 1637.5, 1950.0, 2062.5, 2012.5, 1762.5, 1362.5, 900.0, 312.5, 0.0
            ],
            "actual_power_w": [
                0.0, 0.24, 0.66, 1.16, 1.64, 1.95, 2.06, 2.01, 1.76, 1.36, 0.90, 0.31, 0.0
            ],
            "soiling_gap_mw": [
                0.0, 100.0, 237.5, 412.5, 537.5, 600.0, 637.5, 612.5, 562.5, 437.5, 300.0, 137.5, 0.0
            ],
            "soiling_gap_w": [
                0.0, 0.10, 0.24, 0.41, 0.54, 0.60, 0.64, 0.61, 0.56, 0.44, 0.30, 0.14, 0.0
            ]
        },
        "recent_readings": [
            {
                "timestamp": "13:30:00",
                "irradiance": 785,
                "ambient_temp": 31.5,
                "panel_temp": 44.8,
                "actual_power": 1920.0,
                "expected_power": 2475.0,
                "loss_percent": 22.42,
                "status": "Soiled"
            },
            {
                "timestamp": "13:15:00",
                "irradiance": 802,
                "ambient_temp": 31.8,
                "panel_temp": 45.2,
                "actual_power": 1975.0,
                "expected_power": 2537.5,
                "loss_percent": 22.17,
                "status": "Soiled"
            },
            {
                "timestamp": "13:00:00",
                "irradiance": 820,
                "ambient_temp": 32.0,
                "panel_temp": 45.9,
                "actual_power": 2062.5,
                "expected_power": 2700.0,
                "loss_percent": 23.61,
                "status": "Soiled"
            },
            {
                "timestamp": "12:45:00",
                "irradiance": 835,
                "ambient_temp": 32.2,
                "panel_temp": 46.1,
                "actual_power": 2100.0,
                "expected_power": 2737.5,
                "loss_percent": 23.29,
                "status": "Soiled"
            },
            {
                "timestamp": "12:30:00",
                "irradiance": 845,
                "ambient_temp": 32.1,
                "panel_temp": 46.4,
                "actual_power": 2125.0,
                "expected_power": 2775.0,
                "loss_percent": 23.42,
                "status": "Soiled"
            },
            {
                "timestamp": "12:15:00",
                "irradiance": 830,
                "ambient_temp": 31.9,
                "panel_temp": 45.8,
                "actual_power": 2087.5,
                "expected_power": 2712.5,
                "loss_percent": 23.04,
                "status": "Soiled"
            }
        ]
    }
