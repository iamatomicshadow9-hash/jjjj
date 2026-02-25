"""
🚀 KOYEB PRODUCTION LAUNCHER - МАКСИМАЛЬНАЯ ВЕРСИЯ
Профессиональный запускатель для облачного хостинга с полным мониторингом
"""

import subprocess
import sys
import time
import signal
import os
import threading
import socket
import json
import traceback
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple
from pathlib import Path
from collections import deque
import asyncio
import aiohttp
from enum import Enum

# ═══════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ ДЛЯ KOYEB
# ═══════════════════════════════════════════════════════════════════════════

class KoyebConfig:
    """Специальная конфигурация для Koyeb облака"""
    
    # Основные файлы
    WEB_FILE = "web.py"
    BOT_FILE = "main.py"
    
    # Порты (Koyeb автоматически пробрасывает PORT)
    WEB_PORT = int(os.getenv("PORT", "14828"))
    HEALTH_CHECK_PORT = WEB_PORT  # Используем тот же порт для health check
    
    # Настройки для облака
    CLOUD_PLATFORM = "KOYEB"
    STARTUP_TIMEOUT = 60  # Таймаут запуска (секунды)
    SHUTDOWN_TIMEOUT = 30  # Таймаут остановки (секунды)
    
    # Автоперезапуск
    AUTO_RESTART = True
    RESTART_DELAY = 10  # Увеличенная задержка для облака
    MAX_RESTART_ATTEMPTS = 10  # Больше попыток для продакшена
    RESTART_WINDOW = 300  # Окно для подсчета перезапусков (5 минут)
    
    # Health checks (для Koyeb)
    HEALTH_CHECK_ENABLED = True
    HEALTH_CHECK_INTERVAL = 30  # Проверка каждые 30 секунд
    HEALTH_CHECK_TIMEOUT = 5
    HEALTH_CHECK_PATH = "/health"
    
    # Логирование
    LOG_TO_FILE = True
    LOG_DIR = "logs"
    LOG_ROTATION_SIZE = 10 * 1024 * 1024  # 10MB
    LOG_RETENTION_DAYS = 7
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # Метрики и мониторинг
    METRICS_ENABLED = True
    METRICS_INTERVAL = 60  # Собирать метрики каждую минуту
    SAVE_METRICS_TO_FILE = True
    
    # Graceful shutdown
    GRACEFUL_SHUTDOWN = True
    SIGNAL_HANDLERS_ENABLED = True
    
    # Переменные окружения для процессов
    ENV_VARS = {
        "PYTHONUNBUFFERED": "1",  # Отключаем буферизацию для логов
        "PORT": str(WEB_PORT),
    }
    
    # Цвета (ANSI коды работают в большинстве облачных логов)
    COLORS = {
        'RED': '\033[91m',
        'GREEN': '\033[92m',
        'YELLOW': '\033[93m',
        'BLUE': '\033[94m',
        'MAGENTA': '\033[95m',
        'CYAN': '\033[96m',
        'WHITE': '\033[97m',
        'RESET': '\033[0m',
        'BOLD': '\033[1m',
        'DIM': '\033[2m'
    }

