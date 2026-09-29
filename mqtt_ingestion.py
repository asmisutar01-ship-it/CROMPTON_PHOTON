"""
mqtt_ingestion.py
CROMPTON Solar Monitor - MQTT Telemetry Ingestion (Stub)
Responsible for connecting to the IoT broker and subscribing to telemetry streams
from the single solar panel micro-sensors (voltage, current, power, temperature).
Note: MQTT client connection and payload handlers will be added in upcoming steps.
"""

import os
import json
import logging

from sensor_service import sensor_service

logger = logging.getLogger("crompton.mqtt_ingestion")

class MQTTIngestionService:
    """Manager class for MQTT broker connection and telemetry listener."""

    def __init__(self, broker: str = None, port: int = 1883, topic: str = None):
        self.broker = broker or os.getenv("MQTT_BROKER", "broker.hivemq.com")
        self.port = int(port or os.getenv("MQTT_PORT", 1883))
        self.topic = topic or os.getenv("MQTT_TOPIC", "crompton/solar/panel1")
        self.client = None
        self.is_connected = False

    def connect(self):
        """Placeholder for establishing MQTT connection."""
        print(f"[MQTT] Ingestion service ready for broker: {self.broker}:{self.port}, topic: {self.topic}")
        # Paho MQTT connection will be initiated here in future phase

    def disconnect(self):
        """Placeholder for closing MQTT connection."""
        if self.is_connected:
            self.is_connected = False
            print("[MQTT] Disconnected from broker.")

    def on_message(self, client, userdata, message):
        """Decode an ESP32 JSON payload and forward its sensor values."""
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("MQTT telemetry payload must be a JSON object.")
            sensor_service.set_hardware_reading(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, KeyError) as error:
            logger.warning("Ignoring invalid MQTT sensor payload: %s", error)
