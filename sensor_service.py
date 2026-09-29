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
    Produces voltage, current, LDR/light level, panel temperature, and actual power.
    Can later be bound to MQTTIngestionService when ESP32 microcontrollers are connected.
    """

    def __init__(self, node_id: str = "CR-SOLAR-001"):
        self.node_id = node_id
        self._start_time = time.time()
        self._hardware_connected = False
        self._last_hardware_reading = None

    @property
    def is_hardware(self) -> bool:
        return self._hardware_connected

    def set_hardware_reading(self, reading: Dict[str, Any]):
        """Callback for MQTT listener when real ESP32 messages arrive."""
        self._hardware_connected = True
        normalized = dict(reading)
        normalized["voltage"] = float(normalized["voltage"])
        normalized["current"] = float(normalized["current"])
        normalized["panel_temperature"] = float(
            normalized.get("panel_temperature", normalized.get("panel_temp", 0.0))
        )
        normalized["ldr_value"] = float(
            normalized.get("ldr_value", normalized.get("ldr", normalized.get("light_level", 0.0)))
        )
        normalized["actual_power_w"] = round(normalized["voltage"] * normalized["current"], 1)
        normalized["actual_power"] = normalized["actual_power_w"]
        normalized["power"] = normalized["actual_power_w"]
        normalized.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self._last_hardware_reading = normalized

    def get_current_reading(self) -> Dict[str, Any]:
        """
        Produces realistic panel telemetry with smooth physical dynamics:
        - voltage (V): nominal ~33.8V with realistic load & temperature oscillations
        - current (A): nominal ~4.5A with natural solar irradiance drift
        - ldr_value: raw light-level indicator (not electrical power)
        - panel_temperature (°C): nominal ~42.5°C with thermal inertia
        - actual_power_w (W) = voltage * current
        """
        if self._hardware_connected and self._last_hardware_reading:
            reading = dict(self._last_hardware_reading)
            reading["sensor_source"] = "ESP32 Hardware"
            return reading

        elapsed = time.time() - self._start_time

        # Smooth periodic wave variations + micro-jitter
        v_drift = 0.35 * math.sin(elapsed / 16.0) + 0.15 * math.cos(elapsed / 7.0)
        v_jitter = random.uniform(-0.06, 0.06)
        voltage = round(max(10.0, 33.6 + v_drift + v_jitter), 2)

        # Current drifts realistically with solar flux
        c_drift = 0.28 * math.sin(elapsed / 12.0) + 0.12 * math.cos(elapsed / 5.0)
        c_jitter = random.uniform(-0.04, 0.04)
        current = round(max(0.5, 4.55 + c_drift + c_jitter), 2)

        # Actual power derived from electrical formula P = V * I
        actual_power_w = round(voltage * current, 1)
        ldr_value = int(max(0, min(4095, (current / 5.0) * 4095 + random.uniform(-80, 80))))

        # Panel temperature drifts smoothly
        t_drift = 0.5 * math.sin(elapsed / 25.0)
        t_jitter = random.uniform(-0.08, 0.08)
        panel_temp = round(42.5 + t_drift + t_jitter, 1)

        return {
            "node_id": self.node_id,
            "sensor_source": "Simulated",
            "voltage": voltage,
            "current": current,
            "ldr_value": ldr_value,
            "panel_temperature": panel_temp,
            "actual_power": actual_power_w,
            "actual_power_w": actual_power_w,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

# Global singleton instance
sensor_service = SensorDataSource()
get_sensor_reading = sensor_service.get_current_reading
