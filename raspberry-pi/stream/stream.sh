#!/bin/bash
# ==============================================================================
# SISE - Transmisor de Video RTMP para Raspberry Pi
# Soporta tanto cámaras USB (V4L2) como cámaras oficiales Raspberry Pi (libcamera / rpicam)
# ==============================================================================

# Cargar variables de entorno si existe .env
ENV_FILE="${ENV_FILE:-../.env}"
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

RTMP_URL="${RTMP_SERVER_URL:-rtmp://localhost:1935/live/m1}"
VIDEO_DEVICE="${VIDEO_DEVICE:-/dev/video0}"
WIDTH="${VIDEO_WIDTH:-1280}"
HEIGHT="${VIDEO_HEIGHT:-720}"
FPS="${VIDEO_FPS:-25}"
BITRATE="${VIDEO_BITRATE:-1500k}"

echo "=================================================="
echo "Iniciando transmisión de video SISE"
echo "Destino RTMP : $RTMP_URL"
echo "Dispositivo  : $VIDEO_DEVICE"
echo "Resolución   : ${WIDTH}x${HEIGHT} @ ${FPS}fps"
echo "Bitrate      : $BITRATE"
echo "=================================================="

while true; do
    if command -v rpicam-vid &> /dev/null; then
        echo "[INFO] Usando rpicam-vid (CSI Camera)..."
        rpicam-vid -t 0 --width "$WIDTH" --height "$HEIGHT" --framerate "$FPS" \
            --codec h264 --inline --profile high -o - | \
            ffmpeg -re -f h264 -i - \
            -c:v copy -an \
            -f flv "$RTMP_URL"
    elif command -v libcamera-vid &> /dev/null; then
        echo "[INFO] Usando libcamera-vid (CSI Camera)..."
        libcamera-vid -t 0 --width "$WIDTH" --height "$HEIGHT" --framerate "$FPS" \
            --codec h264 --inline --profile high -o - | \
            ffmpeg -re -f h264 -i - \
            -c:v copy -an \
            -f flv "$RTMP_URL"
    elif command -v ffmpeg &> /dev/null; then
        echo "[INFO] Usando ffmpeg con V4L2 USB ($VIDEO_DEVICE)..."
        ffmpeg -f v4l2 -framerate "$FPS" -video_size "${WIDTH}x${HEIGHT}" -i "$VIDEO_DEVICE" \
            -c:v libx264 -preset ultrafast -tune zerolatency -b:v "$BITRATE" \
            -maxrate "$BITRATE" -bufsize "$BITRATE" -pix_fmt yuv420p -g "$((FPS * 2))" \
            -an -f flv "$RTMP_URL"
    else
        echo "[ERROR] No se encontró ffmpeg, rpicam-vid ni libcamera-vid instalados."
        echo "Instala ffmpeg con: sudo apt install -y ffmpeg"
        sleep 10
        continue
    fi

    echo "[WARN] La transmisión se detuvo. Reintentando en 5 segundos..."
    sleep 5
done