class ProcessState(Enum):
    """Состояния процесса"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    CRASHED = "crashed"
    RESTARTING = "restarting"

# ═══════════════════════════════════════════════════════════════════════════
# СИСТЕМА МЕТРИК
# ═══════════════════════════════════════════════════════════════════════════

class MetricsCollector:
    """Сбор и хранение метрик для мониторинга"""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.metrics = {
            "uptime": 0,
            "total_restarts": 0,
            "process_restarts": {},
            "health_checks": {"passed": 0, "failed": 0},
            "memory_usage": deque(maxlen=60),  # Последний час (по минутам)
            "cpu_usage": deque(maxlen=60),
            "last_errors": deque(maxlen=10)
        }
        self.lock = threading.Lock()
    
    def record_restart(self, process_name: str):
        """Записать перезапуск процесса"""
        with self.lock:
            self.metrics["total_restarts"] += 1
            if process_name not in self.metrics["process_restarts"]:
                self.metrics["process_restarts"][process_name] = 0
            self.metrics["process_restarts"][process_name] += 1
    
    def record_health_check(self, success: bool):
        """Записать результат health check"""
        with self.lock:
            if success:
                self.metrics["health_checks"]["passed"] += 1
            else:
                self.metrics["health_checks"]["failed"] += 1
    
    def record_error(self, error: str, process_name: str = "SYSTEM"):
        """Записать ошибку"""
        with self.lock:
            self.metrics["last_errors"].append({
                "timestamp": datetime.now().isoformat(),
                "process": process_name,
                "error": error
            })
    
    def get_uptime(self) -> int:
        """Получить время работы в секундах"""
        return int((datetime.now() - self.start_time).total_seconds())
    
    def get_metrics_summary(self) -> Dict:
        """Получить сводку метрик"""
        with self.lock:
            return {
                "uptime_seconds": self.get_uptime(),
                "uptime_formatted": str(timedelta(seconds=self.get_uptime())),
                "total_restarts": self.metrics["total_restarts"],
                "process_restarts": dict(self.metrics["process_restarts"]),
                "health_checks": dict(self.metrics["health_checks"]),
                "last_errors": list(self.metrics["last_errors"])
            }
    
    def save_to_file(self, filepath: str):
        """Сохранить метрики в файл"""
        try:
            with open(filepath, 'w') as f:
                json.dump(self.get_metrics_summary(), f, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения метрик: {e}")

# ═══════════════════════════════════════════════════════════════════════════
# ПРОДВИНУТАЯ СИСТЕМА ЛОГИРОВАНИЯ
# ═══════════════════════════════════════════════════════════════════════════

class AdvancedLogger:
    """Продвинутая система логирования с ротацией и уровнями"""
    
    LOG_LEVELS = {
        "DEBUG": 10,
        "INFO": 20,
        "WARNING": 30,
        "ERROR": 40,
        "CRITICAL": 50
    }
    
    def __init__(self, log_to_file: bool = True, log_level: str = "INFO"):
        self.log_to_file = log_to_file
        self.log_level = self.LOG_LEVELS.get(log_level.upper(), 20)
        self.log_file = None
        self.log_file_path = None
        self.lock = threading.Lock()
        
        if self.log_to_file:
            self._setup_logging()
    
    def _setup_logging(self):
        """Настроить логирование в файл"""
        # Создаем директорию
        Path(KoyebConfig.LOG_DIR).mkdir(exist_ok=True)
        
        # Очищаем старые логи
        self._cleanup_old_logs()
        
        # Создаем новый файл лога
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file_path = f"{KoyebConfig.LOG_DIR}/koyeb_run_{timestamp}.log"
        self.log_file = open(self.log_file_path, 'a', encoding='utf-8')
        
        self.info(f"Логирование начато: {self.log_file_path}", "LOGGER")
    
    def _cleanup_old_logs(self):
        """Удалить старые логи"""
        try:
            log_dir = Path(KoyebConfig.LOG_DIR)
            cutoff_time = datetime.now() - timedelta(days=KoyebConfig.LOG_RETENTION_DAYS)
            
            for log_file in log_dir.glob("koyeb_run_*.log"):
                if log_file.stat().st_mtime < cutoff_time.timestamp():
                    log_file.unlink()
                    print(f"Удален старый лог: {log_file}")
        except Exception as e:
            print(f"Ошибка очистки логов: {e}")
    
    def _check_rotation(self):
        """Проверить необходимость ротации лога"""
        if not self.log_file or not self.log_file_path:
            return
        
        try:
            size = os.path.getsize(self.log_file_path)
            if size >= KoyebConfig.LOG_ROTATION_SIZE:
                # Ротация лога
                self.log_file.close()
                
                # Переименовываем старый файл
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                old_path = self.log_file_path
                new_path = f"{self.log_file_path}.{timestamp}.old"
                os.rename(old_path, new_path)
                
                # Создаем новый файл
                self.log_file = open(self.log_file_path, 'a', encoding='utf-8')
                self.info(f"Ротация лога выполнена: {new_path}", "LOGGER")
        except Exception as e:
            print(f"Ошибка ротации: {e}")
    
    def _colorize(self, text: str, color: str) -> str:
        """Добавить цвет к тексту"""
        return f"{KoyebConfig.COLORS.get(color, '')}{text}{KoyebConfig.COLORS['RESET']}"
    
    def _get_timestamp(self) -> str:
        """Получить timestamp"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    def _log(self, message: str, level: str, source: str):
        """Внутренний метод логирования"""
        level_value = self.LOG_LEVELS.get(level, 20)
        if level_value < self.log_level:
            return  # Пропускаем сообщения ниже текущего уровня
        
        with self.lock:
            timestamp = self._get_timestamp()
            
            # Цвета для уровней
            level_colors = {
                "DEBUG": "DIM",
                "INFO": "CYAN",
                "SUCCESS": "GREEN",
                "WARNING": "YELLOW",
                "ERROR": "RED",
                "CRITICAL": "MAGENTA"
            }
            
            # Форматируем для консоли
            color = level_colors.get(level, "WHITE")
            level_colored = self._colorize(f"{level:8}", color)
            source_colored = self._colorize(f"[{source:12}]", "BLUE")
            console_msg = f"[{timestamp}] {level_colored} {source_colored} {message}"
            
            # Выводим в консоль
            print(console_msg, flush=True)
            
            # Записываем в файл (без цветов)
            if self.log_file:
                plain_msg = f"[{timestamp}] [{level:8}] [{source:12}] {message}\n"
                self.log_file.write(plain_msg)
                self.log_file.flush()
                
                # Проверяем ротацию
                self._check_rotation()
    
    def debug(self, message: str, source: str = "MAIN"):
        self._log(message, "DEBUG", source)
    
    def info(self, message: str, source: str = "MAIN"):
        self._log(message, "INFO", source)
    
    def success(self, message: str, source: str = "MAIN"):
        self._log(message, "SUCCESS", source)
    
    def warning(self, message: str, source: str = "MAIN"):
        self._log(message, "WARNING", source)
    
    def error(self, message: str, source: str = "MAIN"):
        self._log(message, "ERROR", source)
    
    def critical(self, message: str, source: str = "MAIN"):
        self._log(message, "CRITICAL", source)
    
    def close(self):
        """Закрыть файл лога"""
        if self.log_file:
            self.log_file.close()

