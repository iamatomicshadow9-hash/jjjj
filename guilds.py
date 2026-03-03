"""
╔══════════════════════════════════════════════════════════════════════╗
║ 🌸 SUNSHINE PARADISE — GUILDS + ECONOMY v5.0 🌸                     ║
╠══════════════════════════════════════════════════════════════════════╣
║ Подключение в main.py:                                               ║
║   from guilds import setup                                           ║
║   setup(bot)                                                         ║
╚══════════════════════════════════════════════════════════════════════╝

v5.0 - IDEAL ECONOMY:
  ✨ НОВОЕ: Система ферм (источников пассивного дохода)
  ✨ НОВОЕ: Апгрейды гильдий для экономических бонусов
  ✨ НОВОЕ: Интеграция полной экономики из economy.py
  ✨ НОВОЕ: Пассивный доход каждый час
  ✨ НОВОЕ: Команды для покупки и управления фермами
  ✨ НОВОЕ: Расширенные статистики экономики
  ✨ УЛУЧШЕНО: Отображение лейтенантов и замов в !ginfo
  ✨ УЛУЧШЕНО: Поддержка флибельного префикса (!, ! )
"""

import disnake
from disnake.ext import commands, tasks
import asyncio
import random
import uuid
import io
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict
from pymongo import MongoClient
from dotenv import load_dotenv
import os

# Импортируем экономику
try:
    from economy import (
        INCOME_SOURCES, GUILD_INCOME_UPGRADES, INCOME_TIERS,
        get_income_per_hour, get_guild_vault_bonus, format_income_sources,
        calculate_farm_payback_days, get_income_sources_by_tier
    )
except ImportError:
    print("⚠️ economy.py не найден - некоторые функции недоступны")
    INCOME_SOURCES = {}
    GUILD_INCOME_UPGRADES = {}
    INCOME_TIERS = {}
    
    # Fallback функции
    def get_income_per_hour(farms, upgrades=None):
        return 0
    def get_guild_vault_bonus(upgrades=None):
        return 1.0
    def format_income_sources(farms, tier=None):
        return "> —\n"
    def calculate_farm_payback_days(farm_key):
        return 0
    def get_income_sources_by_tier(tier):
        return {}

load_dotenv()

# ══════════════════════════════════════════════════════════════
# 🗄️ MONGODB
# ══════════════════════════════════════════════════════════════
MONGO_URI = os.getenv("MONGODB_URI", "mongodb+srv://user:pass@cluster.mongodb.net/sunshine")
DB_NAME = os.getenv("MONGO_DB_NAME", "")  # можно задать явно через env
mongo_client = None
db = None


def _extract_db_name(uri: str) -> str:
    """Извлекает имя БД из URI. Fallback: 'sunshine'."""
    try:
        # URI вида: ...cluster.net/dbname?params
        path = uri.split("?")[0]  # убираем query params
        name = path.rsplit("/", 1)[-1]  # берём последний сегмент пути
        if name and name not in ("", "admin", "local", "config"):
            return name
    except Exception:
        pass
    return "sunshine"


def init_db():
    global mongo_client, db
    try:
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # Явно указываем имя БД — get_database() без аргумента падает если URI без имени
        db_name = DB_NAME or _extract_db_name(MONGO_URI)
        db = mongo_client[db_name]
        db.command("ping")
        print("✅ MongoDB подключена успешно")
        db["users"].create_index([("server_id", 1), ("user_id", 1)], unique=True)
        db["guilds"].create_index([("server_id", 1), ("id", 1)], unique=True)
        return True
    except Exception as e:
        print(f"❌ Ошибка подключения к MongoDB: {e}")

        class MockCursor:
            def sort(self, *a, **kw): return self
            def limit(self, *a, **kw): return self
            def __iter__(self): return iter([])

        class MockCollection:
            def find_one(self, *a, **kw): return None
            def find(self, *a, **kw): return MockCursor()
            def update_one(self, *a, **kw): return None
            def insert_one(self, *a, **kw): return None
            def count_documents(self, *a, **kw): return 0
            def create_index(self, *a, **kw): return None
            def delete_one(self, *a, **kw): return None

        class MockDB:
            def __getitem__(self, name): return MockCollection()
            def command(self, *a, **kw): return None

        db = MockDB()
        return False


def close_db():
    global mongo_client
    if mongo_client:
        mongo_client.close()
        print("🔌 MongoDB подключение закрыто")


# ══════════════════════════════════════════════════════════════
# ⚙️ КОНФИГУРАЦИЯ
# ══════════════════════════════════════════════════════════════
EMBED_AUTHOR = "🌸 Sunshine Paradise 🌸"



# ── СЕРВЕРНЫЙ АЙДИ И БОФФЫ ─────────────────────────────────
HOME_SERVER_ID = 1168585868882215004  # ID главного сервера Sunshine Paradise

MEMBER_BADGES = {
    # Если ТОЛЬКО тег или ссылка на сервер в описании профиля (но не оба сразу)
    "basic": {
        "role_id": 1475882293733363826,
        "multiplier": 1.10,  
        "description": "Тег гильдии",
        "emoji": "🏷️",
    },
    # Если тег  + ссылка в описании профиля 
    "verified": {
        "role_id": 1475884914359406702,
        "multiplier": 1.25,  
        "description": "Полный профиль сервера",
        "emoji": "✅",
    },
    # Можно добавить ещё баффы:
    # "premium": {
    #     "role_id": 1234567890,
    #     "multiplier": 1.50,
    #     "description": "Премиум участник",
    #     "emoji": "⭐",
    # }
}

XP_PER_MSG = 10
COINS_PER_MSG = 2
XP_COOLDOWN_SEC = 10
DAILY_COINS = 200
DAILY_COOLDOWN_H = 20
WORK_COOLDOWN_MIN = 45
DEFAULT_MSG_REQUIRED = 300

# ── Rate limit защита ────────────────────────────────────────
# (uses, per_seconds)  — выбраны с запасом для активных серверов
COOLDOWNS = {
    "info_light":  (1, 8),
    "eco_medium":  (1, 15),
    "guild_heavy": (1, 25),
    "super_heavy": (1, 40),
    "rank_ops":    (1, 20),
    "wars":        (1, 90),
}

# Дополнительный глобальный ограничитель Discord-запросов
# Не чаще 1 запроса в 0.5 с на один объект канала/категории
DISCORD_API_DELAY = 0.55  # секунд между тяжёлыми Discord вызовами

LEVELS = {
    1: 0, 2: 300, 3: 700, 4: 1300, 5: 2100,
    6: 3100, 7: 4300, 8: 5700, 9: 7300, 10: 9100,
    11: 11200, 12: 13600, 13: 16300, 14: 19300, 15: 22700,
    16: 26500, 17: 30700, 18: 35300, 19: 40300, 20: 45700,
}
MAX_LEVEL = 20
BASE_MEMBERS = 10

GUILD_RANKS = {
    "owner":     {"name": "Основатель",  "icon": "👑", "color": 0xFFD700, "xp_bonus": 1.5, "coin_bonus": 1.5,
                  "can_invite": True,  "can_kick": True,  "can_promote": True,  "can_edit_settings": True,
                  "can_manage_vault": True,  "can_delete_guild": True,  "priority": 5},
    "viceowner": {"name": "Вице-лидер", "icon": "💎", "color": 0xDCC0DE, "xp_bonus": 1.3, "coin_bonus": 1.3,
                  "can_invite": True,  "can_kick": True,  "can_promote": True,  "can_edit_settings": False,
                  "can_manage_vault": True,  "can_delete_guild": False, "priority": 4},
    "officer":   {"name": "Офицер",     "icon": "🛡️", "color": 0xC0FFEE, "xp_bonus": 1.15, "coin_bonus": 1.15,
                  "can_invite": True,  "can_kick": True,  "can_promote": False, "can_edit_settings": False,
                  "can_manage_vault": True,  "can_delete_guild": False, "priority": 3},
    "moderator": {"name": "Лейтенант", "icon": "🔨", "color": 0x9370DB, "xp_bonus": 1.1, "coin_bonus": 1.1,
                  "can_invite": True,  "can_kick": False, "can_promote": False, "can_edit_settings": False,
                  "can_manage_vault": False, "can_delete_guild": False, "priority": 2},
    "member":    {"name": "Участник",   "icon": "👤", "color": 0x808080, "xp_bonus": 1.0, "coin_bonus": 1.0,
                  "can_invite": False, "can_kick": False, "can_promote": False, "can_edit_settings": False,
                  "can_manage_vault": False, "can_delete_guild": False, "priority": 1},
    "recruit":   {"name": "Новобранец", "icon": "🌱", "color": 0x90EE90, "xp_bonus": 0.8, "coin_bonus": 0.8,
                  "can_invite": False, "can_kick": False, "can_promote": False, "can_edit_settings": False,
                  "can_manage_vault": False, "can_delete_guild": False, "priority": 0},
}

GUILD_UPGRADES = {
    "slot_1":   {"price": 2_000,  "members": 5,  "emoji": "👥", "name": "Слот I"},
    "slot_2":   {"price": 6_000,  "members": 10, "emoji": "👥", "name": "Слот II"},
    "slot_3":   {"price": 15_000, "members": 20, "emoji": "👥", "name": "Слот III"},
    "vault_1":  {"price": 3_000,  "members": 0,  "emoji": "💰", "name": "Казна I"},
    "vault_2":  {"price": 9_000,  "members": 0,  "emoji": "💰", "name": "Казна II"},
    "prestige": {"price": 25_000, "members": 0,  "emoji": "⭐", "name": "Престиж"},
}

COLORS = {
    "blue":   {"label": "🔵 Синий",      "hex": 0x3498DB, "cat": "🔵", "ch": ["🔹","🔷","💎","🫐","🌀","🧿"]},
    "red":    {"label": "🔴 Красный",    "hex": 0xE74C3C, "cat": "🔴", "ch": ["❤️","🌹","🍎","🔸","💢","🎯"]},
    "green":  {"label": "🟢 Зелёный",   "hex": 0x2ECC71, "cat": "🟢", "ch": ["🍀","🌿","🌱","🌲","🥝","🌾"]},
    "gold":   {"label": "🟡 Золотой",   "hex": 0xF1C40F, "cat": "🟡", "ch": ["⭐","✨","🌟","💛","🏅","🎖️"]},
    "purple": {"label": "🟣 Фиолетовый","hex": 0x9B59B6, "cat": "🟣", "ch": ["💜","🔮","🌌","🦄","🪄","🫂"]},
    "pink":   {"label": "🩷 Розовый",   "hex": 0xFF69B4, "cat": "🩷", "ch": ["🌸","🌷","🌺","🎀","🍬","💅"]},
    "white":  {"label": "⚪ Белый",      "hex": 0xDDDDDD, "cat": "⚪", "ch": ["🤍","🕊️","❄️","🌙","🫧","🌫️"]},
    "orange": {"label": "🟠 Оранжевый","hex": 0xE67E22, "cat": "🟠", "ch": ["🍊","🔶","🦊","🌅","🔥","🎃"]},
    "aqua":   {"label": "🩵 Голубой",   "hex": 0x1ABC9C, "cat": "🩵", "ch": ["🩵","🌊","🐬","🐟","💧","🫧"]},
}
DEFAULT_COLOR = "blue"

CHANNEL_TPL = [
    {"slug": "анонсы",   "type": "text",  "readonly": True,  "officers_only": False, "topic": "Официальные новости гильдии"},
    {"slug": "правила",  "type": "text",  "readonly": True,  "officers_only": False, "topic": "Правила и устав гильдии"},
    {"slug": "чат",      "type": "text",  "readonly": False, "officers_only": False, "topic": "Общение участников"},
    {"slug": "офицеры",  "type": "text",  "readonly": False, "officers_only": True,  "topic": "Канал офицеров"},
    {"slug": "трибуна",  "type": "voice", "readonly": False, "officers_only": False, "topic": ""},
]

SEASON_CH_KEY = "event_channel_id"

WINTER_TASKS = [
    {"id": "wt_snow",   "emoji": "❄️", "name": "Снежки",       "goal": 10, "reward": 300, "desc": "Кинь снежок 10 раз (!snowball)"},
    {"id": "wt_warm",   "emoji": "🔥", "name": "Согрей друга", "goal": 5,  "reward": 200, "desc": "Согрей 5 друзей (!warm @юзер)"},
    {"id": "wt_man",    "emoji": "⛄", "name": "Снеговик",     "goal": 1,  "reward": 500, "desc": "Слепи снеговика (!snowman)"},
    {"id": "wt_patrol", "emoji": "🛡️", "name": "Патруль",      "goal": 3,  "reward": 400, "desc": "Защити гильдию (!gpatrol)"},
]
SPRING_TASKS = [
    {"id": "sp_flower", "emoji": "🌸", "name": "Цветы",   "goal": 15, "reward": 350, "desc": "Собери цветы 15 раз (!flower)"},
    {"id": "sp_plant",  "emoji": "🌱", "name": "Посадка", "goal": 5,  "reward": 250, "desc": "Посади цветок другу (!plant @юзер)"},
    {"id": "sp_rain",   "emoji": "🌧️", "name": "Дождь",   "goal": 1,  "reward": 600, "desc": "Призови дождь (!spring_rain)"},
    {"id": "sp_bloom",  "emoji": "🌺", "name": "Цветение","goal": 5,  "reward": 500, "desc": "Участвуй в делах гильдии"},
]

# ══════════════════════════════════════════════════════════════
# 🏅 СИСТЕМА БАФФОВ И ВЕРИФИКАЦИИ
# ══════════════════════════════════════════════════════════════

# Кэш баффов: {user_id: (badge_level, multiplier, last_check_time)}
_member_badge_cache = {}
_cache_ttl = 3600  # 1 час


BLACKLIST = {
    1373674754946633758,
    1212720500447518801,
    764798931573014549,
    973932002967441408,
    1471537123881386087,
    1442118115596177410,
    747893653397307524,
    1041014507239129088,
    1191744050273984582,
    962405562358853642,
}


async def check_member_profile(member: disnake.Member) -> Optional[str]:
    """
    Проверяет профиль участника на наличие тега HOME_SERVER или ссылки на сервер.
    Возвращает уровень бафф: 'verified' → 'basic' → None
    
    Алгоритм:
    1. Проверяем ник на наличие тега сервера [SP] или другого
    2. Проверяем описание профиля (bio) на тег + ссылку на discord.gg
    3. 'verified' если есть ТАГ + ССЫЛКА
    4. 'basic' если есть только ССЫЛКА или только ТАГ
    5. None если ничего не найдено
    """
    try:
        # Получаем имя и описание
        display_name = member.display_name or ""
        user_bio = getattr(member, 'bio', '') or ""
        
        # HOME_SERVER_ID = 1168585868882215004 → TAG опционально
        # Проверяем наличие тега гильдии (любой клановый тег типа [NAME])
        has_tag = bool(display_name and '[' in display_name and ']' in display_name)
        
        # Проверяем наличие ссылки на сервер Discord и любого тега
        has_server_link = 'discord.gg' in user_bio.lower()
        
        # Логика присвоения баффа
        if has_tag and has_server_link:
            return "verified"  # 1.25x бафф
        elif has_tag or has_server_link:
            return "basic"     # 1.10x бафф
        else:
            return None        # без баффа
            
    except Exception as e:
        print(f"[check_member_profile] {e}")
        return None


def get_member_badge_multiplier(member_id: int) -> float:
    """
    Получает мультипликатор баффа участника из кэша.
    По умолчанию возвращает 1.0 (без баффа).
    Кэш автоматически обновляется фоновой задачей.
    """
    if member_id in _member_badge_cache:
        badge_level, multiplier, _ = _member_badge_cache[member_id]
        if badge_level and badge_level in MEMBER_BADGES:
            return MEMBER_BADGES[badge_level].get("multiplier", 1.0)
    return 1.0


# ══════════════════════════════════════════════════════════════
# ⚔️ БОЕВАЯ СИСТЕМА И АЛЬЯНСЫ
# ══════════════════════════════════════════════════════════════

ARMY_UNITS = {
    "recruit": {
        "name": "🔱 Новобранец",
        "cost": 500,
        "power": 1,
        "emoji": "🔱",
    },
    "soldier": {
        "name": "⚔️ Боец",
        "cost": 2000,
        "power": 3,
        "emoji": "⚔️",
    },
    "knight": {
        "name": "🛡️ Рыцарь",
        "cost": 8000,
        "power": 8,
        "emoji": "🛡️",
    },
    "champion": {
        "name": "👑 Чемпион",
        "cost": 25000,
        "power": 20,
        "emoji": "👑",
    },
    "legend": {
        "name": "✨ Легенда",
        "cost": 100000,
        "power": 50,
        "emoji": "✨",
    },
}

ATTACK_TYPES = {
    "raid": {
        "name": "Рейд",
        "cost": 5000,
        "loot_percent": 0.15,
        "emoji": "🔥",
    },
    "siege": {
        "name": "Осада",
        "cost": 15000,
        "loot_percent": 0.30,
        "emoji": "🏚️",
    },
    "conquest": {
        "name": "Завоевание",
        "cost": 50000,
        "loot_percent": 0.50,
        "emoji": "👑",
    },
}

TECHNOLOGIES = {
    "iron_infantry": {
        "name": "🏗️ Железная пехота",
        "description": "Боевая мощь +20%",
        "cost": 50000,
        "bonus": 0.20,
        "type": "power",
    },
    "shield_mastery": {
        "name": "🛡️ Мастерство щита", 
        "description": "Защита +30%",
        "cost": 40000,
        "bonus": 0.30,
        "type": "defense",
    },
    "supply_chain": {
        "name": "📦 Цепь поставок",
        "description": "Экономия на армии -20%",
        "cost": 30000,
        "bonus": 0.20,
        "type": "economy",
    },
    "espionage": {
        "name": "🕵️ Разведка",
        "description": "Видишь войск противника",
        "cost": 60000,
        "bonus": 0,
        "type": "info",
    },
    "fortifications": {
        "name": "🏰 Укрепления",
        "description": "Защита казны +40%",
        "cost": 80000,
        "bonus": 0.40,
        "type": "vault_defense",
    },
}


# ══════════════════════════════════════════════════════════════
# 💾 БАЗА ДАННЫХ
# ══════════════════════════════════════════════════════════════

def _udef() -> dict:
    return {
        "xp": 0, "level": 1, "coins": 0, "messages": 0,
        "guild_id": None, "guild_rank": None,
        "last_xp": None, "daily_last": None, "work_last": None,
        "event_progress": {}, "event_claimed": [],
        # === НОВОЕ: Экономика ===
        "farms": [],  # Список ключей ферм типа ["flower_garden", "honey_hives"]
        "last_farm_income": None,  # Timestamp последнего сбора дохода
        "farm_income_collected": 0,  # Интнакопленный доход за день
    }


def get_user(uid: str, sid: str) -> dict:
    try:
        doc = db["users"].find_one({"user_id": uid, "server_id": sid})
        if not doc:
            new_user = {"user_id": uid, "server_id": sid, **_udef()}
            db["users"].insert_one(new_user)
            return new_user
        return dict(doc)
    except Exception as e:
        print(f"❌ get_user: {e}")
        return {"user_id": uid, "server_id": sid, **_udef()}


def save_user(uid: str, sid: str, patch: dict):
    try:
        db["users"].update_one(
            {"user_id": uid, "server_id": sid},
            {"$set": patch},
            upsert=True
        )
    except Exception as e:
        print(f"❌ save_user: {e}")


def get_settings(sid: str) -> dict:
    try:
        doc = db["settings"].find_one({"server_id": sid})
        return dict(doc) if doc else {"server_id": sid}
    except Exception as e:
        print(f"❌ get_settings: {e}")
        return {}


def save_settings(sid: str, patch: dict):
    try:
        db["settings"].update_one({"server_id": sid}, {"$set": patch}, upsert=True)
    except Exception as e:
        print(f"❌ save_settings: {e}")


def get_msg_required(sid: str) -> int:
    return get_settings(sid).get("msg_required", DEFAULT_MSG_REQUIRED)

@bot.check
async def global_blacklist_check(ctx):
    return ctx.author.id not in BLACKLIST

# Блок для /slash команд
@bot.before_slash_command_invoke
async def before_slash(inter: disnake.ApplicationCommandInteraction):
    if inter.author.id in BLACKLIST:
        await inter.response.send_message(".", ephemeral=True)
        raise disnake.ext.commands.CheckFailure()

# Блок для кнопок
@bot.listen("on_button_click")
async def blacklist_buttons(inter: disnake.MessageInteraction):
    if inter.author.id in BLACKLIST:
        await inter.response.defer()

# Блок для выпадающих меню
@bot.listen("on_dropdown")
async def blacklist_dropdowns(inter: disnake.MessageInteraction):
    if inter.author.id in BLACKLIST:
        await inter.response.defer()


def get_guild(gid: str) -> Optional[dict]:
    try:
        doc = db["guilds"].find_one({"id": gid})
        return dict(doc) if doc else None
    except Exception as e:
        print(f"❌ get_guild: {e}")
        return None


def save_guild(gid: str, patch: dict):
    try:
        db["guilds"].update_one({"id": gid}, {"$set": patch}, upsert=True)
    except Exception as e:
        print(f"❌ save_guild: {e}")


def guild_by_tag(sid: str, tag: str) -> Optional[dict]:
    try:
        doc = db["guilds"].find_one({"server_id": sid, "tag": tag.upper()})
        return dict(doc) if doc else None
    except Exception as e:
        print(f"❌ guild_by_tag: {e}")
        return None


def guild_members(gid: str, sid: str) -> List[dict]:
    """Возвращает список dict с ключом 'user_id' (всегда)."""
    try:
        return [dict(m) for m in db["users"].find({"server_id": sid, "guild_id": gid})]
    except Exception as e:
        print(f"❌ guild_members: {e}")
        return []


def member_count(gid: str, sid: str) -> int:
    try:
        return db["users"].count_documents({"server_id": sid, "guild_id": gid})
    except Exception as e:
        print(f"❌ member_count: {e}")
        return 0


def calc_guild_power(gd: dict, sid: str) -> int:
    """Рассчитать мощь гильдии по всем параметрам"""
    members = member_count(gd["id"], sid)
    
    # Базовая мощь от казны
    power = gd.get("bank", 0) // 100
    
    # Мощь от членов
    power += members * 50
    
    # Мощь от побед
    power += gd.get("wins", 0) * 200
    
    # Мощь от апгрейдов
    upgrades = gd.get("upgrades", [])
    power += len(upgrades) * 300
    
    # Мощь от описания (если есть, то гильдия развивалась)
    if gd.get("description"):
        power += 500
    
    # Мощь от цвета кастома (если не дефолт)
    if gd.get("color") and gd.get("color") != DEFAULT_COLOR:
        power += 200
    
    return max(1, power)


def calc_guild_level(gd: dict, sid: str) -> tuple:
    """Рассчитать уровень и опыт гильдии: (level, xp, xp_needed)"""
    xp = gd.get("level_xp", 0)
    level = gd.get("level", 1)
    
    # XP нужен для следующего уровня: 1000 + (level * 500)
    xp_needed = 1000 + (level * 500)
    
    # Проверяем повышение уровня
    while xp >= xp_needed:
        xp -= xp_needed
        level += 1
        xp_needed = 1000 + (level * 500)
    
    return level, xp, xp_needed


def add_guild_xp(gid: str, amount: int):
    """Добавить опыт гильдии"""
    try:
        gd = db["guilds"].find_one({"id": gid})
        if gd:
            xp = gd.get("level_xp", 0) + amount
            level = gd.get("level", 1)
            
            # Проверяем повышения уровня
            xp_needed = 1000 + (level * 500)
            while xp >= xp_needed:
                xp -= xp_needed
                level += 1
                xp_needed = 1000 + (level * 500)
            
            db["guilds"].update_one({"id": gid}, {
                "$set": {"level_xp": xp, "level": level}
            })
    except Exception as e:
        print(f"[add_guild_xp] Error: {e}")


def member_limit(upgrades: list) -> int:
    base = BASE_MEMBERS
    for k in upgrades:
        upg = GUILD_UPGRADES.get(k)
        if upg:
            base += upg["members"]
    return base


def get_alliance(sid: str, name: str) -> Optional[dict]:
    """Получить альянс по названию."""
    try:
        doc = db["alliances"].find_one({"server_id": sid, "name": name.lower()})
        return dict(doc) if doc else None
    except Exception as e:
        print(f"❌ get_alliance: {e}")
        return None


def get_alliance_by_id(alliance_id: str) -> Optional[dict]:
    """Получить альянс по ID."""
    try:
        doc = db["alliances"].find_one({"id": alliance_id})
        return dict(doc) if doc else None
    except Exception as e:
        print(f"❌ get_alliance_by_id: {e}")
        return None


def save_alliance(alliance_id: str, patch: dict):
    """Сохранить данные альянса."""
    try:
        db["alliances"].update_one({"id": alliance_id}, {"$set": patch}, upsert=True)
    except Exception as e:
        print(f"❌ save_alliance: {e}")


def get_guild_alliances(gid: str) -> List[dict]:
    """Получить альянсы гильдии."""
    try:
        return [dict(a) for a in db["alliances"].find({"members": gid})]
    except Exception as e:
        print(f"❌ get_guild_alliances: {e}")
        return []



def calc_level(xp: int) -> int:
    lvl = 1
    for lv, req in LEVELS.items():
        if xp >= req:
            lvl = lv
    return min(lvl, MAX_LEVEL)


def xp_needed(xp: int, lvl: int) -> int:
    nxt = lvl + 1
    return 0 if nxt > MAX_LEVEL else LEVELS[nxt] - xp


# ══════════════════════════════════════════════════════════════
# 🎨 УТИЛИТЫ
# ══════════════════════════════════════════════════════════════

def chex(color: str) -> int:
    return COLORS.get(color, COLORS[DEFAULT_COLOR])["hex"]

def ch_emojis(color: str) -> List[str]:
    return COLORS.get(color, COLORS[DEFAULT_COLOR])["ch"]

def cat_em(color: str) -> str:
    return COLORS.get(color, COLORS[DEFAULT_COLOR])["cat"]

def rank_icon(rank: str) -> str:
    return GUILD_RANKS.get(rank, GUILD_RANKS["member"]).get("icon", "👤")

def rank_name(rank: str) -> str:
    return GUILD_RANKS.get(rank, GUILD_RANKS["member"]).get("name", "Участник")

def rank_color(rank: str) -> int:
    return GUILD_RANKS.get(rank, GUILD_RANKS["member"]).get("color", 0x808080)

def has_privilege(rank: str, privilege: str) -> bool:
    return GUILD_RANKS.get(rank, GUILD_RANKS["member"]).get(f"can_{privilege}", False)

def pbar(cur: int, goal: int, n: int = 10) -> str:
    f = int(min(cur, goal) / max(goal, 1) * n)
    return "█" * f + "░" * (n - f)

def ce(title: str, desc: str, srv: disnake.Guild, color: int = 0xFF69B4) -> disnake.Embed:
    e = disnake.Embed(title=title, description=desc, color=color)
    e.set_author(name=EMBED_AUTHOR, icon_url=srv.icon.url if srv.icon else None)
    e.timestamp = datetime.utcnow()
    return e

def ge(title: str, desc: str, gdata: dict, srv: disnake.Guild) -> disnake.Embed:
    return ce(title, desc, srv, chex(gdata.get("color", DEFAULT_COLOR)))

def uid_from_member_doc(doc: dict) -> Optional[str]:
    """Безопасно извлекает user_id из документа пользователя."""
    if not doc:
        return None
    return doc.get("user_id") or doc.get("uid") or doc.get("_id")


# ── Компоненты V1 ────────────────────────────────────────────

def invite_row(gid: str, inviter_id: int, invited_id: int) -> disnake.ui.ActionRow:
    return disnake.ui.ActionRow(
        disnake.ui.Button(label="✅ Принять",  style=disnake.ButtonStyle.success,
                          custom_id=f"invite:accept:{gid}:{inviter_id}:{invited_id}"),
        disnake.ui.Button(label="❌ Отклонить", style=disnake.ButtonStyle.danger,
                          custom_id=f"invite:decline:{gid}:{inviter_id}:{invited_id}"),
    )

def page_row(owner_id: int, page: int, total: int, key: str) -> disnake.ui.ActionRow:
    return disnake.ui.ActionRow(
        disnake.ui.Button(label="◀️", style=disnake.ButtonStyle.secondary,
                          custom_id=f"page:prev:{owner_id}:{page}:{total}:{key}",
                          disabled=page == 0),
        disnake.ui.Button(label="▶️", style=disnake.ButtonStyle.secondary,
                          custom_id=f"page:next:{owner_id}:{page}:{total}:{key}",
                          disabled=page >= total - 1),
    )

def season_claim_row(uid: int, season: str) -> disnake.ui.ActionRow:
    return disnake.ui.ActionRow(
        disnake.ui.Button(label="📬 Забрать награды", style=disnake.ButtonStyle.success,
                          custom_id=f"season:claim:{uid}:{season}"),
    )

def disabled_row(*labels_and_styles) -> disnake.ui.ActionRow:
    btns = []
    for idx, (label, style) in enumerate(labels_and_styles):
        btns.append(disnake.ui.Button(label=label, style=style,
                                       custom_id=f"disabled_noop_{idx}_{random.randint(0, 999999)}",
                                       disabled=True))
    return disnake.ui.ActionRow(*btns)


# ══════════════════════════════════════════════════════════════
# 🏗️ КАНАЛЫ ГИЛЬДИИ
# ══════════════════════════════════════════════════════════════

async def _safe_delete(obj, delay: float = DISCORD_API_DELAY):
    """Удаляет объект Discord с задержкой и обработкой ошибок."""
    try:
        await asyncio.sleep(delay)
        await obj.delete()
    except disnake.NotFound:
        pass
    except disnake.HTTPException as e:
        if e.status == 429:
            retry = e.response.headers.get("Retry-After", 5)
            await asyncio.sleep(float(retry) + 1)
            try:
                await obj.delete()
            except Exception:
                pass
    except Exception as ex:
        print(f"[safe_delete] {ex}")


async def create_guild_role(srv: disnake.Guild, tag: str, color: int) -> Optional[disnake.Role]:
    """Создаёт роль для гильдии."""
    try:
        role_name = f"[{tag}] Члены"
        role = await srv.create_role(
            name=role_name,
            color=disnake.Color(color),
            reason="Роль гильдии для управления доступом"
        )
        return role
    except Exception as e:
        print(f"[create_guild_role] {e}")
        return None


