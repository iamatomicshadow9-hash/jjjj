"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║          🌐  KOYEB WEB SERVER  —  PRODUCTION KEEPALIVE ENGINE                ║
║                                                                              ║
║   Назначение:                                                                ║
║     • Отвечать на health-check пинги от Koyeb → контейнер не убивается       ║
║     • Монитороить bot.py и автоматически его перезапускать                   ║
║     • Предоставлять REST API состояния системы                               ║
║     • Крохотная встроенная HTML-панель мониторинга                           ║
║                                                                              ║
║   Порт берётся из переменной окружения PORT (Koyeb ставит её сам).          ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import time
import signal
import socket
import shutil
import threading
import subprocess
import traceback
import psutil                          # pip install psutil
from datetime import datetime, timedelta
from collections import deque
from pathlib import Path
from flask import Flask, jsonify, request, Response   # pip install flask
from functools import wraps

# ─────────────────────────────────────────────────────────────────────────────
# 1.  КОНФИГУРАЦИЯ
# ─────────────────────────────────────────────────────────────────────────────

class Cfg:
    """Единый источник правды для всех настроек."""

    # ── Порт ─────────────────────────────────────────────────────────────
    PORT: int = int(os.getenv("PORT", "8000"))

    # ── Файл бота ────────────────────────────────────────────────────────
    BOT_FILE: str = os.getenv("BOT_FILE", "bot.py")

    # ── Перезапуск бота ──────────────────────────────────────────────────
    AUTO_RESTART:        bool = True
    RESTART_DELAY_SEC:   float = 5.0          # пауза перед повторным запуском
    MAX_CRASHES_WINDOW:  int   = 10           # макс. краши за окно
    CRASH_WINDOW_SEC:    int   = 300          # 5 минут

    # ── Логирование ──────────────────────────────────────────────────────
    LOG_DIR:             str   = "logs"
    LOG_FILE:            str   = "web_server.log"
    LOG_MAX_BYTES:       int   = 8 * 1024 * 1024   # 8 MB
    LOG_RETENTION_DAYS:  int   = 7

    # ── Буфер событий для UI ─────────────────────────────────────────────
    EVENT_BUFFER_SIZE:   int   = 200

    # ── Упаковочные дни ──────────────────────────────────────────────────
    STARTUP_TIME:        datetime = datetime.now()


# ─────────────────────────────────────────────────────────────────────────────
# 2.  ЛОГГЕР  (потокобезопасный, с ротацией)
# ─────────────────────────────────────────────────────────────────────────────

class Color:
    """ANSI-цвета для терминала."""
    RESET   = "\033[0m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"


_LEVEL_COLOR = {
    "DEBUG":    Color.DIM,
    "INFO":     Color.CYAN,
    "SUCCESS":  Color.GREEN,
    "WARN":     Color.YELLOW,
    "ERROR":    Color.RED,
    "CRIT":     Color.MAGENTA,
}

_LEVEL_ORDER = {"DEBUG": 0, "INFO": 1, "SUCCESS": 1, "WARN": 2, "ERROR": 3, "CRIT": 4}


