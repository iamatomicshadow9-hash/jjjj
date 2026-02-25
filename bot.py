import os
import disnake
from disnake.ext import commands, tasks
from dotenv import load_dotenv
from guilds import setup, init_db, close_db
import logging
import asyncio
import traceback
from datetime import datetime, timedelta
import sys

# ══════════════════════════════════════════════════════════════
#   🎯  ЛОГИРОВАНИЕ И КОНФИГ
# ══════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("DiscordBot")

load_dotenv()
TOKEN = os.getenv("TOKEN")

# ══════════════════════════════════════════════════════════════
#   ⚡  BOT С ОБРАБОТКОЙ RATE LIMITS
# ══════════════════════════════════════════════════════════════

class RateLimitHandler:
    """Обработчик Discord rate limits с exponential backoff"""
    def __init__(self):
        self.retry_delays = {}
        self.request_timestamps = []
    
    async def handle_rate_limit(self, retry_after: float):
        """Обработать rate limit с экспоненциальным ростом задержки"""
        delay = min(retry_after * 1.5, 60)  # Макс 60 секунд
        logger.warning(f"⏰ Rate limit! Ждём {delay:.2f} сек...")
        await asyncio.sleep(delay)

class CustomBot(commands.Bot):
    """Discord бот с улучшенной обработкой ошибок и rate limit"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rate_limit_handler = RateLimitHandler()
        self.start_time = datetime.now()
        self.command_count = 0
        self.error_count = 0
        self._cached_data = {}
        
    async def on_ready(self):
        """Запуск бота - инициализируем MongoDB"""
        logger.info(f"✅ Бот запущен как {self.user}")
        logger.info(f"📊 Подключён к {len(self.guilds)} серверам")
        
        # Инициализируем MongoDB
        if not init_db():
            logger.critical("❌ Не удалось подключиться к MongoDB!")
            await self.close()
            return
        
        # Запускаем фоновые задачи
        self.status_updater.start()
        self.cleanup_cache.start()
    
    @tasks.loop(minutes=5)
    async def status_updater(self):
        """Обновляет статус бота"""
        try:
            guild_count = len(self.guilds)
            await self.change_presence(
                activity=disnake.Activity(
                    type=disnake.ActivityType.watching,
                    name=f"{guild_count} серверов | !help"
                ),
                status=disnake.Status.online
            )
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса: {e}")
    
    @tasks.loop(hours=1)
    async def cleanup_cache(self):
        """Очищает кэш каждый час"""
        self._cached_data.clear()
        logger.info("🧹 Кэш очищен")
    
    async def on_command_error(self, ctx: commands.Context, error: Exception):
        """Элегантная обработка всех ошибок команд"""
        self.error_count += 1
        
        if isinstance(error, commands.CommandNotFound):
            return
        
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Отсутствует аргумент: `{error.param.name}`")
            return
        
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(f"❌ У вас нет прав для этой команды")
            return
        
        if isinstance(error, commands.BotMissingPermissions):
            await ctx.send(f"❌ У бота нет необходимых прав")
            return
        
        if isinstance(error, disnake.HTTPException):
            if error.status == 429:  # Rate limit
                await self.rate_limit_handler.handle_rate_limit(1)
                logger.warning(f"🚫 Rate limit hit: {error}")
                return
        
        # Логируем неожиданную ошибку
        logger.error(f"Ошибка команды {ctx.command}: {error}")
        logger.error(traceback.format_exc())
        
        try:
            await ctx.send(f"❌ Ошибка: {str(error)[:100]}")
        except:
            pass

# ══════════════════════════════════════════════════════════════
#   🤖  КАСТОМНЫЙ ОБРАБОТЧИК ПРЕФИКСА
# ══════════════════════════════════════════════════════════════

def get_prefix(bot, message):
    """
    Обработчик префикса с поддержкой:
    - !command
    - ! command (с пробелом)
    - Игнорирование регистра для команды
    """
    prefixes = ["!", "! "]
    return commands.when_mentioned_or(*prefixes)(bot, message)

# ══════════════════════════════════════════════════════════════
#   🤖  СОЗДАНИЕ БОТА
# ══════════════════════════════════════════════════════════════

intents = disnake.Intents.all()
bot = CustomBot(
    command_prefix=get_prefix,
    intents=intents,
    help_command=commands.DefaultHelpCommand(),
    sync_commands=True
)

# Загружаем модули
setup(bot)

# ══════════════════════════════════════════════════════════════
#   🏃  GRACEFUL SHUTDOWN
# ══════════════════════════════════════════════════════════════

async def graceful_shutdown():
    """Корректное завершение работы бота"""
    logger.info("🛑 Инициирован graceful shutdown...")
    logger.info(f"📈 Статистика: {bot.command_count} команд, {bot.error_count} ошибок")
    
    # Закрываем MongoDB подключение
    close_db()
    logger.info("🔌 MongoDB подключение закрыто")
    
    await bot.close()

def signal_handler(signum, frame):
    """Обработчик сигналов SIGINT и SIGTERM"""
    logger.info("⚠️ Получен сигнал завершения")
    asyncio.create_task(graceful_shutdown())

import signal
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ══════════════════════════════════════════════════════════════
#   🚀  ЗАПУСК БОТА
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        logger.info("🚀 Запуск дискорд бота...")
        bot.run(TOKEN)
    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен пользователем")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка при запуске: {e}")
        logger.critical(traceback.format_exc())
        sys.exit(1)
