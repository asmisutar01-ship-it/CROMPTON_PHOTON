"""
sensor_service.py
CROMPTON Solar Monitor - Telemetry Ingestion & Sensor Source Abstraction
Continuously generates realistic solar-panel readings with temporal micro-variations.
Engineered as a plug-and-play abstraction that can seamlessly switch to real
ESP32 / MQTT hardware telemetry without modifying the prediction model or dashboard.
"""

import time
import math
import random
from datetime import datetime, timezone
from typing import Dict, Any

class SensorDataSource:
    """
    Hardware abstraction layer for single-panel solar telemetry.
    3W solar panel specifications: 6 V max, 500 mA max, 3000 mW (3 W) max.
    Produces voltage (V), current (mA), LDR/light level, panel temperature,
    and actual_power_mw = voltage_V × current_mA.
    Can later be bound to MQTTIngestionService when ESP32 microcontrollers are connected.
    """

    def __init__(self, node_id: str = "CR-SOLAR-001"):
        self.node_id = node_id
        self._start_time = time.time()
        self._hardware_connected = False
        self._last_hardware_reading = None
        self._seed_from_database()

    def _seed_from_database(self):
        """Attempts to seed the last known hardware reading from Supabase on startup."""
        try:
            from supabase_db import get_recent_solar_readings
            recent = get_recent_solar_readings(limit=1)
            if recent and len(recent) > 0:
                row = recent[0]
                v = float(row.get("voltage", 0.0) or 0.0)
                c = float(row.get("current", 0.0) or 0.0)
                p = float(row.get("actual_power_w", row.get("power", 0.0)) or 0.0)
                p_mw = round(max(0.0, min(p if p > 0 else v * max(0.0, c), 3000.0)), 4)
                self._last_hardware_reading = {
                    "node_id": row.get("node_id", self.node_id),
                    "voltage": round(v, 2),
                    "current": round(c, 3),
                    "panel_temperature": float(row.get("panel_temperature", 28.0) or 28.0),
                    "ldr_value": float(row.get("ldr_value", 0.0) or 0.0),
                    "actual_power_mw": p_mw,
                    "actual_power": p_mw,
                    "actual_power_w": p_mw,
                    "power": p_mw,
                    "sensor_source": "ESP32 Hardware",
                    "timestamp": row.get("timestamp") or datetime.now(timezone.utc).isoformat()
                }
                self._hardware_connected = True
                print(f"[SensorService] Seeded initial reading from Supabase: V={v}V, I={c}mA, P={p_mw}mW")
        except Exception as seed_err:
            pass

    @property
    def is_hardware(self) -> bool:
        return self._hardware_connected

    def set_hardware_reading(self, reading: Dict[str, Any]):
        """Callback for MQTT listener when real ESP32 messages arrive."""
        self._hardware_connected = True
        normalized = dict(reading)

        # Support ESP32 field names: voltage_v, current_ma, ldr_light, temperature, power_mw
        voltage = float(normalized.get("voltage_v", normalized.get("voltage", 0.0)) or 0.0)
        current = float(normalized.get("current_ma", normalized.get("current", 0.0)) or 0.0)
        temp = float(normalized.get("temperature", normalized.get("panel_temperature", normalized.get("panel_temp", 25.0))) or 25.0)
        ldr = float(normalized.get("ldr_light", normalized.get("ldr_value", normalized.get("ldr", 0.0))) or 0.0)
        power_mw = normalized.get("power_mw")

        normalized["voltage"] = round(voltage, 2)
        normalized["current"] = round(current, 3)
        normalized["panel_temperature"] = round(temp, 1)
        normalized["ldr_value"] = round(ldr, 1)
        normalized["is_dusty"] = bool(normalized.get("is_dusty", False))
        normalized["hotspot_alarm"] = bool(normalized.get("hotspot_alarm", False))

        # actual_power_mw = voltage_V × current_mA (bounded strictly between 0 and 3000 mW / 3W)
        if power_mw is not None:
            actual_power_mw = round(max(0.0, min(float(power_mw), 3000.0)), 4)
        else:
            actual_power_mw = round(max(0.0, min(voltage * max(0.0, current), 3000.0)), 4)

        normalized["actual_power_mw"] = actual_power_mw
        normalized["actual_power"]    = actual_power_mw
        normalized["actual_power_w"]  = actual_power_mw  # legacy alias
        normalized["power"]           = actual_power_mw
        normalized["sensor_source"]   = "ESP32 Hardware"
        normalized.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self._last_hardware_reading = normalized

    def get_current_reading(self) -> Dict[str, Any]:
        """
        Produces realistic 3W panel telemetry with smooth physical dynamics:
        - voltage (V): 0–6 V, nominal ~4.8 V with realistic load oscillations
        - current (mA): 0–500 mA, nominal ~400 mA with natural solar irradiance drift
        - ldr_value: raw light-level indicator (0–4095, not electrical power)
        - panel_temperature (°C): nominal ~42.5 °C with thermal inertia
        - actual_power_mw (mW) = voltage_V × current_mA
          Physical maximum: 6 V × 500 mA = 3000 mW (3 W)
        """
        if self._hardware_connected and self._last_hardware_reading:
            reading = dict(self._last_hardware_reading)
            reading["sensor_source"] = "ESP32 Hardware"
            return reading

        elapsed = time.time() - self._start_time

        # Voltage: 0–6 V, nominal 4.8 V with smooth variations
        v_drift  = 0.28 * math.sin(elapsed / 16.0) + 0.12 * math.cos(elapsed / 7.0)
        v_jitter = random.uniform(-0.04, 0.04)
        voltage  = round(max(0.0, min(6.0, 4.8 + v_drift + v_jitter)), 3)

        # Current: 0–500 mA, nominal ~380 mA with solar flux drift (scaled to 3W panel)
        c_drift  = 25.0 * math.sin(elapsed / 12.0) + 12.0 * math.cos(elapsed / 5.0)
        c_jitter = random.uniform(-2.5, 2.5)
        current  = round(max(0.0, min(500.0, 380.0 + c_drift + c_jitter)), 2)  # mA

        # actual_power_mw = voltage_V × current_mA (max 3000 mW / 3W)
        actual_power_mw = round(max(0.0, min(voltage * current, 3000.0)), 4)
        ldr_value = int(max(0, min(4095, (current / 4.0) * 4095 + random.uniform(-80, 80))))

        # Panel temperature drifts smoothly
        t_drift   = 0.5 * math.sin(elapsed / 25.0)
        t_jitter  = random.uniform(-0.08, 0.08)
        panel_temp = round(42.5 + t_drift + t_jitter, 1)

        return {
            "node_id":          self.node_id,
            "sensor_source":    "Simulated",
            "voltage":          voltage,      # V (0–6)
            "current":          current,      # mA (0–4)
            "ldr_value":        ldr_value,
            "panel_temperature": panel_temp,
            "actual_power_mw":  actual_power_mw,   # mW (primary)
            "actual_power":     actual_power_mw,   # alias
            "actual_power_w":   actual_power_mw,   # legacy alias (value is mW)
            "timestamp":        datetime.now(timezone.utc).isoformat()
        }

# Global singleton instance
sensor_service = SensorDataSource()
get_sensor_reading = sensor_service.get_current_reading