class Logger:
    """
    Потокобезопасный логгер.
    • Пишет в stdout (с цветом) и в файл (без цвета).
    • Делает ротацию файла по размеру.
    • Удаляет старые файлы логов.
    """

    def __init__(self, min_level: str = "INFO"):
        self._lock     = threading.Lock()
        self._min_lvl  = _LEVEL_ORDER.get(min_level.upper(), 1)
        self._file     = None
        self._file_path: str | None = None
        self._setup_file()

    # ── файл ─────────────────────────────────────────────────────────────
    def _setup_file(self):
        Path(Cfg.LOG_DIR).mkdir(exist_ok=True)
        self._cleanup_old_logs()
        self._file_path = os.path.join(Cfg.LOG_DIR, Cfg.LOG_FILE)
        self._file = open(self._file_path, "a", encoding="utf-8")

    def _cleanup_old_logs(self):
        cutoff = time.time() - Cfg.LOG_RETENTION_DAYS * 86400
        for f in Path(Cfg.LOG_DIR).glob("*.log*"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError:
                pass

    def _maybe_rotate(self):
        if not self._file_path:
            return
        try:
            if os.path.getsize(self._file_path) >= Cfg.LOG_MAX_BYTES:
                self._file.close()
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                os.rename(self._file_path, self._file_path + f".{ts}.old")
                self._file = open(self._file_path, "a", encoding="utf-8")
        except OSError:
            pass

    # ── основной метод ───────────────────────────────────────────────────
    def _log(self, level: str, msg: str, src: str = "WEB"):
        if _LEVEL_ORDER.get(level, 0) < self._min_lvl:
            return

        with self._lock:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            clr = _LEVEL_COLOR.get(level, "")

            # stdout — цветная строка
            console = (
                f"{Color.DIM}[{ts}]{Color.RESET} "
                f"{clr}{level:>7}{Color.RESET} "
                f"{Color.BLUE}[{src:^10}]{Color.RESET} "
                f"{msg}"
            )
            print(console, flush=True)

            # файл — без цвета
            if self._file:
                self._file.write(f"[{ts}] [{level:>7}] [{src:^10}] {msg}\n")
                self._file.flush()
                self._maybe_rotate()

    # ── удобные обёртки ──────────────────────────────────────────────────
    def debug(self,   msg: str, src: str = "WEB"): self._log("DEBUG",   msg, src)
    def info(self,    msg: str, src: str = "WEB"): self._log("INFO",    msg, src)
    def success(self, msg: str, src: str = "WEB"): self._log("SUCCESS", msg, src)
    def warn(self,    msg: str, src: str = "WEB"): self._log("WARN",    msg, src)
    def error(self,   msg: str, src: str = "WEB"): self._log("ERROR",   msg, src)
    def crit(self,    msg: str, src: str = "WEB"): self._log("CRIT",    msg, src)

    def close(self):
        if self._file:
            self._file.close()


# ─────────────────────────────────────────────────────────────────────────────
# 3.  МЕНЕДЖЕР БОТА  (запуск / мониторинг / перезапуск)
# ─────────────────────────────────────────────────────────────────────────────

class BotManager:
    """
    Всё, что связано с жизненным циклом bot.py.

    Алгоритм:
        start_bot()
            ├─ запускаем subprocess
            ├─ стартуем два потока: stdout-reader, stderr-reader
            └─ стартуем _monitor_loop (тоже в потоке)
                    └─ если процесс упал → restart_bot()
                            └─ если слишком много крашей → останавливаемся
    """

    def __init__(self, logger: Logger):
        self.log = logger

        # ── состояние ────────────────────────────────────────────────────
        self._proc:       subprocess.Popen | None = None
        self._lock        = threading.Lock()
        self._running     = False          # мониторинг активен?

        # ── статистика ───────────────────────────────────────────────────
        self.crash_times: deque = deque(maxlen=Cfg.MAX_CRASHES_WINDOW + 5)
        self.total_crashes:     int = 0
        self.total_restarts:    int = 0
        self.last_crash_reason: str = ""
        self.start_time:        datetime | None = None

        # ── буфер вывода бота для UI ─────────────────────────────────────
        self.output_buffer: deque = deque(maxlen=Cfg.EVENT_BUFFER_SIZE)

    # ── публичный API ────────────────────────────────────────────────────

    def start_bot(self) -> bool:
        """Запустить bot.py. Возвращает True если успешно."""
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self.log.warn("bot.py уже запущен", "BOT-MGR")
                return True

            if not os.path.isfile(Cfg.BOT_FILE):
                self.log.crit(f"Файл бота не найден: {Cfg.BOT_FILE}", "BOT-MGR")
                return False

            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"

            try:
                self._proc = subprocess.Popen(
                    [sys.executable, "-u", Cfg.BOT_FILE],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    env=env,
                )
                self.start_time = datetime.now()
                self.log.success(f"bot.py запущен (PID {self._proc.pid})", "BOT-MGR")

                # потоки для чтения stdout / stderr
                threading.Thread(target=self._read_stream, args=(self._proc.stdout, "STDOUT"), daemon=True).start()
                threading.Thread(target=self._read_stream, args=(self._proc.stderr, "STDERR"), daemon=True).start()

                # поток мониторинга
                if not self._running:
                    self._running = True
                    threading.Thread(target=self._monitor_loop, daemon=True).start()

                return True

            except Exception as exc:
                self.log.error(f"Не удалось запустить bot.py: {exc}", "BOT-MGR")
                self._proc = None
                return False

    def stop_bot(self, timeout: float = 10.0) -> bool:
        """Остановить bot.py (graceful → kill)."""
        with self._lock:
            if not self._proc or self._proc.poll() is not None:
                return True

            self.log.info("Остановка bot.py…", "BOT-MGR")
            self._proc.terminate()
            try:
                self._proc.wait(timeout=timeout)
                self.log.success("bot.py остановлен корректно", "BOT-MGR")
            except subprocess.TimeoutExpired:
                self.log.warn("Таймаут — принудительный kill", "BOT-MGR")
                self._proc.kill()
                self._proc.wait(timeout=5)
            self._running = False
            return True

    # ── свойства для опроса ──────────────────────────────────────────────

    @property
    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc else None

    @property
    def uptime_seconds(self) -> int:
        if self.start_time and self.is_alive:
            return int((datetime.now() - self.start_time).total_seconds())
        return 0

    # ── внутренние методы ────────────────────────────────────────────────

    def _read_stream(self, stream, label: str):
        """Читаем stdout/stderr бота и кладём в буфер + логируем."""
        try:
            for line in stream:
                line = line.rstrip("\n")
                if not line:
                    continue
                self.output_buffer.append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "src":  label,
                    "msg":  line,
                })
                if label == "STDERR":
                    self.log.error(f"[bot] {line}", "BOT-OUT")
                else:
                    self.log.info(f"[bot] {line}", "BOT-OUT")
        except Exception:
            pass   # stream закрыт — нормально

    def _monitor_loop(self):
        """Фоновый цикл: проверяет, жив ли бот, и перезапускает при нужде."""
        self.log.info("Мониторинг bot.py запущен", "BOT-MON")
        while self._running:
            time.sleep(3)
            if not self._running:
                break

            with self._lock:
                if self._proc is None:
                    continue
                if self._proc.poll() is None:
                    continue   # процесс жив — ничего не делаем

            # ── процесс упал ─────────────────────────────────────────────
            exit_code = self._proc.returncode if self._proc else -1
            self.last_crash_reason = f"exit code {exit_code}"
            self.total_crashes += 1
            self.crash_times.append(time.time())
            self.log.error(f"bot.py упал! {self.last_crash_reason} (crash #{self.total_crashes})", "BOT-MON")

            if not Cfg.AUTO_RESTART:
                self.log.warn("AUTO_RESTART выключен — перезапуск отменён", "BOT-MON")
                break

            # ── проверка «слишком много крашей» ──────────────────────────
            cutoff = time.time() - Cfg.CRASH_WINDOW_SEC
            recent = sum(1 for t in self.crash_times if t > cutoff)
            if recent >= Cfg.MAX_CRASHES_WINDOW:
                self.log.crit(
                    f"🛑 {recent} крашей за {Cfg.CRASH_WINDOW_SEC}с — "
                    f"автоперезапуск ОТКЛЮЧЁН. Бот остановлен.",
                    "BOT-MON",
                )
                self._running = False
                break

            # ── перезапуск ───────────────────────────────────────────────
            self.log.info(f"Перезапуск bot.py через {Cfg.RESTART_DELAY_SEC}с…", "BOT-MON")
            time.sleep(Cfg.RESTART_DELAY_SEC)
            self.total_restarts += 1
            self.start_bot()   # рекурсивный старт (lock отпущен)

        self.log.info("Мониторинг bot.py остановлен", "BOT-MON")

