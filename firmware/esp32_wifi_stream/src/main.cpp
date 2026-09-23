#include <Arduino.h>
#include <HTTPClient.h>
#include <WiFi.h>

#include "config.h"
#include "scanner.h"

static uint32_t nextSequence = 1;
static uint32_t retryAtMs = 0;
static uint32_t backoffMs = 1000;
static uint32_t lastWiFiAttemptMs = 0;
static bool wasConnected = false;

static void connectWiFi() {
  WiFi.mode(WIFI_STA);
  Serial.printf("Connecting to WiFi: %s\n", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastWiFiAttemptMs = millis();
  const uint32_t startedAt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startedAt < 30000) {
    delay(250);
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("WiFi connected. IP: %s\n", WiFi.localIP().toString().c_str());
    wasConnected = true;
  } else {
    Serial.println("WiFi connect failed");
  }
}

static String escapeJson(const char* value) {
  String escaped;
  for (const char* cursor = value; *cursor; ++cursor) {
    if (*cursor == '"' || *cursor == '\\') escaped += '\\';
    escaped += *cursor;
  }
  return escaped;
}

static String batchPayload(uint32_t deviceTimeMs) {
  String payload = "{\"schema_version\":1,\"device_id\":\"" + escapeJson(DEVICE_ID) +
                   "\",\"sequence\":" + String(nextSequence) +
                   ",\"device_time_ms\":" + String(deviceTimeMs) + ",\"baseline\":{";
  for (int channel = 0; channel < CHANNEL_COUNT; ++channel) {
    if (channel) payload += ',';
    payload += "\"channel_" + String(channel) + "\":" + String(baseline[channel]);
  }
  payload += "},\"channels\":[";
  for (int channel = 0; channel < CHANNEL_COUNT; ++channel) {
    if (channel) payload += ',';
    payload += "{\"channel_id\":\"channel_" + String(channel) +
               "\",\"raw_value\":" + String(lastReading[channel]) + "}";
  }
  payload += "]}";
  return payload;
}

static bool sendBatch(uint32_t deviceTimeMs) {
  if (WiFi.status() != WL_CONNECTED || !strcmp(PAIRING_TOKEN, "paste-token-here") ||
      !strlen(PAIRING_TOKEN)) return false;
  HTTPClient http;
  http.setTimeout(3000);
  if (!http.begin(SERVER_URL)) {
    Serial.println("error: HTTP initialization failed");
    return false;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", "Bearer " + String(PAIRING_TOKEN));
  Serial.printf("sending sequence %lu\n", (unsigned long)nextSequence);
  String payload = batchPayload(deviceTimeMs);
  Serial.printf("Payload size: %u bytes\n", (unsigned)payload.length());
  int status = http.POST(payload);
  Serial.printf("POST -> %d\n", status);
  if (status < 200 || status >= 300) {
    String response = http.getString();
    Serial.printf("Response: %.200s\n", response.c_str());
  }
  http.end();
  if (status < 200 || status >= 300) return false;
  ++nextSequence;
  return true;
}

void setup() {
  Serial.begin(115200);
  delay(500);
  connectWiFi();
  scannerSetup();
}

void loop() {
  // Keep scanning even while Wi-Fi is disconnected or in retry backoff.
  bool roundComplete = scannerTick();
  uint32_t now = millis();
  if (WiFi.status() != WL_CONNECTED) {
    if (wasConnected) Serial.println("error: WiFi disconnected");
    wasConnected = false;
    if (now - lastWiFiAttemptMs >= 5000) {
      Serial.println("WiFi connecting");
      WiFi.reconnect();
      lastWiFiAttemptMs = now;
    }
    return;
  }
  if (!wasConnected) Serial.printf("WiFi connected. IP: %s\n", WiFi.localIP().toString().c_str());
  wasConnected = true;
  if (!roundComplete || (int32_t)(now - retryAtMs) < 0) return;
  if (sendBatch(now)) {
    backoffMs = 1000;
    retryAtMs = 0;
  } else {
    retryAtMs = now + backoffMs;
    Serial.printf("retry in %lu ms\n", (unsigned long)backoffMs);
    backoffMs = min(backoffMs * 2, (uint32_t)30000);
  }
}
