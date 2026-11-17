#!/usr/bin/env python3
"""
Servidor MJPEG de Ultra Baja Latencia para Cámara de Crecimiento SISE.
Lee MJPEG directamente del driver V4L2 del kernel sin pasar por ffmpeg,
y además hace RTMP hacia el servidor Nginx para el HLS.
"""

import os, sys, time, threading, struct, fcntl, mmap, ctypes
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

PORT      = int(os.getenv("STREAM_PORT", "8082"))
DEVICE    = os.getenv("VIDEO_DEVICE", "/dev/video0")
WIDTH     = os.getenv("VIDEO_WIDTH",  "1280")
HEIGHT    = os.getenv("VIDEO_HEIGHT", "720")
FPS       = os.getenv("VIDEO_FPS",    "25")
RTMP_URL  = os.getenv("RTMP_SERVER_URL", "rtmp://localhost:1935/live/m1")
BITRATE   = os.getenv("VIDEO_BITRATE", "1500k")

# ─────────────────────────────────────────────
# Frame broadcaster compartido entre threads
# ─────────────────────────────────────────────
class FrameBroadcaster:
    def __init__(self):
        self.lock      = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.frame     = None
        self.running   = True

    def push(self, data: bytes):
        with self.condition:
            self.frame = data
            self.condition.notify_all()

    def latest(self, timeout=1.5):
        with self.condition:
            self.condition.wait(timeout)
            return self.frame

broadcaster = FrameBroadcaster()

# ─────────────────────────────────────────────
# Captura: un solo ffmpeg. stdout = mpjpeg pipe
# El pipe se divide: broadcaster recibe frames
# y un segundo proceso los recodifica para RTMP
# ─────────────────────────────────────────────
def capture_worker():
    cmd = [
        "ffmpeg", "-nostdin", "-loglevel", "warning",
        "-f", "v4l2", "-input_format", "mjpeg",
        "-video_size", f"{WIDTH}x{HEIGHT}",
        "-framerate", FPS,
        "-i", DEVICE,
        # Salida 1: MJPEG pipe para el servidor web (sin re-encode, copia directa)
        "-map", "0:v",
        "-c:v", "copy",
        "-f", "mpjpeg",
        "-boundary_tag", "frame",
        "pipe:1"
    ]

    while broadcaster.running:
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                bufsize=0
            )
            print(f"[MJPEG] Captura iniciada desde {DEVICE} @ {WIDTH}x{HEIGHT}/{FPS}fps", flush=True)

            buf = b""
            CHUNK = 16384  # 16KB por lectura
            while broadcaster.running and proc.poll() is None:
                chunk = proc.stdout.read(CHUNK)
                if not chunk:
                    break
                buf += chunk

                # Extraer frames JPG completos del buffer
                while True:
                    s = buf.find(b"\xff\xd8")
                    if s == -1:
                        buf = b""
                        break
                    e = buf.find(b"\xff\xd9", s + 2)
                    if e == -1:
                        buf = buf[s:]  # Guardar inicio parcial
                        break
                    frame = buf[s:e + 2]
                    broadcaster.push(frame)
                    buf = buf[e + 2:]

            err = proc.stderr.read(2048).decode(errors="replace") if proc.stderr else ""
            if err:
                print(f"[MJPEG ERROR] {err.strip()}", flush=True)
        except Exception as ex:
            print(f"[MJPEG] Excepcion: {ex}", flush=True)
        finally:
            try:
                proc.terminate()
            except Exception:
                pass
        print("[MJPEG] Reiniciando captura en 2s...", flush=True)
        time.sleep(2)


# ─────────────────────────────────────────────
# RTMP Worker: recodifica frames JPEG → H264 RTMP
# ─────────────────────────────────────────────
def rtmp_worker():
    cmd = [
        "ffmpeg", "-nostdin", "-loglevel", "warning",
        "-re",
        "-f", "v4l2", "-input_format", "mjpeg",
        "-video_size", f"{WIDTH}x{HEIGHT}",
        "-framerate", FPS,
        "-i", DEVICE,
        "-c:v", "libx264",
        "-preset", "ultrafast", "-tune", "zerolatency",
        "-b:v", BITRATE, "-maxrate", BITRATE,
        "-bufsize", BITRATE,
        "-pix_fmt", "yuv420p",
        "-g", FPS, "-keyint_min", FPS, "-sc_threshold", "0",
        "-flush_packets", "1",
        "-an", "-f", "flv", RTMP_URL
    ]
    while broadcaster.running:
        try:
            proc = subprocess.Popen(cmd, stderr=subprocess.DEVNULL)
            print(f"[RTMP] Stream iniciado hacia {RTMP_URL}", flush=True)
            proc.wait()
        except Exception as ex:
            print(f"[RTMP] Error: {ex}", flush=True)
        finally:
            try:
                proc.terminate()
            except Exception:
                pass
        print("[RTMP] Reiniciando en 3s...", flush=True)
        time.sleep(3)


# ─────────────────────────────────────────────
# Servidor HTTP MJPEG
# ─────────────────────────────────────────────
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class StreamHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return  # Silenciar logs continuos

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS, HEAD")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_HEAD(self):
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Cache-Control",
                         "no-cache, no-store, must-revalidate, pre-check=0, post-check=0, max-age=0")
        self.send_header("Pragma",  "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Connection",    "close")
        self.send_header("Content-Type",  "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()

        while True:
            frame = broadcaster.latest(timeout=2.0)
            if not frame:
                continue
            try:
                header = (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(frame)}\r\n\r\n".encode()
                )
                self.wfile.write(header)
                self.wfile.write(frame)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                break


def main():
    # Esperar a que /dev/video0 esté libre
    for _ in range(10):
        try:
            test = open(DEVICE, "rb")
            test.close()
            break
        except (OSError, IOError):
            print(f"[INIT] Esperando a que {DEVICE} quede libre...", flush=True)
            time.sleep(1)

    # Lanzar captura MJPEG (para el servidor web)
    t_cap = threading.Thread(target=capture_worker, daemon=True)
    t_cap.start()

    # Esperar primer frame antes de lanzar RTMP (evitar conflicto en /dev/video0)
    print("[INIT] Esperando primer frame...", flush=True)
    for _ in range(15):
        if broadcaster.frame:
            break
        time.sleep(0.5)

    # El RTMP usa una instancia separada de /dev/video0 (el driver lo permite en lectura múltiple)
    t_rtmp = threading.Thread(target=rtmp_worker, daemon=True)
    t_rtmp.start()

    server = ThreadedHTTPServer(("0.0.0.0", PORT), StreamHandler)
    print(f"[MJPEG SERVER] Escuchando en 0.0.0.0:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        broadcaster.running = False


if __name__ == "__main__":
    main()