# ─────────────────────────────────────────────────────────────────────────────
# 4.  СОБРАНИЕ МЕТРИК СИСТЕМЫ  (CPU / RAM / диск)
# ─────────────────────────────────────────────────────────────────────────────

def _sys_metrics() -> dict:
    """Быстрый снапшот системных метрик через psutil."""
    try:
        cpu   = psutil.cpu_percent(interval=0.3)
        ram   = psutil.virtual_memory()
        disk  = psutil.disk_usage("/")
        return {
            "cpu_pct":          cpu,
            "ram_used_mb":      round(ram.used / 1_048_576, 1),
            "ram_total_mb":     round(ram.total / 1_048_576, 1),
            "ram_pct":          ram.percent,
            "disk_used_mb":     round(disk.used / 1_048_576, 1),
            "disk_total_mb":    round(disk.total / 1_048_576, 1),
            "disk_pct":         disk.percent,
        }
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# 5.  FLASK-ПРИЛОЖЕНИЕ  (маршруты)
# ─────────────────────────────────────────────────────────────────────────────

def create_app(bot_mgr: BotManager, logger: Logger) -> Flask:
    """Фабрика Flask-приложения."""

    app = Flask(__name__)

    # ── / health  ─── Koyeb тянет сюда каждые N секунд ─────────────────
    @app.route("/health", methods=["GET", "HEAD"])
    def health():
        """Основной health-check. Пока этот эндпоинт отвечает 200 — контейнер жив."""
        return jsonify({
            "status":    "healthy",
            "bot_alive": bot_mgr.is_alive,
            "uptime":    str(timedelta(seconds=int((datetime.now() - Cfg.STARTUP_TIME).total_seconds()))),
            "ts":        datetime.now().isoformat(),
        }), 200

    # ── /  ───── корень → HTML-панель ───────────────────────────────────
    @app.route("/", methods=["GET"])
    def index():
        """Встроенная HTML-панель мониторинга."""
        return Response(_render_dashboard(), content_type="text/html; charset=utf-8")

    # ── /api/status ────────────────────────────────────────────────────
    @app.route("/api/status", methods=["GET"])
    def api_status():
        uptime_total = int((datetime.now() - Cfg.STARTUP_TIME).total_seconds())
        data = {
            "server": {
                "status":      "running",
                "uptime_sec":  uptime_total,
                "uptime_fmt":  str(timedelta(seconds=uptime_total)),
                "port":        Cfg.PORT,
                "hostname":    socket.gethostname(),
                "pid":         os.getpid(),
                "python":      sys.version,
            },
            "bot": {
                "alive":          bot_mgr.is_alive,
                "pid":            bot_mgr.pid,
                "uptime_sec":     bot_mgr.uptime_seconds,
                "total_crashes":  bot_mgr.total_crashes,
                "total_restarts": bot_mgr.total_restarts,
                "last_crash":     bot_mgr.last_crash_reason or "—",
            },
            "system": _sys_metrics(),
        }
        return jsonify(data), 200

    # ── /api/bot/restart  ──────────────────────────────────────────────
    @app.route("/api/bot/restart", methods=["POST"])
    def api_bot_restart():
        logger.info("Ручной перезапуск бота запрошен через API", "API")
        bot_mgr.stop_bot()
        time.sleep(1)
        ok = bot_mgr.start_bot()
        return jsonify({"restarted": ok}), 200 if ok else 500

    # ── /api/bot/output  ───────────────────────────────────────────────
    @app.route("/api/bot/output", methods=["GET"])
    def api_bot_output():
        lines = list(bot_mgr.output_buffer)
        return jsonify({"lines": lines, "count": len(lines)}), 200

    # ── /metrics  ──────────────────────────────────────────────────────
    @app.route("/metrics", methods=["GET"])
    def metrics():
        return jsonify(_sys_metrics()), 200

    return app