# ═══════════════════════════════════════════════════════════════════════════
# HEALTH CHECK СЕРВЕР
# ═══════════════════════════════════════════════════════════════════════════

class HealthCheckServer:
    """HTTP сервер для health checks от Koyeb"""
    
    def __init__(self, logger: AdvancedLogger, metrics: MetricsCollector):
        self.logger = logger
        self.metrics = metrics
        self.running = False
        self.server_thread = None
    
    async def handle_health(self, request):
        """Обработчик health check запросов"""
        from aiohttp import web
        try:
            # Проверяем статус
            health_status = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "uptime": self.metrics.get_uptime(),
                "metrics": self.metrics.get_metrics_summary()
            }
            
            self.metrics.record_health_check(True)
            
            return web.json_response(health_status, status=200)
        
        except Exception as e:
            self.logger.error(f"Health check failed: {e}", "HEALTH")
            self.metrics.record_health_check(False)
            return web.json_response(
                {"status": "unhealthy", "error": str(e)},
                status=503
            )
    
    async def handle_metrics(self, request):
        """Обработчик запросов метрик"""
        from aiohttp import web
        return web.json_response(self.metrics.get_metrics_summary())
    
    async def handle_root(self, request):
        """Обработчик корневого пути"""
        from aiohttp import web
        return web.Response(
            text="Koyeb Application Running ✅",
            content_type="text/plain"
        )
    
    async def start_server(self):
        """Запустить HTTP сервер"""
        from aiohttp import web
        app = web.Application()
        app.router.add_get('/', self.handle_root)
        app.router.add_get('/health', self.handle_health)
        app.router.add_get('/metrics', self.handle_metrics)
        
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(
            runner,
            '0.0.0.0',
            KoyebConfig.HEALTH_CHECK_PORT
        )
        
        await site.start()
        self.logger.success(
            f"Health check server started on port {KoyebConfig.HEALTH_CHECK_PORT}",
            "HEALTH"
        )
        
        # Держим сервер запущенным
        while self.running:
            await asyncio.sleep(1)
    
    def start(self):
        """Запустить health check сервер в отдельном потоке"""
        if not KoyebConfig.HEALTH_CHECK_ENABLED:
            return
        
        self.running = True
        
        def run_server():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.start_server())
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        
        self.logger.info("Health check сервер запускается...", "HEALTH")
    
    def stop(self):
        """Остановить health check сервер"""
        self.running = False
        if self.server_thread:
            self.server_thread.join(timeout=5)

