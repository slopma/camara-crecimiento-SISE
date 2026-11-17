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

# Verificar si hay cámara CSI conectada
HAS_CSI=false
if command -v rpicam-hello &> /dev/null; then
    if rpicam-hello --list-cameras 2>&1 | grep -q 'Available cameras'; then
        HAS_CSI=true
    fi
fi

while true; do
    if [ "$HAS_CSI" = true ] && command -v rpicam-vid &> /dev/null; then
        echo "[INFO] Usando rpicam-vid (CSI Camera)..."
        rpicam-vid -t 0 --width "$WIDTH" --height "$HEIGHT" --framerate "$FPS" \
            --codec h264 --inline --profile high -o - | \
            ffmpeg -re -f h264 -i - \
            -c:v copy -an \
            -f flv "$RTMP_URL"
    elif [ -e "$VIDEO_DEVICE" ] && command -v ffmpeg &> /dev/null; then
        echo "[INFO] Usando ffmpeg con cámara USB ($VIDEO_DEVICE) en Ultra Low Latency..."
        ffmpeg -f v4l2 -input_format mjpeg -framerate "$FPS" -video_size "${WIDTH}x${HEIGHT}" -i "$VIDEO_DEVICE" \
            -c:v libx264 -preset ultrafast -tune zerolatency -b:v "$BITRATE" \
            -maxrate "$BITRATE" -bufsize "$((BITRATE / 2))" -pix_fmt yuv420p \
            -g "$FPS" -keyint_min "$FPS" -sc_threshold 0 \
            -flush_packets 1 -an -f flv "$RTMP_URL"
    else
        echo "[ERROR] No se detectó cámara CSI ni dispositivo USB en $VIDEO_DEVICE."
        sleep 5
        continue
    fi

    echo "[WARN] La transmisión se detuvo. Reintentando en 5 segundos..."
    sleep 5
done
