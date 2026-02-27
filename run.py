"""
╔══════════════════════════════════════════════════════════════════════════╗
║        KOYEB LAUNCHER  —  ИСПРАВЛЕННАЯ ВЕРСИЯ                           ║
║                                                                          ║
║  Архитектура:                                                            ║
║    run.py  →  запускает web.py                                           ║
║    web.py  →  Flask на PORT + запускает и мониторит bot.py              ║
║    bot.py  →  Discord бот                                                ║
║                                                                          ║
║  ❌ БЫЛО: run.py поднимал свой HTTP сервер на том же порту что web.py   ║
║  ✅ СТАЛО: run.py только следит за процессом web.py, HTTP — только в    ║
║            web.py (Flask). Никакого конфликта портов.                   ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import subprocess
import sys
import time
import signal
import os
import threading
from datetime import datetime, timedelta
from collections import deque


# ═══════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════

class Cfg:
    WEB_FILE        = "web.py"              # единственный процесс который мы запускаем
    PORT            = int(os.getenv("PORT", "8000"))

    AUTO_RESTART    = True
    RESTART_DELAY   = 5                     # секунд между перезапусками
    MAX_RESTARTS    = 10                    # макс перезапусков за окно
    RESTART_WINDOW  = 300                   # 5 минут

    STATUS_INTERVAL = 60                    # как часто печатать статус (секунд)


# ═══════════════════════════════════════════════════════════════════════════
# ЦВЕТА
# ═══════════════════════════════════════════════════════════════════════════

class C:
    R = "\033[0m"
    RED  = "\033[91m";  GREEN  = "\033[92m";  YELLOW = "\033[93m"
    BLUE = "\033[94m";  CYAN   = "\033[96m";  DIM    = "\033[2m"
    BOLD = "\033[1m"


# ═══════════════════════════════════════════════════════════════════════════
# ЛОГГЕР
# ═══════════════════════════════════════════════════════════════════════════

_lock = threading.Lock()

def _ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def log(level: str, msg: str, src: str = "MAIN"):
    colors = {"INFO": C.CYAN, "SUCCESS": C.GREEN, "WARN": C.YELLOW,
              "ERROR": C.RED, "CRIT": C.RED + C.BOLD}
    clr = colors.get(level, C.R)
    with _lock:
        print(f"[{_ts()}] {clr}{level:8}{C.R} {C.BLUE}[{src:^10}]{C.R} {msg}",
              flush=True)


# ═══════════════════════════════════════════════════════════════════════════
# МЕНЕДЖЕР ПРОЦЕССА web.py
# ═══════════════════════════════════════════════════════════════════════════

class WebManager:
    """
    Запускает web.py и следит за ним.
    web.py сам управляет bot.py — нам не нужно трогать бота напрямую.
    Никакого собственного HTTP сервера — Flask уже запущен внутри web.py.
    """

    def __init__(self):
        self._proc           = None
        self._lock           = threading.Lock()
        self._running        = False
        self.restart_times   = deque(maxlen=Cfg.MAX_RESTARTS + 5)
        self.total_restarts  = 0
        self.start_time      = None

    # ── запуск ───────────────────────────────────────────────────────────

    def start(self) -> bool:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                log("WARN", "web.py уже запущен", "WEB-MGR")
                return True

            if not os.path.isfile(Cfg.WEB_FILE):
                log("CRIT", f"Файл не найден: {Cfg.WEB_FILE}", "WEB-MGR")
                return False

            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["PORT"] = str(Cfg.PORT)

            try:
                self._proc = subprocess.Popen(
                    [sys.executable, "-u", Cfg.WEB_FILE],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    env=env,
                )
                self.start_time = datetime.now()
                log("SUCCESS", f"web.py запущен (PID {self._proc.pid})", "WEB-MGR")

                # читаем stdout/stderr в потоках
                threading.Thread(target=self._pipe, args=(self._proc.stdout, False), daemon=True).start()
                threading.Thread(target=self._pipe, args=(self._proc.stderr, True),  daemon=True).start()
                return True

            except Exception as e:
                log("ERROR", f"Ошибка запуска: {e}", "WEB-MGR")
                return False

    def _pipe(self, stream, is_err: bool):
        """Читает поток процесса и печатает в консоль."""
        src = "WEB"
        try:
            for line in stream:
                line = line.rstrip()
                if line:
                    # строки из web.py уже содержат свой timestamp и уровень —
                    # просто выводим как есть
                    print(line, flush=True)
        except Exception:
            pass

    # ── остановка ────────────────────────────────────────────────────────

    def stop(self, timeout: int = 15):
        with self._lock:
            if not self._proc:
                return
            if self._proc.poll() is not None:
                return

            log("WARN", f"Останавливаем web.py (PID {self._proc.pid})…", "WEB-MGR")
            self._proc.terminate()
            try:
                self._proc.wait(timeout=timeout)
                log("SUCCESS", "web.py остановлен корректно", "WEB-MGR")
            except subprocess.TimeoutExpired:
                log("WARN", "Таймаут — убиваем SIGKILL", "WEB-MGR")
                self._proc.kill()
                self._proc.wait()

    # ── перезапуск ───────────────────────────────────────────────────────

    def _can_restart(self) -> bool:
        cutoff = datetime.now() - timedelta(seconds=Cfg.RESTART_WINDOW)
        recent = sum(1 for t in self.restart_times if t > cutoff)
        if recent >= Cfg.MAX_RESTARTS:
            log("CRIT",
                f"Слишком много перезапусков ({recent}) за последние {Cfg.RESTART_WINDOW}с! "
                "Остановка автоперезапуска.", "WEB-MGR")
            return False
        return True

    def restart(self) -> bool:
        if not self._can_restart():
            return False

        log("WARN", "Перезапуск процесса…", "WEB-MGR")
        self.stop()
        time.sleep(Cfg.RESTART_DELAY)
        self.restart_times.append(datetime.now())
        self.total_restarts += 1
        return self.start()

    # ── мониторинг ───────────────────────────────────────────────────────

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def uptime(self) -> int:
        if self.start_time and self.is_alive():
            return int((datetime.now() - self.start_time).total_seconds())
        return 0

    def monitor(self, shutdown_event: threading.Event):
        """Главный цикл мониторинга — запускается в отдельном потоке."""
        log("INFO", "Мониторинг web.py запущен", "WEB-MON")
        while not shutdown_event.is_set():
            if not self.is_alive():
                log("ERROR", "Процесс упал!", "WEB-MON")
                if Cfg.AUTO_RESTART:
                    ok = self.restart()
                    if not ok:
                        log("CRIT", "Перезапуск не удался — завершение.", "WEB-MON")
                        shutdown_event.set()
                        break
                else:
                    shutdown_event.set()
                    break
            shutdown_event.wait(timeout=5)

        log("INFO", "Мониторинг остановлен", "WEB-MON")


# ═══════════════════════════════════════════════════════════════════════════
# ГЛАВНАЯ ФУНКЦИЯ
# ═══════════════════════════════════════════════════════════════════════════

def main():
    log("INFO", "=" * 70, "MAIN")
    log("INFO", "🚀  KOYEB LAUNCHER  —  стартуем", "MAIN")
    log("INFO", f"   PORT       = {Cfg.PORT}", "MAIN")
    log("INFO", f"   WEB_FILE   = {Cfg.WEB_FILE}  (управляет bot.py)", "MAIN")
    log("INFO", f"   RESTART    = {Cfg.MAX_RESTARTS} раз за {Cfg.RESTART_WINDOW}с", "MAIN")
    log("INFO", "=" * 70, "MAIN")
    log("INFO", "Примечание: HTTP сервер поднимает web.py (Flask),", "MAIN")
    log("INFO", "            run.py НЕ занимает никаких портов.", "MAIN")
    log("INFO", "=" * 70, "MAIN")

    mgr = WebManager()
    shutdown = threading.Event()

    # ── обработчики сигналов ─────────────────────────────────────────────
    def _sig(sig, _):
        log("WARN", f"Получен сигнал {sig} — завершаем…", "MAIN")
        shutdown.set()

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT,  _sig)

    # ── запуск ───────────────────────────────────────────────────────────
    if not mgr.start():
        log("CRIT", "Не удалось запустить web.py — выход.", "MAIN")
        sys.exit(1)

    # ── мониторинг в потоке ──────────────────────────────────────────────
    mon = threading.Thread(target=mgr.monitor, args=(shutdown,), daemon=True)
    mon.start()

    # ── главный цикл ─────────────────────────────────────────────────────
    last_status = time.time()
    while not shutdown.is_set():
        if time.time() - last_status >= Cfg.STATUS_INTERVAL:
            up = timedelta(seconds=mgr.uptime())
            status = "✅ running" if mgr.is_alive() else "❌ down"
            log("INFO", "=" * 70, "MAIN")
            log("INFO", f"📊 СТАТУС: web.py {status} | uptime {up} | "
                        f"перезапусков: {mgr.total_restarts}", "MAIN")
            log("INFO", "=" * 70, "MAIN")
            last_status = time.time()

        shutdown.wait(timeout=1)

    # ── завершение ───────────────────────────────────────────────────────
    log("WARN", "Завершение работы…", "MAIN")
    mgr.stop()
    log("SUCCESS", "👋 Выход.", "MAIN")


if __name__ == "__main__":
    main()