# ═══════════════════════════════════════════════════════════════════════════
# ПРОДВИНУТЫЙ МЕНЕДЖЕР ПРОЦЕССОВ
# ═══════════════════════════════════════════════════════════════════════════

class ProcessInfo:
    """Информация о процессе"""
    
    def __init__(self, name: str, filepath: str):
        self.name = name
        self.filepath = filepath
        self.process: Optional[subprocess.Popen] = None
        self.state = ProcessState.STOPPED
        self.pid: Optional[int] = None
        self.start_time: Optional[datetime] = None
        self.restart_history: deque = deque(maxlen=20)
        self.crash_count = 0
        self.last_output: deque = deque(maxlen=50)
    
    def is_running(self) -> bool:
        """Проверить, запущен ли процесс"""
        return self.process is not None and self.process.poll() is None
    
    def get_uptime(self) -> Optional[int]:
        """Получить время работы процесса"""
        if self.start_time and self.is_running():
            return int((datetime.now() - self.start_time).total_seconds())
        return None
    
    def record_restart(self):
        """Записать перезапуск"""
        self.restart_history.append(datetime.now())
    
    def get_recent_restart_count(self, window_seconds: int = 300) -> int:
        """Получить количество перезапусков за последнее время"""
        cutoff = datetime.now() - timedelta(seconds=window_seconds)
        return sum(1 for t in self.restart_history if t > cutoff)

