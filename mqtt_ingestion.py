"""
mqtt_ingestion.py
CROMPTON Solar Monitor - MQTT Telemetry Ingestion Service
Connects to the IoT MQTT broker, subscribes to ESP32 telemetry topic,
updates the sensor abstraction layer (sensor_service.py), and automatically
persists readings to Supabase database (solar_readings).
"""

import os
import json
import logging
import threading
import time
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

from sensor_service import sensor_service
from supabase_db import insert_solar_reading

logger = logging.getLogger("crompton.mqtt_ingestion")
logging.basicConfig(level=logging.INFO)

class MQTTIngestionService:
    """Manager class for MQTT broker connection, telemetry listener, and DB persistence."""

    def __init__(self, broker: str = None, port: int = 1883, topic: str = None, username: str = None, password: str = None):
        self.broker = broker or os.getenv("MQTT_BROKER", "broker.hivemq.com")
        self.port = int(port or os.getenv("MQTT_PORT", 1883))
        self.topic = topic or os.getenv("MQTT_TOPIC", "herframe/solar_demo/sensors")
        self.username = username or os.getenv("MQTT_USERNAME")
        self.password = password or os.getenv("MQTT_PASSWORD")
        self.client = None
        self.is_connected = False
        self._thread = None

    def connect(self):
        """Initializes Paho MQTT client and connects asynchronously."""
        try:
            # Paho MQTT 2.0+ compatibility
            try:
                self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            except AttributeError:
                self.client = mqtt.Client()

            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)

            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
            self.client.on_message = self.on_message

            print(f"[MQTT] Connecting to {self.broker}:{self.port}, topic: {self.topic}...")
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            logger.error(f"[MQTT] Connection failed: {e}")
            self.is_connected = False

    def on_connect(self, client, userdata, flags, rc, properties=None):
        """Callback when connection to broker is established."""
        rc_code = rc if isinstance(rc, int) else getattr(rc, "value", rc)
        if rc_code == 0:
            self.is_connected = True
            print(f"[MQTT] Connected successfully to {self.broker}. Subscribing to '{self.topic}'...")
            client.subscribe(self.topic)
            logger.info(f"[MQTT] Subscribed to topic: {self.topic}")
        else:
            self.is_connected = False
            logger.error(f"[MQTT] Failed to connect, return code {rc}")

    def on_disconnect(self, client, userdata, rc, properties=None):
        """Callback when client is disconnected."""
        self.is_connected = False
        print(f"[MQTT] Disconnected from broker (rc={rc}). Will attempt auto-reconnect.")

    def on_message(self, client, userdata, message):
        """Decode ESP32 JSON payload, update sensor service, and insert to Supabase."""
        try:
            raw_str = message.payload.decode("utf-8")
            payload = json.loads(raw_str)
            if not isinstance(payload, dict):
                raise ValueError("MQTT telemetry payload must be a JSON object.")

            print(f"\n[MQTT] ESP32 Telemetry Received on '{message.topic}': {payload}")

            # 1. Update in-memory sensor service (powers live dashboard)
            sensor_service.set_hardware_reading(payload)
            current_reading = sensor_service.get_current_reading()

            # 2. Persist directly to Supabase solar_readings table
            try:
                db_record = insert_solar_reading({
                    "voltage": current_reading["voltage"],
                    "current": current_reading["current"],
                    "ldr_value": current_reading.get("ldr_value"),
                    "panel_temperature": current_reading.get("panel_temperature"),
                    "node_id": current_reading.get("node_id", "CR-SOLAR-001"),
                    "timestamp": current_reading.get("timestamp") or datetime.now(timezone.utc).isoformat()
                })
                print(f"[Supabase] Saved reading ID {db_record.get('id', 'OK')} (V={current_reading['voltage']}V, I={current_reading['current']}mA, P={current_reading['actual_power_mw']}mW)")
            except Exception as db_err:
                logger.error(f"[Supabase] Failed to insert solar reading: {db_err}")

        except Exception as error:
            logger.warning(f"[MQTT] Ignoring invalid sensor payload: {error}")

    def disconnect(self):
        """Gracefully disconnect MQTT client."""
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass
            self.is_connected = False
            print("[MQTT] Disconnected from broker.")

# Global singleton
mqtt_service = MQTTIngestionService()