# ─────────────────────────────────────────────────────────────────────────────
# 6.  HTML-ПАНЕЛЬ  (встроенная, без внешних зависимостей)
# ─────────────────────────────────────────────────────────────────────────────

def _render_dashboard() -> str:
    """
    Возвращает полный HTML документ — тёмная панель мониторинга.
    Всё встроено в одну строку: CSS + HTML + JS.
    Автоновление каждые 4 секунды через fetch(/api/status).
    """
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>⚡ Koyeb Bot Monitor</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700&family=Syne:wght@700;800&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg-base:      #0a0c0f;
    --bg-card:      #12151a;
    --bg-card2:     #1a1f2e;
    --border:       rgba(255,255,255,0.06);
    --accent:       #00e5a0;
    --accent-dim:   rgba(0,229,160,0.15);
    --accent2:      #00b4d8;
    --accent2-dim:  rgba(0,180,216,0.12);
    --red:          #ff4d6a;
    --red-dim:      rgba(255,77,106,0.15);
    --yellow:       #f5c542;
    --yellow-dim:   rgba(245,197,66,0.12);
    --text:         #c8d0dd;
    --text-dim:     #5a6478;
    --text-bright:  #eef0f4;
    --radius:       12px;
    --shadow:       0 4px 24px rgba(0,0,0,0.4);
  }

  body {
    font-family: 'JetBrains Mono', monospace;
    background: var(--bg-base);
    color: var(--text);
    min-height: 100vh;
    padding: 32px 24px;
    font-size: 13px;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }

  /* ── header ──────────────────────────────────────────────────────── */
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 32px;
    flex-wrap: wrap;
    gap: 12px;
  }
  .header-left { display: flex; align-items: center; gap: 14px; }
  .logo {
    font-family: 'Syne', sans-serif;
    font-size: 22px;
    font-weight: 800;
    color: var(--text-bright);
    letter-spacing: -0.5px;
  }
  .logo span { color: var(--accent); }
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: var(--accent);
    background: var(--accent-dim);
    border: 1px solid var(--accent);
    border-radius: 20px;
    padding: 4px 10px;
    font-weight: 500;
  }
  .badge .dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: var(--accent);
    animation: pulse-dot 2s infinite;
  }
  @keyframes pulse-dot {
    0%, 100% { opacity: 1; }
    50%      { opacity: 0.4; }
  }
  .header-right { font-size: 11px; color: var(--text-dim); }

  /* ── grid ────────────────────────────────────────────────────────── */
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
  }

  /* ── card ────────────────────────────────────────────────────────── */
  .card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    box-shadow: var(--shadow);
    position: relative;
    overflow: hidden;
    transition: border-color 0.3s;
  }
  .card:hover { border-color: rgba(255,255,255,0.12); }
  .card::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, transparent 60%, rgba(255,255,255,0.015));
    pointer-events: none;
  }

  .card-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1.4px;
    color: var(--text-dim);
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .card-label .icon { font-size: 13px; }
  .card-value {
    font-family: 'Syne', sans-serif;
    font-size: 28px;
    font-weight: 800;
    color: var(--text-bright);
    letter-spacing: -1px;
  }
  .card-value.small { font-size: 18px; }
  .card-sub {
    font-size: 11px;
    color: var(--text-dim);
    margin-top: 6px;
  }

  /* цвета карт */
  .card--green .card-value { color: var(--accent); }
  .card--blue  .card-value { color: var(--accent2); }
  .card--red   .card-value { color: var(--red); }
  .card--yellow .card-value { color: var(--yellow); }

  /* accent-stripe сверху карты */
  .card--green::after { content:''; position:absolute; top:0; left:0; right:0; height:2px; background: var(--accent); border-radius: var(--radius) var(--radius) 0 0; }
  .card--blue::after  { content:''; position:absolute; top:0; left:0; right:0; height:2px; background: var(--accent2); border-radius: var(--radius) var(--radius) 0 0; }
  .card--red::after   { content:''; position:absolute; top:0; left:0; right:0; height:2px; background: var(--red); border-radius: var(--radius) var(--radius) 0 0; }
  .card--yellow::after{ content:''; position:absolute; top:0; left:0; right:0; height:2px; background: var(--yellow); border-radius: var(--radius) var(--radius) 0 0; }

  /* ── bar ─────────────────────────────────────────────────────────── */
  .bar-wrap {
    background: var(--bg-card2);
    border-radius: 6px;
    height: 6px;
    margin-top: 12px;
    overflow: hidden;
  }
  .bar-fill {
    height: 100%;
    border-radius: 6px;
    transition: width 0.6s ease;
  }
  .bar-fill--green  { background: var(--accent); }
  .bar-fill--blue   { background: var(--accent2); }
  .bar-fill--yellow { background: var(--yellow); }
  .bar-fill--red    { background: var(--red); }

  /* ── big-card (бот + вывод) ──────────────────────────────────────── */
  .big-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    overflow: hidden;
  }
  .big-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-card2);
  }
  .big-card-header h3 {
    font-family: 'Syne', sans-serif;
    font-size: 14px;
    font-weight: 700;
    color: var(--text-bright);
    display: flex; align-items: center; gap: 8px;
  }
  .btn-restart {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 500;
    background: var(--accent-dim);
    color: var(--accent);
    border: 1px solid var(--accent);
    border-radius: 6px;
    padding: 5px 14px;
    cursor: pointer;
    transition: background 0.2s, transform 0.1s;
  }
  .btn-restart:hover { background: rgba(0,229,160,0.28); }
  .btn-restart:active { transform: scale(0.95); }

  /* ── bot stats row ──────────────────────────────────────────────── */
  .bot-stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 12px;
    padding: 16px 20px;
    border-bottom: 1px solid var(--border);
  }
  .bot-stat { text-align: center; }
  .bot-stat .val {
    font-family: 'Syne', sans-serif;
    font-size: 18px;
    font-weight: 700;
    color: var(--accent);
  }
  .bot-stat .val--red { color: var(--red); }
  .bot-stat .lbl {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-dim);
    margin-top: 3px;
  }

  /* ── log viewer ──────────────────────────────────────────────────── */
  .log-viewer {
    padding: 16px 20px;
    max-height: 280px;
    overflow-y: auto;
    font-size: 11px;
  }
  .log-viewer::-webkit-scrollbar { width: 4px; }
  .log-viewer::-webkit-scrollbar-track { background: transparent; }
  .log-viewer::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  .log-line {
    display: flex;
    gap: 10px;
    padding: 2.5px 0;
    border-bottom: 1px solid rgba(255,255,255,0.025);
  }
  .log-line:last-child { border-bottom: none; }
  .log-time { color: var(--text-dim); min-width: 68px; flex-shrink: 0; }
  .log-src {
    min-width: 46px;
    text-align: center;
    font-weight: 700;
    font-size: 9px;
    letter-spacing: 0.5px;
    border-radius: 3px;
    padding: 1px 4px;
  }
  .log-src--stdout { color: var(--accent); background: var(--accent-dim); }
  .log-src--stderr { color: var(--red);    background: var(--red-dim);    }
  .log-msg { color: var(--text); flex: 1; word-break: break-all; }

  .log-empty { color: var(--text-dim); font-style: italic; padding: 20px 0; text-align: center; }

  /* ── footer ──────────────────────────────────────────────────────── */
  .footer {
    margin-top: 28px;
    text-align: center;
    font-size: 10px;
    color: var(--text-dim);
    letter-spacing: 0.5px;
  }
  .footer a { color: var(--accent2); text-decoration: none; }
  .footer a:hover { text-decoration: underline; }

  /* ── layout gap ──────────────────────────────────────────────────── */
  .section { margin-bottom: 24px; }

  /* ── skeleton shimmer ────────────────────────────────────────────── */
  @keyframes shimmer {
    0%   { background-position: -200px 0; }
    100% { background-position: calc(200px + 100%) 0; }
  }
  .shimmer {
    background: linear-gradient(90deg, var(--bg-card2) 0%, rgba(255,255,255,0.04) 50%, var(--bg-card2) 100%);
    background-size: 200px 100%;
    animation: shimmer 1.2s ease-in-out infinite;
    border-radius: 4px;
    color: transparent;
  }