async def build_channels(
    srv: disnake.Guild, name: str, tag: str, color: str, owner: disnake.Member,
) -> Tuple[Optional[disnake.CategoryChannel], list]:
    emojis = ch_emojis(color)
    n = len(CHANNEL_TPL)
    cat_ow = {
        srv.default_role: disnake.PermissionOverwrite(read_messages=False, connect=False),
        srv.me: disnake.PermissionOverwrite(read_messages=True, manage_channels=True,
                                             manage_permissions=True, connect=True),
        owner: disnake.PermissionOverwrite(read_messages=True, send_messages=True,
                                            connect=True, manage_messages=True),
    }
    try:
        cat = await srv.create_category(f"——・{name.upper()}", overwrites=cat_ow)
    except disnake.Forbidden:
        return None, []
    except disnake.HTTPException as e:
        print(f"[build_channels] category: {e}")
        return None, []

    created = []
    for i, tpl in enumerate(CHANNEL_TPL):
        await asyncio.sleep(DISCORD_API_DELAY)
        border = "┏" if i == 0 else ("┖" if i == n - 1 else "┃")
        em = emojis[i % len(emojis)]
        cname = f"{border}【{em}】{tpl['slug']}"
        ow = {
            srv.default_role: disnake.PermissionOverwrite(read_messages=False, connect=False),
            srv.me: disnake.PermissionOverwrite(read_messages=True, send_messages=True, connect=True),
            owner: disnake.PermissionOverwrite(read_messages=True, send_messages=True, connect=True),
        }
        try:
            if tpl["type"] == "voice":
                obj = await srv.create_voice_channel(cname, category=cat, overwrites=ow)
            else:
                obj = await srv.create_text_channel(
                    cname, category=cat, topic=tpl.get("topic", ""), overwrites=ow)
                if tpl["readonly"]:
                    await asyncio.sleep(DISCORD_API_DELAY)
                    await obj.set_permissions(owner, read_messages=True,
                                              send_messages=True, manage_messages=True)
            created.append({"id": obj.id, "slug": tpl["slug"], "type": tpl["type"]})
        except disnake.HTTPException as e:
            if e.status == 429:
                retry = float(e.response.headers.get("Retry-After", 5)) + 1
                print(f"[build_channels] rate limited, waiting {retry}s")
                await asyncio.sleep(retry)
            else:
                print(f"[build_channels] {tpl['slug']}: {e}")
        except Exception as ex:
            print(f"[build_channels] {tpl['slug']}: {ex}")

    return cat, created


async def refresh_access(srv: disnake.Guild, gdata: dict, member: disnake.Member, remove: bool = False):
    cat_id = gdata.get("category_id")
    if not cat_id:
        return
    cat = srv.get_channel(int(cat_id))
    if not cat:
        return
    u = get_user(str(member.id), str(srv.id))
    rank = u.get("guild_rank", "member")
    privileged_ranks = [r for r, d in GUILD_RANKS.items() if d.get("can_manage_vault")]

    for ch in cat.channels:
        slug = next((c["slug"] for c in gdata.get("channels", []) if c.get("id") == ch.id), "")
        tpl = next((t for t in CHANNEL_TPL if t["slug"] == slug), None)
        try:
            await asyncio.sleep(DISCORD_API_DELAY)
            if remove:
                await ch.set_permissions(member, overwrite=None)
            elif tpl and tpl.get("officers_only") and rank not in privileged_ranks:
                await ch.set_permissions(member, read_messages=False)
            else:
                if isinstance(ch, disnake.VoiceChannel):
                    await ch.set_permissions(member, read_messages=True, connect=True)
                else:
                    is_readonly = tpl.get("readonly", False) if tpl else False
                    can_write = (not is_readonly) or has_privilege(rank, "manage_vault")
                    can_manage = has_privilege(rank, "manage_vault")
                    await ch.set_permissions(member, read_messages=True,
                                              send_messages=can_write,
                                              manage_messages=can_manage)
        except disnake.HTTPException as e:
            if e.status == 429:
                await asyncio.sleep(float(e.response.headers.get("Retry-After", 5)) + 1)
        except Exception:
            pass


async def rebuild(srv: disnake.Guild, gdata: dict, owner: disnake.Member):
    """Пересоздаёт каналы гильдии с защитой от rate-limit."""
    cat_id = gdata.get("category_id")
    if cat_id:
        old = srv.get_channel(int(cat_id))
        if old:
            for ch in list(old.channels):
                await _safe_delete(ch)
            await _safe_delete(old)

    cat, chs = await build_channels(srv, gdata["name"], gdata["tag"], gdata["color"], owner)
    gdata["category_id"] = cat.id if cat else None
    gdata["channels"] = chs
    gdata["server_id"] = str(srv.id)
    save_guild(gdata["id"], gdata)

    sid = str(srv.id)
    for m in guild_members(gdata["id"], sid):
        uid = uid_from_member_doc(m)
        if uid:
            mo = srv.get_member(int(uid))
            if mo:
                await refresh_access(srv, gdata, mo)


# ══════════════════════════════════════════════════════════════
# 💬 ЛС ДИАЛОГ СОЗДАНИЯ
# ══════════════════════════════════════════════════════════════

async def creation_dialog(ctx: commands.Context, bot: commands.Bot) -> Optional[dict]:
    author = ctx.author

    def dmcheck(m):
        return m.author.id == author.id and isinstance(m.channel, disnake.DMChannel)

    try:
        dm = await author.create_dm()
        await dm.send(embed=disnake.Embed(
            title="🌸 Создание Гильдии — Sunshine Paradise",
            description=(
                "> Привет! Следуй шагам, чтобы создать гильдию.\n> _ _\n"
                "> На каждый шаг **60 секунд**. Напиши `отмена` чтобы прервать.\n> _ _\n"
                "> **Шаг 1 / 4 ·** Введи **название** гильдии (2–30 символов):"
            ), color=0xFF69B4).set_author(name=EMBED_AUTHOR))
    except disnake.Forbidden:
        await ctx.send(embed=ce("Ошибка",
                                "> **❌ Не могу написать в ЛС!** Разреши личные сообщения.",
                                ctx.guild, 0xFF0000))
        return None

    await ctx.send(embed=ce("🌸 Создание Гильдии",
                             f"> {author.mention}, проверь **личные сообщения** 📬", ctx.guild))

    async def step(prompt_embed=None) -> Optional[str]:
        if prompt_embed:
            await dm.send(embed=prompt_embed)
        try:
            m = await bot.wait_for("message", check=dmcheck, timeout=60)
        except asyncio.TimeoutError:
            await dm.send("⏰ Время вышло.")
            return None
        if m.content.lower() == "отмена":
            await dm.send("❌ Отменено.")
            return None
        return m.content.strip()

    # Шаг 1 — Название
    name_raw = await step()
    if not name_raw:
        return None
    name = name_raw
    if not 2 <= len(name) <= 30:
        await dm.send("❌ Название: 2–30 символов. Отменено.")
        return None

    # Шаг 2 — Тег
    tag_raw = await step(disnake.Embed(
        title="🌸 Шаг 2 / 4 · Тег",
        description=(f"> ✅ Название: **{name}**\n> _ _\n"
                     "> Введи **тег** (2–5 латинских букв/цифр). Пример: `SP`, `GP1`"),
        color=0xFF69B4).set_author(name=EMBED_AUTHOR))
    if not tag_raw:
        return None
    tag = tag_raw.upper()
    if not (2 <= len(tag) <= 5 and tag.isascii() and tag.isalnum()):
        await dm.send("❌ Тег: 2–5 латинских букв/цифр. Отменено.")
        return None

    # Шаг 3 — Описание
    desc_raw = await step(disnake.Embed(
        title="🌸 Шаг 3 / 4 · Описание",
        description=(f"> ✅ Название: **{name}**\n> ✅ Тег: **[{tag}]**\n> _ _\n"
                     "> Введи **описание** (до 100 символов) или напиши `пропустить`:"),
        color=0xFF69B4).set_author(name=EMBED_AUTHOR))
    if desc_raw is None:
        return None
    desc = "Нет описания" if desc_raw.lower() == "пропустить" else desc_raw[:100]

    # Шаг 4 — Цвет
    colors_line = " | ".join(f"`{k}` {v['label']}" for k, v in COLORS.items())
    color_raw = await step(disnake.Embed(
        title="🌸 Шаг 4 / 4 · Цвет",
        description=(f"> ✅ Название: **{name}**\n> ✅ Тег: **[{tag}]**\n"
                     f"> ✅ Описание: _{desc}_\n> _ _\n> Напиши **цвет**:\n> {colors_line}"),
        color=0xFF69B4).set_author(name=EMBED_AUTHOR))
    color = DEFAULT_COLOR
    if color_raw and color_raw.lower() in COLORS:
        color = color_raw.lower()
    elif color_raw:
        await dm.send(f"⚠️ Цвет не найден, используем **{DEFAULT_COLOR}**.")

    ci = COLORS[color]
    await dm.send(embed=disnake.Embed(
        title="✅ Гильдия будет создана!",
        description=(f"> **Название:** {name}\n> **Тег:** [{tag}]\n"
                     f"> **Описание:** _{desc}_\n> **Цвет:** {ci['label']}\n"
                     "> _ _\n> Возвращайся на сервер! 🎉"),
        color=ci["hex"]).set_author(name=EMBED_AUTHOR))
    return {"name": name, "tag": tag, "desc": desc, "color": color}


# ══════════════════════════════════════════════════════════════
# 📦 ХРАНИЛИЩЕ ПАГИНАЦИИ
# ══════════════════════════════════════════════════════════════
_page_store: dict = {}


# ══════════════════════════════════════════════════════════════
# 🤖 КОГ
# ══════════════════════════════════════════════════════════════

def is_admin():
    async def predicate(ctx):
        return ctx.author.guild_permissions.administrator or ctx.author.id == 1187841298007330836
    return commands.check(predicate)


class GuildCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._xpcd: dict = {}
        if not self.season_task.is_running():
            self.season_task.start()
        if not self.verify_member_badges_task.is_running():
            self.verify_member_badges_task.start()

    def cog_unload(self):
        self.season_task.cancel()
        self.verify_member_badges_task.cancel()

    # ══════════════════════════════════════════════════════════
    # 📨 XP + МОНЕТЫ ЗА СООБЩЕНИЯ (единственный on_message)
    # ══════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_message(self, msg: disnake.Message):
        if msg.author.bot or not msg.guild:
            return
        uid, sid = str(msg.author.id), str(msg.guild.id)
        now = datetime.utcnow()
        key = f"{sid}:{uid}"

        u = get_user(uid, sid)
        patch: dict = {"messages": u.get("messages", 0) + 1}

        last = self._xpcd.get(key)
        can_gain = not last or (now - last).total_seconds() >= XP_COOLDOWN_SEC
        if can_gain:
            self._xpcd[key] = now
            rank = u.get("guild_rank") or "member"
            rd = GUILD_RANKS.get(rank, GUILD_RANKS["member"])
            xp_gain  = int(XP_PER_MSG   * rd.get("xp_bonus", 1.0))
            co_gain  = int(COINS_PER_MSG * rd.get("coin_bonus", 1.0))
            
            # 🏅 Применяем мультипликатор баффа
            badge_multiplier = get_member_badge_multiplier(msg.author.id)
            co_gain = int(co_gain * badge_multiplier)
            
            new_xp   = u.get("xp", 0) + xp_gain
            new_lvl  = calc_level(new_xp)
            old_lvl  = u.get("level", 1)
            patch.update({"xp": new_xp, "level": new_lvl,
                           "coins": u.get("coins", 0) + co_gain,
                           "last_xp": now.isoformat()})
            save_user(uid, sid, patch)
            if new_lvl > old_lvl:
                bonus = new_lvl * 50
                save_user(uid, sid, {"coins": u.get("coins", 0) + co_gain + bonus})
                try:
                    await msg.channel.send(
                        embed=ce("⬆️ Level Up!",
                                 f"> {msg.author.mention} достиг **{new_lvl} уровня**! 🎉\n"
                                 f"> 🎁 Бонус: **+{bonus} монет**", msg.guild),
                        delete_after=12)
                except Exception:
                    pass
        else:
            save_user(uid, sid, patch)

    # ══════════════════════════════════════════════════════════
    # 🔘 КОМПОНЕНТЫ (единственный обработчик)
    # ══════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_message_interaction(self, i: disnake.MessageInteraction):
        cid = i.data.custom_id

        # ── Invite ──────────────────────────────────────────
        if cid.startswith("invite:"):
            parts = cid.split(":")
            if len(parts) < 5:
                return
            action, gid, inviter_id, invited_id = parts[1], parts[2], int(parts[3]), int(parts[4])
            if i.user.id != invited_id:
                await i.response.send_message("❌ Это не твоё приглашение!", ephemeral=True)
                return
            gd = get_guild(gid)
            guild = i.guild or (self.bot.get_guild(int(gd["server_id"])) if gd else None)
            if not guild or not gd:
                await i.response.edit_message(
                    content="❌ Сервер или гильдия не найдены.", embed=None, components=[])
                return
            sid = str(guild.id)
            dis_row = disabled_row(("✅ Принять", disnake.ButtonStyle.success),
                                    ("❌ Отклонить", disnake.ButtonStyle.danger))

            if action == "decline":
                await i.response.edit_message(
                    embed=ce("Приглашение", f"> ❌ **{i.user.mention}** отклонил(а) приглашение.",
                              guild, 0xFF4444), components=[dis_row])
                return

            u = get_user(str(invited_id), sid)
            if u.get("guild_id"):
                await i.response.edit_message(
                    embed=ce("Приглашение", "> **❌ Ты уже в гильдии!**", guild, 0xFF0000),
                    components=[dis_row])
                return
            cnt = member_count(gid, sid)
            limit = member_limit(gd.get("upgrades", []))
            if cnt >= limit:
                await i.response.edit_message(
                    embed=ce("Приглашение", f"> **❌ Гильдия заполнена!** ({cnt}/{limit})",
                              guild, 0xFF0000), components=[dis_row])
                return
            save_user(str(invited_id), sid, {"guild_id": gid, "guild_rank": "member"})
            invited = guild.get_member(invited_id)
            if invited:
                await refresh_access(guild, gd, invited)
                
                # 🏅 Даём роль гильдии
                guild_role_id = gd.get("guild_role_id")
                if guild_role_id:
                    guild_role = guild.get_role(guild_role_id)
                    if guild_role:
                        try:
                            await invited.add_roles(guild_role, reason=f"Вступление в гильдию {gd['tag']}")
                        except Exception as e:
                            print(f"[invite:accept] Ошибка при присвоении роли: {e}")
                
                try:
                    old = invited.display_name
                    if old.startswith("[") and "]" in old:
                        old = old.split("]", 1)[1].strip()
                    await invited.edit(nick=f"[{gd['tag']}] {old}"[:32])
                except Exception:
                    pass
            await i.response.edit_message(
                embed=ge("🌸 Вступление", f"> ✅ **{i.user.mention}** вступил(а) в **[{gd['tag']}] {gd['name']}**! 🎉",
                          gd, guild), components=[dis_row])

        # ── Pagination ──────────────────────────────────────
        elif cid.startswith("page:"):
            parts = cid.split(":")
            if len(parts) < 6:
                return
            action, owner_id, page, total, key = parts[1], int(parts[2]), int(parts[3]), int(parts[4]), parts[5]
            if i.user.id != owner_id:
                await i.response.send_message("❌ Это не твой список!", ephemeral=True)
                return
            page = page - 1 if action == "prev" else page + 1
            page = max(0, min(page, total - 1))
            pages = _page_store.get(key, [])
            if not pages:
                await i.response.send_message("❌ Данные устарели, повтори команду.", ephemeral=True)
                return
            title_fmt = _page_store.get(key + ":title", "📋 ({}/{})")
            await i.response.edit_message(
                embed=ce(title_fmt.format(page + 1, total), pages[page], i.guild),
                components=[page_row(owner_id, page, total, key)])

        # ── Season claim ────────────────────────────────────
        elif cid.startswith("season:claim:"):
            parts = cid.split(":")
            uid, season = str(parts[2]), parts[3]
            if str(i.user.id) != uid:
                await i.response.send_message("❌ Это не твои задания!", ephemeral=True)
                return
            sid = str(i.guild.id)
            u = get_user(uid, sid)
            pr = u.get("event_progress", {})
            cl = u.get("event_claimed", [])
            task_list = WINTER_TASKS if season == "winter" else SPRING_TASKS
            earned, total_coins = [], 0
            for t in task_list:
                if t["id"] in cl:
                    continue
                if pr.get(t["id"], 0) >= t["goal"]:
                    cl.append(t["id"])
                    total_coins += t["reward"]
                    earned.append(f"> {t['emoji']} **{t['name']}** → +{t['reward']:,} монет")
            if not earned:
                await i.response.send_message(
                    embed=ce("Ивент", "> **❌ Нет завершённых заданий!**", i.guild, 0xFF4444),
                    ephemeral=True)
                return
            save_user(uid, sid, {"event_claimed": cl, "coins": u.get("coins", 0) + total_coins})
            await i.response.send_message(
                embed=ce("🌸 Награды получены!",
                          "> _ _\n" + "\n".join(earned) + f"\n> _ _\n> **Итого:** +{total_coins:,} монет",
                          i.guild), ephemeral=True)

        elif cid.startswith("disabled_noop"):
            await i.response.defer()

    # ══════════════════════════════════════════════════════════
    # 💰 ЭКОНОМИКА
    # ══════════════════════════════════════════════════════════

    @commands.command(name="profile", aliases=["prof"])
    @commands.cooldown(*COOLDOWNS["info_light"], commands.BucketType.user)
    async def profile(self, ctx: commands.Context, member: disnake.Member = None):
        target = member or ctx.author
        uid, sid = str(target.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        lvl = u.get("level", 1)
        xp  = u.get("xp", 0)
        nxt = xp_needed(xp, lvl)
        cur  = xp - LEVELS.get(lvl, 0)
        goal = (LEVELS.get(lvl + 1, LEVELS[MAX_LEVEL]) - LEVELS.get(lvl, 0)) if lvl < MAX_LEVEL else 1
        bar  = pbar(cur, goal)
        g_line = "—"
        if u.get("guild_id"):
            gd = get_guild(u["guild_id"])
            if gd:
                g_line = f"[{gd['tag']}] {gd['name']}"
        msg_req  = get_msg_required(sid)
        msg_line = ""
        if not u.get("guild_id") and u.get("messages", 0) < msg_req:
            need = msg_req - u.get("messages", 0)
            mb   = pbar(u.get("messages", 0), msg_req)
            msg_line = (f"\n> _ _\n> **📋 До создания гильдии:**\n"
                        f"> [{mb}] {u.get('messages',0)}/{msg_req} · осталось **{need}**")
        desc = (f"> **⭐ Уровень:** {lvl} / {MAX_LEVEL}\n"
                f"> **✨ XP:** {xp:,} _(до {lvl+1} лвл: {nxt:,} xp)_\n> [{bar}]\n> _ _\n"
                f"> **💰 Монеты:** {u.get('coins',0):,}\n"
                f"> **💬 Сообщений:** {u.get('messages',0):,}\n> _ _\n"
                f"> **🏰 Гильдия:** {g_line}\n"
                f"> **🎖️ Ранг:** {rank_icon(u.get('guild_rank',''))} "
                f"{(u.get('guild_rank') or '—').capitalize()}{msg_line}")
        e = ce(f"👤 {target.display_name}", desc, ctx.guild)
        if target.display_avatar:
            e.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=e)

    @commands.command(name="balance", aliases=["bal", "coins"])
    @commands.cooldown(*COOLDOWNS["info_light"], commands.BucketType.user)
    async def balance(self, ctx: commands.Context, member: disnake.Member = None):
        t = member or ctx.author
        u = get_user(str(t.id), str(ctx.guild.id))
        await ctx.send(embed=ce("💰 Баланс",
                                 f"> **{t.display_name}**\n> _ _\n"
                                 f"> 💰 **{u.get('coins',0):,}** монет\n"
                                 f"> ⭐ **{u.get('xp',0):,}** XP (ур. {u.get('level',1)})\n"
                                 f"> 💬 **{u.get('messages',0):,}** сообщений", ctx.guild))

    @commands.command(name="daily")
    @commands.cooldown(*COOLDOWNS["eco_medium"], commands.BucketType.user)
    async def daily(self, ctx: commands.Context):
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        now = datetime.utcnow()
        if u.get("daily_last"):
            try:
                diff = now - datetime.fromisoformat(u["daily_last"])
                if diff.total_seconds() < DAILY_COOLDOWN_H * 3600:
                    rem = timedelta(hours=DAILY_COOLDOWN_H) - diff
                    h   = int(rem.total_seconds() // 3600)
                    m   = int((rem.total_seconds() % 3600) // 60)
                    await ctx.send(embed=ce("Daily",
                                            f"> ⏰ Уже получил!\n> Следующий через: **{h}ч {m}м**",
                                            ctx.guild, 0xFF8800))
                    return
            except Exception:
                pass
        bonus = DAILY_COINS + random.randint(0, 100)
        new_co = u.get("coins", 0) + bonus
        save_user(uid, sid, {"coins": new_co, "daily_last": now.isoformat()})
        await ctx.send(embed=ce("🎁 Daily Bonus!",
                                 f"> {ctx.author.mention} получил ежедневный бонус!\n> _ _\n"
                                 f"> 💰 **+{bonus} монет**\n> _ _\n> Баланс: **{new_co:,}**", ctx.guild))

    @commands.command(name="work")
    @commands.cooldown(*COOLDOWNS["eco_medium"], commands.BucketType.user)
    async def work(self, ctx: commands.Context):
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        now = datetime.utcnow()
        if u.get("work_last"):
            try:
                diff = now - datetime.fromisoformat(u["work_last"])
                if diff.total_seconds() < WORK_COOLDOWN_MIN * 60:
                    rem = timedelta(minutes=WORK_COOLDOWN_MIN) - diff
                    m   = int(rem.total_seconds() // 60)
                    await ctx.send(embed=ce("Работа", f"> ⏰ Устал! Отдохни ещё **{m} мин.**",
                                            ctx.guild, 0xFF8800))
                    return
            except Exception:
                pass
        jobs = [
            ("🌸 Украсил парк цветами", 50, 150), ("🎨 Нарисовал картину", 80, 200),
            ("🧹 Навёл порядок в гильдии", 40, 120), ("🍰 Испёк торт", 60, 180),
            ("🎵 Выступил на площади", 70, 160), ("📦 Развёз посылки", 45, 130),
            ("🌿 Собрал урожай", 55, 145), ("🔨 Починил забор", 35, 110),
            ("🐾 Выгулял питомцев", 30, 100), ("📚 Помог с уроками", 40, 120),
        ]
        job, mn, mx = random.choice(jobs)
        earned = random.randint(mn, mx)
        new_co = u.get("coins", 0) + earned
        save_user(uid, sid, {"coins": new_co, "work_last": now.isoformat()})
        await ctx.send(embed=ce("💼 Работа",
                                 f"> {job}\n> _ _\n> 💰 **+{earned} монет**\n> Баланс: **{new_co:,}**",
                                 ctx.guild))

    @commands.command(name="pay")
    @commands.cooldown(*COOLDOWNS["eco_medium"], commands.BucketType.user)
    async def pay(self, ctx: commands.Context, member: disnake.Member, amount: int):
        if member.id == ctx.author.id or member.bot:
            await ctx.send(embed=ce("Перевод", "> **❌ Нельзя!**", ctx.guild, 0xFF0000))
            return
        if amount <= 0:
            await ctx.send(embed=ce("Перевод", "> **❌ Сумма > 0**", ctx.guild, 0xFF0000))
            return
        uid, tid, sid = str(ctx.author.id), str(member.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        if u.get("coins", 0) < amount:
            await ctx.send(embed=ce("Перевод",
                                     f"> **❌ Не хватает монет!** У тебя: **{u.get('coins',0):,}**",
                                     ctx.guild, 0xFF0000))
            return
        t = get_user(tid, sid)
        save_user(uid, sid, {"coins": u.get("coins", 0) - amount})
        save_user(tid, sid, {"coins": t.get("coins", 0) + amount})
        await ctx.send(embed=ce("💸 Перевод",
                                 f"> {ctx.author.mention} → {member.mention}\n> _ _\n> **{amount:,} монет**",
                                 ctx.guild))

    @commands.command(name="top", aliases=["leaderboard", "lb"])
    @commands.cooldown(*COOLDOWNS["info_light"], commands.BucketType.user)
    async def top(self, ctx: commands.Context):
        sid = str(ctx.guild.id)
        try:
            us_docs = list(db["users"].find({"server_id": sid}).sort("xp", -1).limit(10))
        except Exception:
            us_docs = []
        medals = ["🥇", "🥈", "🥉"]
        desc = ""
        for i, u in enumerate(us_docs, 1):
            mo   = ctx.guild.get_member(int(u["user_id"]))
            name = mo.display_name if mo else f"ID:{u['user_id']}"
            med  = medals[i - 1] if i <= 3 else f"`#{i}`"
            desc += f"> {med} **{name}** — ⭐ {u.get('xp',0):,} XP 💰 {u.get('coins',0):,}\n"
        await ctx.send(embed=ce("🏆 Топ по XP", desc or "> Пока нет данных", ctx.guild))

    # ══════════════════════════════════════════════════════════
    # 🏰 ГИЛЬДИИ
    # ══════════════════════════════════════════════════════════

    @commands.command(name="gcreate")
    @commands.cooldown(*COOLDOWNS["guild_heavy"], commands.BucketType.user)
    async def gcreate(self, ctx: commands.Context):
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        msg_req = get_msg_required(sid)
        if u.get("guild_id"):
            await ctx.send(embed=ce("Создание",
                                     "> **❌ Ты уже в гильдии!** Выйди через `!gleave`",
                                     ctx.guild, 0xFF0000))
            return
        if u.get("messages", 0) < msg_req:
            need = msg_req - u.get("messages", 0)
            bar  = pbar(u.get("messages", 0), msg_req)
            await ctx.send(embed=ce("Создание Гильдии",
                                     f"> **❌ Нужно {msg_req} сообщений!**\n"
                                     f"> [{bar}] {u.get('messages',0)}/{msg_req} · осталось **{need}**",
                                     ctx.guild, 0xFF8800))
            return
        result = await creation_dialog(ctx, self.bot)
        if not result:
            return
        name, tag, desc, color = result["name"], result["tag"], result["desc"], result["color"]
        try:
            gs = list(db["guilds"].find({"server_id": sid}))
        except Exception:
            gs = []
        for g in gs:
            if g.get("tag") == tag:
                await ctx.send(embed=ce("Создание", f"> **❌ Тег [{tag}] уже занят!**",
                                         ctx.guild, 0xFF0000))
                return
        gid = str(uuid.uuid4())[:8]
        cat, chs = await build_channels(ctx.guild, name, tag, color, ctx.author)
        
        # 🏅 Создаём роль для гильдии
        guild_role = await create_guild_role(ctx.guild, tag, COLORS[color].get("hex", 0x3498DB))
        guild_role_id = guild_role.id if guild_role else None
        
        save_guild(gid, {
            "id": gid, "server_id": sid, "name": name, "tag": tag,
            "description": desc, "color": color, "owner_id": uid,
            "officers": [], "upgrades": [], "bank": 0, "wins": 0, "losses": 0,
            "category_id": cat.id if cat else None, "channels": chs,
            "guild_role_id": guild_role_id,  # Сохраняем ID роли гильдии
            "created_at": str(datetime.utcnow().date()),
            "level": 1, "level_xp": 0,  # Инициализируем систему уровней
        })
        
        # Даём лидеру роль гильдии
        if guild_role:
            try:
                await ctx.author.add_roles(guild_role, reason="Создатель гильдии")
            except Exception as e:
                print(f"[gcreate] Не удалось дать роль: {e}")
        
        save_user(uid, sid, {"guild_id": gid, "guild_rank": "owner"})
        try:
            old = ctx.author.display_name
            if old.startswith("[") and "]" in old:
                old = old.split("]", 1)[1].strip()
            await ctx.author.edit(nick=f"[{tag}] {old}"[:32])
        except Exception:
            pass
        ann_id = next((c["id"] for c in chs if c["slug"] == "анонсы"), None)
        if ann_id:
            ann_ch = ctx.guild.get_channel(ann_id)
            if ann_ch:
                try:
                    await ann_ch.send(embed=disnake.Embed(
                        title=f"🌸 Гильдия [{tag}] {name} основана!",
                        description=(f"> **Лидер:** {ctx.author.mention}\n"
                                     f"> **Описание:** _{desc}_\n> _ _\n"
                                     f"> Пригласи участников: `!ginvite @юзер`"),
                        color=chex(color)).set_author(name=EMBED_AUTHOR))
                except Exception:
                    pass
        await ctx.send(embed=ge("🏰 Гильдия создана!",
                                 f"> **[{tag}] {name}**\n> _{desc}_\n> _ _\n"
                                 f"> 👑 {ctx.author.mention} · 🎨 {COLORS[color]['label']}\n"
                                 f"> `!ginvite @юзер` — пригласить",
                                 get_guild(gid), ctx.guild))

    @commands.command(name="gdelete")
    @commands.cooldown(*COOLDOWNS["super_heavy"], commands.BucketType.user)
    async def gdelete(self, ctx: commands.Context):
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        if not u.get("guild_id"):
            await ctx.send(embed=ce("Удаление", "> **❌ Ты не в гильдии!**", ctx.guild, 0xFF0000))
            return
        gid = u["guild_id"]
        gd  = get_guild(gid)
        if not gd or gd["owner_id"] != uid:
            await ctx.send(embed=ce("Удаление", "> **❌ Только лидер может удалить!**",
                                     ctx.guild, 0xFF0000))
            return
        await ctx.send(embed=ce("⚠️ Удаление",
                                 f"> Удалить **[{gd['tag']}] {gd['name']}**?\n"
                                 "> Напиши `ДА` для подтверждения (60 сек):", ctx.guild, 0xFF8800))

        def check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id
        try:
            r = await self.bot.wait_for("message", check=check, timeout=60)
        except asyncio.TimeoutError:
            await ctx.send(embed=ce("Удаление", "> ⏰ Отменено.", ctx.guild, 0x888888))
            return
        if r.content.upper() != "ДА":
            await ctx.send(embed=ce("Удаление", "> ❌ Отменено.", ctx.guild, 0x888888))
            return
        await self._dissolve_guild(ctx.guild, gd, sid)
        await ctx.send(embed=ce("💔 Гильдия удалена",
                                 f"> **[{gd['tag']}] {gd['name']}** была распущена.",
                                 ctx.guild, 0x888888))

    async def _dissolve_guild(self, srv: disnake.Guild, gd: dict, sid: str):
        """Внутренний хелпер: удалить каналы + вычистить участников."""
        try:
            if gd.get("category_id"):
                cat = srv.get_channel(int(gd["category_id"]))
                if cat:
                    for ch in list(cat.channels):
                        await _safe_delete(ch)
                    await _safe_delete(cat)
        except Exception:
            pass
        for md in guild_members(gd["id"], sid):
            uid = uid_from_member_doc(md)
            if not uid:
                continue
            save_user(uid, sid, {"guild_id": None, "guild_rank": None})
            try:
                mo = srv.get_member(int(uid))
                if mo and mo.display_name.startswith("["):
                    clean = mo.display_name.split("]", 1)[1].strip()
                    await mo.edit(nick=clean or None)
            except Exception:
                pass
        db["guilds"].delete_one({"id": gd["id"]})

    @commands.command(name="ginfo")
    @commands.cooldown(*COOLDOWNS["info_light"], commands.BucketType.user)
    async def ginfo(self, ctx: commands.Context, *, args: str = None):
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        
        # Парсим аргументы
        show_all = False
        tag = None
        
        if args:
            parts = args.split()
            # Проверяем последнее слово на "all"
            if parts[-1].lower() == "all":
                show_all = True
                # Если всё что осталось это "all", то tag = None (текущая гильдия)
                tag = " ".join(parts[:-1]) if len(parts) > 1 else None
            else:
                tag = args
        
        if tag is None:
            u = get_user(uid, sid)
            if not u.get("guild_id"):
                await ctx.send(embed=ce("Гильдия",
                                         "> **❌ Укажи тег: `!ginfo <тег>` или вступи в гильдию**",
                                         ctx.guild, 0xFF0000))
                return
            gd = get_guild(u["guild_id"])
        else:
            gd = guild_by_tag(sid, tag)
        if not gd:
            await ctx.send(embed=ce("Гильдия", "> **❌ Не найдено!**", ctx.guild, 0xFF0000))
            return
        
        # Собираем информацию о лидере
        owner = ctx.guild.get_member(int(gd["owner_id"]))
        o_name = owner.display_name if owner else f"ID:{gd['owner_id']}"
        
        # Получаем всех членов гильдии для фильтрации по рангам
        all_members_list = guild_members(gd["id"], sid)
        
        # Вице-лидеры
        viceowners = [m for m in all_members_list if m.get("guild_rank") == "viceowner"]
        viceowners_text = ""
        limit = 5 if not show_all else len(viceowners)
        for m in viceowners[:limit]:
            mid = uid_from_member_doc(m)
            mo = ctx.guild.get_member(int(mid)) if mid else None
            name = mo.display_name if mo else f"ID:{mid}"
            viceowners_text += f"> 💎 {name}\n"
        viceowners_text = viceowners_text or "> —\n"
        if not show_all and len(viceowners) > 5:
            viceowners_text += f"> _(и ещё {len(viceowners) - 5})_\n"
        
        # Офицеры
        officers = [m for m in all_members_list if m.get("guild_rank") == "officer"]
        officers_text = ""
        limit = 5 if not show_all else len(officers)
        for m in officers[:limit]:
            mid = uid_from_member_doc(m)
            mo = ctx.guild.get_member(int(mid)) if mid else None
            name = mo.display_name if mo else f"ID:{mid}"
            officers_text += f"> 🛡️ {name}\n"
        officers_text = officers_text or "> —\n"
        if not show_all and len(officers) > 5:
            officers_text += f"> _(и ещё {len(officers) - 5})_\n"
        
        # Лейтенанты
        mods = [m for m in all_members_list if m.get("guild_rank") == "moderator"]
        mods_text = ""
        limit = 5 if not show_all else len(mods)
        for m in mods[:limit]:
            mid = uid_from_member_doc(m)
            mo = ctx.guild.get_member(int(mid)) if mid else None
            name = mo.display_name if mo else f"ID:{mid}"
            mods_text += f"> 🔨 {name}\n"
        mods_text = mods_text or "> —\n"
        if not show_all and len(mods) > 5:
            mods_text += f"> _(и ещё {len(mods) - 5})_\n"
        
        cnt  = member_count(gd["id"], sid)
        lim  = member_limit(gd.get("upgrades", []))
        upg  = "".join(f"> {GUILD_UPGRADES[k]['emoji']} {GUILD_UPGRADES[k]['name']}\n"
                       for k in gd.get("upgrades", []) if k in GUILD_UPGRADES) or "> Нет апгрейдов\n"
        desc = (f"> **🌸 Название:** {gd['name']}\n> **🏷️ Тег:** [{gd['tag']}]\n"
                f"> **📝 Описание:** _{gd['description']}_\n> _ _\n"
                f"> **👑 Лидер:** {o_name}\n"
                f"> **💎 Вице-лидеры:**\n{viceowners_text}"
                f"> **🛡️ Офицеры:**\n{officers_text}"
                f"> **🔨 Лейтенанты:**\n{mods_text}> _ _\n"
                f"> **👥 Участников:** {cnt}/{lim}\n> **💰 Казна:** {gd.get('bank',0):,}\n"
                f"> **⚔️ Бои:** {gd.get('wins',0)}W / {gd.get('losses',0)}L\n> _ _\n"
                f"> **🎨 Цвет:** {COLORS.get(gd['color'], COLORS[DEFAULT_COLOR])['label']}\n"
                f"> **⭐ Апгрейды:**\n{upg}> 📅 Основана: {gd.get('created_at','?')}")
        
        embed = ge(f"🏰 [{gd['tag']}] {gd['name']}", desc, gd, ctx.guild)
        
        # Добавляем визуальную карточку гильдии
        try:
            image_bytes = await create_guild_card(gd, sid, ctx.guild)
            file = disnake.File(io.BytesIO(image_bytes), filename=f"guild_{gd['tag']}.png")
            embed.set_image(url=f"attachment://guild_{gd['tag']}.png")
            await ctx.send(file=file, embed=embed)
        except Exception:
            # Если ошибка с изображением, просто отправляем текст
            await ctx.send(embed=embed)

    @commands.command(name="glist")
    @commands.cooldown(*COOLDOWNS["info_light"], commands.BucketType.user)
    async def glist(self, ctx: commands.Context):
        sid = str(ctx.guild.id)
        try:
            gs = list(db["guilds"].find({"server_id": sid}))
            # Сортируем по новой системе мощи вместо только казны
            gs = sorted(gs, key=lambda g: calc_guild_power(g, sid), reverse=True)
        except Exception:
            gs = []
        if not gs:
            await ctx.send(embed=ce("Гильдии", "> **😢 Нет гильдий! Создай: `!gcreate`**", ctx.guild))
            return
        medals = ["🥇", "🥈", "🥉"]
        pages, per = [], 6
        for i in range(0, len(gs), per):
            chunk = gs[i:i + per]
            desc = ""
            for j, g in enumerate(chunk, i + 1):
                med = medals[j - 1] if j <= 3 else f"`#{j}`"
                cnt = member_count(g["id"], sid)
                lim = member_limit(g.get("upgrades", []))
                pwr = calc_guild_power(g, sid)
                em  = cat_em(g.get("color", DEFAULT_COLOR))
                desc += (f"> {med} {em} **[{g['tag']}] {g['name']}**\n"
                         f"> 👥 {cnt}/{lim} | ⚔️ {g.get('wins',0)}W | 💪 {pwr:,}\n> _ _\n")
            pages.append(desc)
        total = len(pages)
        pkey  = f"glist:{ctx.guild.id}:{ctx.author.id}:{int(datetime.utcnow().timestamp())}"
        _page_store[pkey] = pages
        _page_store[pkey + ":title"] = "📋 Гильдии ({}/{})"
        row = page_row(ctx.author.id, 0, total, pkey)
        await ctx.send(embed=ce("📋 Гильдии (1/{})".format(total), pages[0], ctx.guild),
                       components=[row] if total > 1 else [])

    @commands.command(name="gmembers")
    @commands.cooldown(*COOLDOWNS["info_light"], commands.BucketType.user)
    async def gmembers(self, ctx: commands.Context, *, tag: str = None):
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        if tag is None:
            u = get_user(uid, sid)
            if not u.get("guild_id"):
                await ctx.send(embed=ce("Участники", "> **❌ Укажи тег!**", ctx.guild, 0xFF0000))
                return
            gd = get_guild(u["guild_id"])
        else:
            gd = guild_by_tag(sid, tag)
        if not gd:
            await ctx.send(embed=ce("Участники", "> **❌ Не найдено!**", ctx.guild, 0xFF0000))
            return
        mlist = guild_members(gd["id"], sid)
        desc  = ""
        for md in mlist:
            mid  = uid_from_member_doc(md)
            mo   = ctx.guild.get_member(int(mid)) if mid else None
            name = mo.display_name if mo else f"ID:{mid}"
            desc += f"> {rank_icon(md.get('guild_rank','member'))} **{name}** — ⭐ {md.get('xp',0):,} XP\n"
        cnt = len(mlist)
        lim = member_limit(gd.get("upgrades", []))
        await ctx.send(embed=ge(f"👥 [{gd['tag']}] {gd['name']} ({cnt}/{lim})",
                                 desc or "> *Нет участников*", gd, ctx.guild))

    async def _send_invite(self, guild, inviter, member, respond_fn, error_fn):
        uid, sid = str(inviter.id), str(guild.id)
        if member.bot or member.id == inviter.id:
            await error_fn(ce("Приглашение", "> **❌ Нельзя!**", guild, 0xFF0000))
            return
        u = get_user(uid, sid)
        if not u.get("guild_id"):
            await error_fn(ce("Приглашение", "> **❌ Ты не в гильдии!**", guild, 0xFF0000))
            return
        gid = u["guild_id"]
        gd  = get_guild(gid)
        if not gd:
            return
        if uid != gd["owner_id"] and uid not in gd.get("officers", []):
            await error_fn(ce("Приглашение", "> **❌ Только лидер/офицеры приглашают!**", guild, 0xFF0000))
            return
        t = get_user(str(member.id), sid)
        if t.get("guild_id"):
            await error_fn(ce("Приглашение", f"> **❌ {member.display_name} уже в гильдии!**", guild, 0xFF0000))
            return
        cnt   = member_count(gid, sid)
        limit = member_limit(gd.get("upgrades", []))
        if cnt >= limit:
            await error_fn(ce("Приглашение", f"> **❌ Гильдия заполнена!** ({cnt}/{limit})", guild, 0xFF0000))
            return
        row   = invite_row(gid, inviter.id, member.id)
        emb   = ge(f"🌸 Приглашение в [{gd['tag']}] {gd['name']}",
                    f"> **{inviter.display_name}** приглашает тебя!\n> _ _\n"
                    f"> 📝 _{gd['description']}_\n> 👥 {cnt}/{limit}\n> _ _\n> Нажми кнопку ниже!",
                    gd, guild)
        dm_sent = False
        try:
            dm = await member.create_dm()
            await dm.send(embed=emb, components=[row])
            dm_sent = True
        except Exception:
            pass
        note = "📬 Приглашение отправлено в ЛС!" if dm_sent else "⚠️ ЛС закрыты — ответь здесь:"
        await respond_fn(
            content=member.mention,
            embed=ge(f"🌸 Приглашение в [{gd['tag']}] {gd['name']}",
                      f"> {inviter.mention} приглашает {member.mention}!\n> _{note}_\n> _ _\n"
                      f"> 📝 _{gd['description']}_\n> 👥 {cnt}/{limit}\n> **2 минуты** чтобы ответить!",
                      gd, guild),
            components=[row])

    @commands.command(name="ginvite")
    @commands.cooldown(*COOLDOWNS["guild_heavy"], commands.BucketType.user)
    async def ginvite(self, ctx: commands.Context, member: disnake.Member):
        async def respond_fn(content, embed, components):
            await ctx.send(content=content, embed=embed, components=components)
        async def error_fn(embed):
            await ctx.send(embed=embed)
        await self._send_invite(ctx.guild, ctx.author, member, respond_fn, error_fn)

    @commands.slash_command(name="ginvite", description="Пригласить участника в гильдию")
    async def ginvite_slash(self, inter: disnake.ApplicationCommandInteraction,
                             member: disnake.Member = commands.Param(description="Кого пригласить")):
        await inter.response.defer(ephemeral=False)
        async def respond_fn(content, embed, components):
            await inter.edit_original_response(content=content, embed=embed, components=components)
        async def error_fn(embed):
            await inter.edit_original_response(embed=embed)
        await self._send_invite(inter.guild, inter.author, member, respond_fn, error_fn)

    @commands.command(name="gleave")
    @commands.cooldown(*COOLDOWNS["guild_heavy"], commands.BucketType.user)
    async def gleave(self, ctx: commands.Context):
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        if not u.get("guild_id"):
            await ctx.send(embed=ce("Выход", "> **❌ Ты не в гильдии!**", ctx.guild, 0xFF0000))
            return
        gid = u["guild_id"]
        gd  = get_guild(gid)
        if not gd:
            return
        if gd["owner_id"] == uid:
            await ctx.send(embed=ce("Выход",
                                     "> **❌ Лидер не может просто уйти!**\n"
                                     "> `!gdelete` — удалить | `!gtransfer @юзер` — передать",
                                     ctx.guild, 0xFF0000))
            return
        officers = gd.get("officers", [])
        if uid in officers:
            officers.remove(uid)
            save_guild(gid, {"officers": officers})
        save_user(uid, sid, {"guild_id": None, "guild_rank": None})
        await refresh_access(ctx.guild, gd, ctx.author, remove=True)
        
        # 🏅 Убираем роль гильдии
        guild_role_id = gd.get("guild_role_id")
        if guild_role_id:
            guild_role = ctx.guild.get_role(guild_role_id)
            if guild_role and guild_role in ctx.author.roles:
                try:
                    await ctx.author.remove_roles(guild_role, reason=f"Выход из гильдии {gd['tag']}")
                except Exception as e:
                    print(f"[gleave] Ошибка при удалении роли: {e}")
        
        try:
            if ctx.author.display_name.startswith("["):
                clean = ctx.author.display_name.split("]", 1)[1].strip()
                await ctx.author.edit(nick=clean or None)
        except Exception:
            pass
        await ctx.send(embed=ce("👋 Выход",
                                 f"> {ctx.author.mention} покинул(а) **[{gd['tag']}] {gd['name']}**.",
                                 ctx.guild, 0x888888))

    @commands.command(name="gkick")
    @commands.cooldown(*COOLDOWNS["guild_heavy"], commands.BucketType.user)
    async def gkick(self, ctx: commands.Context, member: disnake.Member):
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        if not u.get("guild_id"):
            await ctx.send(embed=ce("Кик", "> **❌ Ты не в гильдии!**", ctx.guild, 0xFF0000))
            return
        gid = u["guild_id"]
        gd  = get_guild(gid)
        if uid != gd["owner_id"] and uid not in gd.get("officers", []):
            await ctx.send(embed=ce("Кик", "> **❌ Нет прав!**", ctx.guild, 0xFF0000))
            return
        t_uid = str(member.id)
        t = get_user(t_uid, sid)
        if t.get("guild_id") != gid:
            await ctx.send(embed=ce("Кик", f"> **❌ {member.display_name} не в вашей гильдии!**",
                                     ctx.guild, 0xFF0000))
            return
        if t_uid == gd["owner_id"]:
            await ctx.send(embed=ce("Кик", "> **❌ Нельзя кикнуть лидера!**", ctx.guild, 0xFF0000))
            return
        officers = gd.get("officers", [])
        if t_uid in officers:
            officers.remove(t_uid)
            save_guild(gid, {"officers": officers})
        save_user(t_uid, sid, {"guild_id": None, "guild_rank": None})
        await refresh_access(ctx.guild, gd, member, remove=True)
        
        # 🏅 Убираем роль гильдии
        guild_role_id = gd.get("guild_role_id")
        if guild_role_id:
            guild_role = ctx.guild.get_role(guild_role_id)
            if guild_role and guild_role in member.roles:
                try:
                    await member.remove_roles(guild_role, reason=f"Кик из гильдии {gd['tag']}")
                except Exception as e:
                    print(f"[gkick] Ошибка при удалении роли: {e}")
        
        try:
            if member.display_name.startswith("["):
                clean = member.display_name.split("]", 1)[1].strip()
                await member.edit(nick=clean or None)
        except Exception:
            pass
        await ctx.send(embed=ce("👢 Кик",
                                 f"> {member.mention} исключён(а) из **[{gd['tag']}]**.",
                                 ctx.guild, 0xFF4444))

    @commands.command(name="gpromote")
    @commands.cooldown(*COOLDOWNS["rank_ops"], commands.BucketType.user)
    async def gpromote(self, ctx: commands.Context, member: disnake.Member):
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        if not u.get("guild_id"):
            await ctx.send(embed=ce("Повышение", "> **❌ Ты не в гильдии!**", ctx.guild, 0xFF0000))
            return
        gid = u["guild_id"]
        gd  = get_guild(gid)
        if u.get("guild_rank") not in ["owner", "viceowner"]:
            await ctx.send(embed=ce("Повышение", "> **❌ Только лидер/вице-лидер!**", ctx.guild, 0xFF0000))
            return
        t_uid = str(member.id)
        t = get_user(t_uid, sid)
        if t.get("guild_id") != gid:
            await ctx.send(embed=ce("Повышение", f"> **❌ {member.display_name} не в вашей гильдии!**",
                                     ctx.guild, 0xFF0000))
            return
        ladder = ["recruit", "member", "moderator", "officer", "viceowner", "owner"]
        cur_rank = t.get("guild_rank", "recruit")
        if cur_rank == "owner":
            await ctx.send(embed=ce("Повышение", "> **❌ Максимальный ранг!**", ctx.guild, 0xFF0000))
            return
        idx = ladder.index(cur_rank) if cur_rank in ladder else 0
        new_rank = ladder[min(idx + 1, len(ladder) - 1)]
        save_user(t_uid, sid, {"guild_rank": new_rank})
        rd = GUILD_RANKS[new_rank]
        await ctx.send(embed=ge("🔼 Повышение",
                                 f"> {member.mention} → **{rd['icon']} {rd['name']}**!", gd, ctx.guild))

    @commands.command(name="gdemote")
    @commands.cooldown(*COOLDOWNS["rank_ops"], commands.BucketType.user)
    async def gdemote(self, ctx: commands.Context, member: disnake.Member):
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        if not u.get("guild_id"):
            await ctx.send(embed=ce("Понижение", "> **❌ Ты не в гильдии!**", ctx.guild, 0xFF0000))
            return
        gid = u["guild_id"]
        gd  = get_guild(gid)
        if u.get("guild_rank") not in ["owner", "viceowner"]:
            await ctx.send(embed=ce("Понижение", "> **❌ Только лидер/вице-лидер!**", ctx.guild, 0xFF0000))
            return
        t_uid = str(member.id)
        t = get_user(t_uid, sid)
        if t.get("guild_id") != gid:
            await ctx.send(embed=ce("Понижение", f"> **❌ {member.display_name} не в вашей гильдии!**",
                                     ctx.guild, 0xFF0000))
            return
        ladder = ["recruit", "member", "moderator", "officer", "viceowner", "owner"]
        cur_rank = t.get("guild_rank", "member")
        if cur_rank == "recruit":
            await ctx.send(embed=ce("Понижение", "> **❌ Минимальный ранг!**", ctx.guild, 0xFF0000))
            return
        idx = ladder.index(cur_rank) if cur_rank in ladder else 1
        new_rank = ladder[max(idx - 1, 0)]
        save_user(t_uid, sid, {"guild_rank": new_rank})
        rd = GUILD_RANKS[new_rank]
        await ctx.send(embed=ge("🔽 Понижение",
                                 f"> {member.mention} → **{rd['icon']} {rd['name']}**.", gd, ctx.guild))

    @commands.command(name="gtransfer")
    @commands.cooldown(*COOLDOWNS["super_heavy"], commands.BucketType.user)
    async def gtransfer(self, ctx: commands.Context, member: disnake.Member):
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        if not u.get("guild_id"):
            await ctx.send(embed=ce("Передача", "> **❌ Ты не в гильдии!**", ctx.guild, 0xFF0000))
            return
        gid = u["guild_id"]
        gd  = get_guild(gid)
        if gd["owner_id"] != uid:
            await ctx.send(embed=ce("Передача", "> **❌ Только лидер!**", ctx.guild, 0xFF0000))
            return
        t_uid = str(member.id)
        t = get_user(t_uid, sid)
        if t.get("guild_id") != gid:
            await ctx.send(embed=ce("Передача", f"> **❌ {member.display_name} не в вашей гильдии!**",
                                     ctx.guild, 0xFF0000))
            return
        if t_uid == uid:
            await ctx.send(embed=ce("Передача", "> **❌ Ты уже лидер!**", ctx.guild, 0xFF0000))
            return
        officers = gd.get("officers", [])
        if t_uid in officers:
            officers.remove(t_uid)
        save_guild(gid, {"owner_id": t_uid, "officers": officers})
        save_user(uid, sid, {"guild_rank": "member"})
        save_user(t_uid, sid, {"guild_rank": "owner"})
        await ctx.send(embed=ge("👑 Передача лидерства",
                                 f"> {ctx.author.mention} передал(а) корону {member.mention}!\n"
                                 f"> Новый лидер: {member.mention}", gd, ctx.guild))

    @commands.command(name="granks")
    @commands.cooldown(*COOLDOWNS["info_light"], commands.BucketType.user)
    async def granks(self, ctx: commands.Context):
        e = ce("📊 Система Рангов", "Ранги дают бонусы к XP и монетам за сообщения:", ctx.guild, 0x9370DB)
        for rk in ["recruit", "member", "moderator", "officer", "viceowner", "owner"]:
            rd = GUILD_RANKS.get(rk)
            if rd:
                e.add_field(name=f"{rd['icon']} {rd['name']}",
                            value=f"XP ×{rd['xp_bonus']} | Монеты ×{rd['coin_bonus']}", inline=False)
        await ctx.send(embed=e)

    @commands.command(name="gcolor")
    @commands.cooldown(*COOLDOWNS["eco_medium"], commands.BucketType.user)
    async def gcolor(self, ctx: commands.Context, color: str = None):
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        if not u.get("guild_id"):
            await ctx.send(embed=ce("Цвет", "> **❌ Ты не в гильдии!**", ctx.guild, 0xFF0000))
            return
        gid = u["guild_id"]
        gd  = get_guild(gid)
        if uid != gd["owner_id"] and uid not in gd.get("officers", []):
            await ctx.send(embed=ce("Цвет", "> **❌ Нет прав!**", ctx.guild, 0xFF0000))
            return
        if not color or color.lower() not in COLORS:
            avail = " | ".join(f"`{k}` {v['label']}" for k, v in COLORS.items())
            await ctx.send(embed=ce("🎨 Цвета", f"> {avail}\n> `!gcolor <цвет>`", ctx.guild))
            return
        gd["color"] = color.lower()
        save_guild(gid, {"color": color.lower()})
        owner = ctx.guild.get_member(int(gd["owner_id"])) or ctx.author
        msg = await ctx.send(embed=ce("⏳", "> Пересоздаю каналы...", ctx.guild))
        await rebuild(ctx.guild, gd, owner)
        ci = COLORS[color.lower()]
        await msg.edit(embed=ce("🎨 Цвет обновлён!", f"> **[{gd['tag']}]** → {ci['label']}", ctx.guild, ci["hex"]))

    @commands.command(name="gdesc")
    @commands.cooldown(*COOLDOWNS["eco_medium"], commands.BucketType.user)
    async def gdesc(self, ctx: commands.Context, *, text: str):
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        if not u.get("guild_id"):
            await ctx.send(embed=ce("Описание", "> **❌ Ты не в гильдии!**", ctx.guild, 0xFF0000))
            return
        gid = u["guild_id"]
        gd  = get_guild(gid)
        if uid != gd["owner_id"] and uid not in gd.get("officers", []):
            await ctx.send(embed=ce("Описание", "> **❌ Нет прав!**", ctx.guild, 0xFF0000))
            return
        if len(text) > 100:
            await ctx.send(embed=ce("Описание", "> **❌ Максимум 100 символов!**", ctx.guild, 0xFF0000))
            return
        save_guild(gid, {"description": text})
        gd["description"] = text
        await ctx.send(embed=ge("✏️ Описание обновлено", f"> _{text}_", gd, ctx.guild))

    @commands.command(name="gdeposit", aliases=["gdep"])
    @commands.cooldown(*COOLDOWNS["eco_medium"], commands.BucketType.user)
    async def gdeposit(self, ctx: commands.Context, amount: int):
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        if not u.get("guild_id"):
            await ctx.send(embed=ce("Казна", "> **❌ Ты не в гильдии!**", ctx.guild, 0xFF0000))
            return
        if amount <= 0:
            await ctx.send(embed=ce("Казна", "> **❌ Сумма > 0**", ctx.guild, 0xFF0000))
            return
        if u.get("coins", 0) < amount:
            await ctx.send(embed=ce("Казна", f"> **❌ Не хватает монет!** У тебя: {u.get('coins',0):,}",
                                     ctx.guild, 0xFF0000))
            return
        gid = u["guild_id"]
        gd  = get_guild(gid)
        new_bank = gd.get("bank", 0) + amount
        save_guild(gid, {"bank": new_bank})
        save_user(uid, sid, {"coins": u.get("coins", 0) - amount})
        gd["bank"] = new_bank
        
        # 📈 Добавляем XP за вклад (1 XP за 100 монет)
        xp_gain = amount // 100
        if xp_gain > 0:
            add_guild_xp(gid, xp_gain)
        
        await ctx.send(embed=ge("💰 Взнос в казну",
                                 f"> 💸 **+{amount:,}**\n> 🏦 Казна: **{new_bank:,}**", gd, ctx.guild))

    @commands.command(name="gwithdraw", aliases=["gwith"])
    @commands.cooldown(*COOLDOWNS["eco_medium"], commands.BucketType.user)
    async def gwithdraw(self, ctx: commands.Context, amount: int):
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        if not u.get("guild_id"):
            await ctx.send(embed=ce("Казна", "> **❌ Ты не в гильдии!**", ctx.guild, 0xFF0000))
            return
        gid = u["guild_id"]
        gd  = get_guild(gid)
        if gd["owner_id"] != uid:
            await ctx.send(embed=ce("Казна", "> **❌ Только лидер!**", ctx.guild, 0xFF0000))
            return
        if amount <= 0 or gd.get("bank", 0) < amount:
            await ctx.send(embed=ce("Казна",
                                     f"> **❌ Недостаточно в казне!** {gd.get('bank',0):,}",
                                     ctx.guild, 0xFF0000))
            return
        new_bank = gd.get("bank", 0) - amount
        save_guild(gid, {"bank": new_bank})
        save_user(uid, sid, {"coins": u.get("coins", 0) + amount})
        gd["bank"] = new_bank
        await ctx.send(embed=ge("💸 Вывод", f"> **-{amount:,}**\n> Казна: **{new_bank:,}**", gd, ctx.guild))

    @commands.command(name="gupgrade")
    @commands.cooldown(*COOLDOWNS["eco_medium"], commands.BucketType.user)
    async def gupgrade(self, ctx: commands.Context, upg_id: str = None):
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        if not u.get("guild_id"):
            await ctx.send(embed=ce("Апгрейды", "> **❌ Ты не в гильдии!**", ctx.guild, 0xFF0000))
            return
        gid = u["guild_id"]
        gd  = get_guild(gid)
        if not upg_id:
            desc = "> **Доступные апгрейды:**\n> _ _\n"
            for k, upg in GUILD_UPGRADES.items():
                owned = " ✅" if k in gd.get("upgrades", []) else ""
                desc += f"> {upg['emoji']} **{upg['name']}**{owned} — {upg['price']:,} | ID:`{k}`\n> _ _\n"
            desc += f"> 💰 **Казна:** {gd.get('bank',0):,}\n> Пример: `!gupgrade slot_1`"
            await ctx.send(embed=ge("⭐ Апгрейды", desc, gd, ctx.guild))
            return
        if uid != gd["owner_id"] and uid not in gd.get("officers", []):
            await ctx.send(embed=ce("Апгрейды", "> **❌ Нет прав!**", ctx.guild, 0xFF0000))
            return
        if upg_id not in GUILD_UPGRADES:
            await ctx.send(embed=ce("Апгрейды", f"> **❌ `{upg_id}` не найден!**", ctx.guild, 0xFF0000))
            return
        if upg_id in gd.get("upgrades", []):
            await ctx.send(embed=ce("Апгрейды", "> **❌ Уже куплен!**", ctx.guild, 0xFF0000))
            return
        upg  = GUILD_UPGRADES[upg_id]
        bank = gd.get("bank", 0)
        if bank < upg["price"]:
            await ctx.send(embed=ce("Апгрейды",
                                     f"> **❌ Не хватает!** Казна: {bank:,} | Нужно: {upg['price']:,}",
                                     ctx.guild, 0xFF0000))
            return
        new_bank = bank - upg["price"]
        upgrades = gd.get("upgrades", []) + [upg_id]
        save_guild(gid, {"bank": new_bank, "upgrades": upgrades})
        gd["bank"] = new_bank
        gd["upgrades"] = upgrades
        
        # 📈 Добавляем XP за апгрейд (200 XP за апгрейд)
        add_guild_xp(gid, 200)
        
        await ctx.send(embed=ge("⭐ Апгрейд куплен!",
                                 f"> {upg['emoji']} **{upg['name']}**\n> Казна: **{new_bank:,}**", gd, ctx.guild))

    @commands.command(name="gbank", aliases=["gvault", "gcashbox"])
    @commands.cooldown(*COOLDOWNS["info_light"], commands.BucketType.user)
    async def gbank(self, ctx: commands.Context, *, tag: str = None):
        """Просмотр казны гильдии с полной статистикой"""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        
        if tag is None:
            if not u.get("guild_id"):
                await ctx.send(embed=ce("Казна", "> **❌ Ты не в гильдии!**\n> Укажи тег: `!gbank <тег>`",
                                        ctx.guild, 0xFF0000))
                return
            gd = get_guild(u["guild_id"])
        else:
            gd = guild_by_tag(sid, tag)
        
        if not gd:
            await ctx.send(embed=ce("Казна", "> **❌ Гильдия не найдена!**", ctx.guild, 0xFF0000))
            return
        
        bank = gd.get("bank", 0)
        members = guild_members(gd["id"], sid)
        member_count_val = len(members)
        wins = gd.get("wins", 0)
        losses = gd.get("losses", 0)
        
        # Считаем доход членов от ферм
        total_member_income = 0
        if INCOME_SOURCES:
            for member in members:
                farms = member.get("farms", [])
                member_income = get_income_per_hour(farms, gd.get("upgrades", []))
                total_member_income += member_income
        
        # Бонусы
        vault_bonus = get_guild_vault_bonus(gd.get("upgrades", []))
        income_bonus_pct = 0
        for upg_key in gd.get("upgrades", []):
            if upg_key in GUILD_INCOME_UPGRADES:
                upg = GUILD_INCOME_UPGRADES[upg_key]
                if "bonus_percent" in upg and "contribution_bonus_percent" not in upg:
                    income_bonus_pct = max(income_bonus_pct, upg["bonus_percent"])
        
        desc = (f"> **💰 КАЗНА:** {bank:,} монет\n> _ _\n"
                f"> **👥 Участников:** {member_count_val}\n"
                f"> **⚔️ Рекорд:** {wins}W / {losses}L\n> _ _\n")
        
        if total_member_income > 0:
            daily_income = total_member_income * 24 * member_count_val
            desc += (f"> **🌾 ДОХОД ОТ ФЕРМ:**\n"
                    f"> • По часам: +{total_member_income:,}/ч (все члены)\n"
                    f"> • В день: ~+{daily_income:,}/день\n> _ _\n")
        
        if gd.get("upgrades"):
            upg_text = ""
            for upg_key in gd.get("upgrades", []):
                if upg_key in GUILD_UPGRADES:
                    upg = GUILD_UPGRADES[upg_key]
                    upg_text += f"> {upg['emoji']} {upg['name']}\n"
            if upg_text:
                desc += f"> **⭐ АПГРЕЙДЫ:**\n{upg_text}> _ _\n"
        
        if total_member_income > 0 or income_bonus_pct > 0:
            desc += f"> **📈 БОНУСЫ:**\n> • Доход членов: +{income_bonus_pct}%\n> • Взнос в казну: +{(vault_bonus-1)*100:.0f}%\n> _ _\n"
        
        desc += f"> **💡 Совет:** Используй `!gupgrade` для улучшения"
        
        await ctx.send(embed=ge(f"🏦 Казна [{gd['tag']}] {gd['name']}", desc, gd, ctx.guild))

    @commands.command(name="geconomy", aliases=["gecon", "gstas"])
    @commands.cooldown(*COOLDOWNS["info_light"], commands.BucketType.user)
    async def geconomy(self, ctx: commands.Context, *, tag: str = None):
        """Полная статистика экономики гильдии"""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        
        if tag is None:
            if not u.get("guild_id"):
                await ctx.send(embed=ce("Экономика", "> **❌ Ты не в гильдии!**",
                                        ctx.guild, 0xFF0000))
                return
            gd = get_guild(u["guild_id"])
        else:
            gd = guild_by_tag(sid, tag)
        
        if not gd:
            await ctx.send(embed=ce("Экономика", "> **❌ Гильдия не найдена!**", ctx.guild, 0xFF0000))
            return
        
        members = guild_members(gd["id"], sid)
        
        # Анализируем членов по уровню и ферм
        member_stats = []
        total_member_xp = 0
        total_member_coins = 0
        total_farms = 0
        total_member_income = 0
        
        for member in members:
            xp = member.get("xp", 0)
            coins = member.get("coins", 0)
            lvl = member.get("level", 1)
            farms = member.get("farms", [])
            
            total_member_xp += xp
            total_member_coins += coins
            total_farms += len(farms)
            
            if INCOME_SOURCES:
                member_income = get_income_per_hour(farms, gd.get("upgrades", []))
                total_member_income += member_income
        
        avg_lvl = sum(m.get("level", 1) for m in members) / max(1, len(members))
        
        bank = gd.get("bank", 0)
        total_assets = bank + total_member_coins
        
        desc = (f"> **💰 ФИНАНСОВЫЙ ОТЧЕТ:**\n"
                f"> • Казна: **{bank:,}** монет\n"
                f"> • У членов: ~**{total_member_coins:,}** монет\n"
                f"> • **Всего активов: {total_assets:,}** монет\n> _ _\n"
                f"> **👥 ЧЛЕНЫ:**\n"
                f"> • Количество: **{len(members)}** /(15-50)\n"
                f"> • Средний ур.: **{avg_lvl:.1f}**\n"
                f"> • Общий XP: **{total_member_xp:,}**\n> _ _\n")
        
        if INCOME_SOURCES and total_farms > 0:
            daily_passive = total_member_income * 24
            hourly_contribution = int(total_member_income * 0.01)  # 1% в казну
            monthly_passive = daily_passive * 30
            desc += (f"> **🌾 ПАССИВНЫЙ ДОХОД:**\n"
                    f"> • Ферм активно: **{total_farms}**\n"
                    f"> • В час: **{total_member_income:,}** монет\n"
                    f"> • В день: **{daily_passive:,}** монет\n"
                    f"> • В месяц: **~{monthly_passive:,}** монет\n"
                    f"> • В казну/час: **~{hourly_contribution:,}** монет\n> _ _\n")
        
        # Апгрейды
        if gd.get("upgrades"):
            upg_cost = sum(GUILD_UPGRADES.get(upg_key, {}).get("price", 0) for upg_key in gd.get("upgrades", []))
            income_bonus = 0
            for upg_key in gd.get("upgrades", []):
                if upg_key in GUILD_INCOME_UPGRADES:
                    upg_data = GUILD_INCOME_UPGRADES[upg_key]
                    if "bonus_percent" in upg_data and "contribution_bonus_percent" not in upg_data:
                        income_bonus = max(income_bonus, upg_data["bonus_percent"])
            
            desc += (f"> **⭐ ИНВЕСТИЦИИ:**\n"
                    f"> • Апгрейдов куплено: **{len(gd.get('upgrades', []))}**\n"
                    f"> • Вложено всего: **{upg_cost:,}** монет\n"
                    f"> • Бонус доходу: **+{income_bonus}%**\n> _ _\n")
        
        # Нужно для следующего апгрейда
        next_upg = None
        for upg_id, upg in GUILD_UPGRADES.items():
            if upg_id not in gd.get("upgrades", []):
                next_upg = (upg_id, upg)
                break
        
        if next_upg:
            desc += (f"> **🎯 СЛЕДУЮЩИЙ АПГРЕЙД:**\n"
                    f"> {next_upg[1]['emoji']} **{next_upg[1]['name']}**\n"
                    f"> Стоимость: **{next_upg[1]['price']:,}** монет\n"
                    f"> Нужны еще: **{max(0, next_upg[1]['price'] - bank):,}** монет")
        else:
            desc += "> **✅ Все апгрейды куплены! Вы легенды! 🏆**"
        
        await ctx.send(embed=ge(f"📊 Экономика [{gd['tag']}]", desc, gd, ctx.guild))

    @commands.command(name="gmyincome")
    @commands.cooldown(*COOLDOWNS["info_light"], commands.BucketType.user)
    async def gmyincome(self, ctx: commands.Context):
        """Твой личный пассивный доход от ферм"""
        if not INCOME_SOURCES:
            await ctx.send(embed=ce("Доход", "> **❌ Система ферм недоступна**", ctx.guild, 0xFF0000))
            return
        
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        farms = u.get("farms", [])
        
        if not farms:
            await ctx.send(embed=ce("🌾 Мой доход", "> **❌ У тебя нет ферм!**\n> Купи: `!buyfarm`",
                                    ctx.guild, 0xFF8800))
            return
        
        gd = get_guild(u.get("guild_id")) if u.get("guild_id") else None
        guild_upgrades = gd.get("upgrades", []) if gd else []
        
        hourly = get_income_per_hour(farms, guild_upgrades)
        daily = hourly * 24
        monthly = daily * 30
        
        vault_bonus = get_guild_vault_bonus(guild_upgrades) if gd else 1.0
        guild_contribution = int(hourly * 0.01) if gd else 0
        player_gets = hourly - guild_contribution
        
        desc = (f"> **⏰ ТВОЙ ПАССИВНЫЙ ДОХОД:**\n> _ _\n"
                f"> 🌾 Всего ферм: **{len(farms)}**\n"
                f"> 📈 Доход в час: **{hourly:,}** монет\n> _ _\n"
                f"> **Без апгрейдов:**\n"
                f"> • В день: **{daily:,}** монет\n"
                f"> • В месяц: **~{monthly:,}** монет\n> _ _\n")
        
        if gd:
            daily_with_contribution = (player_gets * 24) if guild_contribution > 0 else daily
            monthly_with_contribution = daily_with_contribution * 30
            desc += (f"> **С учётом взносов в казну:**\n"
                    f"> • Тебе за час: **{player_gets:,}** монет\n"
                    f"> • В казну гильдии: **{guild_contribution:,}** монет\n"
                    f"> • Тебе в день: **{player_gets * 24:,}** монет\n"
                    f"> • Тебе в месяц: **~{player_gets * 24 * 30:,}** монет\n> _ _\n"
                    f"> 💡 Бонус казны: **+{(vault_bonus-1)*100:.0f}%**")
        
        await ctx.send(embed=ce("🌾 Твой пассивный доход", desc, ctx.guild, 0x2ECC71))

    @commands.command(name="gwar")
    @commands.cooldown(*COOLDOWNS["wars"], commands.BucketType.user)
    async def gwar(self, ctx: commands.Context, *, tag: str):
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        if not u.get("guild_id"):
            await ctx.send(embed=ce("Война", "> **❌ Ты не в гильдии!**", ctx.guild, 0xFF0000))
            return
        gid = u["guild_id"]
        gd  = get_guild(gid)
        if gd["owner_id"] != uid:
            await ctx.send(embed=ce("Война", "> **❌ Только лидер объявляет войну!**", ctx.guild, 0xFF0000))
            return
        enemy = guild_by_tag(sid, tag)
        if not enemy:
            await ctx.send(embed=ce("Война", f"> **❌ [{tag.upper()}] не найдена!**", ctx.guild, 0xFF0000))
            return
        if enemy["id"] == gid:
            await ctx.send(embed=ce("Война", "> **❌ Нельзя воевать с собой!**", ctx.guild, 0xFF0000))
            return
        
        # ⚔️ УЛУЧШЕННЫЙ РАСЧЕТ МОЩИ
        my_members = member_count(gid, sid)
        en_members = member_count(enemy["id"], sid)
        
        my_base = gd.get("bank", 0) + my_members * 1000
        en_base = enemy.get("bank", 0) + en_members * 1000
        
        my_p = my_base + random.randint(-2000, 5000)
        en_p = en_base + random.randint(-2000, 5000)
        
        # Эмодзи для боя
        my_emoji = "🌸"
        en_emoji = "⚔️"
        
        # Начало боя
        wmsg = await ctx.send(embed=ce("🌸 ВОЙНА ГИЛЬДИЙ! ⚔️",
                                        f"> **[{gd['tag']}] {gd['name']}** ({my_members} чел)\n"
                                        f"> vs\n"
                                        f"> **[{enemy['tag']}] {enemy['name']}** ({en_members} чел)\n"
                                        f"> _ _\n"
                                        f"> 🎖️ Мощь:\n"
                                        f"> {my_emoji} {my_p:,} | {en_emoji} {en_p:,}\n"
                                        f"> _ _\n> ⚡ Боевые раунды...", ctx.guild, 0xFF6B9D))
        
        # 🎭 БОЕВЫЕ РАУНДЫ
        my_hp = 100
        en_hp = 100
        round_num = 1
        
        for _ in range(5):
            await asyncio.sleep(2)
            
            # Урон в этом раунде
            my_dmg = random.randint(int(my_p * 0.2), int(my_p * 0.4))
            en_dmg = random.randint(int(en_p * 0.2), int(en_p * 0.4))
            
            my_hp = max(0, my_hp - en_dmg // 1000)
            en_hp = max(0, en_hp - my_dmg // 1000)
            
            # Показываем раунд
            round_text = (
                f"> **📍 Раунд {round_num}/5**\n> _ _\n"
                f"> {my_emoji} [{gd['tag']}] HP: {my_hp}/100\n"
                f"> {en_emoji} [{enemy['tag']}] HP: {en_hp}/100\n"
                f"> _ _\n"
                f"> 💥 Урон: {my_dmg:,} ↔️ {en_dmg:,}"
            )
            
            await wmsg.edit(embed=ce("🌸 БОЙ ИДЕТ! ⚔️", round_text, ctx.guild, 0xFF6B9D))
            round_num += 1
            
            if my_hp <= 0 or en_hp <= 0:
                break
        
        # 🏆 РЕЗУЛЬТАТ
        winner = gd if en_hp <= 0 else enemy
        loser = enemy if en_hp <= 0 else gd
        
        prize = min(loser.get("bank", 0) // 5, 25_000)
        
        save_guild(winner["id"], {
            "bank": winner.get("bank", 0) + prize, 
            "wins": winner.get("wins", 0) + 1
        })
        save_guild(loser["id"], {
            "bank": max(0, loser.get("bank", 0) - prize), 
            "losses": loser.get("losses", 0) + 1
        })
        
        # 📈 Добавляем XP за победу
        add_guild_xp(winner["id"], 500)  # Победитель получает 500 XP
        add_guild_xp(loser["id"], 100)   # Проигравший получает 100 XP за участие
        
        wr = get_guild(winner["id"])
        lr = get_guild(loser["id"])
        
        result_text = (
            f"> 🏆 **ПОБЕДИТЕЛЬ: [{winner['tag']}] {winner['name']}!**\n"
            f"> _ _\n"
            f"> 💰 Трофей: **+{prize:,} монет**\n"
            f"> 💀 Потеря противника: **-{prize:,} монет**\n"
            f"> _ _\n"
            f"> 📊 **Статистика:**\n"
            f"> 🥇 [{winner['tag']}]: {wr.get('wins', 0)} побед\n"
            f"> ☠️ [{loser['tag']}]: {lr.get('losses', 0)} поражений"
        )
        
        await wmsg.edit(embed=ce(
            "🌸 ВОЙНА ЗАВЕРШЕНА! ⚔️" if winner == gd else "⚔️ ВОЙНА ЗАВЕРШЕНА! 🌸",
            result_text, ctx.guild, 0xFFD700))

    @commands.command(name="gstats")
    async def gstats(self, ctx: commands.Context, *, tag: str = None):
        """📊 Полная статистика гильдии"""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        if tag is None:
            u = get_user(uid, sid)
            if not u.get("guild_id"):
                await ctx.send(embed=ce("📊", "> **❌ Укажи тег или состой в гильдии!**", ctx.guild, 0xFF0000), delete_after=10)
                return
            gd = get_guild(u["guild_id"])
        else:
            gd = guild_by_tag(sid, tag)
        
        if not gd:
            await ctx.send(embed=ce("📊", f"> **❌ [{tag.upper() if tag else '?'}] не найдена!**", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        cnt = member_count(gd["id"], sid)
        lim = member_limit(gd.get("upgrades", []))
        pwr = calc_guild_power(gd, sid)
        
        desc = (
            f"> 📛 **Название:** {gd['name']}\n"
            f"> 🏷️ **Тег:** [{gd['tag']}]\n"
            f"> 👑 **Лидер:** <@{gd['owner_id']}>\n"
            f"> _ _\n"
            f"> 👥 **Члены:** {cnt}/{lim}\n"
            f"> 💰 **Казна:** {gd.get('bank', 0):,}\n"
            f"> 💪 **Мощь:** {pwr:,}\n"
            f"> _ _\n"
            f"> 🏆 **Побед:** {gd.get('wins', 0)}\n"
            f"> 💀 **Поражений:** {gd.get('losses', 0)}\n"
            f"> 🔧 **Апгрейдов:** {len(gd.get('upgrades', []))}\n"
            f"> _ _\n"
            f"> 📝 **Описание:** {gd.get('description', 'Нет')}"
        )
        
        embed = disnake.Embed(title=f"📊 [{gd['tag']}] {gd['name']} — Статистика", 
                              description=desc, color=COLORS.get(gd.get("color"), COLORS[DEFAULT_COLOR]).get("hex", 0xFF69B4))
        
        # Добавляем визуальную карточку гильдии
        try:
            image_bytes = await create_guild_card(gd, sid, ctx.guild)
            file = disnake.File(io.BytesIO(image_bytes), filename=f"guild_{gd['tag']}.png")
            embed.set_image(url=f"attachment://guild_{gd['tag']}.png")
            await ctx.send(file=file, embed=embed)
        except Exception:
            # Если ошибка с изображением, просто отправляем текст
            await ctx.send(embed=embed)

    @commands.command(name="granking")
    async def granking(self, ctx: commands.Context, sort_by: str = "power"):
        """🏅 Рейтинг гильдий по разным критериям: power|wins|members|bank"""
        sid = str(ctx.guild.id)
        try:
            gs = list(db["guilds"].find({"server_id": sid}))
        except Exception:
            gs = []
        
        if not gs:
            await ctx.send(embed=ce("🏅", "> **Гильдий нет!**", ctx.guild), delete_after=10)
            return
        
        sort_by = sort_by.lower()
        if sort_by == "power":
            gs = sorted(gs, key=lambda g: calc_guild_power(g, sid), reverse=True)
            title_sort = "💪 По Мощи"
        elif sort_by == "wins":
            gs = sorted(gs, key=lambda g: g.get("wins", 0), reverse=True)
            title_sort = "🏆 По Победам"
        elif sort_by == "members":
            gs = sorted(gs, key=lambda g: member_count(g["id"], sid), reverse=True)
            title_sort = "👥 По Членам"
        elif sort_by == "bank":
            gs = sorted(gs, key=lambda g: g.get("bank", 0), reverse=True)
            title_sort = "💰 По Казне"
        else:
            gs = sorted(gs, key=lambda g: calc_guild_power(g, sid), reverse=True)
            title_sort = "💪 По Мощи"
        
        desc = ""
        medals = ["🥇", "🥈", "🥉"]
        for j, g in enumerate(gs[:10], 1):
            med = medals[j - 1] if j <= 3 else f"`#{j}`"
            cnt = member_count(g["id"], sid)
            pwr = calc_guild_power(g, sid)
            
            if sort_by == "power":
                stat = f"💪 {pwr:,}"
            elif sort_by == "wins":
                stat = f"🏆 {g.get('wins', 0)} побед"
            elif sort_by == "members":
                stat = f"👥 {cnt} чел"
            else:
                stat = f"💰 {g.get('bank', 0):,}"
            
            desc += f"> {med} **[{g['tag']}] {g['name']}** — {stat}\n"
        
        embed = disnake.Embed(title=f"🏅 Рейтинг {title_sort}", description=desc, color=0xFF69B4)
        await ctx.send(embed=embed)

    @commands.command(name="gtribute")
    @commands.cooldown(1, 3600, commands.BucketType.user)  # 1 раз в час
    async def gtribute(self, ctx: commands.Context, amount: int):
        """💝 Пожертвовать денег в казну гильдии"""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        
        if not u.get("guild_id"):
            await ctx.send(embed=ce("💝", "> **❌ Ты не в гильдии!**", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        if amount <= 0:
            await ctx.send(embed=ce("💝", "> **❌ Сумма должна быть больше 0!**", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        if coins < amount:
            await ctx.send(embed=ce("❌ Не хватает монет", 
                                     f"> Нужно **{amount:,}**, а у тебя **{coins:,}**",
                                     ctx.guild, 0xFF0000), delete_after=10)
            return
        
        gd = get_guild(u["guild_id"])
        new_coins = coins - amount
        new_bank = gd.get("bank", 0) + amount
        
        save_user(uid, sid, {"coins": new_coins})
        save_guild(gd["id"], {"bank": new_bank})
        
        desc = (
            f"> **[{gd['tag']}] {gd['name']}**\n"
            f"> _ _\n"
            f"> 💝 **+{amount:,}** монет в казну!\n"
            f"> 💰 Новый баланс казны: **{new_bank:,}**\n"
            f"> _ _\n"
            f"> Твой баланс: **{new_coins:,}**"
        )
        
        await ctx.send(embed=ce("💝 Пожертвование", desc, ctx.guild, 0x00FF00))

    @commands.command(name="glevel")
    async def glevel(self, ctx: commands.Context, *, tag: str = None):
        """📈 Показать уровень и прогресс гильдии"""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        
        if tag is None:
            u = get_user(uid, sid)
            if not u.get("guild_id"):
                await ctx.send(embed=ce("📈", "> **❌ Укажи тег или состой в гильдии!**", ctx.guild, 0xFF0000), delete_after=10)
                return
            gd = get_guild(u["guild_id"])
        else:
            gd = guild_by_tag(sid, tag)
        
        if not gd:
            await ctx.send(embed=ce("📈", f"> **❌ Гильдия не найдена!**", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        level, xp, xp_needed = calc_guild_level(gd, sid)
        pwr = calc_guild_power(gd, sid)
        
        # Прогресс-бар XP
        xp_bar = pbar(xp, xp_needed)
        
        # Бонусы за уровень
        level_bonus = {
            "members_bonus": level * 5,
            "bank_bonus_percent": level * 2,
            "power_bonus": level * 100
        }
        
        desc = (
            f"> 📛 **Гильдия:** [{gd['tag']}] {gd['name']}\n"
            f"> _ _\n"
            f"> 📊 **Уровень:** {level}\n"
            f"> ⭐ **Опыт:** {xp:,}/{xp_needed:,}\n"
            f"> [{xp_bar}]\n"
            f"> _ _\n"
            f"> 💪 **Мощь:** +{level_bonus['power_bonus']:,}\n"
            f"> 👥 **Доп. слотов:** +{level_bonus['members_bonus']}\n"
            f"> 💰 **Вознагр. казны:** +{level_bonus['bank_bonus_percent']}%\n"
            f"> _ _\n"
            f"> 🎯 **Общая мощь:** {pwr:,}"
        )
        
        embed = disnake.Embed(title="📈 Уровень Гильдии", description=desc, color=0x00D4FF)
        await ctx.send(embed=embed)

    @commands.command(name="glevels")
    async def glevels(self, ctx: commands.Context):
        """🎯 Система уровней гильдий"""
        desc = (
            "> **Как получить опыт гильдии:**\n"
            "> ✅ Побеждать в войнах: +500 XP за победу\n"
            "> ✅ Пополнять казну: +1 XP за 100 монет\n"
            "> ✅ Завершать квесты: +250 XP за квест\n"
            "> ✅ Поднимать апгрейды: +200 XP за апгрейд\n"
            "> _ _\n"
            "> **Бонусы по уровням:**\n"
            "> 🎁 **За каждый уровень:**\n"
            ">   • +5 слотов членов\n"
            ">   • +2% к доходу казны\n"
            ">   • +100 к общей мощи\n"
            "> _ _\n"
            "> 🎯 **XP для повышения:**\n"
            "> Формула: 1000 + (уровень × 500)\n"
            "> Уровень 1→2: 1500 XP\n"
            "> Уровень 10→11: 6000 XP\n"
            "> Уровень 20→21: 11000 XP"
        )
        
        embed = disnake.Embed(title="🎯 Система Уровней Гильдий", description=desc, color=0x00D4FF)
        embed.set_footer(text="Используй !glevel [тег] для просмотра прогресса")
        await ctx.send(embed=embed)

    @commands.command(name="gtop")
    async def gtop(self, ctx: commands.Context):
        """🏆 ТОП 3 гильдий сервера"""
        sid = str(ctx.guild.id)
        try:
            gs = list(db["guilds"].find({"server_id": sid}))
            gs = sorted(gs, key=lambda g: calc_guild_power(g, sid), reverse=True)[:3]
        except Exception:
            gs = []
        
        if not gs:
            await ctx.send(embed=ce("🏆", "> **Гильдий нет!**", ctx.guild), delete_after=10)
            return
        
        desc = ""
        medals = ["🥇", "🥈", "🥉"]
        for j, g in enumerate(gs):
            med = medals[j]
            cnt = member_count(g["id"], sid)
            pwr = calc_guild_power(g, sid)
            desc += (f"> {med} **[{g['tag']}] {g['name']}**\n"
                     f"> 💪 {pwr:,} | 👥 {cnt} чел | 👑 <@{g['owner_id']}>\n> _ _\n")
        
        embed = disnake.Embed(title="🏆 ТОП 3 Гильдии Сервера", description=desc, color=0xFFD700)
        await ctx.send(embed=embed)

    @commands.command(name="gcard", aliases=["gimage"])
    async def gcard(self, ctx: commands.Context, *, guild_tag: str = None):
        """🃏 Красивая визуальная карточка гильдии"""
        sid = str(ctx.guild.id)
        
        if guild_tag is None:
            # Если аргумента нет, ищем гильдию игрока
            user_data = find_user(ctx.author.id, sid)
            if not user_data or "guild_id" not in user_data or not user_data["guild_id"]:
                await ctx.send(embed=ce("❌", "> **Вы не в гильдии!**", ctx.guild), delete_after=10)
                return
            gd = db["guilds"].find_one({"id": user_data["guild_id"], "server_id": sid})
            if not gd:
                await ctx.send(embed=ce("❌", "> **Гильдия не найдена!**", ctx.guild), delete_after=10)
                return
        else:
            # Ищем гильдию по тегу
            try:
                gd = db["guilds"].find_one({"tag": guild_tag.upper(), "server_id": sid})
            except Exception:
                gd = None
            
            if not gd:
                await ctx.send(embed=ce("❌", f"> **Гильдия '{guild_tag}' не найдена!**", ctx.guild), delete_after=10)
                return
        
        try:
            # Генерируем изображение карточки
            image_bytes = await create_guild_card(gd, sid, ctx.guild)
            
            # Отправляем изображение
            file = disnake.File(io.BytesIO(image_bytes), filename=f"guild_{gd['tag']}.png")
            embed = disnake.Embed(title=f"🃏 {gd['tag']} - {gd['name']}", color=gd.get("color", 0xFF69B4))
            embed.set_image(url="attachment://guild_{}.png".format(gd['tag']))
            await ctx.send(file=file, embed=embed)
        except Exception as e:
            await ctx.send(embed=ce("❌", f"> **Ошибка: {str(e)[:50]}**", ctx.guild), delete_after=10)

    # ══════════════════════════════════════════════════════════
    # 👮 АДМИНСКИЕ КОМАНДЫ
    # ══════════════════════════════════════════════════════════

    @commands.command(name="greset")
    @is_admin()
    async def greset(self, ctx: commands.Context):
        sid = str(ctx.guild.id)
        try:
            us_list = list(db["users"].find({"server_id": sid}))
        except Exception:
            us_list = []
        for u in us_list:
            uid = uid_from_member_doc(u)
            if uid:
                save_user(uid, sid, {"messages": 0, "xp": 0, "level": 1, "coins": 0})
        await ctx.send(embed=ce("Admin", "🧹 Статистика сброшена.", ctx.guild))

    @commands.command(name="grebuildall")
    @is_admin()
    async def grebuildall(self, ctx: commands.Context):
        sid = str(ctx.guild.id)
        try:
            gs_list = list(db["guilds"].find({"server_id": sid}))
        except Exception:
            gs_list = []
        msg = await ctx.send(embed=ce("⏳", f"> Пересоздаю {len(gs_list)} гильдий...", ctx.guild))
        for g in gs_list:
            gd    = dict(g)
            owner = ctx.guild.get_member(int(gd["owner_id"])) or ctx.author
            await rebuild(ctx.guild, gd, owner)
        await msg.edit(embed=ce("✅ Готово!", f"> {len(gs_list)} гильдий пересозданы!", ctx.guild))

    @commands.command(name="gforcecolor")
    @is_admin()
    async def gforcecolor(self, ctx: commands.Context, tag: str, color: str):
        sid = str(ctx.guild.id)
        gd  = guild_by_tag(sid, tag)
        if not gd:
            await ctx.send(embed=ce("Admin", f"> **❌ [{tag.upper()}] не найдена!**", ctx.guild, 0xFF0000))
            return
        if color.lower() not in COLORS:
            await ctx.send(embed=ce("Admin", f"> **❌ Цвет `{color}` не найден!**", ctx.guild, 0xFF0000))
            return
        gd["color"] = color.lower()
        save_guild(gd["id"], {"color": color.lower()})
        owner = ctx.guild.get_member(int(gd["owner_id"])) or ctx.author
        msg = await ctx.send(embed=ce("⏳", f"> Меняю цвет **[{gd['tag']}]**...", ctx.guild))
        await rebuild(ctx.guild, gd, owner)
        await msg.edit(embed=ce("✅", f"> **[{gd['tag']}]** → {COLORS[color.lower()]['label']}!",
                                 ctx.guild, COLORS[color.lower()]["hex"]))

    @commands.command(name="gforcedelete")
    @is_admin()
    async def gforcedelete(self, ctx: commands.Context, *, tag: str):
        sid = str(ctx.guild.id)
        gd  = guild_by_tag(sid, tag)
        if not gd:
            await ctx.send(embed=ce("Admin", f"> **❌ [{tag.upper()}] не найдена!**", ctx.guild, 0xFF0000))
            return
        await self._dissolve_guild(ctx.guild, gd, sid)
        await ctx.send(embed=ce("✅", f"> **[{gd['tag']}] {gd['name']}** удалена.", ctx.guild))

    @commands.command(name="gforcekick")
    @is_admin()
    async def gforcekick(self, ctx: commands.Context, member: disnake.Member):
        uid, sid = str(member.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        if not u.get("guild_id"):
            await ctx.send(embed=ce("Admin", f"> **❌ {member.display_name} не в гильдии!**",
                                     ctx.guild, 0xFF0000))
            return
        gid = u["guild_id"]
        gd  = get_guild(gid)
        if gd:
            officers = gd.get("officers", [])
            if uid in officers:
                officers.remove(uid)
                save_guild(gid, {"officers": officers})
        save_user(uid, sid, {"guild_id": None, "guild_rank": None})
        if gd:
            await refresh_access(ctx.guild, gd, member, remove=True)
        try:
            if member.display_name.startswith("["):
                clean = member.display_name.split("]", 1)[1].strip()
                await member.edit(nick=clean or None)
        except Exception:
            pass
        await ctx.send(embed=ce("👢 Force Kick",
                                 f"> {member.mention} принудительно исключён(а).", ctx.guild, 0xFF4444))

    @commands.command(name="gforcejoin")
    @is_admin()
    async def gforcejoin(self, ctx: commands.Context, member: disnake.Member, *, tag: str):
        uid, sid = str(member.id), str(ctx.guild.id)
        gd = guild_by_tag(sid, tag)
        if not gd:
            await ctx.send(embed=ce("Admin", f"> **❌ [{tag.upper()}] не найдена!**", ctx.guild, 0xFF0000))
            return
        u = get_user(uid, sid)
        if u.get("guild_id"):
            await ctx.send(embed=ce("Admin", f"> **❌ {member.display_name} уже в гильдии!**",
                                     ctx.guild, 0xFF0000))
            return
        save_user(uid, sid, {"guild_id": gd["id"], "guild_rank": "member"})
        await refresh_access(ctx.guild, gd, member)
        try:
            old = member.display_name
            if old.startswith("[") and "]" in old:
                old = old.split("]", 1)[1].strip()
            await member.edit(nick=f"[{gd['tag']}] {old}"[:32])
        except Exception:
            pass
        await ctx.send(embed=ce("✅ Force Join",
                                 f"> {member.mention} добавлен(а) в **[{gd['tag']}]**.", ctx.guild))

    @commands.command(name="gsetowner")
    @is_admin()
    async def gsetowner(self, ctx: commands.Context, member: disnake.Member, *, tag: str):
        sid = str(ctx.guild.id)
        gd  = guild_by_tag(sid, tag)
        if not gd:
            await ctx.send(embed=ce("Admin", f"> **❌ [{tag.upper()}] не найдена!**", ctx.guild, 0xFF0000))
            return
        uid = str(member.id)
        t   = get_user(uid, sid)
        if t.get("guild_id") != gd["id"]:
            await ctx.send(embed=ce("Admin", f"> **❌ {member.display_name} не в этой гильдии!**",
                                     ctx.guild, 0xFF0000))
            return
        old_owner = gd.get("owner_id")
        if old_owner:
            save_user(str(old_owner), sid, {"guild_rank": "member"})
        officers = gd.get("officers", [])
        if uid in officers:
            officers.remove(uid)
        save_guild(gd["id"], {"owner_id": uid, "officers": officers})
        save_user(uid, sid, {"guild_rank": "owner"})
        await ctx.send(embed=ce("👑 Новый лидер",
                                 f"> {member.mention} теперь лидер **[{gd['tag']}]**.", ctx.guild))

    @commands.command(name="gaddbank")
    @is_admin()
    async def gaddbank(self, ctx: commands.Context, tag: str, amount: int):
        sid = str(ctx.guild.id)
        gd = guild_by_tag(sid, tag)
        if not gd:
            await ctx.send(embed=ce("Admin", f"> **❌ [{tag.upper()}] не найдена!**", ctx.guild, 0xFF0000))
            return
        try:
            db["guilds"].update_one({"id": gd["id"]}, {"$inc": {"bank": amount}})
            new_bank = (gd.get("bank", 0) or 0) + amount
            await ctx.send(embed=ce("💰 Казна пополнена",
                                     f"> **[{gd['tag']}]** +{amount:,} монет\n> Казна: **{new_bank:,}**", ctx.guild))
        except Exception as e:
            await ctx.send(embed=ce("Ошибка", f"> **❌ Ошибка БД: {e}**", ctx.guild, 0xFF0000))

    @commands.command(name="givemoney")
    @is_admin()
    async def givemoney(self, ctx: commands.Context, member: disnake.Member, amount: int):
        uid, sid = str(member.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        new_co = u.get("coins", 0) + amount
        save_user(uid, sid, {"coins": new_co})
        await ctx.send(embed=ce("💰 Выдача", f"> {member.mention} **+{amount:,}** | Баланс: **{new_co:,}**",
                                 ctx.guild))

    @commands.command(name="takemoney")
    @is_admin()
    async def takemoney(self, ctx: commands.Context, member: disnake.Member, amount: int):
        uid, sid = str(member.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        new_co = max(0, u.get("coins", 0) - amount)
        save_user(uid, sid, {"coins": new_co})
        await ctx.send(embed=ce("Admin", f"> Изъято **{amount:,}** у {member.mention}\n> Баланс: **{new_co:,}**",
                                 ctx.guild))

    @commands.command(name="resetuser")
    @is_admin()
    async def resetuser(self, ctx: commands.Context, member: disnake.Member):
        db["users"].delete_one({"user_id": str(member.id), "server_id": str(ctx.guild.id)})
        await ctx.send(embed=ce("Admin", f"> Данные {member.mention} сброшены.", ctx.guild))

    @commands.command(name="glistall")
    @is_admin()
    async def glistall(self, ctx: commands.Context):
        sid = str(ctx.guild.id)
        try:
            gs = list(db["guilds"].find({"server_id": sid}))
        except Exception:
            gs = []
        if not gs:
            await ctx.send("> Гильдий нет.")
            return
        desc = "".join(f"> **[{g['tag']}] {g['name']}** (ID:{g['id']})\n" for g in gs)
        await ctx.send(embed=ce("Все гильдии", desc, ctx.guild))

    @commands.command(name="setmessages")
    @is_admin()
    async def setmessages(self, ctx: commands.Context, member: disnake.Member, amount: int):
        save_user(str(member.id), str(ctx.guild.id), {"messages": amount})
        await ctx.send(embed=ce("📝", f"> {member.mention}: **{amount:,}** сообщений", ctx.guild))

    @commands.command(name="setxp")
    @is_admin()
    async def setxp(self, ctx: commands.Context, member: disnake.Member, amount: int):
        lvl = calc_level(amount)
        save_user(str(member.id), str(ctx.guild.id), {"xp": amount, "level": lvl})
        await ctx.send(embed=ce("⭐ XP", f"> {member.mention}: **{amount:,}** XP | ур. **{lvl}**", ctx.guild))

    @commands.command(name="gcleardata")
    @is_admin()
    async def gcleardata(self, ctx: commands.Context, member: disnake.Member):
        db["users"].delete_one({"user_id": str(member.id), "server_id": str(ctx.guild.id)})
        await ctx.send(embed=ce("🗑️ Сброс", f"> Данные {member.mention} сброшены.", ctx.guild, 0xFF4444))

    @commands.command(name="stats")
    @is_admin()
    async def stats(self, ctx: commands.Context):
        sid = str(ctx.guild.id)
        try:
            gs_list = list(db["guilds"].find({"server_id": sid}))
            us_list = list(db["users"].find({"server_id": sid}))
        except Exception:
            gs_list, us_list = [], []
        await ctx.send(embed=ce("📊 Статистика",
                                 f"> 🏰 Гильдий: **{len(gs_list)}**\n"
                                 f"> 👤 Игроков: **{len(us_list)}**\n"
                                 f"> 💰 Монет: **{sum(u.get('coins',0) for u in us_list):,}**\n"
                                 f"> ⭐ XP: **{sum(u.get('xp',0) for u in us_list):,}**\n"
                                 f"> 💬 Сообщений: **{sum(u.get('messages',0) for u in us_list):,}**",
                                 ctx.guild))

    @commands.command(name="gsetcalendar")
    @is_admin()
    async def gsetcalendar(self, ctx: commands.Context, channel: disnake.TextChannel):
        save_settings(str(ctx.guild.id), {SEASON_CH_KEY: channel.id})
        await ctx.send(embed=ce("✅", f"> Анонсы → {channel.mention}", ctx.guild))

    @commands.command(name="gsetmsg")
    @is_admin()
    async def gsetmsg(self, ctx: commands.Context, amount: int):
        save_settings(str(ctx.guild.id), {"msg_required": amount})
        await ctx.send(embed=ce("⚙️", f"> Порог создания гильдии: **{amount}** сообщений", ctx.guild))

    # ══════════════════════════════════════════════════════════
    # 🌸❄️ ИВЕНТ
    # ══════════════════════════════════════════════════════════

    def _season(self) -> str:
        return "winter" if datetime.utcnow().month in [12, 1, 2] else "spring"

    def _stasks(self, s: str) -> list:
        return WINTER_TASKS if s == "winter" else SPRING_TASKS

    def _stitle(self, s: str) -> str:
        return "❄️ Конец Зимы" if s == "winter" else "🌸 Начало Весны"

    @commands.command(name="gseason")
    @commands.cooldown(*COOLDOWNS["info_light"], commands.BucketType.user)
    async def gseason(self, ctx: commands.Context):
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        s     = self._season()
        tasks = self._stasks(s)
        u = get_user(uid, sid)
        pr = u.get("event_progress", {})
        cl = u.get("event_claimed", [])
        desc = f"> **Сезон: {self._stitle(s)}**\n> _ _\n"
        for t in tasks:
            cur  = pr.get(t["id"], 0)
            bar  = pbar(cur, t["goal"])
            if t["id"] in cl:
                status = "✅ Получено"
            elif cur >= t["goal"]:
                status = "🟩 Готово! Нажми ↓"
            else:
                status = f"⏳ {cur}/{t['goal']}"
            desc += (f"> {t['emoji']} **{t['name']}** — {status}\n"
                     f"> _{t['desc']}_\n> [{bar}] 💰 {t['reward']:,}\n> _ _\n")
        col = 0x5BC8FF if s == "winter" else 0xFF69B4
        await ctx.send(embed=ce(f"🎉 Ивент | {self._stitle(s)}", desc, ctx.guild, col),
                       components=[season_claim_row(ctx.author.id, s)])

    async def _prog(self, uid: str, sid: str, task_id: str, n: int = 1):
        u  = get_user(uid, sid)
        pr = u.get("event_progress", {})
        tl = self._stasks(self._season())
        t  = next((x for x in tl if x["id"] == task_id), None)
        if t:
            pr[task_id] = min(pr.get(task_id, 0) + n, t["goal"])
            save_user(uid, sid, {"event_progress": pr})

    @commands.command(name="snowball")
    @commands.cooldown(*COOLDOWNS["eco_medium"], commands.BucketType.user)
    async def snowball(self, ctx: commands.Context, target: disnake.Member = None):
        await self._prog(str(ctx.author.id), str(ctx.guild.id), "wt_snow")
        t = f"в {target.mention}" if target else "в воздух"
        await ctx.send(embed=ce("❄️ Снежок!", f"> {ctx.author.mention} кинул снежок {t}! ❄️",
                                 ctx.guild, 0x5BC8FF))

    @commands.command(name="warm")
    @commands.cooldown(*COOLDOWNS["eco_medium"], commands.BucketType.user)
    async def warm(self, ctx: commands.Context, member: disnake.Member):
        if member.id == ctx.author.id:
            await ctx.send(embed=ce("Тепло", "> **❌ Нельзя себе!**", ctx.guild, 0xFF0000))
            return
        await self._prog(str(ctx.author.id), str(ctx.guild.id), "wt_warm")
        await ctx.send(embed=ce("🔥 Тепло!", f"> {ctx.author.mention} поделился теплом с {member.mention}! 🧣",
                                 ctx.guild, 0xFF8C00))

    @commands.command(name="snowman")
    @commands.cooldown(*COOLDOWNS["super_heavy"], commands.BucketType.user)
    async def snowman(self, ctx: commands.Context):
        await self._prog(str(ctx.author.id), str(ctx.guild.id), "wt_man")
        await ctx.send(embed=ce("⛄ Снеговик!", f"> {ctx.author.mention} слепил снеговика! ⛄🥕",
                                 ctx.guild, 0x5BC8FF))

    @commands.command(name="gpatrol")
    @commands.cooldown(*COOLDOWNS["wars"], commands.BucketType.user)
    async def gpatrol(self, ctx: commands.Context):
        u = get_user(str(ctx.author.id), str(ctx.guild.id))
        if not u.get("guild_id"):
            await ctx.send(embed=ce("Патруль", "> **❌ Ты не в гильдии!**", ctx.guild, 0xFF0000))
            return
        await self._prog(str(ctx.author.id), str(ctx.guild.id), "wt_patrol")
        msg = random.choice(["🛡️ Враги разбежались!", "❄️ Патруль прошёл!", "⚔️ Граница под защитой!"])
        await ctx.send(embed=ce("🛡️ Патруль!", f"> {msg}", ctx.guild, 0x4A90D9))

    @commands.command(name="flower")
    @commands.cooldown(*COOLDOWNS["eco_medium"], commands.BucketType.user)
    async def flower(self, ctx: commands.Context):
        await self._prog(str(ctx.author.id), str(ctx.guild.id), "sp_flower")
        f = random.choice(["🌸 Сакура", "🌷 Тюльпан", "🌺 Гибискус", "🌻 Подсолнух", "🌼 Ромашка"])
        await ctx.send(embed=ce("🌸 Сбор!", f"> {ctx.author.mention} нашёл **{f}**!", ctx.guild, 0xFF69B4))

    @commands.command(name="plant")
    @commands.cooldown(*COOLDOWNS["eco_medium"], commands.BucketType.user)
    async def plant(self, ctx: commands.Context, member: disnake.Member):
        if member.id == ctx.author.id:
            await ctx.send(embed=ce("Посадка", "> **❌ Нельзя себе!**", ctx.guild, 0xFF0000))
            return
        await self._prog(str(ctx.author.id), str(ctx.guild.id), "sp_plant")
        await ctx.send(embed=ce("🌱 Посадка!", f"> {ctx.author.mention} посадил цветок для {member.mention}! 🌷",
                                 ctx.guild, 0x2ECC71))

    @commands.command(name="spring_rain")
    @commands.cooldown(*COOLDOWNS["super_heavy"], commands.BucketType.user)
    async def spring_rain(self, ctx: commands.Context):
        await self._prog(str(ctx.author.id), str(ctx.guild.id), "sp_rain")
        await ctx.send(embed=ce("🌧️ Весенний дождь!",
                                 f"> {ctx.author.mention} призвал весенний дождь! 🌧️🌸",
                                 ctx.guild, 0xFF69B4))

    # ══════════════════════════════════════════════════════════
    # 🌾 СИСТЕМА ФЕРМ (ПАССИВНЫЙ ДОХОД)
    # ══════════════════════════════════════════════════════════

    @commands.command(name="buyfarm", aliases=["farm"])
    @commands.cooldown(*COOLDOWNS["eco_medium"], commands.BucketType.user)
    async def buyfarm(self, ctx: commands.Context, farm_name: str = None):
        """Купить ферму для пассивного дохода"""
        if not INCOME_SOURCES:
            await ctx.send(embed=ce("Ошибка", "> **❌ Система ферм недоступна**", ctx.guild, 0xFF0000))
            return
        
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        lvl = u.get("level", 1)
        
        if not farm_name:
            # Показываем каталог ферм
            desc = ""
            for tier_num in range(1, 6):
                tier_farms = get_income_sources_by_tier(tier_num)
                if tier_farms:
                    tier_info = INCOME_TIERS.get(tier_num, {})
                    desc += f"\n> **{tier_info.get('emoji')} Уровень {tier_num} — {tier_info.get('name')}:**\n"
                    for farm_key, farm in tier_farms.items():
                        can_afford = u.get("coins", 0) >= farm["price"]
                        can_unlock = lvl >= farm.get("unlock_level", 1)
                        status = "✅" if can_afford and can_unlock else ("🔒" if not can_unlock else "❌")
                        desc += f"> {status} `{farm_key}` — {farm['name']} ({farm['price']:,} монет)\n"
                        desc += f">    +{farm['income_per_hour']:,}/ч — окуп. {calculate_farm_payback_days(farm_key):.1f} дня\n"
            
            await ctx.send(embed=ce("🌾 Каталог ферм",
                                    desc + f"\n> _ _\n> Используй: `!buyfarm <название>`",
                                    ctx.guild))
            return
        
        farm_key = farm_name.lower()
        if farm_key not in INCOME_SOURCES:
            await ctx.send(embed=ce("Ошибка", f"> **❌ Ферма '{farm_name}' не найдена**", ctx.guild, 0xFF0000))
            return
        
        farm = INCOME_SOURCES[farm_key]
        if u.get("coins", 0) < farm["price"]:
            need = farm["price"] - u.get("coins", 0)
            await ctx.send(embed=ce("Покупка ферм",
                                    f"> **❌ Не хватает {need:,} монет!**\n> Твой баланс: {u.get('coins', 0):,}",
                                    ctx.guild, 0xFF0000))
            return
        
        if lvl < farm.get("unlock_level", 1):
            await ctx.send(embed=ce("Покупка ферм",
                                    f"> **❌ Недостаточен уровень!**\n> Требуется ур. {farm.get('unlock_level', 1)}, у тебя {lvl}",
                                    ctx.guild, 0xFF0000))
            return
        
        farms = u.get("farms", [])
        if farm_key in farms:
            await ctx.send(embed=ce("Покупка ферм",
                                    f"> **⚠️ У тебя уже есть эта ферма!**",
                                    ctx.guild, 0xFF8800))
            return
        
        # Покупаем ферму
        farms.append(farm_key)
        new_coins = u.get("coins", 0) - farm["price"]
        save_user(uid, sid, {"coins": new_coins, "farms": farms})
        
        await ctx.send(embed=ce("🌾 Ферма куплена!",
                                f"> {farm['emoji']} **{farm['name']}**\n> _ _\n"
                                f"> 💰 **-{farm['price']:,} монет**\n"
                                f"> 📈 **+{farm['income_per_hour']:,}** монет в час\n> _ _\n"
                                f"> Новый баланс: **{new_coins:,}**",
                                ctx.guild, farm['tier'] * 0x101010))

    @commands.command(name="myfarms")
    @commands.cooldown(*COOLDOWNS["info_light"], commands.BucketType.user)
    async def myfarms(self, ctx: commands.Context, member: disnake.Member = None):
        """Показывает твои фермы и пассивный доход"""
        if not INCOME_SOURCES:
            await ctx.send(embed=ce("Ошибка", "> **❌ Система ферм недоступна**", ctx.guild, 0xFF0000))
            return
        
        target = member or ctx.author
        uid, sid = str(target.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        farms = u.get("farms", [])
        
        if not farms:
            await ctx.send(embed=ce("🌾 Твои фермы",
                                    f"> **{target.display_name}** ещё не имеет ферм\n> Начни с `!buyfarm`",
                                    ctx.guild, 0xFF8800))
            return
        
        total_income = get_income_per_hour(farms, get_guild(u.get("guild_id")).get("upgrades", []) if u.get("guild_id") else [])
        
        desc = f"> **Всего ферм:** {len(farms)}\n> **Доход в час:** {total_income:,} монет\n> **Доход в день:** {total_income * 24:,} монет\n> _ _\n"
        
        for tier_num in range(1, 6):
            tier_farms = [f for f in farms if INCOME_SOURCES.get(f, {}).get("tier") == tier_num]
            if tier_farms:
                tier_info = INCOME_TIERS.get(tier_num, {})
                desc += f"> **{tier_info.get('emoji')} {tier_info.get('name')} ({len(tier_farms)}):**\n"
                for farm_key in tier_farms:
                    farm = INCOME_SOURCES[farm_key]
                    desc += f"> {farm['emoji']} **{farm['name']}** — +{farm['income_per_hour']:,}/ч\n"
                desc += "> _ _\n"
        
        e = ce("🌾 Твои фермы", desc, ctx.guild, 0x2ECC71)
        if ctx.author == target:
            e.add_field(name="Совет", value="Используй `!harvest` каждый час для сбора дохода", inline=False)
        await ctx.send(embed=e)

    @commands.command(name="harvest")
    @commands.cooldown(*COOLDOWNS["eco_medium"], commands.BucketType.user)
    async def harvest(self, ctx: commands.Context):
        """Собрать доход от фермы (раз в час)"""
        if not INCOME_SOURCES:
            await ctx.send(embed=ce("Ошибка", "> **❌ Система ферм недоступна**", ctx.guild, 0xFF0000))
            return
        
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        farms = u.get("farms", [])
        
        if not farms:
            await ctx.send(embed=ce("🌾 При сборе урожая",
                                    "> **❌ У тебя нет ферм!**\n> Купи ферму через `!buyfarm`",
                                    ctx.guild, 0xFF0000))
            return
        
        now = datetime.utcnow()
        last_harvest = u.get("last_farm_income")
        
        if last_harvest:
            try:
                last_time = datetime.fromisoformat(last_harvest)
                diff = now - last_time
                if diff.total_seconds() < 3600:  # Минимум час
                    rem = 3600 - diff.total_seconds()
                    m = int(rem // 60)
                    await ctx.send(embed=ce("🌾 При сборе урожая",
                                           f"> ⏰ Уже собирал сегодня!\n> Возвращайся через **{m} минут**",
                                           ctx.guild, 0xFF8800))
                    return
            except Exception:
                pass
        
        # Вычисляем доход
        gd = get_guild(u.get("guild_id"))
        guild_upgrades = gd.get("upgrades", []) if gd else []
        income = get_income_per_hour(farms, guild_upgrades)
        
        # Применяем бонусы гильдии за взнос
        vault_bonus = get_guild_vault_bonus(guild_upgrades) if gd else 1.0
        
        # Часть дохода идёт в казну гильдии
        guild_contribution = int(income * (vault_bonus - 1.0) * 0.1) if gd else 0
        player_income = income - guild_contribution
        
        new_coins = u.get("coins", 0) + player_income
        save_user(uid, sid, {
            "coins": new_coins,
            "last_farm_income": now.isoformat(),
            "farm_income_collected": u.get("farm_income_collected", 0) + player_income
        })
        
        # Добавляем в казну гильдии если есть
        if gd and guild_contribution > 0:
            save_guild(gd["id"], {"bank": gd.get("bank", 0) + guild_contribution})
        
        desc = f"> {ctx.author.mention} собрал урожай!\n> _ _\n"
        desc += f"> 💰 **+{player_income:,}** монет (за час)\n"
        if guild_contribution > 0:
            desc += f"> 🏰 **+{guild_contribution:,}** в казну гильдии ({vault_bonus*100-100:.0f}%)\n"
        desc += f"> _ _\n> Баланс: **{new_coins:,}**"
        
        await ctx.send(embed=ce("🌾 Сбор урожая!", desc, ctx.guild, 0x2ECC71))

    # ══════════════════════════════════════════════════════════
    # 🏅 ФОНОВАЯ ЗАДАЧА ПРОВЕРКИ БАФФОВ
    # ══════════════════════════════════════════════════════════

    @tasks.loop(minutes=30)
    async def verify_member_badges_task(self):
        """
        Фоновая задача проверки профилей участников главного сервера.
        Обновляет кэш баффов для присвоения мультипликаторов к монетам.
        И присваивает соответствующие роли на Discord.
        """
        global _member_badge_cache
        try:
            home_server = self.bot.get_guild(HOME_SERVER_ID)
            if not home_server:
                return
            
            # Очищаем устаревший кэш
            now = datetime.utcnow().timestamp()
            expired_keys = [
                k for k, v in _member_badge_cache.items()
                if (now - v[2]) > _cache_ttl
            ]
            for k in expired_keys:
                del _member_badge_cache[k]
            
            # Проверяем участников
            checked = 0
            roles_updated = 0
            for member in home_server.members[:50]:  # 50 участников за итерацию
                if member.bot:
                    continue
                
                badge_level = await check_member_profile(member)
                _member_badge_cache[member.id] = (badge_level, 
                    MEMBER_BADGES.get(badge_level, {}).get("multiplier", 1.0),
                    now)
                
                # Присваиваем роли на основе баффа
                try:
                    for badge_key, badge_data in MEMBER_BADGES.items():
                        role_id = badge_data.get("role_id")
                        if not role_id:
                            continue
                        role = home_server.get_role(role_id)
                        if not role:
                            continue
                        
                        if badge_level == badge_key:
                            # Нужно добавить роль
                            if role not in member.roles:
                                await member.add_roles(role, reason="Автоверификация баффа")
                                roles_updated += 1
                        else:
                            # Нужно удалить роль
                            if role in member.roles:
                                await member.remove_roles(role, reason="Автоверификация баффа")
                                roles_updated += 1
                except Exception as e:
                    print(f"[verify_member_badges_task] Ошибка при работе с ролями {member.id}: {e}")
                
                checked += 1
                await asyncio.sleep(0.2)  # Небольшая задержка для избежания rate limit
            
            if checked > 0 or roles_updated > 0:
                print(f"[verify_member_badges_task] Проверено {checked} участников, обновлено {roles_updated} ролей")
                
        except Exception as e:
            print(f"[verify_member_badges_task] Ошибка: {e}")

    @tasks.loop(hours=1)
    async def season_task(self):
        season = self._season()
        for srv in self.bot.guilds:
            sid = str(srv.id)
            st  = get_settings(sid)
            if st.get("last_season") == season:
                continue
            ch_id = st.get(SEASON_CH_KEY)
            if not ch_id:
                continue
            ch = srv.get_channel(int(ch_id))
            if not ch:
                continue
            if season == "winter":
                title = "❄️ КОНЕЦ ЗИМЫ — Ивент начался!"
                col   = 0x5BC8FF
                desc  = ("> ❄️ `!snowball` · 🔥 `!warm @` · ⛄ `!snowman` · 🛡️ `!gpatrol`\n"
                         "> _ _\n> `!gseason` — прогресс 🎁")
            else:
                title = "🌸 НАЧАЛО ВЕСНЫ — Ивент начался!"
                col   = 0xFF69B4
                desc  = ("> 🌸 `!flower` · 🌱 `!plant @` · 🌧️ `!spring_rain`\n"
                         "> _ _\n> `!gseason` — прогресс 🎁")
            try:
                await ch.send(embed=ce(title, desc, srv, col))
                save_settings(sid, {"last_season": season})
            except Exception as ex:
                print(f"[SEASON] {srv.name}: {ex}")

    @season_task.before_loop
    async def before_season(self):
        await self.bot.wait_until_ready()

    # ── Баффы и Верификация ─────────────────────────────────

    @commands.command(name="mybadge")
    async def mybadge(self, ctx: commands.Context, user: Optional[disnake.Member] = None):
        """Показывает текущий статус баффа участника."""
        target = user or ctx.author
        home_server = self.bot.get_guild(HOME_SERVER_ID)
        if not home_server:
            await ctx.send("❌ Главный сервер не найден", delete_after=10)
            return
        
        member = home_server.get_member(target.id)
        if not member:
            await ctx.send("❌ Участник не найден на главном сервере", delete_after=10)
            return
        
        badge_level = await check_member_profile(member)
        badge_info = MEMBER_BADGES.get(badge_level, {})
        multiplier = badge_info.get("multiplier", 1.0)
        description = badge_info.get("description", "Без баффа")
        emoji = badge_info.get("emoji", "❌")
        
        desc = f"{emoji} **{description}**\n> Мультипликатор: **x{multiplier}**"
        
        if badge_level:
            desc += f"\n> Таг: {'🏷️' if '[' in (member.display_name or '') else '❌'}"
            desc += f"\n> Ссылка на сервер: {'✅' if 'discord.gg' in (member.bio or '').lower() else '❌'}"
        
        await ctx.send(embed=ce("🏅 Статус баффа", desc, ctx.guild))

    @commands.command(name="badgestatus")
    @commands.has_permissions(administrator=True)
    async def badgestatus(self, ctx: commands.Context, user: disnake.Member):
        """[Админ] Показывает статус баффа участника и детали профиля."""
        home_server = self.bot.get_guild(HOME_SERVER_ID)
        if not home_server:
            await ctx.send("❌ Главный сервер не найден", delete_after=10)
            return
        
        member = home_server.get_member(user.id)
        if not member:
            await ctx.send("❌ Участник не найден на главном сервере", delete_after=10)
            return
        
        badge_level = await check_member_profile(member)
        badge_info = MEMBER_BADGES.get(badge_level, {})
        
        desc = f"👤 {member.mention}\n> _ _\n"
        desc += f"**Ник:** {member.display_name}\n"
        desc += f"**Bio:** {member.bio or 'Не установлено'}\n"
        desc += f"> _ _\n"
        desc += f"**Статус баффа:** {badge_info.get('emoji', '❌')} {badge_info.get('description', 'Без баффа')}\n"
        desc += f"**Мультипликатор:** x{badge_info.get('multiplier', 1.0)}\n"
        
        if badge_info.get('role_id'):
            role = home_server.get_role(badge_info['role_id'])
            if role:
                desc += f"**Роль:** {role.mention}"
        
        await ctx.send(embed=ce("🏅 Детали баффа", desc, ctx.guild))

    @commands.command(name="verifyall")
    @commands.is_owner()
    async def verifyall(self, ctx: commands.Context):
        """[Владелец] Принудительно проверить всех участников главного сервера."""
        global _member_badge_cache
        home_server = self.bot.get_guild(HOME_SERVER_ID)
        if not home_server:
            await ctx.send("❌ Главный сервер не найден", delete_after=10)
            return
        
        msg = await ctx.send("⏳ Проверка всех участников...")
        checked = 0
        now = datetime.utcnow().timestamp()
        
        for member in home_server.members:
            if member.bot:
                continue
            
            badge_level = await check_member_profile(member)
            _member_badge_cache[member.id] = (badge_level,
                MEMBER_BADGES.get(badge_level, {}).get("multiplier", 1.0),
                now)
            checked += 1
        
        await msg.edit(content=f"✅ Проверено **{checked}** участников | Обновлено кэш баффов")

    @commands.command(name="applyretro")
    @commands.is_owner()
    async def applyretro(self, ctx: commands.Context):
        """
        [Владелец] Ретроактивно применить роли гильдий для всех существующих членов.
        Создаёт роли для гильдий, у которых их ещё нет.
        """
        msg = await ctx.send("⏳ Применение к существующим гильдиям...")
        sid = str(ctx.guild.id)
        
        try:
            guilds_data = list(db["guilds"].find({"server_id": sid}))
        except Exception as e:
            await msg.edit(content=f"❌ Ошибка при получении гильдий: {e}")
            return
        
        created_roles = 0
        applied_members = 0
        
        for gd in guilds_data:
            gid = gd.get("id")
            if not gid:
                continue
            
            # Проверяем наличие роли гильдии
            guild_role_id = gd.get("guild_role_id")
            guild_role = None
            
            if guild_role_id:
                guild_role = ctx.guild.get_role(guild_role_id)
            
            # Создаём роль если её нет
            if not guild_role:
                try:
                    guild_color = COLORS.get(gd.get("color", DEFAULT_COLOR), {}).get("hex", 0x3498DB)
                    guild_role = await ctx.guild.create_role(
                        name=f"[{gd['tag']}] Члены",
                        color=disnake.Color(guild_color),
                        reason="Ретроактивное создание роли гильдии"
                    )
                    save_guild(gid, {"guild_role_id": guild_role.id})
                    created_roles += 1
                except Exception as e:
                    print(f"[applyretro] Не удалось создать роль для {gd['tag']}: {e}")
                    continue
            
            # Присваиваем роль всем членам гильдии
            try:
                members = guild_members(gid, sid)
                for member_data in members:
                    mid = member_data.get("user_id")
                    if not mid:
                        continue
                    
                    try:
                        member = ctx.guild.get_member(int(mid))
                        if member and guild_role not in member.roles:
                            await member.add_roles(guild_role, reason="Ретроактивное применение")
                            applied_members += 1
                    except Exception as e:
                        print(f"[applyretro] Ошибка для члена {mid}: {e}")
                    
                    await asyncio.sleep(0.1)  # Rate limit
                    
            except Exception as e:
                print(f"[applyretro] Ошибка при применении к гильдии {gid}: {e}")
        
        await msg.edit(content=f"✅ Завершено!\n"
                               f"> Создано ролей: **{created_roles}**\n"
                               f"> Применено участникам: **{applied_members}**")

    # ══════════════════════════════════════════════════════════
    # 🎰 КАЗИНО
    # ══════════════════════════════════════════════════════════

    @commands.command(name="blackjack", aliases=["bj"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def blackjack(self, ctx: commands.Context, bet: str = "100"):
        """🃏 Полный блэкджек! !bj all|half|25% или !bj 1000"""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        
        # Парсинг bet параметра
        if bet.lower() == "all":
            bet_amount = coins
        elif bet.lower() == "half":
            bet_amount = coins // 2
        elif bet.lower().endswith("%"):
            try:
                percent = int(bet[:-1])
                bet_amount = max(1, int(coins * percent / 100))
            except ValueError:
                await ctx.send(embed=ce("❌ Ошибка", "> Используй: all | half | 25% | 1000", ctx.guild, 0xFF0000), delete_after=10)
                return
        else:
            try:
                bet_amount = int(bet)
            except ValueError:
                await ctx.send(embed=ce("❌ Ошибка", "> Используй: all | half | 25% | 1000", ctx.guild, 0xFF0000), delete_after=10)
                return
        
        if bet_amount < 50 or bet_amount > 100000:
            await ctx.send(embed=ce("🃏 Блэкджек", 
                                     "> Ставка: **50-100,000** монет!", 
                                     ctx.guild, 0xFF8800), delete_after=10)
            return
        
        if coins < bet_amount:
            await ctx.send(embed=ce("❌ Не хватает монет",
                                     f"> Нужно **{bet_amount:,}**, а у тебя **{coins:,}**",
                                     ctx.guild, 0xFF0000), delete_after=10)
            return
        
        # 🎴 КАРТЫ
        suits = ["♠️", "♥️", "♦️", "♣️"]
        ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
        deck = [(r, s) for r in ranks for s in suits] * 4
        
        def card_value(card):
            rank = card[0]
            if rank in ["J", "Q", "K"]:
                return 10
            elif rank == "A":
                return 11
            else:
                return int(rank)
        
        def hand_value(hand):
            total = sum(card_value(c) for c in hand)
            aces = sum(1 for c in hand if c[0] == "A")
            while total > 21 and aces > 0:
                total -= 10
                aces -= 1
            return total
        
        def format_hand(hand):
            return " ".join(f"{c[0]}{c[1]}" for c in hand)
        
        # Раздача
        random.shuffle(deck)
        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]
        
        class BlackjackView(disnake.ui.View):
            def __init__(self, deck, player_hand, dealer_hand, bet_amount, coins, ctx_author_id, author_name):
                super().__init__(timeout=30)
                self.deck = deck
                self.player_hand = player_hand
                self.dealer_hand = dealer_hand
                self.bet_amount = bet_amount
                self.coins = coins
                self.ctx_author_id = ctx_author_id
                self.author_name = author_name
                self.game_over = False
            
            def make_embed(self, show_dealer=False, guild_name="Сервер"):
                player_val = hand_value(self.player_hand)
                dealer_val = hand_value(self.dealer_hand) if show_dealer else hand_value([self.dealer_hand[0]])
                
                if show_dealer:
                    dealer_cards = format_hand(self.dealer_hand)
                    dealer_info = f"Дилер | {dealer_val}\n{dealer_cards}"
                else:
                    dealer_cards = f"{self.dealer_hand[0][0]}{self.dealer_hand[0][1]} 🔒"
                    dealer_info = f"Дилер | ?\n{dealer_cards}"
                
                description = (
                    f"**{self.author_name}** | {player_val}\n"
                    f"{format_hand(self.player_hand)}\n"
                    f"_ _\n"
                    f"{dealer_info}\n"
                    f"_ _\n"
                    f"Только для {guild_name}\n"
                    f"Ставка: 💰 {self.bet_amount:,}"
                )
                
                embed = disnake.Embed(
                    title="🃏 Блэкджек",
                    description=description,
                    color=0xFF6B9D
                )
                return embed
            
            async def update_embed(self, msg, show_dealer=False):
                embed = self.make_embed(show_dealer, guild_name="Сервер")
                await msg.edit(embed=embed, view=self)
            
            @disnake.ui.button(label="Удар | Возьми другую карту", style=disnake.ButtonStyle.primary)
            async def hit_button(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
                if inter.author.id != self.ctx_author_id:
                    await inter.response.defer()
                    return
                
                self.player_hand.append(self.deck.pop())
                player_val = hand_value(self.player_hand)
                
                if player_val > 21:
                    # Перебор
                    save_user(str(self.ctx_author_id), str(inter.guild.id), {"coins": self.coins - self.bet_amount})
                    embed = disnake.Embed(
                        title="💥 ПЕРЕБОР!",
                        description=(
                            f"**{self.author_name}** | {player_val}\n"
                            f"{format_hand(self.player_hand)}\n"
                            f"_ _\n"
                            f"❌ **-{self.bet_amount:,}** монет\n"
                            f"> Баланс: **{self.coins - self.bet_amount:,}**"
                        ),
                        color=0xFF0000
                    )
                    self.game_over = True
                    for item in self.children:
                        item.disabled = True
                    await inter.response.edit_message(embed=embed, view=self)
                else:
                    await inter.response.defer()
                    embed = self.make_embed(show_dealer=False, guild_name="Сервер")
                    await inter.message.edit(embed=embed)
            
            @disnake.ui.button(label="Стоять | Стоп", style=disnake.ButtonStyle.danger)
            async def stand_button(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
                if inter.author.id != self.ctx_author_id:
                    await inter.response.defer()
                    return
                
                await inter.response.defer()
                
                # Логика дилера
                dealer_val = hand_value(self.dealer_hand)
                while dealer_val < 17:
                    self.dealer_hand.append(self.deck.pop())
                    dealer_val = hand_value(self.dealer_hand)
                
                player_val = hand_value(self.player_hand)
                
                # Результат
                if dealer_val > 21:
                    result = "ДИЛЕР ПЕРЕБРАЛ!"
                    winnings = int(self.bet_amount * 2)
                    new_coins = self.coins + winnings
                    color = 0x00FF00
                    profit_text = f"✅ **+{winnings:,}** монет!"
                elif player_val > dealer_val:
                    result = "ТЫ ВЫИГРАЛ!"
                    winnings = int(self.bet_amount * 2)
                    new_coins = self.coins + winnings
                    color = 0x00FF00
                    profit_text = f"✅ **+{winnings:,}** монет!"
                elif player_val < dealer_val:
                    result = "ДИЛЕР ВЫИГРАЛ"
                    new_coins = self.coins - self.bet_amount
                    color = 0xFF0000
                    profit_text = f"❌ **-{self.bet_amount:,}** монет"
                else:
                    result = "НИЧЬЯ!"
                    new_coins = self.coins
                    color = 0xFFFF00
                    profit_text = "🤝 Возврат ставки"
                
                save_user(str(self.ctx_author_id), str(inter.guild.id), {"coins": new_coins})
                
                embed = disnake.Embed(
                    title=f"🎰 {result}",
                    description=(
                        f"**{self.author_name}** | {player_val}\n"
                        f"{format_hand(self.player_hand)}\n"
                        f"_ _\n"
                        f"Дилер | {dealer_val}\n"
                        f"{format_hand(self.dealer_hand)}\n"
                        f"_ _\n"
                        f"{profit_text}\n"
                        f"> Баланс: **{new_coins:,}**"
                    ),
                    color=color
                )
                self.game_over = True
                for item in self.children:
                    item.disabled = True
                await inter.message.edit(embed=embed, view=self)
        
        # Показ начального состояния
        embed = disnake.Embed(
            title="🃏 Блэкджек",
            description=(
                f"**{ctx.author.name}** | {hand_value(player_hand)}\n"
                f"{format_hand(player_hand)}\n"
                f"_ _\n"
                f"Дилер | ?\n"
                f"{dealer_hand[0][0]}{dealer_hand[0][1]} 🔒\n"
                f"_ _\n"
                f"Только для {ctx.guild.name}\n"
                f"Ставка: 💰 {bet_amount:,}"
            ),
            color=0xFF6B9D
        )
        
        view = BlackjackView(deck, player_hand, dealer_hand, bet_amount, coins, ctx.author.id, ctx.author.name)
        msg = await ctx.send(embed=embed, view=view)
        
        # Проверка на blackjack
        if hand_value(player_hand) == 21:
            winnings = int(bet_amount * 2.5)
            new_coins = coins + winnings
            save_user(uid, sid, {"coins": new_coins})
            embed = disnake.Embed(
                title="🎉 НАТУРАЛЬНЫЙ БЛЭКДЖЕК!",
                description=(
                    f"**{ctx.author.name}** | 21\n"
                    f"{format_hand(player_hand)}\n"
                    f"_ _\n"
                    f"✅ **+{winnings:,}** монет!\n"
                    f"> Баланс: **{new_coins:,}**"
                ),
                color=0x00FF00
            )
            for item in view.children:
                item.disabled = True
            await msg.edit(embed=embed, view=view)

    @commands.command(name="slots")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def slots(self, ctx: commands.Context, bet: int = 100):
        """🍒 Крутить слоты! Попади в комбо для выигрыша."""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        
        if bet < 25 or bet > 150000:
            await ctx.send(embed=ce("🍒 Слоты", 
                                     "> Ставка должна быть от **25** до **150,000**!", 
                                     ctx.guild, 0xFF8800), delete_after=10)
            return
        
        if coins < bet:
            await ctx.send(embed=ce("❌ Не хватает монет",
                                     f"> Нужно **{bet:,}**, а у тебя **{coins:,}**",
                                     ctx.guild, 0xFF0000), delete_after=10)
            return
        
        reels = [random.choice(["🍒","🍊","🍋","⭐","💎"]) for _ in range(3)]
        
        if reels[0] == reels[1] == reels[2]:
            winnings = int(bet * 5)
            result = "🎊 ДЖЕКПОТ! ВСЕ ТРИ!"
        elif reels[0] == reels[1] or reels[1] == reels[2]:
            winnings = int(bet * 2)
            result = "⭐ Два совпадения!"
        else:
            winnings = 0
            result = "❌ Не повезло"
        
        new_coins = coins + winnings - bet if winnings > 0 else coins - bet
        save_user(uid, sid, {"coins": new_coins})
        
        desc = f"> {' '.join(reels)}\n> {result}\n"
        if winnings > 0:
            desc += f"> 🎁 **+{winnings:,}** монет!"
        else:
            desc += f"> Потеряно **-{bet:,}** монет"
        desc += f"\n> Баланс: **{new_coins:,}**"
        
        await ctx.send(embed=ce("🍒 Слоты", desc, ctx.guild, 0x2ECC71 if winnings > 0 else 0xE74C3C))

    @commands.command(name="coinflip", aliases=["cf"])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def coinflip(self, ctx: commands.Context, bet: int = 100, choice: str = "heads"):
        """🪙 Орёл или решка? Выбери heads/h/орел или tails/t/решка."""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        
        if bet < 50 or bet > 200000:
            await ctx.send(embed=ce("🪙 Орёл-Решка", 
                                     "> Ставка должна быть от **50** до **200,000**!", 
                                     ctx.guild, 0xFF8800), delete_after=10)
            return
        
        if coins < bet:
            await ctx.send(embed=ce("❌ Не хватает монет",
                                     f"> Нужно **{bet:,}**, а у тебя **{coins:,}**",
                                     ctx.guild, 0xFF0000), delete_after=10)
            return
        
        result = random.choice(["орел", "решка"])
        choice = choice.lower()
        win = (choice in ["орел", "heads", "h", "о"] and result == "орел") or \
              (choice in ["решка", "tails", "t", "р"] and result == "решка")
        
        if win:
            winnings = bet
            new_coins = coins + winnings
            emoji = "🪙 ОРЕЛ!" if result == "орел" else "🪙 РЕШКА!"
        else:
            new_coins = coins - bet
            emoji = "⚠️ Не совпало!"
        
        save_user(uid, sid, {"coins": new_coins})
        
        desc = f"> Выпало: **{result.upper()}**\n> {emoji}\n"
        if win:
            desc += f"> 🎉 **+{bet:,}** монет!"
        else:
            desc += f"> ❌ **-{bet:,}** монет"
        desc += f"\n> Баланс: **{new_coins:,}**"
        
        await ctx.send(embed=ce("🪙 Орёл-Решка", desc, ctx.guild, 0x2ECC71 if win else 0xE74C3C))

    @commands.command(name="roulette", aliases=["rle"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def roulette(self, ctx: commands.Context, bet: int = 100, choice: str = "red"):
        """🎡 Рулетка! Выбери red, black или число 1-36."""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        
        if bet < 100 or bet > 50000:
            await ctx.send(embed=ce("🎡 Рулетка", 
                                     "> Ставка должна быть от **100** до **50,000**!", 
                                     ctx.guild, 0xFF8800), delete_after=10)
            return
        
        if coins < bet:
            await ctx.send(embed=ce("❌ Не хватает монет",
                                     f"> Нужно **{bet:,}**, а у тебя **{coins:,}**",
                                     ctx.guild, 0xFF0000), delete_after=10)
            return
        
        spin = random.randint(1, 36)
        red_nums = [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]
        
        choice = choice.lower()
        win = False
        winnings = 0
        result_color = "⚫ Чёрный" if spin not in red_nums else "🔴 Красный"
        
        if choice in ["red", "красный", "к"]:
            is_red = spin in red_nums
            if is_red:
                win = True
                winnings = int(bet * 2.5)
        elif choice in ["black", "чёрный", "чёр", "ч"]:
            is_red = spin in red_nums
            if not is_red:
                win = True
                winnings = int(bet * 2.5)
        else:
            try:
                num = int(choice)
                if num == spin:
                    win = True
                    winnings = int(bet * 36)
            except ValueError:
                await ctx.send(embed=ce("❌", "> Выбери red, black или число 1-36!", ctx.guild, 0xFF0000), delete_after=10)
                return
        
        new_coins = coins + (winnings - bet) if win else coins - bet
        save_user(uid, sid, {"coins": new_coins})
        
        desc = f"> 🎡 Число: **{spin}** {result_color}\n"
        if win:
            desc += f"> 🎉 **ТЫ ВЫИГРАЛ! +{winnings:,}** монет!"
        else:
            desc += f"> ❌ Проиграл **-{bet:,}** монет"
        desc += f"\n> Баланс: **{new_coins:,}**"
        
        await ctx.send(embed=ce("🎡 Рулетка", desc, ctx.guild, 0x2ECC71 if win else 0xE74C3C))

    @commands.command(name="dice")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def dice(self, ctx: commands.Context, bet: int = 100):
        """🎲 Кубики! Твои кубики против бота (выше = победа)."""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        
        if bet < 50 or bet > 75000:
            await ctx.send(embed=ce("🎲 Кубики", 
                                     "> Ставка должна быть от **50** до **75,000**!", 
                                     ctx.guild, 0xFF8800), delete_after=10)
            return
        
        if coins < bet:
            await ctx.send(embed=ce("❌ Не хватает монет",
                                     f"> Нужно **{bet:,}**, а у тебя **{coins:,}**",
                                     ctx.guild, 0xFF0000), delete_after=10)
            return
        
        player_dice = random.randint(1, 100)
        bot_dice = random.randint(1, 100)
        
        if player_dice > bot_dice:
            win = True
            result_text = "**✅ ТЫ ВЫИГРАЛ!**"
            color = 0x2ECC71
        elif player_dice < bot_dice:
            win = False
            result_text = "**❌ ТЫ ПРОИГРАЛ!**"
            color = 0xE74C3C
        else:
            win = False
            result_text = "**🤝 НИЧЬЯ!**"
            color = 0xFFFF00
        
        if win:
            new_coins = coins + bet
            winnings = bet
        elif player_dice == bot_dice:
            new_coins = coins  # Возврат ставки
            winnings = 0
        else:
            new_coins = coins - bet
            winnings = -bet
        
        save_user(uid, sid, {"coins": new_coins})
        
        desc = f"> 🎲 Твои кубики: **{player_dice}**\n> 🎲 Кубики бота: **{bot_dice}**\n> {result_text}\n"
        if winnings > 0:
            desc += f"> 🎉 **+{winnings:,}** монет!"
        elif winnings < 0:
            desc += f"> ❌ **-{abs(winnings):,}** монет"
        else:
            desc += f"> ↩️ Ставка вернена"
        desc += f"\n> Баланс: **{new_coins:,}**"
        
        await ctx.send(embed=ce("🎲 Кубики", desc, ctx.guild, color))

    @commands.command(name="wheel", aliases=["w"])
    @commands.cooldown(1, 8, commands.BucketType.user)
    async def wheel(self, ctx: commands.Context, bet: int = 100):
        """🎡 Крутите колесо фортуны! 50x мультипликатор!"""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        
        if bet < 50 or bet > 200000:
            await ctx.send(embed=ce("🎡 Колесо", 
                                     "> Ставка должна быть от **50** до **200,000**!", 
                                     ctx.guild, 0xFF8800), delete_after=10)
            return
        
        if coins < bet:
            await ctx.send(embed=ce("❌ Не хватает монет",
                                     f"> Нужно **{bet:,}**, а у тебя **{coins:,}**",
                                     ctx.guild, 0xFF0000), delete_after=10)
            return
        
        WHEEL = {
            "💀": {"mult": 0, "chance": 30},
            "🔴": {"mult": 0.5, "chance": 22},
            "⚪": {"mult": 1, "chance": 19},
            "🌸": {"mult": 2, "chance": 18},
            "🟢": {"mult": 3, "chance": 7},
            "🟡": {"mult": 5, "chance": 2.5},
            "💜": {"mult": 10, "chance": 1.3},
            "⭐": {"mult": 50, "chance": 0.2},
        }
        
        embed = disnake.Embed(title="🎡 Колесо Крутится...", 
                              description="> 🎡 🎡 🎡\n> *Ожидайте результат...*", 
                              color=0xFF69B4)
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(2)
        
        roll = random.uniform(0, 100)
        cumulative = 0
        result_emoji = "⚪"
        
        for emoji, data in WHEEL.items():
            cumulative += data["chance"]
            if roll <= cumulative:
                result_emoji = emoji
                break
        
        mult = WHEEL[result_emoji]["mult"]
        profit = int(bet * mult) - bet
        new_coins = coins + profit
        save_user(uid, sid, {"coins": new_coins})
        
        if profit > 0:
            color = 0x2ECC71
            res_text = f"🎉 ВЫИГРЫШ! **+{profit:,}** монет (x{mult})"
        elif profit == 0:
            color = 0xFFFF00
            res_text = f"➡️ Вернули ставку (x{mult})"
        else:
            color = 0xE74C3C
            res_text = f"😞 Потеря **-{abs(profit):,}** монет (x{mult})"
        
        embed = disnake.Embed(title="🎡 Колесо Остановилось!", 
                              description=f"> {result_emoji} **x{mult}**\n> _ _\n> {res_text}\n> Баланс: **{new_coins:,}**", 
                              color=color)
        await msg.edit(embed=embed)

    # ══════════════════════════════════════════════════════════
    # 📊 РЫНОК И ТОРГОВЛЯ
    # ══════════════════════════════════════════════════════════

    @commands.command(name="market")
    async def market(self, ctx: commands.Context):
        """📊 Посмотреть цены на рынке."""
        from economy import MARKET_GOODS
        import random
        
        desc = ""
        for good_key, good in MARKET_GOODS.items():
            base = good["base_price"]
            # Симуляция колебания цены
            variance = random.uniform(-good["volatility"], good["volatility"])
            current_price = int(base * (1 + variance))
            arrow = "📈" if current_price > base else "📉" if current_price < base else "➡️"
            desc += f"> {good['emoji']} {good['name']}: **{current_price:,}** монет {arrow}\n"
        
        await ctx.send(embed=ce("📊 Рыночные Цены", desc, ctx.guild, 0x3498DB))

    @commands.command(name="invest")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def invest(self, ctx: commands.Context, plan: str = "short_term", amount: int = 10000):
        """🏦 Инвестировать в план. Выбор: short_term, medium_term, long_term, guild_fund"""
        from economy import INVESTMENT_PLANS
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        
        if plan not in INVESTMENT_PLANS:
            await ctx.send(embed=ce("❌", f"> План '{plan}' не найден!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        inv_plan = INVESTMENT_PLANS[plan]
        if amount < inv_plan["min_investment"] or amount > inv_plan["max_investment"]:
            await ctx.send(embed=ce("❌", 
                f"> Сумма должна быть от **{inv_plan['min_investment']:,}** до **{inv_plan['max_investment']:,}**!", 
                ctx.guild, 0xFF0000), delete_after=10)
            return
        
        if coins < amount:
            await ctx.send(embed=ce("❌ Не хватает монет",
                                     f"> Нужно **{amount:,}**, а у тебя **{coins:,}**",
                                     ctx.guild, 0xFF0000), delete_after=10)
            return
        
        # Вычисляем прибыль
        apy = inv_plan["apy"]
        days = inv_plan["duration_days"]
        profit = int(amount * apy * (days / 365))
        
        new_coins = coins - amount
        save_user(uid, sid, {"coins": new_coins})
        
        desc = f"> {inv_plan['emoji']} {inv_plan['name']}\n"
        desc += f"> Инвестировано: **{amount:,}** монет\n"
        desc += f"> 📈 Годовая доходность: **{apy*100:.0f}%**\n"
        desc += f"> 💰 Прибыль: **+{profit:,}** монет\n"
        desc += f"> 📅 Срок: **{days} дней**\n"
        desc += f"> Возврат: **{amount + profit:,}** монет"
        
        await ctx.send(embed=ce("🏦 Инвестиция", desc, ctx.guild, 0x2ECC71))

    @commands.command(name="lottery")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def lottery(self, ctx: commands.Context, ticket_type: str = "common"):
        """🎫 Купить лотерейный билет! Типы: common, rare, epic, legendary"""
        from economy import LOTTERY_TICKETS
        import random
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        
        if ticket_type not in LOTTERY_TICKETS:
            await ctx.send(embed=ce("❌", "> Неверный тип билета!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        ticket = LOTTERY_TICKETS[ticket_type]
        if coins < ticket["price"]:
            await ctx.send(embed=ce("❌ Не хватает монет",
                                     f"> Нужно **{ticket['price']:,}**, а у тебя **{coins:,}**",
                                     ctx.guild, 0xFF0000), delete_after=10)
            return
        
        # Розыгрыш
        win = random.random() < 0.25  # 25% шанс выигрыша
        
        if win:
            prize = random.randint(int(ticket["avg_win"] * 0.5), ticket["max_win"])
            new_coins = coins - ticket["price"] + prize
            desc = f"> {ticket['emoji']} Ого! Ты выиграл!\n> 🎁 **+{prize:,}** монет!\n> Баланс: **{new_coins:,}**"
        else:
            new_coins = coins - ticket["price"]
            desc = f"> {ticket['emoji']} Не повезло на этот раз...\n> Потеряно **-{ticket['price']:,}** монет\n> Баланс: **{new_coins:,}**"
        
        save_user(uid, sid, {"coins": new_coins})
        
        await ctx.send(embed=ce(ticket["name"], desc, ctx.guild, 0x2ECC71 if win else 0xE74C3C))

    # ══════════════════════════════════════════════════════════
    # 🎊 ЕЖЕДНЕВНЫЕ КВЕСТЫ
    # ══════════════════════════════════════════════════════════

    @commands.command(name="quests")
    async def quests(self, ctx: commands.Context):
        """🎊 Посмотреть доступные ежедневные квесты и награды."""
        from economy import DAILY_QUESTS
        
        desc = ""
        for q in DAILY_QUESTS:
            desc += f"> {q['emoji']} **{q['title']}**\n"
            desc += f"  _{q['description']}_\n"
            desc += f"  Цель: **{q['goal']}** | Награда: **{q['reward']:,}** монет\n\n"
        
        await ctx.send(embed=ce("🎊 Ежедневные Квесты", desc, ctx.guild, 0x9B59B6))

    # ══════════════════════════════════════════════════════════
    # ⚔️ БОЕВАЯ СИСТЕМА
    # ══════════════════════════════════════════════════════════

    @commands.command(name="army")
    async def army(self, ctx: commands.Context):
        """⚔️ Посмотреть армию гильдии."""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        gid = u.get("guild_id")
        
        if not gid:
            await ctx.send(embed=ce("❌", "> Ты не в гильдии!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        gd = get_guild(gid)
        if not gd:
            return
        
        army = gd.get("army", {})
        total_power = sum(ARMY_UNITS[u]["power"] * c for u, c in army.items() if u in ARMY_UNITS)
        
        desc = f"**[{gd['tag']}] {gd['name']}**\n> _ _\n"
        for unit_key, unit_data in ARMY_UNITS.items():
            count = army.get(unit_key, 0)
            power_val = unit_data["power"] * count
            if count > 0:
                desc += f"> {unit_data['emoji']} {unit_data['name']}: **{count}** (мощь: **{power_val}**)\n"
        
        desc += f"\n> **Общая мощь: {total_power}**"
        tech = gd.get("technologies", [])
        if "iron_infantry" in tech:
            total_power = int(total_power * 1.2)
            desc += f"\n> 🏗️ С технологией Железная пехота: **{total_power}**"
        
        await ctx.send(embed=ce("⚔️ Армия Гильдии", desc, ctx.guild, 0xE74C3C))

    @commands.command(name="recruit")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def recruit(self, ctx: commands.Context, unit: str = "recruit", amount: int = 1):
        """⚔️ Нанять войска. Типы: recruit, soldier, knight, champion, legend"""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        gid = u.get("guild_id")
        
        if not gid:
            await ctx.send(embed=ce("❌", "> Ты не в гильдии!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        if unit not in ARMY_UNITS:
            await ctx.send(embed=ce("❌", "> Такого юнита нет!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        unit_data = ARMY_UNITS[unit]
        total_cost = unit_data["cost"] * amount
        
        # Применяем технологию
        gd = get_guild(gid)
        if "supply_chain" in gd.get("technologies", []):
            total_cost = int(total_cost * 0.8)
        
        if coins < total_cost:
            await ctx.send(embed=ce("❌ Не хватает монет",
                                     f"> Нужно **{total_cost:,}**, а у тебя **{coins:,}**",
                                     ctx.guild, 0xFF0000), delete_after=10)
            return
        
        # Нанимаем войска
        army = gd.get("army", {})
        army[unit] = army.get(unit, 0) + amount
        save_guild(gid, {"army": army})
        save_user(uid, sid, {"coins": coins - total_cost})
        
        desc = f"> {unit_data['emoji']} **{unit_data['name']}** × {amount}\n"
        desc += f"> Стоимость: **{total_cost:,}** монет\n"
        desc += f"> Новый баланс: **{coins - total_cost:,}**"
        
        await ctx.send(embed=ce(f"✅ Нанято войск!", desc, ctx.guild, 0x2ECC71))

    @commands.command(name="attack")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def attack(self, ctx: commands.Context, target_tag: str, attack_type: str = "raid"):
        """⚔️ Напасть на гильдию! Типы: raid, siege, conquest"""
        import random
        
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        gid = u.get("guild_id")
        
        if not gid:
            await ctx.send(embed=ce("❌", "> Ты не в гильдии!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        # Проверяем права
        if u.get("guild_rank") not in ["owner", "viceowner", "officer"]:
            await ctx.send(embed=ce("❌", "> Только лидеры могут нападать!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        gd = get_guild(gid)
        if attack_type not in ATTACK_TYPES:
            await ctx.send(embed=ce("❌", "> Такого типа атаки нет!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        target_guild = guild_by_tag(sid, target_tag)
        if not target_guild:
            await ctx.send(embed=ce("❌", f"> Гильдия [{target_tag}] не найдена!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        if target_guild["id"] == gid:
            await ctx.send(embed=ce("❌", "> Ты не можешь напасть на свою гильдию!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        # Проверяем стоимость
        attack_data = ATTACK_TYPES[attack_type]
        cost = attack_data["cost"]
        
        if coins < cost:
            await ctx.send(embed=ce("❌ Не хватает монет",
                                     f"> Нужно **{cost:,}**, а у тебя **{coins:,}**",
                                     ctx.guild, 0xFF0000), delete_after=10)
            return
        
        # Вычисляем мощь
        attacker_power = sum(ARMY_UNITS[u]["power"] * c for u, c in gd.get("army", {}).items() if u in ARMY_UNITS)
        defender_power = sum(ARMY_UNITS[u]["power"] * c for u, c in target_guild.get("army", {}).items() if u in ARMY_UNITS)
        
        # Применяем технологии
        if "iron_infantry" in gd.get("technologies", []):
            attacker_power = int(attacker_power * 1.2)
        if "shield_mastery" in target_guild.get("technologies", []):
            defender_power = int(defender_power * 1.3)
        if "fortifications" in target_guild.get("technologies", []):
            defender_power = int(defender_power * 1.4)
        
        attacker_power = max(1, attacker_power)
        defender_power = max(1, defender_power)
        
        # Боевая система
        attacker_roll = random.randint(1, 100) + (attacker_power // 10)
        defender_roll = random.randint(1, 100) + (defender_power // 10)
        
        win = attacker_roll > defender_roll
        
        loot_amount = 0
        if win:
            target_bank = target_guild.get("bank", 0)
            # Применяем укрепления защиты
            if "fortifications" in target_guild.get("technologies", []):
                loot_amount = int(target_bank * attack_data["loot_percent"] * 0.6)  # -40% от укреплений
            else:
                loot_amount = int(target_bank * attack_data["loot_percent"])
            
            new_bank = max(0, target_bank - loot_amount)
            save_guild(target_guild["id"], {"bank": new_bank})
            save_user(uid, sid, {"coins": coins - cost + loot_amount})
            
            desc = f"> ✅ **ПОБЕДА!**\n> {attack_data['emoji']} {attack_data['name']}\n"
            desc += f"> Противник: **[{target_guild['tag']}]**\n"
            desc += f"> Прибыль: **+{loot_amount:,}** монет\n"
            desc += f"> Новый баланс: **{coins - cost + loot_amount:,}**"
            color = 0x2ECC71
        else:
            save_user(uid, sid, {"coins": coins - cost})
            desc = f"> ❌ **ПОРАЖЕНИЕ!**\n> {attack_data['emoji']} {attack_data['name']}\n"
            desc += f"> Противник: **[{target_guild['tag']}]**\n"
            desc += f"> Потеря: **-{cost:,}** монет\n"
            desc += f"> Новый баланс: **{coins - cost:,}**"
            color = 0xE74C3C
        
        await ctx.send(embed=ce("⚔️ Боевой Результат", desc, ctx.guild, color))

    @commands.command(name="tech")
    async def tech(self, ctx: commands.Context):
        """🔬 Посмотреть доступные технологии и улучшения."""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        gid = u.get("guild_id")
        
        if not gid:
            await ctx.send(embed=ce("❌", "> Ты не в гильдии!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        gd = get_guild(gid)
        tech_list = gd.get("technologies", [])
        coins = gd.get("bank", 0)
        
        desc = ""
        for tech_key, tech_data in TECHNOLOGIES.items():
            status = "✅ Куплена" if tech_key in tech_list else f"🔒 {tech_data['cost']:,} монет"
            desc += f"> {tech_data['name']}\n"
            desc += f"  {tech_data['description']}\n"
            desc += f"  {status}\n\n"
        
        desc += f"Баланс казны: **{coins:,}**"
        await ctx.send(embed=ce("🔬 Технологии Гильдии", desc, ctx.guild, 0x9B59B6))

    @commands.command(name="buytech")
    @commands.cooldown(1, 20, commands.BucketType.user)
    async def buytech(self, ctx: commands.Context, tech_name: str):
        """🔬 Купить технологию для гильдии."""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        gid = u.get("guild_id")
        
        if not gid:
            await ctx.send(embed=ce("❌", "> Ты не в гильдии!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        if u.get("guild_rank") != "owner":
            await ctx.send(embed=ce("❌", "> Только лидер может покупать технологии!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        if tech_name not in TECHNOLOGIES:
            await ctx.send(embed=ce("❌", "> Такой технологии не существует!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        gd = get_guild(gid)
        tech_list = gd.get("technologies", [])
        if tech_name in tech_list:
            await ctx.send(embed=ce("❌", "> Эта технология уже куплена!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        tech_data = TECHNOLOGIES[tech_name]
        bank = gd.get("bank", 0)
        
        if bank < tech_data["cost"]:
            await ctx.send(embed=ce("❌ Не хватает в казне",
                                     f"> Нужно **{tech_data['cost']:,}**, а в казне **{bank:,}**",
                                     ctx.guild, 0xFF0000), delete_after=10)
            return
        
        tech_list.append(tech_name)
        save_guild(gid, {
            "technologies": tech_list,
            "bank": bank - tech_data["cost"]
        })
        
        desc = f"> {tech_data['name']}\n"
        desc += f"> {tech_data['description']}\n"
        desc += f"> Стоимость: **{tech_data['cost']:,}** монет\n"
        desc += f"> Новый баланс казны: **{bank - tech_data['cost']:,}**"
        
        await ctx.send(embed=ce("✅ Технология Куплена!", desc, ctx.guild, 0x2ECC71))

    @commands.command(name="statss")
    async def statss(self, ctx: commands.Context):
        """📊 Расширенная статистика гильдии с рейтингом."""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        gid = u.get("guild_id")
        
        if not gid:
            await ctx.send(embed=ce("❌", "> Ты не в гильдии!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        gd = get_guild(gid)
        
        # Собираем все гильдии для рейтинга
        all_guilds = list(db["guilds"].find({"server_id": sid}))
        all_guilds = sorted(all_guilds, key=lambda x: x.get("bank", 0), reverse=True)
        
        rank = next((i+1 for i, g in enumerate(all_guilds) if g["id"] == gid), 0)
        total_guilds = len(all_guilds)
        
        # Боевая мощь
        army = gd.get("army", {})
        total_power = sum(ARMY_UNITS[u]["power"] * c for u, c in army.items() if u in ARMY_UNITS)
        
        desc = f"**[{gd['tag']}] {gd['name']}**\n> _ _\n"
        desc += f"> 👑 Лидер: <@{gd['owner_id']}>\n"
        desc += f"> 👥 Участников: **{member_count(gid, sid)}**\n"
        desc += f"> 💰 Казна: **{gd.get('bank', 0):,}** монет\n"
        desc += f"> ⚔️ Боевая мощь: **{total_power}**\n"
        desc += f"> 🎓 Технологий: **{len(gd.get('technologies', []))}**\n"
        desc += f"> 🏆 Побед: **{gd.get('wins', 0)}** | Поражений: **{gd.get('losses', 0)}**\n"
        desc += f"> 📊 Позиция в рейтинге: **#{rank} из {total_guilds}**"
        
        await ctx.send(embed=ce("📊 Статистика Гильдии", desc, ctx.guild, 0x3498DB))

    @commands.command(name="achievements")
    async def achievements(self, ctx: commands.Context, user: Optional[disnake.Member] = None):
        """🏆 Посмотреть достижения."""
        from economy import ACHIEVEMENTS
        target = user or ctx.author
        uid, sid = str(target.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        
        coins = u.get("coins", 0)
        farms = len(u.get("farms", []))
        
        desc = ""
        for ach_key, ach in ACHIEVEMENTS.items():
            unlocked = False
            if ach_key == "millionaire" and coins >= 1000000:
                unlocked = True
            elif ach_key == "farmer" and farms >= 10:
                unlocked = True
            
            emoji = "✅" if unlocked else "🔒"
            desc += f"> {emoji} {ach['emoji']} **{ach['title']}**\n"
            desc += f"  {ach['description']}\n"
            if unlocked:
                desc += f"  🎁 Награда: **{ach['reward']:,}** монет\n\n"
            else:
                desc += f"  Заблокировано\n\n"
        
        await ctx.send(embed=ce("🏆 Достижения", desc, ctx.guild, 0xF1C40F))

    # ══════════════════════════════════════════════════════════
    # 💼 РЫНОК: ПОКУПКА И ПРОДАЖА
    # ══════════════════════════════════════════════════════════

    @commands.command(name="mbuy")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def market_buy(self, ctx: commands.Context, good: str = None, quantity: int = 1):
        """💼 Купить товар на рынке! mbuy [товар] [кол-во]"""
        from economy import MARKET_GOODS
        import random
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        
        if not good or good not in MARKET_GOODS:
            await ctx.send(embed=ce("❌", "> Товар не найден! mbuy ore 5", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        good_data = MARKET_GOODS[good]
        base = good_data["base_price"]
        variance = random.uniform(-good_data["volatility"], good_data["volatility"])
        current_price = int(base * (1 + variance))
        total_cost = current_price * quantity
        
        if coins < total_cost:
            await ctx.send(embed=ce("❌ Не хватает монет",
                                     f"> Нужно **{total_cost:,}**, а у тебя **{coins:,}**",
                                     ctx.guild, 0xFF0000), delete_after=10)
            return
        
        # Сохраняем покупку в инвентарь
        inventory = u.get("market_inventory", {})
        inventory[good] = inventory.get(good, 0) + quantity
        new_coins = coins - total_cost
        save_user(uid, sid, {"coins": new_coins, "market_inventory": inventory})
        
        desc = f"> {good_data['emoji']} **{good_data['name']}** x{quantity}\n"
        desc += f"> Цена за шт: **{current_price:,}** монет\n"
        desc += f"> Итого: **-{total_cost:,}** монет\n"
        desc += f"> Баланс: **{new_coins:,}**"
        
        await ctx.send(embed=ce("✅ Покупка", desc, ctx.guild, 0x2ECC71))

    @commands.command(name="msell")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def market_sell(self, ctx: commands.Context, good: str = None, quantity: int = 1):
        """💼 Продать товар! msell [товар] [кол-во]"""
        from economy import MARKET_GOODS
        import random
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        inventory = u.get("market_inventory", {})
        
        if not good or good not in MARKET_GOODS:
            await ctx.send(embed=ce("❌", "> Товар не найден!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        if inventory.get(good, 0) < quantity:
            await ctx.send(embed=ce("❌", f"> У тебя только **{inventory.get(good, 0)}** этого товара!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        good_data = MARKET_GOODS[good]
        base = good_data["base_price"]
        variance = random.uniform(-good_data["volatility"], good_data["volatility"])
        current_price = int(base * (1 + variance) * 0.95)  # 95% цены (комиссия 5%)
        total_gain = current_price * quantity
        
        inventory[good] -= quantity
        new_coins = coins + total_gain
        save_user(uid, sid, {"coins": new_coins, "market_inventory": inventory})
        
        desc = f"> {good_data['emoji']} **{good_data['name']}** x{quantity}\n"
        desc += f"> Цена за шт: **{current_price:,}** монет\n"
        desc += f"> Итого: **+{total_gain:,}** монет\n"
        desc += f"> Баланс: **{new_coins:,}**"
        
        await ctx.send(embed=ce("✅ Продажа", desc, ctx.guild, 0x2ECC71))

    @commands.command(name="minventory")
    async def market_inventory(self, ctx: commands.Context):
        """💼 Посмотреть инвентарь товаров."""
        from economy import MARKET_GOODS
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        inventory = u.get("market_inventory", {})
        
        if not inventory:
            await ctx.send(embed=ce("❌", "> Твой инвентарь пуст!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        desc = ""
        total_value = 0
        for good, qty in inventory.items():
            if good in MARKET_GOODS:
                good_data = MARKET_GOODS[good]
                est_value = good_data["base_price"] * qty
                total_value += est_value
                desc += f"> {good_data['emoji']} {good_data['name']}: x**{qty}** (~{est_value:,} монет)\n"
        
        desc += f"\n> 📊 Примерная стоимость: **{total_value:,}** монет"
        await ctx.send(embed=ce("💼 Инвентарь", desc, ctx.guild, 0x3498DB))

    # ══════════════════════════════════════════════════════════
    # 🏦 ИНВЕСТИЦИИ: ОТСЛЕЖИВАНИЕ И ВЫВОД
    # ══════════════════════════════════════════════════════════

    @commands.command(name="invests")
    async def investments(self, ctx: commands.Context):
        """🏦 Посмотреть свои активные инвестиции."""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        inv_list = u.get("investments", [])
        
        if not inv_list:
            await ctx.send(embed=ce("❌", "> У тебя нет активных инвестиций!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        from datetime import datetime
        from economy import INVESTMENT_PLANS
        
        desc = ""
        now = datetime.utcnow().timestamp()
        
        for inv in inv_list:
            plan_key = inv.get("plan")
            plan = INVESTMENT_PLANS.get(plan_key, {})
            amount = inv.get("amount", 0)
            created = inv.get("created_at", now)
            end_time = created + (plan.get("duration_days", 0) * 86400)
            
            apy = plan.get("apy", 0)
            profit = int(amount * apy * (plan.get("duration_days", 0) / 365))
            
            time_left = max(0, end_time - now)
            days_left = int(time_left / 86400)
            
            status = "✅ Готово!" if time_left <= 0 else f"⏳ {days_left} дней"
            desc += f"> {plan.get('emoji', '📆')} {plan.get('name', 'Неизвестный план')}\n"
            desc += f"> Сумма: **{amount:,}** | Прибыль: **+{profit:,}** | {status}\n\n"
        
        await ctx.send(embed=ce("🏦 Инвестиции", desc, ctx.guild, 0x2ECC71))

    @commands.command(name="iwithdraw")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def invest_withdraw(self, ctx: commands.Context, index: int = 0):
        """🏦 Вывести инвестицию! iwithdraw [номер]"""
        from datetime import datetime
        from economy import INVESTMENT_PLANS
        
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        inv_list = u.get("investments", [])
        coins = u.get("coins", 0)
        
        if not inv_list or index >= len(inv_list) or index < 0:
            await ctx.send(embed=ce("❌", "> Инвестиция не найдена!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        inv = inv_list[index]
        plan_key = inv.get("plan")
        plan = INVESTMENT_PLANS.get(plan_key, {})
        amount = inv.get("amount", 0)
        created = inv.get("created_at", datetime.utcnow().timestamp())
        end_time = created + (plan.get("duration_days", 0) * 86400)
        now = datetime.utcnow().timestamp()
        
        if now < end_time:
            days_left = int((end_time - now) / 86400)
            await ctx.send(embed=ce("❌", f"> Можно вывести через **{days_left}** дней!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        apy = plan.get("apy", 0)
        profit = int(amount * apy * (plan.get("duration_days", 0) / 365))
        total_return = amount + profit
        
        new_coins = coins + total_return
        inv_list.pop(index)
        save_user(uid, sid, {"coins": new_coins, "investments": inv_list})
        
        desc = f"> Инвестированно: **{amount:,}** монет\n"
        desc += f"> Прибыль: **+{profit:,}** монет\n"
        desc += f"> Итого: **+{total_return:,}** монет\n"
        desc += f"> Баланс: **{new_coins:,}**"
        
        await ctx.send(embed=ce("✅ Вывод Средств", desc, ctx.guild, 0x2ECC71))

    # ══════════════════════════════════════════════════════════
    # 🎊 КВЕСТЫ: ОТСЛЕЖИВАНИЕ И ПОЛУЧЕНИЕ НАГРАД
    # ══════════════════════════════════════════════════════════

    @commands.command(name="qclaim")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def quest_claim(self, ctx: commands.Context, quest_id: str = None):
        """🎊 Получить награду за квест! qclaim [id]"""
        from economy import DAILY_QUESTS
        
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        quest_progress = u.get("quest_progress", {})
        claimed_quests = u.get("claimed_quests", {})
        
        quest = None
        for q in DAILY_QUESTS:
            if q["id"] == quest_id:
                quest = q
                break
        
        if not quest:
            await ctx.send(embed=ce("❌", "> Квест не найден!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        # Проверяем прогресс
        progress = quest_progress.get(quest_id, 0)
        if progress < quest["goal"]:
            await ctx.send(embed=ce("❌", f"> Прогресс: **{progress}/{quest['goal']}**", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        # Проверяем, не получена ли уже награда
        if claimed_quests.get(quest_id, False):
            await ctx.send(embed=ce("❌", "> Ты уже получил награду за этот квест!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        # Выдаём награду
        new_coins = coins + quest["reward"]
        claimed_quests[quest_id] = True
        save_user(uid, sid, {"coins": new_coins, "claimed_quests": claimed_quests})
        
        desc = f"> {quest['emoji']} **{quest['title']}**\n"
        desc += f"> 🎁 Награда: **+{quest['reward']:,}** монет\n"
        desc += f"> Баланс: **{new_coins:,}**"
        
        await ctx.send(embed=ce("✅ Квест Завершён", desc, ctx.guild, 0x2ECC71))

    # ══════════════════════════════════════════════════════════
    # 🏆 ДОСТИЖЕНИЯ: ПОЛУЧЕНИЕ НАГРАД
    # ══════════════════════════════════════════════════════════

    @commands.command(name="aclaim")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def achievement_claim(self, ctx: commands.Context, ach_id: str = None):
        """🏆 Получить награду за достижение! aclaim [id]"""
        from economy import ACHIEVEMENTS
        
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        claimed_ach = u.get("claimed_achievements", [])
        
        if ach_id not in ACHIEVEMENTS:
            await ctx.send(embed=ce("❌", "> Достижение не найдено!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        if ach_id in claimed_ach:
            await ctx.send(embed=ce("❌", "> Ты уже получил награду за это достижение!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        ach = ACHIEVEMENTS[ach_id]
        
        # Проверяем условие разблокировки
        unlocked = False
        if ach_id == "millionaire" and coins >= 1000000:
            unlocked = True
        elif ach_id == "farmer" and u.get("farms", {}) and len(u.get("farms", {})) >= 10:
            unlocked = True
        elif ach_id == "gambler" and u.get("casino_earnings", 0) >= 100000:
            unlocked = True
        elif ach_id == "trader" and u.get("market_trades", 0) >= 50:
            unlocked = True
        elif ach_id == "investor" and u.get("total_investments", 0) >= 500000:
            unlocked = True
        
        if not unlocked:
            await ctx.send(embed=ce("❌", "> Это достижение ещё не разблокировано!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        # Выдаём награду
        new_coins = coins + ach["reward"]
        claimed_ach.append(ach_id)
        save_user(uid, sid, {"coins": new_coins, "claimed_achievements": claimed_ach})
        
        desc = f"> {ach['emoji']} **{ach['title']}**\n"
        desc += f"> 🎁 Награда: **+{ach['reward']:,}** монет\n"
        desc += f"> Баланс: **{new_coins:,}**"
        
        await ctx.send(embed=ce("✅ Достижение Получено", desc, ctx.guild, 0x2ECC71))

    # ══════════════════════════════════════════════════════════
    # ⬆️ СИСТЕМА УРОВНЕЙ И ОПЫТА
    # ══════════════════════════════════════════════════════════

    @commands.command(name="level")
    async def profile_level(self, ctx: commands.Context, user: disnake.Member = None):
        """⬆️ Посмотреть уровень и опыт!"""
        from economy import PLAYER_LEVELS
        
        if not user:
            user = ctx.author
        
        uid, sid = str(user.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        
        xp = u.get("xp", 0)
        coins = u.get("coins", 0)
        current_level = 1
        
        for level in sorted(PLAYER_LEVELS.keys(), reverse=True):
            if xp >= PLAYER_LEVELS[level]["xp_required"]:
                current_level = level
                break
        
        level_data = PLAYER_LEVELS.get(current_level, {})
        next_level = current_level + 5
        next_data = PLAYER_LEVELS.get(next_level, {})
        
        xp_for_next = next_data.get("xp_required", xp + 1000) if next_data else xp + 1000
        xp_progress = xp - level_data.get("xp_required", 0)
        xp_needed = xp_for_next - level_data.get("xp_required", 1000)
        bar_filled = int((xp_progress / xp_needed) * 20) if xp_needed > 0 else 20
        xp_bar = "🟩" * bar_filled + "⬜" * (20 - bar_filled)
        
        desc = f"> {level_data.get('title', '🌱 Новичок')} (Уровень **{current_level}**)\n"
        desc += f"> 💰 Баланс: **{coins:,}** монет\n"
        desc += f"> 📊 Опыт: **{xp:,}**\n\n"
        desc += f"> {xp_bar}\n"
        desc += f"> До уровня {next_level}: **{max(0, xp_for_next - xp):,}** опыта\n"
        desc += f"> 10% бонус к заработкам за лучший арсенал: **+{int(level_data.get('coin_bonus', 1.0) * 100) - 100}%**"
        
        await ctx.send(embed=ce(f"⬆️ Профиль {user.display_name}", desc, ctx.guild, 0x9B59B6))

    # ══════════════════════════════════════════════════════════
    # 🎁 РЕЙТИНГИ И НАГРАДЫ
    # ══════════════════════════════════════════════════════════

    @commands.command(name="leaderboard1")
    async def leaderboard1(self, ctx: commands.Context, board_type: str = "wealth"):
        """📊 Посмотреть рейтинги! leaderboard [wealth/power/level]"""
        from economy import LEADERBOARD_REWARDS
        
        sid = str(ctx.guild.id)
        board_config = LEADERBOARD_REWARDS.get(board_type)
        
        if not board_config:
            await ctx.send(embed=ce("❌", "> Тип рейтинга не найден!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        all_users = list(db["users"].find({"server_id": sid}))
        
        if board_type == "wealth":
            all_users.sort(key=lambda u: u.get("coins", 0), reverse=True)
            field_name = "💰"
        elif board_type == "power":
            all_users.sort(key=lambda u: u.get("guild_power", 0), reverse=True)
            field_name = "⚔️"
        elif board_type == "level":
            all_users.sort(key=lambda u: u.get("xp", 0), reverse=True)
            field_name = "📈"
        
        desc = ""
        for i, u in enumerate(all_users[:10], 1):
            try:
                user = await ctx.bot.fetch_user(int(u["user_id"]))
                user_name = user.name
            except:
                user_name = "Unknown"
            
            if board_type == "wealth":
                value = u.get("coins", 0)
                emoji = "💰"
            elif board_type == "power":
                value = u.get("guild_power", 0)
                emoji = "⚔️"
            else:
                value = u.get("xp", 0)
                emoji = "📈"
            
            # Медали
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"#{i}"
            reward = board_config["places"].get(i, 0)
            
            desc += f"> {medal} **{user_name}** {emoji} **{value:,}** ({reward:,} 💰)\n"
        
        desc += f"\n> 🎁 Награды выдаются в конце месяца!"
        
        await ctx.send(embed=ce(f"📊 {board_config['title']}", desc, ctx.guild, 0xF39C12))

    # ══════════════════════════════════════════════════════════
    # ✨ СИСТЕМА ПРЕСТИЖА
    # ══════════════════════════════════════════════════════════

    @commands.command(name="prestige")
    async def prestige(self, ctx: commands.Context):
        """✨ Информация о системе престижа!"""
        from economy import PRESTIGE_BONUSES
        
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        current_prestige = u.get("prestige_level", 0)
        coins = u.get("coins", 0)
        
        current_data = PRESTIGE_BONUSES.get(current_prestige, {})
        next_prestige = current_prestige + 1
        next_data = PRESTIGE_BONUSES.get(next_prestige)
        
        desc = f"> Текущий уровень: {current_data.get('title', '🌱')} **({current_prestige})**\n"
        desc += f"> Множитель: **x{current_data.get('mult', 1.0)}**\n"
        desc += f"> Баланс: **{coins:,}** монет\n\n"
        
        if next_data:
            cost = next_data.get("cost", 0)
            desc += f"> 🔼 Следующий уровень: {next_data.get('title', '⭐')}\n"
            desc += f"> Стоимость: **{cost:,}** монет\n"
            if coins >= cost:
                desc += f"> ✅ Можешь повысить престиж!"
            else:
                desc += f"> ❌ Не хватает **{cost - coins:,}** монет"
        else:
            desc += f"> 👑 Ты достиг максимального уровня престижа!"
        
        await ctx.send(embed=ce("✨ Система Престижа", desc, ctx.guild, 0xE74C3C))

    @commands.command(name="ppromote")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def prestige_promote(self, ctx: commands.Context):
        """✨ Повысить уровень престижа!"""
        from economy import PRESTIGE_BONUSES
        
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        current_prestige = u.get("prestige_level", 0)
        
        next_prestige = current_prestige + 1
        next_data = PRESTIGE_BONUSES.get(next_prestige)
        
        if not next_data:
            await ctx.send(embed=ce("❌", "> Уже максимальный престиж!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        cost = next_data.get("cost", 0)
        if coins < cost:
            await ctx.send(embed=ce("❌ Не хватает монет",
                                     f"> Нужно **{cost:,}**, а у тебя **{coins:,}**",
                                     ctx.guild, 0xFF0000), delete_after=10)
            return
        
        new_coins = coins - cost
        new_xp = 0  # Обнуляем опыт при престиже
        save_user(uid, sid, {"coins": new_coins, "xp": new_xp, "prestige_level": next_prestige})
        
        desc = f"> 🎉 Престиж повышен!\n"
        desc += f"> {next_data.get('title', '⭐')}\n"
        desc += f"> Новый множитель: **x{next_data.get('mult', 1.0)}**\n"
        desc += f"> Баланс: **{new_coins:,}** монет"
        
        await ctx.send(embed=ce("✨ Престиж Повышен", desc, ctx.guild, 0x2ECC71))

    # ══════════════════════════════════════════════════════════
    # 🔥 ЕЖЕДНЕВНЫЕ ЛУКИ МОЛОТЫ (DAILY STREAKS)
    # ══════════════════════════════════════════════════════════

    @commands.command(name="streak")
    async def daily_streak(self, ctx: commands.Context):
        """🔥 Посмотреть ежедневную серию!"""
        from datetime import datetime
        
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        
        streak = u.get("daily_streak", 0)
        last_claim = u.get("last_daily_claim", 0)
        now = datetime.utcnow().timestamp()
        
        # Проверяем, можно ли получить ежедневный подарок
        can_claim = (now - last_claim) > 86400  # 24 часа
        
        next_reward = 100 * (1 + streak // 5)  # +100 за каждые 5 дней
        
        desc = f"> 🔥 Текущая серия: **{streak}** дней\n"
        desc += f"> 💰 Следующая награда: **{next_reward:,}** монет\n\n"
        
        if can_claim:
            desc += f"> ✅ Ты можешь получить награду! Используй `!dclaim`"
        else:
            hours_left = int((86400 - (now - last_claim)) / 3600)
            desc += f"> ⏳ Возвращайся через **{hours_left}** часов"
        
        await ctx.send(embed=ce("🔥 Ежедневная Серия", desc, ctx.guild, 0xFF9800))

    @commands.command(name="dclaim")
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily_claim(self, ctx: commands.Context):
        """🔥 Получить ежедневный подарок!"""
        from datetime import datetime
        from economy import DAILY_STREAK_REWARDS
        
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        streak = u.get("daily_streak", 0)
        
        # Увеличиваем серию
        new_streak = streak + 1
        reward = DAILY_STREAK_REWARDS.get(new_streak, 100)
        new_coins = coins + reward
        
        save_user(uid, sid, {
            "coins": new_coins,
            "daily_streak": new_streak,
            "last_daily_claim": datetime.utcnow().timestamp()
        })
        
        desc = f"> 🎁 Награда за {new_streak} дней!\n"
        desc += f"> **+{reward:,}** монет\n"
        desc += f"> Баланс: **{new_coins:,}**"
        
        await ctx.send(embed=ce("✅ Ежедневный Подарок", desc, ctx.guild, 0x2ECC71))

    # ══════════════════════════════════════════════════════════
    # 🤝 АЛЬЯНСЫ
    # ══════════════════════════════════════════════════════════

    @commands.command(name="alliance")
    async def alliance(self, ctx: commands.Context):
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        gid = u.get("guild_id")
        
        if not gid:
            await ctx.send(embed=ce("❌", "> Ты не в гильдии!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        alliances = get_guild_alliances(gid)
        
        if not alliances:
            await ctx.send(embed=ce("❌", "> Твоя гильдия не состоит ни в каком альянсе!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        for alliance in alliances:
            members = alliance.get("members", [])
            member_guilds = [get_guild(m) for m in members]
            member_guilds = [g for g in member_guilds if g]
            
            total_power = 0
            for guild in member_guilds:
                army = guild.get("army", {})
                power = sum(ARMY_UNITS[u]["power"] * c for u, c in army.items() if u in ARMY_UNITS)
                total_power += power
            
            desc = f"**{alliance['name']}** (Лидер: <@{alliance['leader_id']}>)\n> _ _\n"
            desc += f"> Участников: **{len(member_guilds)}**\n"
            desc += f"> Общая боевая мощь: **{total_power}**\n"
            desc += f"> Казна альянса: **{alliance.get('bank', 0):,}** монет\n"
            desc += f"> _ _\n> Члены:\n"
            
            for guild in member_guilds:
                tag = guild["tag"]
                desc += f"> • **[{tag}]** {guild['name']}\n"
            
            await ctx.send(embed=ce("🤝 Альянс", desc, ctx.guild, 0x9B59B6))

    @commands.command(name="createalliance")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def createalliance(self, ctx: commands.Context, alliance_name: str):
        """🤝 Создать новый альянс."""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        gid = u.get("guild_id")
        
        if not gid:
            await ctx.send(embed=ce("❌", "> Ты не в гильдии!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        gd = get_guild(gid)
        if u.get("guild_rank") != "owner":
            await ctx.send(embed=ce("❌", "> Только лидер может создать альянс!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        if get_alliance(sid, alliance_name):
            await ctx.send(embed=ce("❌", "> Альянс с таким названием уже существует!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        alliance_id = str(uuid.uuid4())[:8]
        save_alliance(alliance_id, {
            "id": alliance_id,
            "server_id": sid,
            "name": alliance_name.lower(),
            "leader_id": uid,
            "members": [gid],
            "bank": 0,
            "created_at": str(datetime.utcnow()),
        })
        
        desc = f"> **{alliance_name}**\n"
        desc += f"> Лидер: {ctx.author.mention}\n"
        desc += f"> Основатель: [**{gd['tag']}**] {gd['name']}"
        
        await ctx.send(embed=ce("✅ Альянс Создан!", desc, ctx.guild, 0x2ECC71))

    @commands.command(name="joinalliance")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def joinalliance(self, ctx: commands.Context, alliance_name: str):
        """🤝 Присоединиться к альянсу (нужно приглашение лидера)."""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        gid = u.get("guild_id")
        
        if not gid:
            await ctx.send(embed=ce("❌", "> Ты не в гильдии!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        gd = get_guild(gid)
        if u.get("guild_rank") != "owner":
            await ctx.send(embed=ce("❌", "> Только лидер может присоединить гильдию!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        alliance = get_alliance(sid, alliance_name)
        if not alliance:
            await ctx.send(embed=ce("❌", f"> Альянс '{alliance_name}' не найден!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        if gid in alliance.get("members", []):
            await ctx.send(embed=ce("❌", "> Ты уже в этом альянсе!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        members = alliance.get("members", [])
        members.append(gid)
        save_alliance(alliance["id"], {"members": members})
        
        desc = f"> {ctx.author.mention} присоединил **[{gd['tag']}]** к альянсу **{alliance['name']}**!"
        
        await ctx.send(embed=ce("✅ Вступление в Альянс!", desc, ctx.guild, 0x2ECC71))

    @commands.command(name="alliances")
    async def alliances_list(self, ctx: commands.Context):
        """🤝 Посмотреть все альянсы сервера."""
        sid = str(ctx.guild.id)
        
        try:
            all_alliances = list(db["alliances"].find({"server_id": sid}))
        except:
            all_alliances = []
        
        if not all_alliances:
            await ctx.send(embed=ce("❌", "> На сервере нет альянсов!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        desc = ""
        for alliance in all_alliances:
            members_count = len(alliance.get("members", []))
            desc += f"> 🤝 **{alliance['name']}** ({members_count} гильдий)\n"
            desc += f"  Казна: **{alliance.get('bank', 0):,}** | Лидер: <@{alliance['leader_id']}>\n\n"
        
        await ctx.send(embed=ce("🤝 Альянсы Сервера", desc, ctx.guild, 0x9B59B6))

    @commands.command(name="galliancepay")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def galliancepay(self, ctx: commands.Context, amount: int):
        """🤝 Пожертвовать деньги в казну альянса."""
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        gid = u.get("guild_id")
        
        if not gid:
            await ctx.send(embed=ce("❌", "> Ты не в гильдии!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        alliances = get_guild_alliances(gid)
        if not alliances:
            await ctx.send(embed=ce("❌", "> Твоя гильдия не состоит в альянсе!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        if coins < amount:
            await ctx.send(embed=ce("❌ Не хватает монет",
                                     f"> Нужно **{amount:,}**, а у тебя **{coins:,}**",
                                     ctx.guild, 0xFF0000), delete_after=10)
            return
        
        alliance = alliances[0]
        new_bank = alliance.get("bank", 0) + amount
        save_alliance(alliance["id"], {"bank": new_bank})
        save_user(uid, sid, {"coins": coins - amount})
        
        desc = f"> {ctx.author.mention} пожертвовал **{amount:,}** монет в казну альянса!\n"
        desc += f"> Казна: **{new_bank:,}** монет\n"
        desc += f"> Баланс: **{coins - amount:,}**"
        
        await ctx.send(embed=ce("🤝 Пожертвование в Альянс", desc, ctx.guild, 0x2ECC71))

    # ── Помощь ──────────────────────────────────────────────

    @commands.command(name="ghelp")
    async def ghelp(self, ctx: commands.Context):
        sid     = str(ctx.guild.id)
        msg_req = get_msg_required(sid)
        e = disnake.Embed(title="🌸 Sunshine Paradise — ПОЛНАЯ СПРАВКА v5.2", color=0xFF69B4)
        e.set_author(name=EMBED_AUTHOR, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        
        e.add_field(name="💰 ЭКОНОМИКА ИГРОКОВ",
                    value=("`!profile [@]` `!balance` `!daily` `!work [job]`\n"
                           "`!pay @юзер сумма` `!top` `!level [@]`"),
                    inline=False)
        
        e.add_field(name="🎰 КАЗИНО — 6 ИГР (с параметрами all/half/25%)",
                    value=("`!blackjack [ставка]` или `!bj all/half/25%/число` — **Блэкджек**\n"
                           "`!slots [ставка]` — **Слоты** (3x, 2x, 1x)\n"
                           "`!coinflip [ставка] [heads/tails/h/t]` — **Монетка**\n"
                           "`!roulette [ставка] [red/black/число]` — **Рулетка**\n"
                           "`!dice [ставка]` — **Кубики** 1-100\n"
                           "`!wheel [ставка]` — **Колесо Фортуны** (x50!)"),
                    inline=False)
        
        e.add_field(name="🏰 ГИЛЬДИИ — ПОЛНОЕ УПРАВЛЕНИЕ",
                    value=(f"`!gcreate [название]` _(нужно {msg_req} msg)_ — Создать\n"
                           "`!ginfo [тег]` `!glist` `!gmembers`\n"
                           "`!ginvite @юзер` `!gleave` `!gdelete`"),
                    inline=False)
        
        e.add_field(name="💸 КАЗНА И БАНК ГИЛЬДИИ",
                    value=("`!gbank` — Состояние казны\n"
                           "`!gdeposit сумма` — Пополнить казну\n"
                           "`!gwithdraw сумма` — Вывести из казны\n"
                           "`!geconomy` — Прибыль гильдии"),
                    inline=False)
        
        e.add_field(name="⚙️ ВЛАСТЬ И УПРАВЛЕНИЕ",
                    value=("`!gkick @юзер` — Исключить\n"
                           "`!gpromote @юзер` — Повысить в должность\n"
                           "`!gdemote @юзер` — Понизить в должность\n"
                           "`!gtransfer @юзер` — Передать лидерство"),
                    inline=False)
        
        e.add_field(name="🎨 ДОП. УПРАВЛЕНИЕ ГИЛЬДИЕЙ",
                    value=("`!gcolor цвет` — Изменить цвет\n"
                           "`!gdesc описание` — Установить описание\n"
                           "`!granks` — Список рангов\n"
                           "`!gstats` — Статистика"),
                    inline=False)
        
        e.add_field(name="⚔️ ВОЙНЫ И КОНФЛИКТЫ",
                    value=("`!gwar @тег` — **Война гильдий** с боевой системой\n"
                           "`!gpatrol` — Патруль гильдии\n"
                           "`!army` — Состав армии\n"
                           "`!recruit [тип] [кол]` — Нанять войск"),
                    inline=False)
        
        e.add_field(name="🌾 ФЕРМЫ И ПАССИВНЫЙ ДОХОД",
                    value=("`!buyfarm [тип]` — Купить ферму\n"
                           "`!myfarms` — Моиы фермы\n"
                           "`!harvest` — Собрать урожай\n"
                           "`!gmyincome` — Доход гильдии"),
                    inline=False)
        
        e.add_field(name="📊 РЫНОК И ИНВЕСТИЦИИ",
                    value=("`!market` — Цены на товары\n"
                           "`!invest [план] [сумма]` — Инвестировать\n"
                           "`!invests` — Мои инвестиции\n"
                           "`!iwithdraw [id]` — Вывести"),
                    inline=False)
        
        e.add_field(name="🎊 КВЕСТЫ И ДОСТИЖЕНИЯ",
                    value=("`!quests` — Ежедневные квесты\n"
                           "`!qclaim [id]` — Получить награду квеста\n"
                           "`!achievements` — Достижения\n"
                           "`!aclaim [id]` — Получить награду за достижение"),
                    inline=False)
        
        e.add_field(name="🎁 СИСТЕМА ПРЕДМЕТОВ",
                    value=("`!inventory` — Инвентарь предметов\n"
                           "`!sellitem [id]` — Продать предмет\n"
                           "`!mybadge` — Мой статус баффа"),
                    inline=False)
        
        e.add_field(name="📈 ПРОГРЕССИЯ",
                    value=("`!prestige` — Инфо о престиже\n"
                           "`!ppromote` — Повысить престиж\n"
                           "`!streak` — Ежедневная серия\n"
                           "`!dclaim` — Получить подарок дня"),
                    inline=False)
        
        e.add_field(name="🔬 ТЕХНОЛОГИИ",
                    value=("`!tech` — Список технологий\n"
                           "`!buytech [название]` — Купить технологию"),
                    inline=False)
        
        e.add_field(name="🤝 АЛЬЯНСЫ",
                    value=("`!createalliance [название]` — Создать альянс\n"
                           "`!joinalliance [название]` — Присоединиться\n"
                           "`!alliance` — Информация альянса\n"
                           "`!alliances` — Все альянсы"),
                    inline=False)
        
        e.add_field(name="� МОЩЬ И РЕЙТИНГИ ГИЛЬДИЙ",
                    value=("`!glist` — **Гильдии по мощи** (казна+члены+победы+апгрейды)\n"
                           "`!gstats [тег]` — **Полная статистика** гильдии\n"
                           "`!gcard [тег]` — **Визуальная карточка** гильдии\n"
                           "`!granking [power|wins|members|bank]` — **Рейтинг** по разным критериям\n"
                           "`!gtop` — **ТОП 3** лучшие гильдии"),
                    inline=False)
        
        e.add_field(name="💝 ПОДДЕРЖКА ГИЛЬДИИ",
                    value=("`!gtribute [сумма]` — **Пожертвовать** денег в казну гильдии (1 раз в час)"),
                    inline=False)
        
        e.add_field(name="📈 СИСТЕМА УРОВНЕЙ ГИЛЬДИЙ",
                    value=("`!glevel [тег]` — **Уровень и прогресс** гильдии\n"
                           "`!glevels` — **Информация о системе** уровней и бонусов"),
                    inline=False)
        
        e.add_field(name="�🎮 ПРИМЕРЫ КОМАНД",
                    value=("`!bj all` — Поставить все монеты\n"
                           "`!bj half` — Поставить половину\n"
                           "`!bj 25%` — Поставить 25% от баланса\n"
                           "`!BJ 1000` — Поставить 1000 (регистр не важен)\n"
                           "`!GAY` = `!gay` = `!gAy` (любые команды)"),
                    inline=False)
        
        clr_line = " ".join(f"`{k}`" for k in COLORS)
        e.add_field(name="🎨 ЦВЕТА ГИЛЬДИИ", value=clr_line, inline=False)
        e.set_footer(text=f"🌸 Sunshine Paradise | Все команды работают в любом регистре! | Нужно {msg_req} сообщений для создания 💬")
        await ctx.send(embed=e)

    # ══════════════════════════════════════════════════════════
    # 🎁 СИСТЕМА ПРЕДМЕТОВ И ЛУТА
    # ══════════════════════════════════════════════════════════

    @commands.command(name="inventory")
    async def player_inventory(self, ctx: commands.Context, user: disnake.Member = None):
        """🎒 Посмотреть инвентарь предметов!"""
        from economy import EQUIPMENT_ITEMS, EQUIPMENT_TIERS
        
        if not user:
            user = ctx.author
        
        uid, sid = str(user.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        equipment = u.get("equipment", {})
        
        if not equipment:
            await ctx.send(embed=ce("❌", "> Инвентарь пуст!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        desc = ""
        total_power = 0
        for item_id, tier in equipment.items():
            if item_id in EQUIPMENT_ITEMS:
                item = EQUIPMENT_ITEMS[item_id]
                tier_data = EQUIPMENT_TIERS.get(tier, {})
                stats = tier_data.get("stats", {})
                power = stats.get("power", 1)
                total_power += power
                desc += f"> {tier_data.get('rarity', '?')} {item['name']} (+{power} мощи)\n"
        
        desc += f"\n> ⚔️ Общая мощь: **+{total_power}**"
        await ctx.send(embed=ce("🎒 Инвентарь", desc, ctx.guild, 0x9B59B6))

    @commands.command(name="sellitem")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def sell_item(self, ctx: commands.Context, item_id: str = None):
        """🎁 Продать предмет! sellitem [item_id]"""
        from economy import EQUIPMENT_ITEMS, EQUIPMENT_TIERS
        
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        equipment = u.get("equipment", {})
        
        if not item_id or item_id not in equipment:
            await ctx.send(embed=ce("❌", "> Предмет не найден!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        tier = equipment[item_id]
        item = EQUIPMENT_ITEMS.get(item_id, {})
        tier_data = EQUIPMENT_TIERS.get(tier, {})
        
        # Цена зависит от редкости
        base_price = item.get("sell_price", 100)
        multiplier = {"common": 1, "rare": 3, "epic": 8, "legendary": 25, "mythic": 100}
        sell_price = base_price * multiplier.get(tier, 1)
        
        new_coins = coins + sell_price
        del equipment[item_id]
        save_user(uid, sid, {"coins": new_coins, "equipment": equipment})
        
        desc = f"> {tier_data.get('rarity', '?')} {item.get('name', 'Предмет')}\n"
        desc += f"> 💰 **+{sell_price:,}** монет\n"
        desc += f"> Баланс: **{new_coins:,}**"
        
        await ctx.send(embed=ce("✅ Продажа Предмета", desc, ctx.guild, 0x2ECC71))

    # ══════════════════════════════════════════════════════════
    # 🎯 СИСТЕМА ОХОТЫ (BOUNTIES)
    # ══════════════════════════════════════════════════════════

    @commands.command(name="bounties")
    async def bounties(self, ctx: commands.Context):
        """🎯 Посмотреть доступные охоты (bounties)!"""
        from economy import BOUNTY_TYPES
        
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        active_bounties = u.get("active_bounties", [])
        
        desc = ""
        for bounty_type, bounty_data in BOUNTY_TYPES.items():
            is_active = bounty_type in active_bounties
            status = "✅ АКТИВНА" if is_active else "❌ Доступна"
            desc += f"> {bounty_data['title']} ({status})\n"
            desc += f"  Сложность: {bounty_data['difficulty']}\n"
            desc += f"  Награда: **{bounty_data['reward']:,}** монет\n"
            desc += f"  Время: {bounty_data['timer']} сек\n\n"
        
        desc += "> Используй `!acceptbounty [тип]` для принятия охоты!"
        await ctx.send(embed=ce("🎯 Охоты Сервера", desc, ctx.guild, 0xE74C3C))

    @commands.command(name="acceptbounty")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def accept_bounty(self, ctx: commands.Context, bounty_type: str = None):
        """🎯 Принять охоту! acceptbounty [тип]"""
        from economy import BOUNTY_TYPES
        from datetime import datetime
        
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        active_bounties = u.get("active_bounties", [])
        
        if bounty_type not in BOUNTY_TYPES:
            await ctx.send(embed=ce("❌", "> Охота не найдена!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        if bounty_type in active_bounties:
            await ctx.send(embed=ce("❌", "> Ты уже принял эту охоту!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        bounty = BOUNTY_TYPES[bounty_type]
        active_bounties.append(bounty_type)
        
        save_user(uid, sid, {
            "active_bounties": active_bounties,
            f"bounty_{bounty_type}_start": datetime.utcnow().timestamp()
        })
        
        desc = f"> {bounty['title']}\n"
        desc += f"> Сложность: **{bounty['difficulty']}**\n"
        desc += f"> Награда: **{bounty['reward']:,}** монет\n"
        desc += f"> Время: **{bounty['timer']}** сек\n\n"
        desc += f"> Используй `!completebounty {bounty_type}` для завершения!"
        
        await ctx.send(embed=ce("✅ Охота Принята", desc, ctx.guild, 0x2ECC71))

    @commands.command(name="completebounty")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def complete_bounty(self, ctx: commands.Context, bounty_type: str = None):
        """🎯 Завершить охоту (если время вышло)!"""
        from economy import BOUNTY_TYPES
        from datetime import datetime
        
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        active_bounties = u.get("active_bounties", [])
        
        if bounty_type not in active_bounties:
            await ctx.send(embed=ce("❌", "> Ты не принял эту охоту!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        bounty = BOUNTY_TYPES[bounty_type]
        start_time = u.get(f"bounty_{bounty_type}_start", 0)
        now = datetime.utcnow().timestamp()
        elapsed = now - start_time
        
        if elapsed < bounty["timer"]:
            minutes_left = int((bounty["timer"] - elapsed) / 60)
            await ctx.send(embed=ce("⏳", f"> Охота активна ещё **{minutes_left}** минут!", ctx.guild, 0xFF8800), delete_after=10)
            return
        
        # Выдаём награду
        new_coins = coins + bounty["reward"]
        active_bounties.remove(bounty_type)
        save_user(uid, sid, {
            "coins": new_coins,
            "active_bounties": active_bounties,
            f"bounty_{bounty_type}_completed": True
        })
        
        desc = f"> {bounty['title']} завершена!\n"
        desc += f"> 💰 **+{bounty['reward']:,}** монет\n"
        desc += f"> Баланс: **{new_coins:,}**"
        
        await ctx.send(embed=ce("✅ Охота Завершена", desc, ctx.guild, 0x2ECC71))

    # ══════════════════════════════════════════════════════════
    # 🔨 СИСТЕМА КРАФТА
    # ══════════════════════════════════════════════════════════

    @commands.command(name="crafting")
    async def crafting(self, ctx: commands.Context):
        """🔨 Посмотреть рецепты крафта!"""
        from economy import CRAFTING_RECIPES, MARKET_GOODS
        
        desc = ""
        for recipe_id, recipe in CRAFTING_RECIPES.items():
            ingredients_str = ", ".join([
                f"{MARKET_GOODS.get(ing, {}).get('emoji', '?')} x{qty}"
                for ing, qty in recipe["ingredients"].items()
            ])
            desc += f"> **{recipe['name']}**\n"
            desc += f"  Ингредиенты: {ingredients_str}\n"
            desc += f"  Стоимость: **{recipe['coin_cost']:,}** монет\n"
            desc += f"  ⭐ XP: **+{recipe['xp_reward']}**\n\n"
        
        desc += "> Используй `!craft [рецепт]` для крафта!"
        await ctx.send(embed=ce("🔨 Рецепты Крафта", desc, ctx.guild, 0x8B4513))

    @commands.command(name="craft")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def craft_item(self, ctx: commands.Context, recipe_id: str = None):
        """🔨 Создать предмет! craft [recipe_id]"""
        from economy import CRAFTING_RECIPES, MARKET_GOODS
        
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        u = get_user(uid, sid)
        coins = u.get("coins", 0)
        market_inv = u.get("market_inventory", {})
        xp = u.get("xp", 0)
        
        if recipe_id not in CRAFTING_RECIPES:
            await ctx.send(embed=ce("❌", "> Рецепт не найден!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        recipe = CRAFTING_RECIPES[recipe_id]
        
        # Проверяем монеты
        if coins < recipe["coin_cost"]:
            await ctx.send(embed=ce("❌ Не хватает монет",
                                     f"> Нужно **{recipe['coin_cost']:,}**",
                                     ctx.guild, 0xFF0000), delete_after=10)
            return
        
        # Проверяем ингредиенты
        for ingredient, qty_needed in recipe["ingredients"].items():
            if market_inv.get(ingredient, 0) < qty_needed:
                await ctx.send(embed=ce("❌", f"> Не хватает **{ingredient}** (нужно {qty_needed})", ctx.guild, 0xFF0000), delete_after=10)
                return
        
        # Выполняем крафт
        new_coins = coins - recipe["coin_cost"]
        new_xp = xp + recipe["xp_reward"]
        
        for ingredient, qty_needed in recipe["ingredients"].items():
            market_inv[ingredient] -= qty_needed
        
        save_user(uid, sid, {
            "coins": new_coins,
            "xp": new_xp,
            "market_inventory": market_inv
        })
        
        desc = f"> ✨ {recipe['name']}\n"
        desc += f"> Создано успешно!\n"
        desc += f"> 💰 Стоимость: **-{recipe['coin_cost']:,}** монет\n"
        desc += f"> ⭐ XP: **+{recipe['xp_reward']}**\n"
        desc += f"> Баланс: **{new_coins:,}**"
        
        await ctx.send(embed=ce("✅ Крафт Завершён", desc, ctx.guild, 0x2ECC71))

    # ══════════════════════════════════════════════════════════
    # 👹 СИСТЕМА РЕЙДОВ (GUILD RAIDS/BOSSES)
    # ══════════════════════════════════════════════════════════

    @commands.command(name="raid")
    async def guild_raid(self, ctx: commands.Context):
        """👹 Информация о рейдах гильдии!"""
        from economy import RAID_BOSSES
        
        gid = str(ctx.guild.id)
        g = get_guild(gid)
        
        raid_progress = g.get("raid_progress", {})
        
        desc = ""
        for boss_id, boss in RAID_BOSSES.items():
            progress = raid_progress.get(boss_id, {"health": 0, "participants": 0})
            health_pct = max(0, int((progress.get("health", boss["health"]) / boss["health"]) * 100))
            
            health_bar = "🟥" * (health_pct // 10) + "⬛" * (10 - (health_pct // 10))
            
            desc += f"> {boss['name']} (Уровень {boss['level']})\n"
            desc += f"> HP: {health_bar} **{health_pct}%**\n"
            desc += f"> Участников: **{progress.get('participants', 0)}**\n"
            desc += f"> Награда: **{boss['rewards_per_player']:,}** монет/участнику\n\n"
        
        desc += "> Используй `!raidattack [boss_id]` для атаки!"
        await ctx.send(embed=ce("👹 Рейды Гильдии", desc, ctx.guild, 0x8B0000))

    @commands.command(name="raidattack")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def raid_attack(self, ctx: commands.Context, boss_id: str = None):
        """👹 Атаковать босса рейда! raidattack [boss_id]"""
        from economy import RAID_BOSSES
        import random
        
        uid, sid = str(ctx.author.id), str(ctx.guild.id)
        gid = str(ctx.guild.id)
        u = get_user(uid, sid)
        g = get_guild(gid)
        
        if boss_id not in RAID_BOSSES:
            await ctx.send(embed=ce("❌", "> Босс не найден!", ctx.guild, 0xFF0000), delete_after=10)
            return
        
        boss = RAID_BOSSES[boss_id]
        user_power = sum(ARMY_UNITS[un]["power"] * ct for un, ct in u.get("army", {}).items() if un in ARMY_UNITS)
        tech_bonus = sum(TECHNOLOGIES[t].get("power_bonus", 0) for t in u.get("technologies", []) if t in TECHNOLOGIES)
        total_power = user_power + tech_bonus
        
        # Урон случайный
        damage = random.randint(int(total_power * 0.5), int(total_power * 1.5))
        
        raid_progress = g.get("raid_progress", {})
        boss_progress = raid_progress.get(boss_id, {"health": boss["health"], "participants": 0})
        
        new_health = max(0, boss_progress.get("health", boss["health"]) - damage)
        boss_progress["health"] = new_health
        boss_progress["participants"] = boss_progress.get("participants", 0) + 1
        raid_progress[boss_id] = boss_progress
        
        save_guild(gid, {"raid_progress": raid_progress})
        
        defeated = new_health <= 0
        
        if defeated:
            # Раздаём награду всем участникам
            reward = boss["rewards_per_player"]
            participants = boss_progress["participants"]
            total_reward = reward * participants
            
            new_coins = u.get("coins", 0) + reward
            save_user(uid, sid, {"coins": new_coins})
            
            desc = f"> 🎉 **{boss['name']}** ПОБЕЖДЕН!\n"
            desc += f"> Участников: **{participants}**\n"
            desc += f"> Награда: **+{reward:,}** монет\n"
            desc += f"> 💰 Итого раздано: **{total_reward:,}** монет\n"
            desc += f"> Баланс: **{new_coins:,}**"
            
            # Сбрасываем босса
            boss_progress = {"health": boss["health"], "participants": 0}
            raid_progress[boss_id] = boss_progress
            save_guild(gid, {"raid_progress": raid_progress})
        else:
            desc = f"> ⚔️ Атака по **{boss['name']}**\n"
            desc += f"> Урон: **-{damage}** HP\n"
            desc += f"> Осталось: **{new_health:,}/{boss['health']:,}** HP\n"
            desc += f"> Участников: **{boss_progress['participants']}**"
        
        await ctx.send(embed=ce("👹 Атака на Босса", desc, ctx.guild, 0xFF6347 if defeated else 0xFFA500))

    # ── Ошибки ──────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: disnake.Member):
        """Автоматически проверяет профиль новых участников на главном сервере."""
        global _member_badge_cache
        
        if member.guild.id != HOME_SERVER_ID or member.bot:
            return
        
        try:
            # Проверяем профиль
            badge_level = await check_member_profile(member)
            now = datetime.utcnow().timestamp()
            _member_badge_cache[member.id] = (badge_level,
                MEMBER_BADGES.get(badge_level, {}).get("multiplier", 1.0),
                now)
            
            # Присваивают роль если есть бафф
            if badge_level and badge_level in MEMBER_BADGES:
                role_id = MEMBER_BADGES[badge_level].get("role_id")
                if role_id:
                    role = member.guild.get_role(role_id)
                    if role:
                        await member.add_roles(role, reason=f"Автоверификация баффа: {badge_level}")
                        
        except Exception as e:
            print(f"[on_member_join] Ошибка для {member.id}: {e}")

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error):
        if hasattr(ctx.command, "on_error") or ctx.cog is not self:
            return
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(embed=ce("⏰ Кулдаун",
                                     f"> Жди **{error.retry_after:.0f} сек**!", ctx.guild, 0xFF8800),
                           delete_after=5)
        elif isinstance(error, commands.CheckFailure):
            await ctx.send(embed=ce("❌", "> Доступ запрещен!", ctx.guild, 0xFF0000), delete_after=5)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(embed=ce("❌", "> Пользователь не найден!", ctx.guild, 0xFF0000), delete_after=5)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=ce("❌", f"> Не хватает аргумента!\n> `!ghelp`", ctx.guild, 0xFF0000),
                           delete_after=8)
        elif isinstance(error, commands.CommandNotFound):
            pass
        else:
            print(f"[ERR] {ctx.command}: {error}")


# ══════════════════════════════════════════════════════════════
# 🎨 ГЕНЕРАТОР КАРТИНОК ГИЛЬДИЙ
# ══════════════════════════════════════════════════════════════

async def create_guild_card(gd: dict, sid: str, guild: disnake.Guild = None) -> bytes:
    """Создать красивую карточку гильдии с PIL"""
    from PIL import Image, ImageDraw, ImageFont
    import io
    
    try:
        # Размеры
        W, H = 800, 600
        img = Image.new('RGB', (W, H), color=(15, 15, 30))  # Тёмный фон
        draw = ImageDraw.Draw(img)
        
        # Градиент-подобный эффект (рамка)
        guild_color = COLORS.get(gd.get("color"), DEFAULT_COLOR)
        hex_color = f"#{guild_color:06X}"
        
        # Рисуем красивую рамку
        for i in range(5):
            draw.rectangle([i, i, W-i-1, H-i-1], outline=hex_color, width=1)
        
        # Получаем данные
        cnt = member_count(gd["id"], sid)
        lim = member_limit(gd.get("upgrades", []))
        pwr = calc_guild_power(gd, sid)
        wins = gd.get("wins", 0)
        losses = gd.get("losses", 0)
        bank = gd.get("bank", 0)
        upgrades = len(gd.get("upgrades", []))
        level, xp, xp_needed = calc_guild_level(gd, sid)
        
        # Пытаемся получить шрифты
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
            header_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
            text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
            small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        except:
            title_font = ImageFont.load_default()
            header_font = ImageFont.load_default()
            text_font = ImageFont.load_default()
            small_font = ImageFont.load_default()
        
        # ЗАГОЛОВОК - Тег и Название
        tag_text = f"[{gd['tag']}]"
        name_text = gd['name'][:25]
        
        draw.text((W//2, 40), tag_text, fill=(100, 200, 255), font=header_font, anchor="mm")
        draw.text((W//2, 90), name_text, fill=(255, 200, 100), font=title_font, anchor="mm")
        
        # Разделитель
        draw.line([(50, 130), (W-50, 130)], fill=guild_color, width=2)
        
        # ЛЕВАЯ КОЛОНКА
        left_x, top_y = 60, 150
        draw.text((left_x, top_y), "📊 СТАТИСТИКА", fill=(100, 255, 200), font=header_font)
        
        # Добавляем уровень сверху
        draw.text((W-100, top_y), f"📈 Уровень {level}", fill=(255, 200, 100), font=header_font, anchor="ra")
        
        stats_y = top_y + 45
        stats = [
            (f"💪 Мощь: {pwr:,}", (100, 200, 255)),
            (f"💰 Казна: {bank:,}", (255, 215, 100)),
            (f"👥 Члены: {cnt}/{lim}", (150, 255, 150)),
        ]
        
        for stat, color in stats:
            draw.text((left_x, stats_y), stat, fill=color, font=text_font)
            stats_y += 35
        
        # ПРАВАЯ КОЛОНКА
        right_x = W // 2 + 30
        draw.text((right_x, top_y), "🏆 БОЕВАЯ СТАТИСТИКА", fill=(255, 100, 150), font=header_font)
        
        battle_y = top_y + 45
        battles = [
            (f"🥇 Побед: {wins}", (100, 255, 100)),
            (f"☠️ Поражений: {losses}", (255, 100, 100)),
            (f"🔧 Апгрейдов: {upgrades}", (200, 150, 255)),
        ]
        
        for battle, color in battles:
            draw.text((right_x, battle_y), battle, fill=color, font=text_font)
            battle_y += 35
        
        # Разделитель 2
        draw.line([(50, 300), (W-50, 300)], fill=guild_color, width=2)
        
        # НИЖНЯЯ СЕКЦИЯ - Описание и Лидер
        desc_y = 320
        draw.text((W//2, desc_y), "ИНФОРМАЦИЯ", fill=(200, 200, 200), font=header_font, anchor="mm")
        
        desc = gd.get("description", "🌸 Гильдия без описания")[:50] + "..."
        draw.text((W//2, desc_y + 50), f'"{desc}"', fill=(180, 180, 200), font=small_font, anchor="mm")
        
        # Лидер
        leader_id = gd.get("owner_id", "unknown")
        leader_text = f"👑 Лидер: ID {leader_id}"
        draw.text((W//2, desc_y + 100), leader_text, fill=(255, 215, 0), font=small_font, anchor="mm")
        
        # Нижний текст
        draw.text((W//2, H-35), "🌸 Sunshine Paradise", fill=(200, 100, 200), font=small_font, anchor="mm")
        
        # Сохраняем в BytesIO
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        return img_buffer.getvalue()
    
    except Exception as e:
        print(f"❌ Ошибка при создании карточки: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# 🔌 ПОДКЛЮЧЕНИЕ
# ══════════════════════════════════════════════════════════════

def setup(bot: commands.Bot):
    init_db()
    bot.add_cog(GuildCog(bot))
    # CasinoCog уже включен в GuildCog, не добавляем дважды
    print("✅ Sunshine Paradise — Guilds v4.1 загружен!")
    print(f"   🗄️ MongoDB | 🎨 Цветов: {len(COLORS)} | ⏱️ Rate-limit защита активна")
    print("✅ Казино команды загружены!")