class KoyebProcessManager:
    """Продвинутый менеджер процессов для Koyeb"""
    
    def __init__(self, logger: AdvancedLogger, metrics: MetricsCollector):
        self.logger = logger
        self.metrics = metrics
        self.processes: Dict[str, ProcessInfo] = {}
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.output_threads: List[threading.Thread] = []
    
    def register_process(self, name: str, filepath: str):
        """Зарегистрировать процесс"""
        self.processes[name] = ProcessInfo(name, filepath)
        self.logger.debug(f"Процесс зарегистрирован: {filepath}", name)
    
    def _prepare_environment(self) -> Dict[str, str]:
        """Подготовить переменные окружения"""
        env = os.environ.copy()
        env.update(KoyebConfig.ENV_VARS)
        return env
    
    def start_process(self, name: str) -> bool:
        """Запустить процесс"""
        if name not in self.processes:
            self.logger.error(f"Процесс не зарегистрирован", name)
            return False
        
        proc_info = self.processes[name]
        
        # Проверяем, не запущен ли уже
        if proc_info.is_running():
            self.logger.warning(f"Процесс уже запущен", name)
            return True
        
        # Проверяем существование файла
        if not os.path.exists(proc_info.filepath):
            self.logger.error(f"Файл не найден: {proc_info.filepath}", name)
            return False
        
        try:
            proc_info.state = ProcessState.STARTING
            self.logger.info(f"Запуск процесса: {proc_info.filepath}", name)
            
            # Подготавливаем окружение
            env = self._prepare_environment()
            
            # Запускаем процесс
            process = subprocess.Popen(
                [sys.executable, "-u", proc_info.filepath],  # -u для unbuffered
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env
            )
            
            proc_info.process = process
            proc_info.pid = process.pid
            proc_info.start_time = datetime.now()
            proc_info.state = ProcessState.RUNNING
            
            self.logger.success(f"Процесс запущен (PID: {process.pid})", name)
            
            # Запускаем мониторинг вывода
            self._start_output_monitoring(name, proc_info)
            
            return True
        
        except Exception as e:
            proc_info.state = ProcessState.CRASHED
            self.logger.error(f"Ошибка запуска: {e}", name)
            self.logger.debug(traceback.format_exc(), name)
            self.metrics.record_error(str(e), name)
            return False
    
    def _start_output_monitoring(self, name: str, proc_info: ProcessInfo):
        """Запустить мониторинг вывода процесса"""
        
        def monitor_stream(stream, is_error: bool):
            stream_name = "STDERR" if is_error else "STDOUT"
            try:
                for line in stream:
                    if line.strip():
                        # Сохраняем в историю
                        proc_info.last_output.append({
                            "timestamp": datetime.now(),
                            "stream": stream_name,
                            "line": line.strip()
                        })
                        
                        # Логируем
                        if is_error:
                            self.logger.error(line.strip(), name)
                        else:
                            self.logger.info(line.strip(), name)
            except Exception as e:
                self.logger.error(f"Ошибка мониторинга {stream_name}: {e}", name)
        
        # Создаем потоки для STDOUT и STDERR
        stdout_thread = threading.Thread(
            target=monitor_stream,
            args=(proc_info.process.stdout, False),
            daemon=True
        )
        stderr_thread = threading.Thread(
            target=monitor_stream,
            args=(proc_info.process.stderr, True),
            daemon=True
        )
        
        stdout_thread.start()
        stderr_thread.start()
        
        self.output_threads.extend([stdout_thread, stderr_thread])
    
    def stop_process(self, name: str, timeout: int = KoyebConfig.SHUTDOWN_TIMEOUT) -> bool:
        """Остановить процесс с graceful shutdown"""
        if name not in self.processes:
            return False
        
        proc_info = self.processes[name]
        
        if not proc_info.is_running():
            self.logger.debug(f"Процесс уже остановлен", name)
            return True
        
        try:
            proc_info.state = ProcessState.STOPPING
            self.logger.warning(f"Остановка процесса (PID: {proc_info.pid})...", name)
            
            # Пытаемся graceful shutdown
            proc_info.process.terminate()
            
            try:
                proc_info.process.wait(timeout=timeout)
                self.logger.success(f"Процесс остановлен корректно", name)
                proc_info.state = ProcessState.STOPPED
                return True
            
            except subprocess.TimeoutExpired:
                # Принудительная остановка
                self.logger.warning(f"Таймаут! Принудительная остановка...", name)
                proc_info.process.kill()
                proc_info.process.wait(timeout=5)
                self.logger.success(f"Процесс убит принудительно", name)
                proc_info.state = ProcessState.STOPPED
                return True
        
        except Exception as e:
            self.logger.error(f"Ошибка остановки: {e}", name)
            proc_info.state = ProcessState.CRASHED
            return False
    
    def restart_process(self, name: str) -> bool:
        """Перезапустить процесс"""
        if name not in self.processes:
            return False
        
        proc_info = self.processes[name]
        
        # Проверяем частоту перезапусков
        recent_restarts = proc_info.get_recent_restart_count(
            KoyebConfig.RESTART_WINDOW
        )
        
        if recent_restarts >= KoyebConfig.MAX_RESTART_ATTEMPTS:
            self.logger.critical(
                f"Слишком много перезапусков ({recent_restarts}) за последние "
                f"{KoyebConfig.RESTART_WINDOW}с! Остановка автоперезапуска.",
                name
            )
            proc_info.state = ProcessState.CRASHED
            return False
        
        proc_info.state = ProcessState.RESTARTING
        self.logger.warning(f"Перезапуск процесса...", name)
        
        # Останавливаем
        self.stop_process(name)
        
        # Задержка
        time.sleep(KoyebConfig.RESTART_DELAY)
        
        # Записываем перезапуск
        proc_info.record_restart()
        self.metrics.record_restart(name)
        
        # Запускаем
        return self.start_process(name)
    
    def get_process_status(self, name: str) -> Dict:
        """Получить статус процесса"""
        if name not in self.processes:
            return {"error": "Process not found"}
        
        proc_info = self.processes[name]
        
        return {
            "name": name,
            "filepath": proc_info.filepath,
            "state": proc_info.state.value,
            "pid": proc_info.pid,
            "running": proc_info.is_running(),
            "uptime": proc_info.get_uptime(),
            "crash_count": proc_info.crash_count,
            "recent_restarts": proc_info.get_recent_restart_count(),
            "last_output_lines": len(proc_info.last_output)
        }
    
    def monitor_processes(self):
        """Мониторить процессы и перезапускать при необходимости"""
        self.running = True
        self.logger.info("Мониторинг процессов запущен", "MONITOR")
        
        while self.running:
            try:
                for name, proc_info in self.processes.items():
                    # Проверяем, не упал ли процесс
                    if proc_info.state == ProcessState.RUNNING and not proc_info.is_running():
                        self.logger.error(f"Процесс упал!", name)
                        proc_info.crash_count += 1
                        proc_info.state = ProcessState.CRASHED
                        
                        if KoyebConfig.AUTO_RESTART:
                            self.restart_process(name)
                
                time.sleep(5)  # Проверяем каждые 5 секунд
            
            except Exception as e:
                self.logger.error(f"Ошибка мониторинга: {e}", "MONITOR")
                time.sleep(5)
        
        self.logger.info("Мониторинг процессов остановлен", "MONITOR")
    
    def start_monitoring(self):
        """Запустить мониторинг в отдельном потоке"""
        self.monitor_thread = threading.Thread(
            target=self.monitor_processes,
            daemon=True
        )
        self.monitor_thread.start()
    
    def stop_all(self):
        """Остановить все процессы"""
        self.logger.info("Остановка всех процессов...", "MANAGER")
        self.running = False
        
        for name in list(self.processes.keys()):
            self.stop_process(name)
        
        self.logger.success("Все процессы остановлены", "MANAGER")