</style>
</head>
<body>

<!-- ─── HEADER ─────────────────────────────────────────────────────────── -->
<div class="header">
  <div class="header-left">
    <div class="logo">⚡ <span>Koyeb</span> Monitor</div>
    <div class="badge"><div class="dot"></div> LIVE</div>
  </div>
  <div class="header-right" id="last-update">Загрузка…</div>
</div>

<!-- ─── TOP CARDS ──────────────────────────────────────────────────────── -->
<div class="section">
  <div class="grid" id="top-cards">
    <!-- js рендеринг -->
  </div>
</div>

<!-- ─── BOT PANEL ──────────────────────────────────────────────────────── -->
<div class="section">
  <div class="big-card">
    <div class="big-card-header">
      <h3><span id="bot-status-icon">🟢</span> Discord Bot</h3>
      <button class="btn-restart" onclick="restartBot()">↻ Restart</button>
    </div>
    <div class="bot-stats" id="bot-stats">
      <!-- js -->
    </div>
    <div class="log-viewer" id="log-viewer">
      <div class="log-empty">Ожидание вывода…</div>
    </div>
  </div>
</div>

<!-- ─── FOOTER ─────────────────────────────────────────────────────────── -->
<div class="footer">
  Koyeb Web Server &middot; <a href="/health">health</a> &middot;
  <a href="/api/status">api/status</a> &middot;
  <a href="/metrics">metrics</a>
