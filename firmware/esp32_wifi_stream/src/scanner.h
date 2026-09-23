#ifndef SCANNER_H
#define SCANNER_H

#include <Arduino.h>

const int SIGNAL_PIN = 34;
const int S0 = 16;
const int S1 = 17;
const int S2 = 18;
const int S3 = 19;

const int CHANNEL_COUNT = 16;
const int CALIBRATION_ROUNDS = 2;
const int DELTA_THRESHOLD = 60;

int currentChannel = 0;
int calibrationRound = 0;

long baselineSum[CHANNEL_COUNT] = {0};
int baseline[CHANNEL_COUNT] = {0};

// Последнее прочитанное значение каждого канала
// (добавлено, чтобы main.cpp мог забрать данные после круга)
int lastReading[CHANNEL_COUNT] = {0};

void selectChannel(int channel) {
  digitalWrite(S0, channel & 1);
  digitalWrite(S1, (channel >> 1) & 1);
  digitalWrite(S2, (channel >> 2) & 1);
  digitalWrite(S3, (channel >> 3) & 1);

  // Ждём стабилизации после переключения
  delay(5);

  // Удаляем старые показания АЦП
  for (int i = 0; i < 20; i++) {
    analogRead(SIGNAL_PIN);
  }
}

int readChannel(int channel) {
  selectChannel(channel);

  long sum = 0;

  for (int i = 0; i < 20; i++) {
    sum += analogRead(SIGNAL_PIN);
    delayMicroseconds(100);
  }

  return sum / 20;
}

// Инициализация сканера (замена оригинального setup())
void scannerSetup() {
  pinMode(S0, OUTPUT);
  pinMode(S1, OUTPUT);
  pinMode(S2, OUTPUT);
  pinMode(S3, OUTPUT);

  pinMode(SIGNAL_PIN, INPUT);

  digitalWrite(S0, LOW);
  digitalWrite(S1, LOW);
  digitalWrite(S2, LOW);
  digitalWrite(S3, LOW);

  analogReadResolution(12);
  analogSetPinAttenuation(SIGNAL_PIN, ADC_11db);

  Serial.println();
  Serial.println("Scanner started");
  Serial.println("Do not touch sensors!");
  Serial.println("First two rounds - baseline calibration.");
  Serial.println();
}

// Один такт сканера (замена тела оригинального loop()).
// Возвращает true, если завершён полный круг C0–C15
// и калибровка уже пройдена — значит, можно отправлять батч.
bool scannerTick() {
  int signal = readChannel(currentChannel);
  lastReading[currentChannel] = signal;

  if (calibrationRound < CALIBRATION_ROUNDS) {
    baselineSum[currentChannel] += signal;

    Serial.print("Calibration ");
    Serial.print(calibrationRound + 1);
    Serial.print("/2 | C");
    Serial.print(currentChannel);
    Serial.print(" | Signal: ");
    Serial.println(signal);
  } else {
    int delta = abs(signal - baseline[currentChannel]);

    Serial.print("C");
    Serial.print(currentChannel);
    Serial.print(" | Baseline: ");
    Serial.print(baseline[currentChannel]);
    Serial.print(" | Signal: ");
    Serial.print(signal);
    Serial.print(" | Delta: ");
    Serial.print(delta);

    if (delta > DELTA_THRESHOLD) {
      Serial.print(" | [HAND]");
    } else {
      Serial.print(" | no touch");
    }

    Serial.println();
  }

  currentChannel++;

  if (currentChannel >= CHANNEL_COUNT) {
    currentChannel = 0;

    if (calibrationRound < CALIBRATION_ROUNDS) {
      calibrationRound++;

      Serial.println("--------------------------------");

      if (calibrationRound == CALIBRATION_ROUNDS) {
        Serial.println("Calibration complete. Baselines:");

        for (int channel = 0; channel < CHANNEL_COUNT; channel++) {
          baseline[channel] =
              baselineSum[channel] / CALIBRATION_ROUNDS;

          Serial.print("C");
          Serial.print(channel);
          Serial.print(" = ");
          Serial.println(baseline[channel]);
        }

        Serial.println();
        Serial.println("Touch detection started.");
      }
    }

    Serial.println("--------------------------------");

    // Полный круг завершён и калибровка пройдена
    return calibrationRound >= CALIBRATION_ROUNDS;
  }

  return false;
}

#endif