# ═══════════════════════════════════════════════════════════════════════════
# ГЛАВНЫЙ ЛОНЧЕР ДЛЯ KOYEB
# ═══════════════════════════════════════════════════════════════════════════

class KoyebApplicationLauncher:
    """Главный класс запуска приложения на Koyeb"""
    
    def __init__(self):
        # Инициализация компонентов
        self.logger = AdvancedLogger(
            log_to_file=KoyebConfig.LOG_TO_FILE,
            log_level=KoyebConfig.LOG_LEVEL
        )
        self.metrics = MetricsCollector()
        self.process_manager = KoyebProcessManager(self.logger, self.metrics)
        self.health_server = HealthCheckServer(self.logger, self.metrics)
        
        # Флаги состояния
        self.running = False
        self.shutdown_requested = False
        
        # Потоки
        self.metrics_thread: Optional[threading.Thread] = None
    
    def print_banner(self):
        """Красивый баннер запуска"""
        # Подготовка значений
        platform = KoyebConfig.CLOUD_PLATFORM.ljust(58)
        web_file = KoyebConfig.WEB_FILE.ljust(54)
        bot_file = KoyebConfig.BOT_FILE.ljust(53)
        port = str(KoyebConfig.WEB_PORT).ljust(60)
        auto_restart = ('✅ ENABLED' if KoyebConfig.AUTO_RESTART else '❌ DISABLED').ljust(54)
        health_checks = ('✅ ENABLED' if KoyebConfig.HEALTH_CHECK_ENABLED else '❌ DISABLED').ljust(53)
        metrics = ('✅ ENABLED' if KoyebConfig.METRICS_ENABLED else '❌ DISABLED').ljust(57)
        log_level = KoyebConfig.LOG_LEVEL.ljust(55)
        
        banner = f"""
{KoyebConfig.COLORS['CYAN']}{KoyebConfig.COLORS['BOLD']}
╔══════════════════════════════════════════════════════════════════════╗
║                                                                      ║
║              🚀 KOYEB PRODUCTION LAUNCHER v2.0 🚀                    ║
║                                                                      ║
║  Platform: {platform} ║
║  Web Server: {web_file} ║
║  Discord Bot: {bot_file} ║
║                                                                      ║
║  Port: {port} ║
║  Auto-Restart: {auto_restart} ║
║  Health Checks: {health_checks} ║
║  Metrics: {metrics} ║
║  Log Level: {log_level} ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
{KoyebConfig.COLORS['RESET']}
"""
        print(banner)
    
    def validate_environment(self) -> bool:
        """Проверить окружение перед запуском"""
        self.logger.info("Проверка окружения...", "VALIDATOR")
        
        issues = []
        
        # Проверяем файлы
        if not os.path.exists(KoyebConfig.WEB_FILE):
            issues.append(f"Файл {KoyebConfig.WEB_FILE} не найден")
        
        if not os.path.exists(KoyebConfig.BOT_FILE):
            issues.append(f"Файл {KoyebConfig.BOT_FILE} не найден")
        
        # Проверяем порт
        if not (1 <= KoyebConfig.WEB_PORT <= 65535):
            issues.append(f"Некорректный порт: {KoyebConfig.WEB_PORT}")
        
        # Проверяем Python версию
        if sys.version_info < (3, 8):
            issues.append(f"Python 3.8+ требуется, текущая версия: {sys.version}")
        
        if issues:
            self.logger.error("Обнаружены проблемы в окружении:", "VALIDATOR")
            for issue in issues:
                self.logger.error(f"  - {issue}", "VALIDATOR")
            return False
        
        self.logger.success("Окружение валидно ✅", "VALIDATOR")
        return True
    
    def start_metrics_collection(self):
        """Запустить сбор метрик"""
        if not KoyebConfig.METRICS_ENABLED:
            return
        
        def collect_metrics():
            while self.running:
                try:
                    # Сохраняем метрики в файл
                    if KoyebConfig.SAVE_METRICS_TO_FILE:
                        metrics_file = f"{KoyebConfig.LOG_DIR}/metrics.json"
                        self.metrics.save_to_file(metrics_file)
                    
                    time.sleep(KoyebConfig.METRICS_INTERVAL)
                
                except Exception as e:
                    if self.logger:
                        self.logger.error(f"Ошибка сбора метрик: {e}", "METRICS")
        
        self.metrics_thread = threading.Thread(target=collect_metrics, daemon=True)
        self.metrics_thread.start()
        self.logger.info("Сбор метрик запущен", "METRICS")
    
    def start(self):
        """Запустить приложение"""
        try:
            self.print_banner()
            
            self.logger.info("="*70)
            self.logger.success("🚀 ЗАПУСК KOYEB ПРИЛОЖЕНИЯ")
            self.logger.info("="*70)
            
            # Валидация
            if not self.validate_environment():
                self.logger.critical("Валидация не пройдена! Остановка.")
                return
            
            self.running = True
            
            # Запускаем health check сервер (ПЕРВЫМ!)
            self.health_server.start()
            time.sleep(2)  # Даем серверу запуститься
            
            # Регистрируем процессы
            self.process_manager.register_process("BOT", KoyebConfig.BOT_FILE)
            
            # Запускаем bot процесс
            bot_started = self.process_manager.start_process("BOT")
            
            if not bot_started:
                self.logger.error("Не удалось запустить bot процесс!")
                self.stop()
                return
            
            # Запускаем мониторинг
            if KoyebConfig.AUTO_RESTART:
                self.process_manager.start_monitoring()
            
            # Запускаем сбор метрик
            self.start_metrics_collection()
            
            self.logger.info("="*70)
            self.logger.success("✅ ВСЕ СИСТЕМЫ ЗАПУЩЕНЫ!")
            self.logger.info("="*70)
            self.logger.info(f"Health check: http://0.0.0.0:{KoyebConfig.WEB_PORT}/health")
            self.logger.info(f"Metrics: http://0.0.0.0:{KoyebConfig.WEB_PORT}/metrics")
            self.logger.info("="*70)
            
            # Главный цикл
            self._main_loop()
        
        except KeyboardInterrupt:
            self.logger.warning("Получен сигнал остановки (Ctrl+C)")
            self.stop()
        
        except Exception as e:
            self.logger.critical(f"Критическая ошибка: {e}")
            self.logger.debug(traceback.format_exc())
            self.stop()
    
    def _main_loop(self):
        """Главный цикл приложения"""
        status_interval = 60  # Показывать статус каждую минуту
        last_status = time.time()
        
        while self.running and not self.shutdown_requested:
            try:
                # Периодически показываем статус
                if time.time() - last_status >= status_interval:
                    self._print_status()
                    last_status = time.time()
                
                time.sleep(1)
            
            except KeyboardInterrupt:
                break
    
    def _print_status(self):
        """Вывести статус системы"""
        self.logger.info("="*70)
        self.logger.info("📊 СТАТУС СИСТЕМЫ")
        self.logger.info("="*70)
        
        # Общая информация
        metrics = self.metrics.get_metrics_summary()
        self.logger.info(f"Uptime: {metrics['uptime_formatted']}")
        self.logger.info(f"Total Restarts: {metrics['total_restarts']}")
        self.logger.info(f"Health Checks: ✅ {metrics['health_checks']['passed']} "
                        f"❌ {metrics['health_checks']['failed']}")
        
        # Статус процессов
        for name in ["WEB", "BOT"]:
            status = self.process_manager.get_process_status(name)
            state_emoji = "✅" if status.get("running") else "❌"
            uptime = status.get("uptime", 0) or 0
            self.logger.info(
                f"{name}: {state_emoji} State={status.get('state')} "
                f"PID={status.get('pid')} Uptime={uptime}s "
                f"Restarts={status.get('recent_restarts')}"
            )
        
        self.logger.info("="*70)
    
    def stop(self):
        """Остановить приложение"""
        if self.shutdown_requested:
            return
        
        self.shutdown_requested = True
        
        self.logger.info("="*70)
        self.logger.warning("🛑 ОСТАНОВКА ПРИЛОЖЕНИЯ")
        self.logger.info("="*70)
        
        # Останавливаем процессы
        self.process_manager.stop_all()
        
        # Останавливаем health check сервер
        self.health_server.stop()
        
        # Сохраняем финальные метрики
        if KoyebConfig.METRICS_ENABLED and KoyebConfig.SAVE_METRICS_TO_FILE:
            final_metrics_file = f"{KoyebConfig.LOG_DIR}/final_metrics.json"
            self.metrics.save_to_file(final_metrics_file)
            self.logger.info(f"Финальные метрики сохранены: {final_metrics_file}")
        
        # Выводим финальную статистику
        self._print_final_stats()
        
        # Закрываем логгер
        self.logger.info("="*70)
        self.logger.success("👋 ПРИЛОЖЕНИЕ ОСТАНОВЛЕНО")
        self.logger.info("="*70)
        self.logger.close()
        
        self.running = False
        sys.exit(0)
    
    def _print_final_stats(self):
        """Вывести финальную статистику"""
        self.logger.info("="*70)
        self.logger.info("📊 ФИНАЛЬНАЯ СТАТИСТИКА")
        self.logger.info("="*70)
        
        metrics = self.metrics.get_metrics_summary()
        
        self.logger.info(f"Total Uptime: {metrics['uptime_formatted']}")
        self.logger.info(f"Total Restarts: {metrics['total_restarts']}")
        
        for proc_name, count in metrics['process_restarts'].items():
            self.logger.info(f"  - {proc_name}: {count} restarts")
        
        self.logger.info(f"Health Checks: ✅ {metrics['health_checks']['passed']} "
                        f"❌ {metrics['health_checks']['failed']}")
        
        if metrics['last_errors']:
            self.logger.warning(f"Last {len(metrics['last_errors'])} errors:")
            for error in metrics['last_errors']:
                self.logger.error(
                    f"  [{error['timestamp']}] [{error['process']}] {error['error']}"
                )
        
        self.logger.info("="*70)

# ═══════════════════════════════════════════════════════════════════════════
# ТОЧКА ВХОДА
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """Главная функция"""
    launcher = KoyebApplicationLauncher()
    
    # Обработчики сигналов
    if KoyebConfig.SIGNAL_HANDLERS_ENABLED:
        def signal_handler(sig, frame):
            launcher.logger.warning(f"Получен сигнал: {sig}")
            launcher.stop()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    # Запускаем
    launcher.start()

if __name__ == "__main__":
    main()