</div>

<!-- ─── JAVASCRIPT ─────────────────────────────────────────────────────── -->
<script>
(function(){
  "use strict";

  const $ = (id) => document.getElementById(id);

  // ── fetch helpers ──────────────────────────────────────────────────
  async function fetchJSON(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(r.statusText);
    return r.json();
  }

  // ── render top cards ─────────────────────────────────────────────
  function renderCards(data) {
    const s = data.server || {};
    const b = data.bot    || {};
    const m = data.system || {};

    const cards = [
      {
        cls: "card--green", icon: "🟢", label: "Bot Status",
        value: b.alive ? "ONLINE" : "OFFLINE",
        sub: b.alive ? `PID ${b.pid}` : (b.last_crash || "не запущен"),
      },
      {
        cls: "card--blue", icon: "⏱️", label: "Server Uptime",
        value: s.uptime_fmt || "—",
        sub: `Port ${s.port || "?"}`,
      },
      {
        cls: "card--yellow", icon: "💾", label: "RAM",
        value: `${m.ram_pct || 0}%`,
        sub: `${m.ram_used_mb || 0} / ${m.ram_total_mb || 0} MB`,
        bar: m.ram_pct, barCls: m.ram_pct > 80 ? "bar-fill--red" : "bar-fill--yellow",
      },
      {
        cls: "card--blue", icon: "⚡", label: "CPU",
        value: `${m.cpu_pct || 0}%`,
        sub: "utilisation",
        bar: m.cpu_pct, barCls: m.cpu_pct > 75 ? "bar-fill--red" : "bar-fill--blue",
      },
      {
        cls: b.total_crashes > 0 ? "card--red" : "card--green",
        icon: "💥", label: "Crashes",
        value: String(b.total_crashes || 0),
        sub: `${b.total_restarts || 0} auto-restarts`,
      },
      {
        cls: "card--blue", icon: "💿", label: "Disk",
        value: `${m.disk_pct || 0}%`,
        sub: `${m.disk_used_mb || 0} / ${m.disk_total_mb || 0} MB`,
        bar: m.disk_pct, barCls: m.disk_pct > 85 ? "bar-fill--red" : "bar-fill--green",
      },
    ];

    $("top-cards").innerHTML = cards.map(c => `
      <div class="card ${c.cls}">
        <div class="card-label"><span class="icon">${c.icon}</span>${c.label}</div>
        <div class="card-value ${c.value.length > 12 ? 'small' : ''}">${c.value}</div>
        <div class="card-sub">${c.sub}</div>
        ${c.bar != null ? `<div class="bar-wrap"><div class="bar-fill ${c.barCls}" style="width:${Math.min(c.bar,100)}%"></div></div>` : ''}
      </div>
    `).join("");
  }

  // ── render bot stats ─────────────────────────────────────────────
  function renderBotStats(b) {
    const uptimeFmt = (sec) => {
      const h = Math.floor(sec / 3600);
      const m = Math.floor((sec % 3600) / 60);
      const s = sec % 60;
      return [h,m,s].map(v => String(v).padStart(2,"0")).join(":");
    };

    $("bot-status-icon").textContent = b.alive ? "🟢" : "🔴";

    $("bot-stats").innerHTML = `
      <div class="bot-stat"><div class="val ${b.alive ? '' : 'val--red'}">${b.alive ? 'UP' : 'DOWN'}</div><div class="lbl">Status</div></div>
      <div class="bot-stat"><div class="val">${b.pid || '—'}</div><div class="lbl">PID</div></div>
      <div class="bot-stat"><div class="val">${uptimeFmt(b.uptime_sec || 0)}</div><div class="lbl">Uptime</div></div>
      <div class="bot-stat"><div class="val val--red">${b.total_crashes || 0}</div><div class="lbl">Crashes</div></div>
      <div class="bot-stat"><div class="val">${b.total_restarts || 0}</div><div class="lbl">Restarts</div></div>
    `;
  }

  // ── render log lines ─────────────────────────────────────────────
  let lastLogCount = 0;
  function renderLogs(lines) {
    if (lines.length === lastLogCount) return;   // ничего нового
    lastLogCount = lines.length;

    if (!lines.length) {
      $("log-viewer").innerHTML = '<div class="log-empty">Вывода пока нет…</div>';
      return;
    }
    // берём последние 80 строк
    const slice = lines.slice(-80);
    $("log-viewer").innerHTML = slice.map(l => `
      <div class="log-line">
        <span class="log-time">${l.time || ''}</span>
        <span class="log-src log-src--${(l.src||'').toLowerCase()}">${l.src || ''}</span>
        <span class="log-msg">${escHtml(l.msg || '')}</span>
      </div>
    `).join("");

    // auto-scroll вниз
    const v = $("log-viewer");
    v.scrollTop = v.scrollHeight;
  }

  function escHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  // ── main poll ────────────────────────────────────────────────────
  async function poll() {
    try {
      const data = await fetchJSON("/api/status");
      renderCards(data);
      renderBotStats(data.bot || {});

      const outData = await fetchJSON("/api/bot/output");
      renderLogs(outData.lines || []);

      $("last-update").textContent = "Updated " + new Date().toLocaleTimeString();
    } catch (e) {
      $("last-update").textContent = "⚠ fetch error";
    }
  }

  // ── restart ──────────────────────────────────────────────────────
  window.restartBot = async function() {
    if (!confirm("Перезапустить бот?")) return;
    try {
      await fetch("/api/bot/restart", { method: "POST" });
      lastLogCount = 0;   // сброс кэша логов
    } catch(e) { /* ignore */ }
  };

  // старт: сразу + каждые 4 секунды
  poll();
  setInterval(poll, 4000);
})();
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# 7.  ТОЧКА ВХОДА
# ─────────────────────────────────────────────────────────────────────────────

