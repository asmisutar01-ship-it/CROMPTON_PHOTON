"""
supabase_db.py
CROMPTON Solar Monitor - Supabase Database Layer
Handles database connectivity, telemetry insertions, weather logs,
AI predictions, and retrieval of recent readings.
"""

import os
import socket
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

# Load environment configuration (.env)
load_dotenv()

# Safe DNS fallback helper to handle brand-new Supabase subdomains during ISP DNS propagation
_original_getaddrinfo = socket.getaddrinfo

def _resilient_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        return _original_getaddrinfo(host, port, family, type, proto, flags)
    except socket.gaierror:
        try:
            import dns.resolver
            resolver = dns.resolver.Resolver()
            resolver.nameservers = ["8.8.8.8", "1.1.1.1"]
            answers = resolver.resolve(host, "A")
            ip = answers[0].to_text()
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
        except Exception:
            raise

socket.getaddrinfo = _resilient_getaddrinfo


class SupabaseDB:
    """Supabase client interface for CROMPTON Solar monitoring."""

    def __init__(self):
        self.url: Optional[str] = os.getenv("SUPABASE_URL")
        self.key: Optional[str] = os.getenv("SUPABASE_KEY")
        self._client = None

    def get_client(self):
        """Returns initialized Supabase client singleton."""
        if self._client is not None:
            return self._client

        if not self.url or not self.key:
            raise ValueError(
                "Missing Supabase credentials. Please set SUPABASE_URL and SUPABASE_KEY in .env"
            )

        from supabase import create_client
        self._client = create_client(self.url, self.key)
        return self._client

    # -------------------------------------------------------------------------
    # 1. Solar Readings Operations
    # -------------------------------------------------------------------------
    def insert_solar_reading(self, reading_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inserts a single panel telemetry reading into the 'solar_readings' table.
        Expected fields:
            - voltage (float)
            - current (float)
            - actual_power_w (float, always calculated from voltage × current)
            - ldr_value (float, raw light-level indicator)
            - panel_temperature (float, optional)
            - node_id (str, optional, defaults to 'CR-SOLAR-001')
            - timestamp (isoformat str, optional, defaults to utcnow)
        """
        client = self.get_client()

        voltage = float(reading_data.get("voltage", 0.0))
        current = float(reading_data.get("current", 0.0))
        actual_power_w = round(voltage * current, 2)
        panel_temp = reading_data.get("panel_temperature")
        if panel_temp is not None:
            panel_temp = float(panel_temp)

        payload = {
            "timestamp": reading_data.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            "node_id": str(reading_data.get("node_id", "CR-SOLAR-001")),
            "voltage": round(voltage, 2),
            "current": round(current, 3),
            "power": actual_power_w,
            "actual_power_w": actual_power_w,
            "ldr_value": float(reading_data["ldr_value"]) if reading_data.get("ldr_value") is not None else None,
            "panel_temperature": round(panel_temp, 2) if panel_temp is not None else None,
        }

        response = client.table("solar_readings").insert(payload).execute()
        return response.data[0] if response.data else payload

    def get_recent_solar_readings(self, limit: int = 10, node_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves recent solar readings ordered by timestamp descending."""
        client = self.get_client()
        query = client.table("solar_readings").select("*").order("timestamp", desc=True).limit(limit)
        if node_id:
            query = query.eq("node_id", node_id)
        response = query.execute()
        return response.data or []

    # -------------------------------------------------------------------------
    # 2. Weather Readings Operations
    # -------------------------------------------------------------------------
    def insert_weather_reading(self, weather_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inserts an environmental reading into the 'weather_readings' table.
        Expected fields:
            - temperature (float)
            - humidity (float)
            - solar_radiation (float)
            - cloud_cover (float)
            - rainfall (float)
            - wind_speed (float)
            - timestamp (isoformat str, optional)
        """
        client = self.get_client()

        payload = {
            "timestamp": weather_data.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            "temperature": float(weather_data["temperature"]) if weather_data.get("temperature") is not None else None,
            "ambient_temperature": float(weather_data.get("ambient_temperature", weather_data.get("temperature"))) if weather_data.get("ambient_temperature", weather_data.get("temperature")) is not None else None,
            "humidity": float(weather_data["humidity"]) if weather_data.get("humidity") is not None else None,
            "solar_radiation": float(weather_data["solar_radiation"]) if weather_data.get("solar_radiation") is not None else None,
            "cloud_cover": float(weather_data["cloud_cover"]) if weather_data.get("cloud_cover") is not None else None,
            "rainfall": float(weather_data["rainfall"]) if weather_data.get("rainfall") is not None else 0.0,
            "wind_speed": float(weather_data["wind_speed"]) if weather_data.get("wind_speed") is not None else None,
            "rain_expected_next_4h": bool(weather_data.get("rain_expected_next_4h", False)),
            "rain_probability_next_4h": float(weather_data.get("rain_probability_next_4h", 0.0) or 0.0),
            "rain_next_4h_mm": float(weather_data.get("rain_next_4h_mm", 0.0) or 0.0),
        }

        response = client.table("weather_readings").insert(payload).execute()
        return response.data[0] if response.data else payload

    def get_recent_weather_readings(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieves recent weather readings ordered by timestamp descending."""
        client = self.get_client()
        response = client.table("weather_readings").select("*").order("timestamp", desc=True).limit(limit).execute()
        return response.data or []

    # -------------------------------------------------------------------------
    # 3. Predictions Operations
    # -------------------------------------------------------------------------
    def insert_prediction(self, prediction_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inserts AI prediction & soiling loss analysis into 'predictions' table.
        Expected fields:
            - expected_power (float)
            - actual_power (float)
            - soiling_loss_percent (float)
            - energy_loss (float, optional)
            - estimated_cost_loss (float, optional)
            - cleaning_status (str, e.g. 'NORMAL', 'CLEANING_RECOMMENDED', 'CLEANING_URGENT')
            - timestamp (isoformat str, optional)
        """
        client = self.get_client()

        payload = {
            "timestamp": prediction_data.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            "expected_power": round(float(prediction_data.get("expected_power", prediction_data.get("expected_clean_power", 0.0))), 2),
            "actual_power": round(float(prediction_data.get("actual_power", prediction_data.get("actual_power_w", 0.0))), 2),
            "soiling_loss_percent": round(float(prediction_data.get("soiling_loss_percent", 0.0)), 2),
            "energy_loss": round(float(prediction_data.get("energy_loss", 0.0)), 3),
            "estimated_cost_loss": round(float(prediction_data.get("estimated_cost_loss", 0.0)), 2),
            "cleaning_status": str(prediction_data.get("cleaning_status", "NORMAL")),
            "expected_clean_power": round(float(prediction_data.get("expected_clean_power", prediction_data.get("expected_power", 0.0))), 2),
            "actual_power_w": round(float(prediction_data.get("actual_power_w", prediction_data.get("actual_power", 0.0))), 2),
            "power_loss_w": round(float(prediction_data.get("power_loss_w", 0.0)), 2),
            "rain_expected": bool(prediction_data.get("rain_expected_next_4h", prediction_data.get("rain_expected", False))),
            "rain_probability": round(float(prediction_data.get("rain_probability_next_4h", prediction_data.get("rain_probability", 0.0)) or 0.0), 2),
            "cleaning_cost": round(float(prediction_data.get("cleaning_cost", 0.0)), 2),
            "estimated_future_savings": round(float(prediction_data.get("estimated_future_savings", prediction_data.get("estimated_cost_loss", 0.0))), 2),
            "net_benefit": round(float(prediction_data.get("net_benefit", 0.0)), 2),
            "cleaning_recommendation": str(prediction_data.get("cleaning_recommendation", "NO CLEANING NEEDED")),
            "model_version": str(prediction_data.get("model_version", "rf-clean-power-v3")),
        }

        response = client.table("predictions").insert(payload).execute()
        return response.data[0] if response.data else payload

    def get_recent_predictions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieves recent predictions ordered by timestamp descending."""
        client = self.get_client()
        response = client.table("predictions").select("*").order("timestamp", desc=True).limit(limit).execute()
        return response.data or []

    # -------------------------------------------------------------------------
    # 4. Connection & Health Check
    # -------------------------------------------------------------------------
    def test_connection(self) -> Dict[str, Any]:
        """
        Tests connection to Supabase and verifies existence of the three required tables.
        Returns detailed status report.
        """
        result = {
            "configured": bool(self.url and self.key),
            "url": self.url,
            "connected": False,
            "tables": {
                "solar_readings": False,
                "weather_readings": False,
                "predictions": False,
            },
            "error": None,
        }

        if not result["configured"]:
            result["error"] = "SUPABASE_URL or SUPABASE_KEY is missing from .env"
            return result

        try:
            client = self.get_client()
            result["connected"] = True

            # Test each table
            for tbl in ["solar_readings", "weather_readings", "predictions"]:
                try:
                    client.table(tbl).select("id").limit(1).execute()
                    result["tables"][tbl] = True
                except Exception as table_err:
                    err_msg = str(table_err)
                    if "PGRST205" in err_msg or "Could not find the table" in err_msg:
                        result["tables"][tbl] = False
                    else:
                        result["tables"][tbl] = f"Error: {err_msg}"
        except Exception as conn_err:
            result["connected"] = False
            result["error"] = str(conn_err)

        return result


# Singleton instance for quick imports
db = SupabaseDB()

# Module-level convenience functions
insert_solar_reading = db.insert_solar_reading
get_recent_solar_readings = db.get_recent_solar_readings

insert_weather_reading = db.insert_weather_reading
get_recent_weather_readings = db.get_recent_weather_readings

insert_prediction = db.insert_prediction
get_recent_predictions = db.get_recent_predictions

test_connection = db.test_connection
