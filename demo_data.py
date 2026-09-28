"""
demo_data.py
CROMPTON Solar Monitor - Mock/Dummy Data Provider
Provides mock telemetry, performance metrics, and diurnal power curves
for single-solar-panel monitoring and soiling loss detection.
"""

from datetime import datetime, timezone

def get_demo_metrics():
    """Return realistic mock telemetry and calculated metrics for a single 400W solar panel."""
    return {
        "panel_info": {
            "panel_id": "CR-SOLAR-001",
            "model": "Crompton Monocrystalline 400W",
            "rated_capacity_w": 400,
            "tilt_angle": "22° South",
            "installation_date": "2024-01-15"
        },
        "power_metrics": {
            "actual_power_w": 248.5,
            "expected_clean_power_w": 320.0,
            "soiling_loss_percent": 22.34,
            "energy_loss_kwh": 0.43,
            "estimated_financial_loss_inr": 3.44,  # Approx ₹8/kWh
            "cumulative_monthly_loss_inr": 103.20,
            "panel_voltage_v": 34.2,
            "panel_current_a": 7.27
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
            "cleaning_recommended": True,
            "urgency": "Medium",
            "projected_weekly_revenue_loss_inr": 24.08,
            "optimal_cleaning_window": "Tomorrow morning before 08:30 AM",
            "weather_forecast_note": "No rain predicted in the next 5 days; manual/automated cleaning advised.",
            "confidence_score": 0.91
        },
        "panel_health": {
            "overall_status": "Healthy",
            "efficiency_ratio": 77.66,  # actual / clean power * 100
            "thermal_derating_percent": 3.8,
            "cell_degradation_index": "Normal (< 0.5%/yr)",
            "operating_state": "Grid-Tied Active"
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
            "expected_power_w": [
                0, 45, 120, 210, 290, 340, 360, 350, 310, 240, 160, 60, 0
            ],
            "actual_power_w": [
                0, 32, 88, 155, 218, 260, 275, 268, 235, 182, 120, 42, 0
            ],
            "soiling_gap_w": [
                0, 13, 32, 55, 72, 80, 85, 82, 75, 58, 40, 18, 0
            ]
        },
        "recent_readings": [
            {
                "timestamp": "13:30:00",
                "irradiance": 785,
                "ambient_temp": 31.5,
                "panel_temp": 44.8,
                "actual_power": 248.5,
                "expected_power": 320.0,
                "loss_percent": 22.34,
                "status": "Soiled"
            },
            {
                "timestamp": "13:15:00",
                "irradiance": 802,
                "ambient_temp": 31.8,
                "panel_temp": 45.2,
                "actual_power": 255.0,
                "expected_power": 328.0,
                "loss_percent": 22.25,
                "status": "Soiled"
            },
            {
                "timestamp": "13:00:00",
                "irradiance": 820,
                "ambient_temp": 32.0,
                "panel_temp": 45.9,
                "actual_power": 268.0,
                "expected_power": 350.0,
                "loss_percent": 23.42,
                "status": "Soiled"
            },
            {
                "timestamp": "12:45:00",
                "irradiance": 835,
                "ambient_temp": 32.2,
                "panel_temp": 46.1,
                "actual_power": 272.0,
                "expected_power": 356.0,
                "loss_percent": 23.59,
                "status": "Soiled"
            },
            {
                "timestamp": "12:30:00",
                "irradiance": 845,
                "ambient_temp": 32.1,
                "panel_temp": 46.4,
                "actual_power": 275.0,
                "expected_power": 360.0,
                "loss_percent": 23.61,
                "status": "Soiled"
            },
            {
                "timestamp": "12:15:00",
                "irradiance": 830,
                "ambient_temp": 31.9,
                "panel_temp": 45.8,
                "actual_power": 270.0,
                "expected_power": 352.0,
                "loss_percent": 23.29,
                "status": "Soiled"
            }
        ]
    }