def main():
    log = Logger(min_level=os.getenv("LOG_LEVEL", "INFO"))

    # ── баннер ───────────────────────────────────────────────────────
    log.info("=" * 68)
    log.success("🌐  KOYEB WEB SERVER  —  стартуем")
    log.info("=" * 68)
    log.info(f"PORT          = {Cfg.PORT}")
    log.info(f"BOT_FILE      = {Cfg.BOT_FILE}")
    log.info(f"AUTO_RESTART  = {Cfg.AUTO_RESTART}")
    log.info(f"CRASH_LIMIT   = {Cfg.MAX_CRASHES_WINDOW} за {Cfg.CRASH_WINDOW_SEC}с")
    log.info("=" * 68)

    # ── менеджер бота ────────────────────────────────────────────────
    bot = BotManager(log)

    # ── грейфул-шатдаун ──────────────────────────────────────────────
    def _shutdown(sig, _frame):
        log.warn(f"Получен сигнал {sig} — останавливаемся…")
        bot.stop_bot()
        log.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT,  _shutdown)

    # ── запускаем бота ───────────────────────────────────────────────
    bot.start_bot()

    # ── создаём Flask-приложение ─────────────────────────────────────
    app = create_app(bot, log)

    # ── запускаем Flask ──────────────────────────────────────────────
    log.success(f"Flask слушает на 0.0.0.0:{Cfg.PORT}")
    log.info("Health-check доступен: http://0.0.0.0:{}/health".format(Cfg.PORT))

    # use_reloader=False — иначе процесс дублируется в контейнере
    app.run(
        host="0.0.0.0",
        port=Cfg.PORT,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


if __name__ == "__main__":
    main()
