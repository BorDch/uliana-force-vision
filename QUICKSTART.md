# ULIANA — Quick Start

## Что нужно

- **Ноутбук** (Linux/macOS).
- **ESP32 + коврик** (заряженный powerbank).
- **iPhone** (hotspot) или Wi-Fi сеть.
- **Репозиторий** в `~/CODE/PROJECTS/Skoltech/TEAM_10`.

## Быстрый запуск

### 1. Окружение

    cd ~/CODE/PROJECTS/Skoltech/TEAM_10
    source .venv/bin/activate

### 2. Wi-Fi (iPhone hotspot)

- iPhone → Настройки → Режим модема → включить **Максимальная совместимость**.
- Ноутбук → подключиться к iPhone hotspot.
- Проверить IP:

    ip addr show wlan0 | grep "inet "

Ожидаемо: `172.20.10.10`.

### 3. Backend

    ULIANA_PILOT_CODE='your-private-invite' \
    ULIANA_PAIRING_TTL_MINUTES=180 \
    scripts/start_mobile.sh

Дождаться: `ULIANA mobile is ready at http://127.0.0.1:8001/`.

Терминал **оставить открытым**.

### 4. ESP32

- ESP32 → подключить к powerbank.
- Проверить:

    curl -i http://172.20.10.10:8001/api/sensors

Ожидаемо: JSON с `channels`, `hand: true/false`.

### 5. UI

Открыть: `http://127.0.0.1:8001/`

Войти под аккаунтом. Открыть completed session.

### 6. Проверка

- **Chat-first** — открывается.
- **Review** — skeleton, маркер, полосы hand width.
- **Experimental sensor** — heatmap, `Receiving data`.
- **Live session** — камера + heatmap.

## Если что-то не работает

### ESP32 не определяется

    ls /dev/ttyUSB*
    lsusb | grep -i qinheng
    sudo modprobe ch341

Если нет — другой USB-кабель или другой порт.

### Backend не отвечает

    ps aux | grep uvicorn | grep 8001

Если пусто — перезапустить:

    ULIANA_PILOT_CODE='your-private-invite' scripts/start_mobile.sh

### UI пустой

- F5 (hard reload: Ctrl+Shift+R).
- DevTools (F12) → Console — есть ли ошибки.

### Токен истёк

- UI → `Experimental sensor` → `Create pairing token`.
- Скопировать → вставить в `firmware/esp32_wifi_stream/src/config.h`.
- Перепрошить:

    unset ALL_PROXY HTTP_PROXY HTTPS_PROXY all_proxy http_proxy https_proxy
    .venv/bin/pio run -d firmware/esp32_wifi_stream -e esp32dev \
      --target upload --upload-port /dev/ttyUSB0

## Проверка hand-width

    curl -i http://172.20.10.10:8001/api/sessions/<SESSION_ID>/hand-width

## Запуск мониторинга ESP-32 mat

    .venv/bin/pio device monitor -d firmware/esp32_wifi_stream             


Ожидаемо:

    {
      "shoulder_width_cm": 40,
      "hand_width_cm": 51.5,
      "deviation_cm": 11.5,
      "classification": "too wide",
      "recommendation": "Bring hands closer to shoulder width."
    }

## Остановка

- Backend: Ctrl+C в терминале.
- ESP32: отключить от powerbank.

## Точки возврата

- `v0.1-working-2026-09-24` — без hand-width visualization.
- `v0.2-hand-width-2026-09-24` — с hand-width visualization.

Откат к версии:

    git checkout v0.1-working-2026-09-24 -- .