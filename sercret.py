import os
import asyncio
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from collections import Counter
import disnake
from disnake.ext import commands, tasks
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import FastAPI
import uvicorn
from dotenv import load_dotenv
import sys
# Add at the top of the file with other imports
import traceback
from pathlib import Path
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from keep_alive import keep_alive

QUINCY_SPAWN_CATEGORY_ID = 1433859101074653309  # Замените на ID вашей категории
# Исправьте загрузку токена:
# 1. Сначала пытаемся загрузить из той же папки, где main.py
load_dotenv()  # Загружает bot.env если он есть

TOKEN = os.getenv("BOT_TOKEN")
MONGODB_URI = os.getenv("MONGO_URI")
PORT = int(os.getenv("PORT", 8000))

# Проверка обязательных переменных
if not TOKEN:
    print("❌ ERROR: BOT_TOKEN не найден в переменных окружения!")
    print("Для Koyeb: установите в Environment Variables")
    print("Для локальной разработки: создайте файл bot.env")
    sys.exit(1)

if not MONGODB_URI:
    print("❌ ERROR: MONGO_URI не найден в переменных окружения!")
    sys.exit(1)

print(f"✅ Переменные окружения загружены успешно")

EMBED_COLOR = 0x5DADE2
EMBED_AUTHOR = "❄️ Bleach World ❄️"

# Глобальный кулдаун для команд (5 секунд)
COMMAND_COOLDOWN = 5
MIN_BET = 100  # Минимальная ставка

# Глобальное хранилище для лобби рулетки
roulette_lobbies: Dict[int, dict] = {}
# Глобальное хранилище для игр в блэкджек
blackjack_games: Dict[int, dict] = {}

# Константы для Блэкджека
CARD_SUITS_EMOJI = ["♠️", "♥️", "♦️", "♣️"]
CARD_VALUES = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "10": 10,
    "J": 10, "Q": 10, "K": 10, "A": 11
}
CARD_DECK_TEMPLATE = [f"{value}{suit}" for suit in CARD_SUITS_EMOJI for value in CARD_VALUES.keys()]

# ID РОЛИ ДЛЯ 2X БУСТЕРОВ
BOOSTER_ROLE_2X_ID = 1434100077378666579

# Награды бустерам (в банк)
BOOSTER_REWARD_1X = 2500
BOOSTER_REWARD_2X = 5000

LOG_CHANNEL_ID = 1434094855151292416


# (Вставить в секцию КОНФИГУРАЦИЯ, ~ строка 70)

IGNORED_USER_IDS = {
    13091622014704722544
}


# ==================== МАГАЗИН (ФЕРМЫ НА РОЛЯХ) ====================
# ВАЖНО: Замените None на реальные ID ролей на вашем сервере!

# ==================== МАГАЗИН (ФЕРМЫ НА РОЛЯХ) ====================# ==================== МАГАЗИН (ФЕРМЫ НА РОЛЯХ) ====================
# (ПОЛНЫЙ РЕБАЛАНС - ДЕБАФФ НАЧАЛЬНЫХ)
SHOP_ITEMS = {
    # === (ИЗМЕНЕНИЯ ЗДЕСЬ) ===
    # Начальный уровень (Окупаемость ~25-27 часов)
    "rukongai_district": {
        "price": 5000,        # (Было 8000)
        "income": 200,        # (Было 350)
        "name": "Район Руконгай",
        "description": "Бедный район душ. Дает 200 Кан/час",
        "emoji": "🏚️",
        "role_id": 1434991903824281631 
    },
    "academy_student": {
        "price": 12000,       # (Было 20000)
        "income": 450,        # (Было 750)
        "name": "Студент Академии",
        "description": "Обучение будущих шинигами. Дает 450 Кан/час",
        "emoji": "📚",
        "role_id": 1435015763848200323 
    },
    
    # === (ОСТАЛЬНЫЕ БЕЗ ИЗМЕНЕНИЙ) ===

    # Средний уровень (Окупаемость ~30-33 часа)
    "seireitei_house": {
        "price": 60000,       
        "income": 2000,
        "name": "Дом в Сейрейтей",
        "description": "Жилище в городе шинигами. Дает 2000 Кан/час",
        "emoji": "🏯",
        "role_id": 1435015823172305056 
    },
    "squad_barracks": {
        "price": 250000,      
        "income": 7500,
        "name": "Казармы Отряда",
        "description": "База одного из 13 отрядов. Дает 7500 Кан/час",
        "emoji": "⚔️",
        "role_id": 1435015824674132050
    },
    "zanpakuto_forge": {
        "price": 500000,      
        "income": 15000,
        "name": "Кузница Занпакто",
        "description": "Создание духовных мечей. Дает 15000 Кан/час",
        "emoji": "🔨",
        "role_id": 1435015825491886111
    },
    
    # Продвинутый уровень (Окупаемость ~40-47 часов)
    "hollow_hunting": {
        "price": 700000,      
        "income": 17500,
        "name": "Охота на Пустых",
        "description": "Зачистка территорий от Пустых. Дает 17500 Кан/час",
        "emoji": "👹",
        "role_id": 1435015826183950458 
    },
    "karakura_town": {
        "price": 850000,      
        "income": 20000,
        "name": "Город Каракура",
        "description": "Контроль духовно насыщенного города. Дает 20000 Кан/час",
        "emoji": "🌆",
        "role_id": 1435015826905235617
    },
    "hueco_mundo_patrol": {
        "price": 1400000,     
        "income": 30000,
        "name": "Патруль Уэко Мундо",
        "description": "Экспедиции в мир пустых. Дает 30000 Кан/час",
        "emoji": "🌙",
        "role_id": 1435015828537086084 
    },
    
    # Элитный уровень (Окупаемость ~46-50 часов)
    "vice_captain_position": {
        "price": 3000000,     
        "income": 65000,
        "name": "Должность Вице-Капитана",
        "description": "Заместитель капитана отряда. Дает 65000 Кан/час",
        "emoji": "🎖️",
        "role_id": 1435015828537086084 # (Та же роль, что и у патруля - доход суммируется)
    },
    "captain_position": {
        "price": 5000000,     
        "income": 100000,
        "name": "Должность Капитана",
        "description": "Капитан одного из 13 отрядов. Дает 100000 Кан/час",
        "emoji": "👑",
        "role_id": 1435016099488858134 
    },
    
    # Легендарный уровень (Окупаемость ~60-64 часа)
    "royal_guard": {
        "price": 9000000,     
        "income": 150000,     
        "name": "Королевская Гвардия",
        "description": "Защита Короля Душ. Дает 150,000 Кан/час",
        "emoji": "🛡️",
        "role_id": 1435016100290101398 
    },
    "soul_king_palace": {
        "price": 16000000,    
        "income": 250000,     
        "name": "Дворец Короля Душ",
        "description": "Владение священным дворцом. Дает 250,000 Кан/час",
        "emoji": "🏰",
        "role_id": 1435016100977836195 
    },
    
    # Секретные (Окупаемость ~75-81 час)
    "hogyoku": {
        "price": 30000000,    
        "income": 400000,     
        "name": "Хогёку",
        "description": "Легендарный артефакт Айзена. Дает 400,000 Кан/час",
        "emoji": "💎",
        "role_id": 1435016101502128240 
    },
    "soul_society_control": {
        "price": 65000000,    
        "income": 800000,     
        "name": "Контроль Общества Душ",
        "description": "Абсолютная власть над миром. Дает 800,000 Кан/час",
        "emoji": "✨",
        "role_id": 1435016102051840020
    }
}

# (ВСТАВИТЬ ПОСЛЕ SHOP_ITEMS, ~ строка 149)

# ==================== ПРЕДМЕТЫ В ИНВЕНТАРЕ (РАСХОДУЕМЫЕ) ====================
# ID юзера, которого нужно пинговать при использовании купона
CUSTOM_PING_USER_ID = 1421780820833730590# (ВСТАВИТЬ ПОСЛЕ SHOP_ITEMS, ~ строка 149)


# ==================== АПГРЕЙДЫ КЛАНОВ ====================
CLAN_UPGRADES = {
    "member_slot_1": {
        "price": 10000,
        "name": "Слот участника I",
        "description": "+5 к лимиту участников",
        "emoji": "👥"
    },
    "member_slot_2": {
        "price": 25000,
        "name": "Слот участника II",
        "description": "+10 к лимиту участников",
        "emoji": "👥"
    },
    "member_slot_3": {
        "price": 50000,
        "name": "Слот участника III",
        "description": "+15 к лимиту участников",
        "emoji": "👥"
    },
    "bank_boost_1": {
        "price": 30000,
        "name": "Казна клана I",
        "description": "+5% к взносам в казну",
        "emoji": "💰"
    },
    "bank_boost_2": {
        "price": 75000,
        "name": "Казна клана II",
        "description": "+10% к взносам в казну",
        "emoji": "💰"
    },
    "prestige_1": {
        "price": 100000,
        "name": "Престиж I",
        "description": "Особая метка клана в списке",
        "emoji": "⭐"
    }
}

BASE_MEMBER_LIMIT = 10  # Базовый лимит участников
CLAN_CONTRIBUTION_RATE = 0.10  # 10% от наград идет в казну# ==================== АПГРЕЙДЫ КЛАНОВ ====================

# (ВСТАВИТЬ ПОСЛЕ CUSTOM_PING_USER_ID, ~строка 155)

# ==================== ПРЕДМЕТЫ В ИНВЕНТАРЕ (РАСХОДУЕМЫЕ) ====================
CONSUMABLE_ITEMS = {
    "custom_coupon": {
        "name": "Купон на Кастомку",
        "emoji": "🎟️",
        "description": "Дает право на 1 кастомную роль/итем. Используйте: !use custom_coupon"
    },
    
    "custom_farm_coupon": {
        "name": "Купон на Кастомную Ферму",
        "emoji": "📜",
        "description": "Дает право на 1 кастомную ферму. Используйте: !use custom_farm_coupon"
    },
    
    # === (НОВЫЙ ИТЕМ ДЛЯ ИВЕНТА) ===
    "feastables": {
        "name": "Feastables",
        "emoji": "🍫",
        "description": "Особый ивентовый предмет."
    }
}
# (НОВАЯ КОЛЛЕКЦИЯ БД)
# ==================== MONGODB SETUP ====================
client = AsyncIOMotorClient(MONGODB_URI)
db = client["bleach_world"]
users_collection = db["users"]
promocodes_collection = db["promocodes"]
clans_collection = db["clans"] 
custom_farms_collection = db["custom_farms"] # <-- НОВАЯ КОЛЛЕКЦИЯ# (ВСТАВИТЬ ПОСЛЕ CUSTOM_PING_USER_ID, ~строка 155)


# (ЗАМЕНИТЬ СТАРУЮ ФУНКЦИЮ get_user, ~строка 156)
async def get_user(user_id: int, guild_id: int) -> dict:
    """Получает данные юзера и создает их, если нет (с HP и Квинси)"""
    user = await users_collection.find_one({"userId": user_id, "guildId": guild_id})
    
    if not user:
        user = {
            "userId": user_id,
            "guildId": guild_id,
            "balance": 0,
            "bank": 0,
            "inventory": [],
            "daily_cooldown": None,
            "work_cooldowns": {}, 
            "command_cooldowns": {},
            "quest_progress": {}, 
            "claimed_quests": [],
            "hp": 100,
            "quincy_wins": 0,
            "quincy_cooldown": None,
            "trade_cooldown": None  # <-- НОВОЕ ПОЛЕ
        }
        await users_collection.insert_one(user)
    
    # (Это добавит недостающие поля старым игрокам при первом вызове)
    if "hp" not in user:
        user["hp"] = 100
    if "quincy_wins" not in user:
        user["quincy_wins"] = 0
        
    return user# (ЗАМЕНИТЬ СТАРУЮ ФУНКЦИЮ get_user, ~строка 156)


# (ЗАМЕНИТЬ СТАРУЮ ФУНКЦИЮ update_user)

async def update_user(user_id: int, guild_id: int, update_data: dict):
    """
    Обновляет юзера, поддерживая $set, $inc, $push, и $pull.
    """
    
    # (Эта новая логика нужна для $push/$pull в трейдах и !giveitem)
    update_payload = {}
    
    if "$set" in update_data and update_data["$set"]:
       update_payload["$set"] = update_data["$set"]
       
    if "$inc" in update_data and update_data["$inc"]:
       update_payload["$inc"] = update_data["$inc"]
       
    if "$push" in update_data and update_data["$push"]:
       update_payload["$push"] = update_data["$push"]
       
    if "$pull" in update_data and update_data["$pull"]:
       update_payload["$pull"] = update_data["$pull"]
    
    # Если пришел старый формат (без $), оборачиваем в $set
    if not update_payload and update_data:
        update_payload["$set"] = update_data

    if not update_payload: # Если payload все еще пуст
        print(f"[UPDATE_USER_WARN] Вызван update_user, но нет данных для {user_id}")
        return

    await users_collection.update_one(
        {"userId": user_id, "guildId": guild_id},
        update_payload,
        upsert=True 
    )# (ЗАМЕНИТЬ СТАРУЮ ФУНКЦИЮ update_user)

    
# (ВСТАВИТЬ ПОСЛЕ update_user, ~строка 205)
async def get_event_leaderboard() -> list[dict]:
    """(НОВАЯ) Получает топ-10 игроков по 'quincy_wins'."""
    cursor = users_collection.find({"quincy_wins": {"$gt": 0}}).sort("quincy_wins", -1).limit(10)
    return await cursor.to_list(length=10)

    
async def get_clan(clan_id) -> dict:
    """Получает клан по ObjectId"""
    return await clans_collection.find_one({"_id": clan_id})

async def get_clan_by_tag(guild_id: int, tag: str) -> dict:
    """Получает клан по тэгу"""
    return await clans_collection.find_one({"guildId": guild_id, "tag": tag.upper()})

async def update_clan(clan_id, update_data: dict):
    """Обновляет данные клана"""
    await clans_collection.update_one({"_id": clan_id}, {"$set": update_data})

async def get_clan_member_count(clan_id) -> int:
    """Подсчитывает количество участников клана"""
    return await users_collection.count_documents({"clan_id": clan_id})

async def get_clan_members(clan_id) -> list:
    """Получает всех участников клана"""
    return await users_collection.find({"clan_id": clan_id}).to_list(None)

def calculate_member_limit(upgrades: list) -> int:
    """Рассчитывает лимит участников с учетом апгрейдов"""
    limit = BASE_MEMBER_LIMIT
    for upgrade_id in upgrades:
        if upgrade_id == "member_slot_1":
            limit += 5
        elif upgrade_id == "member_slot_2":
            limit += 10
        elif upgrade_id == "member_slot_3":
            limit += 15
    return limit

def calculate_contribution_bonus(upgrades: list) -> float:
    """Рассчитывает бонус к взносам в казну"""
    bonus = CLAN_CONTRIBUTION_RATE
    for upgrade_id in upgrades:
        if upgrade_id == "bank_boost_1":
            bonus += 0.05
        elif upgrade_id == "bank_boost_2":
            bonus += 0.10
    return bonus

async def set_clan_nickname(member: disnake.Member, clan_tag: str):
    """Устанавливает никнейм с тэгом клана"""
    try:
        new_nick = f"[{clan_tag}] {member.display_name}"
        # Убираем старый тэг, если есть
        if member.display_name.startswith("[") and "]" in member.display_name:
            old_name = member.display_name.split("]", 1)[1].strip()
            new_nick = f"[{clan_tag}] {old_name}"
        
        # Обрезаем до 32 символов
        if len(new_nick) > 32:
            base_name = member.display_name
            if base_name.startswith("["):
                base_name = base_name.split("]", 1)[1].strip()
            new_nick = f"[{clan_tag}] {base_name}"[:32]
        
        await member.edit(nick=new_nick)
    except disnake.Forbidden:
        pass  # Нет прав на изменение ника
    except Exception as e:
        print(f"[NICKNAME ERROR] {e}")

async def remove_clan_nickname(member: disnake.Member):
    """Убирает тэг клана из никнейма"""
    try:
        if member.display_name.startswith("[") and "]" in member.display_name:
            new_nick = member.display_name.split("]", 1)[1].strip()
            await member.edit(nick=new_nick if new_nick else None)
    except disnake.Forbidden:
        pass
    except Exception as e:
        print(f"[NICKNAME ERROR] {e}")

async def check_command_cooldown(ctx: commands.Context, command_name: str) -> bool:
    """Проверяет кулдаун команды (5 секунд)"""
    user = await get_user(ctx.author.id, ctx.guild.id)
    now = datetime.utcnow()
    
    cooldowns = user.get("command_cooldowns", {})
    if command_name in cooldowns:
        cooldown_time = cooldowns[command_name]
        if now < cooldown_time:
            remaining = cooldown_time - now
            seconds = int(remaining.total_seconds())
            desc = f"> **❄️ Подожди {seconds} секунд перед использованием этой команды!**"
            embed = create_embed("Кулдаун", desc, ctx)
            await ctx.send(embed=embed, delete_after=5)
            return False
    
    # Устанавливаем новый кулдаун
    cooldowns[command_name] = now + timedelta(seconds=COMMAND_COOLDOWN)
    await update_user(ctx.author.id, ctx.guild.id, {"command_cooldowns": cooldowns})
    return True

# ==================== DISCORD BOT ====================
intents = disnake.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

def create_embed(title: str, description: str, ctx: commands.Context) -> disnake.Embed:
    embed = disnake.Embed(title=title, description=description, color=EMBED_COLOR)
    icon_url = ctx.guild.icon.url if ctx.guild and ctx.guild.icon else None
    embed.set_author(name=EMBED_AUTHOR, icon_url=icon_url)
    return embed

        
# (Вставить сразу после bot = commands.Bot(...), ~ строка 202)

@bot.check
async def global_user_check(ctx: commands.Context) -> bool:
    """
    Эта глобальная проверка запускается перед КАЖДОЙ командой.
    Если она возвращает False, бот молча игнорирует команду.
    """
    if ctx.author.id in IGNORED_USER_IDS:
        # Мы ничего не отвечаем, просто возвращаем False
        # Бот будет "мертвым" для этого пользователя
        print(f"[IGNORE] Команда от {ctx.author.name} ({ctx.author.id}) проигнорирована.")
        return False
        
    # Если ID не в списке, разрешаем команду
    return True# (Вставить сразу после bot = commands.Bot(...), ~ строка 202)


# ==================== ПАССИВНЫЙ ДОХОД ====================

# ==================== ПАССИВНЫЙ ДОХОД ====================

async def send_log(guild: disnake.Guild, title: str, description: str):
    """Отправляет лог в специальный канал"""
    try:
        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if not log_channel:
            print(f"[LOG WARNING] Канал логов {LOG_CHANNEL_ID} не найден на сервере {guild.name}")
            return
        
        embed = disnake.Embed(
            title=title,
            description=description,
            color=EMBED_COLOR,
            timestamp=datetime.utcnow()
        )
        embed.set_author(name=EMBED_AUTHOR)
        await log_channel.send(embed=embed)
    except Exception as e:
        print(f"[LOG ERROR] Не удалось отправить лог: {e}")

# @tasks.loop(hours=1)
async def passive_income():
    """Начисляет пассивный доход каждый час НА БАНК по ролям"""
    try:
        print(f"[PASSIVE INCOME] Начало начисления пассивного дохода...")
        
        for guild in bot.guilds:
            count = 0
            total_income_given = 0
            errors = []
            income_list = []
            
            # Получаем всех пользователей этого сервера из БД
            all_users = await users_collection.find({"guildId": guild.id}).to_list(None)
            
            for user_data in all_users:
                try:
                    member = await guild.fetch_member(user_data["userId"])
                except:
                    continue  # Пользователь покинул сервер
                
                total_income = 0
                user_farms = []
                
                # Проверяем роли участника
                for item_id, item in SHOP_ITEMS.items():
                    role_id = item.get("role_id")
                    if role_id is None:
                        continue
                    
                    # Проверяем, есть ли у участника эта роль
                    if any(role.id == role_id for role in member.roles):
                        total_income += item["income"]
                        user_farms.append(item['emoji'])
                
                # Начисляем доход на БАНК
                if total_income > 0:
                    current_bank = user_data.get("bank", 0)
                    new_bank = current_bank + total_income
                    
                    # Начисляем
                    await update_user(user_data["userId"], guild.id, {"bank": new_bank})
                    
                    # ПЕРЕПРОВЕРКА: Читаем из БД снова
                    verification_user = await get_user(user_data["userId"], guild.id)
                    actual_new_bank = verification_user.get("bank", 0)
                    
                    if actual_new_bank == new_bank:
                        # Успешно начислено
                        count += 1
                        total_income_given += total_income
                        farms_emoji = "".join(user_farms)
                        income_list.append(f"> {farms_emoji} **{member.display_name}**: +{total_income:,} Кан (Баланс: {actual_new_bank:,})")
                        print(f"[PASSIVE INCOME] ✅ {member.display_name} получил {total_income:,} Кан (Проверено)")
                    else:
                        # Ошибка начисления
                        errors.append(f"> ❌ **{member.display_name}**: Ошибка начисления (ожидалось {new_bank:,}, получено {actual_new_bank:,})")
                        print(f"[PASSIVE INCOME] ❌ ОШИБКА у {member.display_name}: ожидалось {new_bank:,}, получено {actual_new_bank:,}")
            
            # Отправляем лог в канал
            if count > 0 or errors:
                log_desc = f"> **❄️ Пассивный доход начислен!**\n> _ _\n"
                log_desc += f"> **🧊 Обработано:** {count} пользователей\n"
                log_desc += f"> **💰 Всего выдано:** {total_income_given:,} Кан\n"
                log_desc += f"> _ _\n"
                
                if income_list:
                    # Ограничиваем список (Discord имеет лимит 4096 символов)
                    if len(income_list) > 20:
                        log_desc += "\n".join(income_list[:20])
                        log_desc += f"\n> ... и ещё {len(income_list) - 20} пользователей"
                    else:
                        log_desc += "\n".join(income_list)
                
                if errors:
                    log_desc += f"\n> _ _\n> **⚠️ Ошибки:**\n" + "\n".join(errors)
                
                await send_log(guild, "Пассивный Доход | Фермы", log_desc)
            
            print(f"[PASSIVE INCOME] Сервер {guild.name}: {count} пользователей, {total_income_given:,} Кан")
            
    except Exception as e:
        print(f"[PASSIVE INCOME ERROR] {e}")
        import traceback
        traceback.print_exc()

# @passive_income.before_loop
async def before_passive_income():
    await bot.wait_until_ready()# ==================== ПАССИВНЫЙ ДОХОД ====================



# ==================== ПАССИВНЫЙ ДОХОД БУСТЕРАМ ====================

# ==================== ПАССИВНЫЙ ДОХОД БУСТЕРАМ ====================

@tasks.loop(hours=1)
async def booster_income():
    """Начисляет доход бустерам сервера каждый час СРАЗУ В БАНК."""
    try:
        print(f"[BOOSTER INCOME] Начало проверки бустеров...")
        
        for guild in bot.guilds:
            count_1x = 0
            count_2x = 0
            total_given_1x = 0
            total_given_2x = 0
            booster_list = []
            errors = []
            
            role_2x = guild.get_role(BOOSTER_ROLE_2X_ID)
            
            if not role_2x:
                print(f"[BOOSTER INCOME WARNING] Роль с ID {BOOSTER_ROLE_2X_ID} не найдена на сервере {guild.name}")

            for booster in guild.premium_subscribers:
                if booster.bot:
                    continue
                
                # Проверяем, есть ли у бустера роль 2x
                has_2x_role = role_2x and role_2x in booster.roles
                
                if has_2x_role:
                    reward = BOOSTER_REWARD_2X
                    tier = "2X 💎"
                else:
                    reward = BOOSTER_REWARD_1X
                    tier = "1X ⭐"
                    
                user_data = await get_user(booster.id, guild.id)
                current_bank = user_data.get("bank", 0)
                new_bank = current_bank + reward
                
                # Начисляем
                await update_user(booster.id, guild.id, {"bank": new_bank})
                
                # ПЕРЕПРОВЕРКА: Читаем из БД снова
                verification_user = await get_user(booster.id, guild.id)
                actual_new_bank = verification_user.get("bank", 0)
                
                if actual_new_bank == new_bank:
                    # Успешно начислено
                    if has_2x_role:
                        count_2x += 1
                        total_given_2x += reward
                    else:
                        count_1x += 1
                        total_given_1x += reward
                    
                    booster_list.append(f"> {tier} **{booster.display_name}**: +{reward:,} Кан (Баланс: {actual_new_bank:,})")
                    print(f"[BOOSTER INCOME] ✅ {booster.display_name} получил {reward:,} Кан ({tier}) (Проверено)")
                else:
                    # Ошибка начисления
                    errors.append(f"> ❌ **{booster.display_name}**: Ошибка начисления (ожидалось {new_bank:,}, получено {actual_new_bank:,})")
                    print(f"[BOOSTER INCOME] ❌ ОШИБКА у {booster.display_name}: ожидалось {new_bank:,}, получено {actual_new_bank:,}")
            
            # Отправляем лог в канал
            if booster_list or errors:
                log_desc = f"> **❄️ Награда бустерам начислена!**\n> _ _\n"
                log_desc += f"> **⭐ Бустеры 1X:** {count_1x} ({total_given_1x:,} Кан)\n"
                log_desc += f"> **💎 Бустеры 2X:** {count_2x} ({total_given_2x:,} Кан)\n"
                log_desc += f"> **💰 Всего выдано:** {(total_given_1x + total_given_2x):,} Кан\n"
                log_desc += f"> _ _\n"
                
                if booster_list:
                    log_desc += "\n".join(booster_list)
                
                if errors:
                    log_desc += f"\n> _ _\n> **⚠️ Ошибки:**\n" + "\n".join(errors)
                
                await send_log(guild, "Пассивный Доход | Бустеры", log_desc)
            
            print(f"[BOOSTER INCOME] Сервер {guild.name}: {count_1x} бустеров (1x), {count_2x} бустеров (2x)")
                
    except Exception as e:
        print(f"[BOOSTER INCOME ERROR] {e}")
        import traceback
        traceback.print_exc()

@booster_income.before_loop
async def before_booster_income():
    await bot.wait_until_ready()

# ==================== ЭКОНОМИЧЕСКИЕ КОМАНДЫ ====================

# Добавьте в команду !daily




# --- (НОВЫЙ КЛАСС) КНОПКИ ДЛЯ ПРИГЛАШЕНИЯ ---
class ClanInviteView(disnake.ui.View):
    def __init__(self, inviter: disnake.Member, invited: disnake.Member, clan: dict):
        super().__init__(timeout=120.0) # 2 минуты на ответ
        self.inviter = inviter
        self.invited = invited
        self.clan = clan
        self.message: disnake.Message = None

    # Проверка, кто нажимает
    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        # Только тот, кого пригласили, может нажать
        if interaction.user.id != self.invited.id:
            await interaction.response.send_message("❌ Это приглашение не для вас!", ephemeral=True)
            return False
        return True

    @disnake.ui.button(label="Принять", style=disnake.ButtonStyle.success)
    async def accept_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        # 1. Обновляем юзера в БД
        await update_user(self.invited.id, self.invited.guild.id, {
            "clan_id": self.clan["_id"],
            "clan_rank": "member"
        })
        
        # 2. (ВАЖНО) Меняем ему ник
        try:
            await set_clan_nickname(self.invited, self.clan["tag"])
        except Exception as e:
            print(f"[NICKNAME ERROR] Не удалось сменить ник (возможно, нет прав): {e}")

        # 3. Редактируем сообщение
        embed = disnake.Embed(
            title="Приглашение принято",
            description=f"> **{self.invited.display_name}** вступил в клан **{self.clan['name']}**!",
            color=0x00FF00 # Зеленый
        )
        embed.set_author(name=EMBED_AUTHOR)
        
        # Выключаем кнопки
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @disnake.ui.button(label="Отклонить", style=disnake.ButtonStyle.danger)
    async def decline_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        # 1. Редактируем сообщение
        embed = disnake.Embed(
            title="Приглашение отклонено",
            description=f"> **{self.invited.display_name}** отклонил приглашение в клан **{self.clan['name']}**.",
            color=0xFF0000 # Красный
        )
        embed.set_author(name=EMBED_AUTHOR)
        
        # Выключаем кнопки
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()
        
    async def on_timeout(self):
        # Если 2 минуты прошли, а ответа нет
        embed = disnake.Embed(
            title="Приглашение просрочено",
            description=f"> Приглашение для **{self.invited.display_name}** истекло.",
            color=0xAAAAAA # Серый
        )
        embed.set_author(name=EMBED_AUTHOR)
        
        # Выключаем кнопки
        for child in self.children:
            child.disabled = True
        try:
            if self.message:
                await self.message.edit(embed=embed, view=self)
        except disnake.NotFound:
            pass 

@bot.command(name="pay")
async def pay(ctx: commands.Context, member: disnake.Member, amount: int):
    if not await check_command_cooldown(ctx, "pay"):
        return
    
    if amount <= 0:
        await ctx.send("❌ Сумма должна быть положительной!")
        return
    
    if member.id == ctx.author.id:
        await ctx.send("❌ Нельзя переводить деньги самому себе!")
        return
    
    sender = await get_user(ctx.author.id, ctx.guild.id)
    
    if sender["balance"] < amount:
        desc = f"> **❄️ Недостаточно средств!**\n> Ваш баланс: {sender['balance']:,} Кан\n> Требуется: {amount:,} Кан"
        embed = create_embed("Перевод", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    receiver = await get_user(member.id, ctx.guild.id)
    
    await update_user(ctx.author.id, ctx.guild.id, {"balance": sender["balance"] - amount})
    await update_user(member.id, ctx.guild.id, {"balance": receiver["balance"] + amount})
    
    desc = f"> **❄️ Перевод выполнен!**\n> От: {ctx.author.display_name}\n> Кому: {member.display_name}\n> Сумма: {amount:,} Кан 💴"
    embed = create_embed("Перевод", desc, ctx)
    await ctx.send(embed=embed)


@bot.command(name="balance", aliases=["bal"])
async def balance(ctx: commands.Context, member: Optional[disnake.Member] = None):
    target = member or ctx.author
    user = await get_user(target.id, ctx.guild.id)
    
    bank_balance = user.get("bank", 0)
    cash_balance = user["balance"]
    total = cash_balance + bank_balance
    
    desc = (
        f"> **❄️ Баланс {target.display_name}:**\n"
        f"> _ _\n"
        f"> 💴 **Наличные:** {cash_balance:,} Кан\n"
        f"> 🏦 **В банке:** {bank_balance:,} Кан\n"
        f"> _ _\n"
        f"> 💎 **Всего:** {total:,} Кан"
    )
    embed = create_embed("Баланс", desc, ctx)
    await ctx.send(embed=embed)
@bot.command(name="deposit", aliases=["dep"])
async def deposit(ctx: commands.Context, amount: str):
    if not await check_command_cooldown(ctx, "deposit"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    if amount.lower() == "all":
        amount = user["balance"]
    else:
        try:
            amount = int(amount)
        except:
            await ctx.send("❌ Укажите корректную сумму или 'all'!")
            return
    
    if amount <= 0:
        await ctx.send("❌ Сумма должна быть положительной!")
        return
    
    if user["balance"] < amount:
        desc = f"> **❄️ Недостаточно наличных!**\n> У вас: {user['balance']:,} Кан"
        embed = create_embed("Депозит", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    bank_balance = user.get("bank", 0)
    new_cash = user["balance"] - amount
    new_bank = bank_balance + amount
    
    await update_user(ctx.author.id, ctx.guild.id, {
        "balance": new_cash,
        "bank": new_bank
    })
   
    # --- (ВОТ ИСПРАВЛЕНИЕ) ---
    # (Эта строка теперь имеет правильный отступ)
    await update_quest_progress(ctx.author.id, ctx.guild.id, "daily_rich", amount)

    
    desc = (
        f"> **🧊 Депозит выполнен!**\n"
        f"> Внесено: {amount:,} Кан\n"
        f"> _ _\n"
        f"> 💴 **Наличные:** {new_cash:,} Кан\n"
        f"> 🏦 **В банке:** {new_bank:,} Кан"
    )
    embed = create_embed("Депозит", desc, ctx)
    await ctx.send(embed=embed)

@bot.command(name="withdraw", aliases=["with"])
async def withdraw(ctx: commands.Context, amount: str):
    if not await check_command_cooldown(ctx, "withdraw"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    bank_balance = user.get("bank", 0)
    
    if amount.lower() == "all":
        amount = bank_balance
    else:
        try:
            amount = int(amount)
        except:
            await ctx.send("❌ Укажите корректную сумму или 'all'!")
            return
    
    if amount <= 0:
        await ctx.send("❌ Сумма должна быть положительной!")
        return
    
    if bank_balance < amount:
        desc = f"> **❄️ Недостаточно средств в банке!**\n> В банке: {bank_balance:,} Кан"
        embed = create_embed("Снятие", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    new_bank = bank_balance - amount
    new_cash = user["balance"] + amount
    
    await update_user(ctx.author.id, ctx.guild.id, {
        "balance": new_cash,
        "bank": new_bank
    })
    
    desc = (
        f"> **🧊 Снятие выполнено!**\n"
        f"> Снято: {amount:,} Кан\n"
        f"> _ _\n"
        f"> 💴 **Наличные:** {new_cash:,} Кан\n"
        f"> 🏦 **В банке:** {new_bank:,} Кан"
    )
    embed = create_embed("Снятие", desc, ctx)
    await ctx.send(embed=embed)

@bot.command(name="rob")
async def rob(ctx: commands.Context, member: disnake.Member):
    if not await check_command_cooldown(ctx, "rob"):
        return
    
    if member.id == ctx.author.id:
        await ctx.send("❌ Нельзя ограбить самого себя!")
        return
    
    if member.bot:
        await ctx.send("❌ Нельзя ограбить бота!")
        return
    
    robber = await get_user(ctx.author.id, ctx.guild.id)
    victim = await get_user(member.id, ctx.guild.id)
    
    now = datetime.utcnow()
    rob_cooldown = robber.get("rob_cooldown")
    if rob_cooldown and now < rob_cooldown:
        remaining = rob_cooldown - now
        minutes = int(remaining.total_seconds() // 60)
        seconds = int(remaining.total_seconds() % 60)
        desc = f"> **❄️ Кулдаун активен!**\n> Осталось: {minutes}м {seconds}с"
        embed = create_embed("Ограбление", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    victim_cash = victim["balance"]
    
    if victim_cash == 0:
        penalty = random.randint(5, 20)
        
        robber_total = robber["balance"] + robber.get("bank", 0)
        if robber_total < penalty:
            penalty = robber_total
        
        new_robber_cash = robber["balance"]
        new_robber_bank = robber.get("bank", 0)
        
        if new_robber_cash >= penalty:
            new_robber_cash -= penalty
        else:
            remaining = penalty - new_robber_cash
            new_robber_cash = 0
            new_robber_bank = max(0, new_robber_bank - remaining)
        
        await update_user(ctx.author.id, ctx.guild.id, {
            "balance": new_robber_cash,
            "bank": new_robber_bank,
            "rob_cooldown": now + timedelta(minutes=30)
        })
        
        desc = (
            f"> **❌ Ограбление провалилось!**\n"
            f"> У {member.display_name} все деньги в банке!\n"
            f"> _ _\n"
            f"> **🧊 Штраф:**\n"
            f"> Вы потеряли {penalty:,} Кан"
        )
        embed = create_embed("Ограбление", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    success_chance = 30
    if random.randint(1, 100) <= success_chance:
        stolen = random.randint(int(victim_cash * 0.1), int(victim_cash * 0.3))
        if stolen == 0:
            stolen = min(100, victim_cash)
        
        new_victim_cash = victim["balance"] - stolen
        new_robber_cash = robber["balance"] + stolen
        
        await update_user(member.id, ctx.guild.id, {"balance": new_victim_cash})
        await update_user(ctx.author.id, ctx.guild.id, {
            "balance": new_robber_cash,
            "rob_cooldown": now + timedelta(minutes=30)
        })
        
        desc = (
            f"> **✅ Ограбление успешно!**\n"
            f"> Вы украли {stolen:,} Кан у {member.display_name}\n"
            f"> _ _\n"
            f"> **💴 Ваш новый баланс:**\n"
            f"> {new_robber_cash:,} Кан"
        )
        embed = create_embed("Ограбление", desc, ctx)
        await ctx.send(embed=embed)
    else:
        penalty = random.randint(50, 200)
        new_robber_cash = max(0, robber["balance"] - penalty)
        
        await update_user(ctx.author.id, ctx.guild.id, {
            "balance": new_robber_cash,
            "rob_cooldown": now + timedelta(minutes=30)
        })
        
        desc = (
            f"> **❌ Вас поймали!**\n"
            f"> Ограбление провалилось\n"
            f"> _ _\n"
            f"> **🧊 Штраф:**\n"
            f"> Вы потеряли {penalty:,} Кан"
        )
        embed = create_embed("Ограбление", desc, ctx)
        await ctx.send(embed=embed)

# (ВСТАВИТЬ ПОСЛЕ !takefarm, ~строка 1055)

@bot.command(name="giveitem")
@commands.has_permissions(administrator=True)
async def giveitem(ctx: commands.Context, member: disnake.Member, item_id: str, amount: int = 1):
    """Выдает предмет (из CONSUMABLE_ITEMS) в инвентарь игрока."""
    
    item_id = item_id.lower()
    if item_id not in CONSUMABLE_ITEMS:
        embed = create_embed("Ошибка", f"> **❌ Ошибка:**\n> Предмет `{item_id}` не найден в `CONSUMABLE_ITEMS`!", ctx)
        await ctx.send(embed=embed)
        return
        
    if amount <= 0:
        embed = create_embed("Ошибка", "> **❌ Ошибка:**\n> Количество должно быть больше нуля!", ctx)
        await ctx.send(embed=embed)
        return

    item = CONSUMABLE_ITEMS[item_id]
    
    # Создаем список из N копий предмета
    items_to_add = [item_id] * amount
    
    # Добавляем в инвентарь
    await update_user(member.id, ctx.guild.id, {
        "$push": {"inventory": {"$each": items_to_add}}
    })
    
    desc = (
        f"> **🧊 Успех:**\n"
        f"> Вы выдали **{amount}x** предмета пользователю {member.display_name}\n"
        f"> _ _\n"
        f"> {item['emoji']} **{item['name']}**"
    )
    embed = create_embed("Выдача Предмета", desc, ctx)
    await ctx.send(embed=embed)


# (ЗАМЕНИТЬ СТАРУЮ КОМАНДУ !use, ~строка 1087)

@bot.command(name="use")
async def use_item(ctx: commands.Context, item_id: str):
    """Использовать предмет из инвентаря"""
    if not await check_command_cooldown(ctx, "use"):
        return
        
    item_id = item_id.lower()
    user = await get_user(ctx.author.id, ctx.guild.id)
    inventory = user.get("inventory", [])
    
    if item_id not in inventory:
        desc = f"> **❌ Ошибка:**\n> У вас нет предмета `{item_id}` в инвентаре!\n> Проверьте `!inv`."
        embed = create_embed("Использование", desc, ctx)
        await ctx.send(embed=embed)
        return
        
    if item_id not in CONSUMABLE_ITEMS:
        desc = f"> **❌ Ошибка:**\n> Этот предмет нельзя использовать (`{item_id}`)."
        embed = create_embed("Использование", desc, ctx)
        await ctx.send(embed=embed)
        return
        
    item_data = CONSUMABLE_ITEMS[item_id]

    # === ЛОГИКА ИСПОЛЬЗОВАНИЯ ===
    ping_user_id = CUSTOM_PING_USER_ID
    ping_text = f"<@{ping_user_id}>"
    
    if item_id == "custom_coupon":
        # 1. Забираем 1 купон
        await update_user(ctx.author.id, ctx.guild.id, {
            "$pull": {"inventory": item_id} # (Удалит только одно вхождение)
        })
        
        # 2. Отправляем пинг админу
        desc = (
            f"> **✅ Купон на Кастомку использован!**\n"
            f"> _ _\n"
            f"> {item_data['emoji']} {ctx.author.mention} использовал **{item_data['name']}**.\n"
            f"> _ _\n"
            f"> {ping_text}, пожалуйста, свяжитесь с ним для выдачи **кастомной роли/итема**!"
        )
        embed = create_embed("Использование Купона", desc, ctx)
        embed.color = 0x00FF00 # Зеленый
        
        await ctx.send(content=ping_text, embed=embed)
        
    # --- (НОВАЯ ЛОГИКА) ---
    elif item_id == "custom_farm_coupon":
        # 1. НЕ ЗАБИРАЕМ КУПОН. Админ заберет его командой !createcustomfarm
        
        # 2. Отправляем пинг админу
        desc = (
            f"> **✅ Запрос на Кастомную Ферму!**\n"
            f"> _ _\n"
            f"> {item_data['emoji']} {ctx.author.mention} хочет использовать **{item_data['name']}**.\n"
            f"> _ _\n"
            f"> {ping_text}, пожалуйста, свяжитесь с ним, чтобы обсудить параметры фермы (название, доход, цену) и создать ее командой `!createcustomfarm`!"
        )
        embed = create_embed("Использование Купона", desc, ctx)
        embed.color = 0x00FF00 # Зеленый
        
        await ctx.send(content=ping_text, embed=embed)
        
    else:
        await ctx.send("❌ У этого предмета пока нет логики использования.")# (ЗАМЕНИТЬ СТАРУЮ КОМАНДУ !use, ~строка 1087)
# (ВСТАВИТЬ ПОСЛЕ !giveitem, ~строка 1085)

@bot.command(name="createcustomfarm")
@commands.has_permissions(administrator=True)
async def createcustomfarm(ctx: commands.Context, member: disnake.Member, income: int, price: int, *, name: str):
    """Создает кастомную ферму (роль) и выдает ее игроку, забирая купон."""
    
    user_data = await get_user(member.id, ctx.guild.id)
    inventory = user_data.get("inventory", [])
    
    # 1. Проверяем, есть ли у юзера купон
    if "custom_farm_coupon" not in inventory:
        await ctx.send(f"❌ У {member.display_name} нет 'custom_farm_coupon' в инвентаре!")
        return
        
    if income <= 0 or price <= 0:
        await ctx.send("❌ Доход и цена должны быть больше нуля!")
        return
        
    try:
        # 2. Создаем роль
        # (Название роли будет уникальным, чтобы мы могли ее найти)
        role_name = f"🌟 [CF] {name}"
        new_role = await ctx.guild.create_role(name=role_name, reason=f"Создание кастомной фермы для {member.display_name}")
        
        # 3. Сохраняем в БД
        farm_data = {
            "_id": new_role.id, # (Используем ID роли как ID в БД)
            "owner_id": member.id,
            "name": name,
            "income": income,
            "price": price,
            "emoji": "🌟" # (Эмодзи по умолчанию для кастомок)
        }
        await custom_farms_collection.insert_one(farm_data)
        
        # 4. Выдаем роль юзеру
        await member.add_roles(new_role, reason="Активация кастомной фермы")
        
        # 5. Забираем купон
        await update_user(member.id, ctx.guild.id, {
            "$pull": {"inventory": "custom_farm_coupon"}
        })
        
        desc = (
            f"> **✅ Кастомная ферма создана!**\n"
            f"> _ _\n"
            f"> **Владелец:** {member.mention}\n"
            f"> **Название:** {name} (Роль: {new_role.mention})\n"
            f"> **Доход:** {income:,} Кан/час\n"
            f"> **(Цена):** {price:,} Кан (для инфо)\n"
            f"> _ _\n"
            f"> Купон 'custom_farm_coupon' был успешно потрачен."
        )
        embed = create_embed("Админ | Создание Фермы", desc, ctx)
        await ctx.send(embed=embed)
        
    except disnake.Forbidden:
        await ctx.send("❌ **Ошибка прав:** У меня нет прав на создание или выдачу ролей!")
    except Exception as e:
        await ctx.send(f"❌ Произошла ошибка: {e}")
# ==================== ЛИДЕРБОРД ====================

class LeaderboardView(disnake.ui.View):
    def __init__(self, ctx: commands.Context, pages: List[dict], current_category: str):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.pages = pages
        self.current_page = 0
        self.current_category = current_category
        
    def create_page_embed(self) -> disnake.Embed:
        page_data = self.pages[self.current_page]
        
        category_names = {
            "money": "💰 По Деньгам",
            "farms": "🏭 По Фермам",
            "clans": "🏛️ По Кланам"
        }
        
        title = f"Лидерборд | {category_names.get(self.current_category, self.current_category)}"
        
        if len(self.pages) > 1:
            title += f" (Страница {self.current_page + 1}/{len(self.pages)})"
        
        embed = disnake.Embed(
            title=title,
            description=page_data["content"],
            color=EMBED_COLOR
        )
        
        icon_url = self.ctx.guild.icon.url if self.ctx.guild and self.ctx.guild.icon else None
        embed.set_author(name=EMBED_AUTHOR, icon_url=icon_url)
        
        return embed
        
    @disnake.ui.button(label="◀️", style=disnake.ButtonStyle.primary)
    async def previous_button(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Это не ваш лидерборд!", ephemeral=True)
            return
        self.current_page = (self.current_page - 1) % len(self.pages)
        embed = self.create_page_embed()
        await interaction.response.edit_message(embed=embed)
    
    @disnake.ui.button(label="▶️", style=disnake.ButtonStyle.primary)
    async def next_button(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Это не ваш лидерборд!", ephemeral=True)
            return
        self.current_page = (self.current_page + 1) % len(self.pages)
        embed = self.create_page_embed()
        await interaction.response.edit_message(embed=embed)
    
    @disnake.ui.button(label="💰 Деньги", style=disnake.ButtonStyle.success, row=1)
    async def money_button(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Это не ваш лидерборд!", ephemeral=True)
            return
        
        if self.current_category == "money":
            await interaction.response.send_message("Вы уже смотрите эту категорию!", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        # Загружаем данные по деньгам
        self.pages = await load_money_leaderboard(self.ctx)
        self.current_category = "money"
        self.current_page = 0
        
        embed = self.create_page_embed()
        await interaction.edit_original_message(embed=embed)
    
    @disnake.ui.button(label="🏭 Фермы", style=disnake.ButtonStyle.success, row=1)
    async def farms_button(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Это не ваш лидерборд!", ephemeral=True)
            return
        
        if self.current_category == "farms":
            await interaction.response.send_message("Вы уже смотрите эту категорию!", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        # Загружаем данные по фермам
        self.pages = await load_farms_leaderboard(self.ctx)
        self.current_category = "farms"
        self.current_page = 0
        
        embed = self.create_page_embed()
        await interaction.edit_original_message(embed=embed)
    
    @disnake.ui.button(label="🏛️ Кланы", style=disnake.ButtonStyle.success, row=1)
    async def clans_button(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Это не ваш лидерборд!", ephemeral=True)
            return
        
        if self.current_category == "clans":
            await interaction.response.send_message("Вы уже смотрите эту категорию!", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        # Загружаем данные по кланам
        self.pages = await load_clans_leaderboard(self.ctx)
        self.current_category = "clans"
        self.current_page = 0
        
        embed = self.create_page_embed()
        await interaction.edit_original_message(embed=embed)

async def load_money_leaderboard(ctx: commands.Context) -> List[dict]:
    """Загружает данные лидерборда по деньгам"""
    pipeline = [
        {"$match": {"guildId": ctx.guild.id}},
        {"$addFields": {
            "total": {"$add": ["$balance", {"$ifNull": ["$bank", 0]}]}
        }},
        {"$sort": {"total": -1}}
    ]
    
    users = await users_collection.aggregate(pipeline).to_list(None)
    
    if not users:
        return [{"content": "> **❄️ Нет данных для отображения!**"}]
    
    pages = []
    per_page = 10
    
    for i in range(0, len(users), per_page):
        page_users = users[i:i+per_page]
        desc = ""
        
        for idx, user in enumerate(page_users, start=i+1):
            try:
                member = await ctx.guild.fetch_member(user["userId"])
                name = member.display_name
            except:
                name = f"User#{user['userId']}"
            
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else "💠"
            total = user.get("total", 0)
            cash = user.get("balance", 0)
            bank = user.get("bank", 0)
            
            desc += f"> {medal} **#{idx}** {name}\n"
            desc += f"> 💴 Наличные: {cash:,} | 🏦 Банк: {bank:,}\n"
            desc += f"> 💎 **Всего: {total:,} Кан**\n"
            desc += "> _ _\n"
        
        pages.append({"content": desc})
    
    return pages

async def load_farms_leaderboard(ctx: commands.Context) -> List[dict]:
    """Загружает данные лидерборда по фермам"""
    user_incomes = []
    
    all_users = await users_collection.find({"guildId": ctx.guild.id}).to_list(None)
    
    for user_data in all_users:
        try:
            member = await ctx.guild.fetch_member(user_data["userId"])
        except:
            continue
        
        total_income = 0
        farm_count = 0
        
        for item_id, item in SHOP_ITEMS.items():
            role_id = item.get("role_id")
            if role_id is None:
                continue
            
            if any(role.id == role_id for role in member.roles):
                total_income += item["income"]
                farm_count += 1
        
        if total_income > 0:
            user_incomes.append({
                "member": member,
                "income": total_income,
                "farm_count": farm_count
            })
    
    user_incomes.sort(key=lambda x: x["income"], reverse=True)
    
    if not user_incomes:
        return [{"content": "> **❄️ Ни у кого нет ферм!**\n> Купите улучшения в `!shop`"}]
    
    pages = []
    per_page = 10
    
    for i in range(0, len(user_incomes), per_page):
        page_users = user_incomes[i:i+per_page]
        desc = ""
        
        for idx, user_info in enumerate(page_users, start=i+1):
            member = user_info["member"]
            income = user_info["income"]
            farm_count = user_info["farm_count"]
            
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else "🏭"
            
            desc += f"> {medal} **#{idx}** {member.display_name}\n"
            desc += f"> 🏭 Ферм: {farm_count} | 💰 **{income:,} Кан/час**\n"
            desc += f"> 📅 За день: {income * 24:,} Кан\n"
            desc += "> _ _\n"
        
        pages.append({"content": desc})
    
    return pages

async def load_clans_leaderboard(ctx: commands.Context) -> List[dict]:
    """Загружает данные лидерборда по кланам"""
    clans = await clans_collection.find({"guildId": ctx.guild.id}).sort("bank", -1).to_list(None)
    
    if not clans:
        return [{"content": "> **❄️ Нет кланов на сервере!**\n> Создайте первый: `!clan create <тэг> <название>`"}]
    
    pages = []
    per_page = 10
    
    for i in range(0, len(clans), per_page):
        page_clans = clans[i:i+per_page]
        desc = ""
        
        for idx, clan_data in enumerate(page_clans, start=i+1):
            try:
                owner = await ctx.guild.fetch_member(clan_data["owner_id"])
                owner_name = owner.display_name
            except:
                owner_name = f"User#{clan_data['owner_id']}"
            
            member_count = await get_clan_member_count(clan_data["_id"])
            member_limit = calculate_member_limit(clan_data.get("upgrades", []))
            
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else "🏛️"
            
            desc += f"> {medal} **#{idx}** {clan_data['name']} [{clan_data['tag']}]\n"
            desc += f"> 👑 Владелец: {owner_name}\n"
            desc += f"> 👥 Участников: {member_count}/{member_limit}\n"
            desc += f"> 💰 **Казна: {clan_data.get('bank', 0):,} Кан**\n"
            desc += "> _ _\n"
        
        pages.append({"content": desc})
    
    return pages
@bot.command(name="leaderboard", aliases=["lb", "top"])
async def leaderboard(ctx: commands.Context, category: str = "money", page: int = 1):
    """
    Лидерборд сервера
    Категории: money (деньги), farms (фермы), clans (кланы)
    """
    async with ctx.typing():  # ВОТ ИСПРАВЛЕНИЕ
        category = category.lower()
        
        if category not in ["money", "farms", "clans"]:
            desc = (
                "> **❌ Неверная категория!**\n"
                "> _ _\n"
                "> **Доступные категории:**\n"
                "> `money` - По деньгам\n"
                "> `farms` - По фермам\n"
                "> `clans` - По кланам\n"
                "> _ _\n"
                "> **Использование:**\n"
                "> `!leaderboard <категория> [страница]`\n"
                "> `!lb money` или `!top farms`"
            )
            embed = create_embed("Лидерборд", desc, ctx)
            await ctx.send(embed=embed)
            return
        
        # Загружаем нужную категорию
        if category == "money":
            pages = await load_money_leaderboard(ctx)
        elif category == "farms":
            pages = await load_farms_leaderboard(ctx)
        else:  # clans
            pages = await load_clans_leaderboard(ctx)
        
        # Проверка страницы
        if page > len(pages):
            page = len(pages)
        if page < 1:
            page = 1
        
        view = LeaderboardView(ctx, pages, category)
        view.current_page = page - 1
        
        embed = view.create_page_embed()
        await ctx.send(embed=embed, view=view)
    

        
@bot.command(name="createpromo")
@commands.has_permissions(administrator=True)
async def createpromo(ctx: commands.Context, code: str, reward: int, uses: int):
    # БЕЗ КУЛДАУНА - админская команда
    
    code = code.lower() # Сохраняем код в нижнем регистре
    
    # Проверяем, существует ли уже такой код
    existing = await promocodes_collection.find_one({"guildId": ctx.guild.id, "code": code})
    if existing:
        await ctx.send(f"❌ Промокод `{code}` уже существует!")
        return
        
    if reward <= 0 or uses <= 0:
        await ctx.send("❌ Награда и количество использований должны быть больше нуля!")
        return

    await promocodes_collection.insert_one({
        "guildId": ctx.guild.id,
        "code": code,
        "reward": reward,
        "max_uses": uses,
        "redeemed_by": [] # Список тех, кто использовал
    })
    
    desc = (
        f"> **✅ Промокод создан!**\n"
        f"> _ _\n"
        f"> **Код:** `{code}`\n"
        f"> **Награда:** {reward:,} Кан 💴\n"
        f"> **Использования:** {uses} раз"
    )
    embed = create_embed("Создание Промокода", desc, ctx)
    await ctx.send(embed=embed)

@bot.command(name="deletepromo")
@commands.has_permissions(administrator=True)
async def deletepromo(ctx: commands.Context, code: str):
    # БЕЗ КУЛДАУНА - админская команда
    code = code.lower()
    
    result = await promocodes_collection.delete_one({"guildId": ctx.guild.id, "code": code})
    
    if result.deleted_count == 0:
        await ctx.send(f"❌ Промокод `{code}` не найден!")
        return
        
    desc = f"> **✅ Промокод `{code}` был успешно удален!**"
    embed = create_embed("Удаление Промокода", desc, ctx)
    await ctx.send(embed=embed)
    


@bot.command(name="promo")
async def promo(ctx: commands.Context, code: str):
    if not await check_command_cooldown(ctx, "promo"):
        return
        
    code = code.lower()
    user_id = ctx.author.id
    guild_id = ctx.guild.id
    
    # Ищем промокод
    promo_data = await promocodes_collection.find_one({"guildId": guild_id, "code": code})
    
    # 1. Проверка: Существует ли код?
    if not promo_data:
        desc = f"> **❌ Промокод `{code}` не найден!**\n> Убедитесь, что вы ввели его правильно."
        embed = create_embed("Промокод", desc, ctx)
        await ctx.send(embed=embed)
        return
        
    # 2. Проверка: Использовал ли юзер этот код?
    if user_id in promo_data.get("redeemed_by", []):
        desc = f"> **❌ Вы уже активировали этот промокод!**"
        embed = create_embed("Промокод", desc, ctx)
        await ctx.send(embed=embed)
        return
        
    # 3. Проверка: Остались ли использования?
    redeemed_count = len(promo_data.get("redeemed_by", []))
    if redeemed_count >= promo_data.get("max_uses"):
        desc = f"> **❌ У промокода `{code}` закончились использования!**\n> Вы не успели."
        embed = create_embed("Промокод", desc, ctx)
        await ctx.send(embed=embed)
        return

    # === Все проверки пройдены, выдаем награду ===
    
    user = await get_user(user_id, guild_id)
    reward = promo_data["reward"]
    new_balance = user["balance"] + reward
    
    # Обновляем баланс юзера
    await update_user(user_id, guild_id, {"balance": new_balance})
    
    # Обновляем промокод (добавляем юзера в список)
    await promocodes_collection.update_one(
        {"_id": promo_data["_id"]},
        {"$push": {"redeemed_by": user_id}}
    )
    
    uses_left = promo_data.get("max_uses") - (redeemed_count + 1)
    
    desc = (
        f"> **✅ Промокод `{code}` успешно активирован!**\n"
        f"> _ _\n"
        f"> **🧊 Награда:**\n"
        f"> +{reward:,} Кан 💴\n"
        f"> _ _\n"
        f"> **💴 Новый баланс:**\n"
        f"> {new_balance:,} Кан\n"
        f"> _ _\n"
        f"> (Осталось использований: {uses_left})"
    )
    embed = create_embed("Промокод Активирован", desc, ctx)
    await ctx.send(embed=embed)
# ==================== КАЗИНО ====================

@bot.command(name="coinflip", aliases=["cf"])
async def coinflip(ctx: commands.Context, amount: int, choice: str):
    if not await check_command_cooldown(ctx, "coinflip"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    if amount < MIN_BET:
        await ctx.send(f"❌ Минимальная ставка: {MIN_BET:,} Кан!")
        return
    
    if amount <= 0:
        await ctx.send("❌ Ставка должна быть положительной!")
        return
    
    if user["balance"] < amount:
        desc = f"> **❄️ Недостаточно средств!**\n> Ваш баланс: {user['balance']:,} Кан\n> Требуется: {amount:,} Кан"
        embed = create_embed("Подброс Монеты", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    choice = choice.lower()
    if choice not in ["орел", "решка", "heads", "tails"]:
        await ctx.send("❌ Выберите 'орел' или 'решка'!")
        return
    
    result = random.choice(["орел", "решка"])
    user_choice = "орел" if choice in ["орел", "heads"] else "решка"
    
    won = random.randint(1, 100) <= 30 and result == user_choice
    
    new_balance = user["balance"] + amount if won else user["balance"] - amount
    await update_user(ctx.author.id, ctx.guild.id, {"balance": new_balance})
    
    # --- (ВОТ ИСПРАВЛЕНИЕ) ---
    # (Эта строка теперь имеет правильный отступ)
    await update_quest_progress(ctx.author.id, ctx.guild.id, "daily_gambler")

    
    result_emoji = "🪙" if result == "орел" else "💿"
    win_text = f"**+{amount:,} Кан**" if won else f"-{amount:,} Кан"
    status = "Вы выиграли" if won else "Вы проиграли"
    
    desc = f"> **❄️ Выпало:**\n> {result_emoji} {result.capitalize()}\n> _ _\n> **🧊 Результат:**\n> {status} {win_text}\n> _ _\n> **💴 Новый баланс:**\n> {new_balance:,} Кан"
    embed = create_embed("Подброс Монеты", desc, ctx)
    await ctx.send(embed=embed)
@bot.command(name="slots")
async def slots(ctx: commands.Context, amount: int):
    if not await check_command_cooldown(ctx, "slots"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    if amount < MIN_BET:
        await ctx.send(f"❌ Минимальная ставка: {MIN_BET:,} Кан!")
        return
    
    if amount <= 0:
        await ctx.send("❌ Ставка должна быть положительной!")
        return
    
    if user["balance"] < amount:
        desc = f"> **❄️ Недостаточно средств!**\n> Ваш баланс: {user['balance']:,} Кан\n> Требуется: {amount:,} Кан"
        embed = create_embed("Слот-Машина", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    symbols = ["🧊", "💎", "❄️", "⚔️"]
    result = [random.choice(symbols) for _ in range(3)]
    
    win_multiplier = 0
    win_chance = random.randint(1, 1000)
    
    if win_chance <= 5:
        if result[0] == result[1] == result[2]:
            win_multiplier = 10
    elif win_chance <= 55:
        if result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
            win_multiplier = 2
    
    winnings = amount * win_multiplier if win_multiplier > 0 else -amount
    new_balance = user["balance"] + winnings
    await update_user(ctx.author.id, ctx.guild.id, {"balance": new_balance})
   
    # --- (ВОТ ИСПРАВЛЕНИЕ) ---
    # (Эта строка теперь имеет правильный отступ)
    await update_quest_progress(ctx.author.id, ctx.guild.id, "daily_gambler")
    
    result_str = f"[ {result[0]} | {result[1]} | {result[2]} ]"
    
    if winnings > 0:
        status = f"Вы выиграли **+{winnings:,} Кан** (x{win_multiplier})"
    else:
        status = f"Вы проиграли {abs(winnings):,} Кан"
    
    desc = f"> **❄️ Результат:**\n> {result_str}\n> _ _\n> **🧊 Итог:**\n> {status}\n> _ _\n> **💴 Новый баланс:**\n> {new_balance:,} Кан"
    embed = create_embed("Слот-Машина", desc, ctx)
    await ctx.send(embed=embed)
# ==================== РУЛЕТКА ====================

def get_roulette_color(number: int) -> str:
    if number == 0:
        return "green"
    reds = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
    return "red" if number in reds else "black"

def check_roulette_win(bet_type: str, number: int) -> bool:
    color = get_roulette_color(number)
    
    base_chance = random.randint(1, 100) <= 30
    
    if not base_chance:
        return False
    
    if bet_type == "red":
        return color == "red"
    elif bet_type == "black":
        return color == "black"
    elif bet_type == "green":
        return number == 0
    elif bet_type == "0":
        return number == 0
    elif bet_type == "1-11":
        return 1 <= number <= 11
    elif bet_type == "12-23":
        return 12 <= number <= 23
    elif bet_type == "24-36":
        return 24 <= number <= 36
    return False

def get_roulette_multiplier(bet_type: str) -> int:
    if bet_type in ["red", "black"]:
        return 2
    elif bet_type == "green" or bet_type == "0":
        return 35
    elif bet_type in ["1-11", "12-23", "24-36"]:
        return 3
    return 0

@bot.command(name="roulette", aliases=["rl"])
async def roulette(ctx: commands.Context, bet_type: str, amount: int):
    if not await check_command_cooldown(ctx, "roulette"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    if amount < MIN_BET:
        await ctx.send(f"❌ Минимальная ставка: {MIN_BET:,} Кан!")
        return
    
    if amount <= 0:
        await ctx.send("❌ Ставка должна быть положительной!")
        return
    
    if user["balance"] < amount:
        desc = f"> **❄️ Недостаточно средств!**\n> Ваш баланс: {user['balance']:,} Кан\n> Требуется: {amount:,} Кан"
        embed = create_embed("Рулетка", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    bet_type = bet_type.lower()
    valid_bets = ["red", "black", "green", "0", "1-11", "12-23", "24-36"]
    if bet_type not in valid_bets:
        await ctx.send(f"❌ Неверная ставка! Доступны: {', '.join(valid_bets)}")
        return
    
    channel_id = ctx.channel.id
    
    if channel_id in roulette_lobbies:
        lobby = roulette_lobbies[channel_id]
        
        for bet in lobby["bets"]:
            if bet["user_id"] == ctx.author.id:
                desc = "> **❌ Вы уже сделали ставку!**\n> Дождитесь окончания текущего раунда"
                embed = create_embed("Рулетка", desc, ctx)
                await ctx.send(embed=embed, delete_after=5)
                return
    
    await update_user(ctx.author.id, ctx.guild.id, {"balance": user["balance"] - amount})   
    # --- (ВОТ ИСПРАВЛЕНИЕ) ---
    # (Эта строка теперь имеет правильный отступ)
    await update_quest_progress(ctx.author.id, ctx.guild.id, "daily_gambler")

    
    bet_display = {
        "red": "🔴 КРАСНОЕ",
        "black": "⚫ ЧЕРНОЕ", 
        "green": "🟢 ЗЕЛЕНОЕ",
        "0": "🟢 0",
        "1-11": "🔢 1-11",
        "12-23": "🔢 12-23",
        "24-36": "🔢 24-36"
    }
    
    if channel_id in roulette_lobbies:
        lobby = roulette_lobbies[channel_id]
        lobby["bets"].append({
            "user_id": ctx.author.id,
            "user_name": ctx.author.display_name,
            "bet_type": bet_type,
            "amount": amount
        })
        
        desc = "> **❄️ Текущие ставки:**\n>\n"
        for bet in lobby["bets"]:
            desc += f"> {bet['user_name']}: {bet['amount']:,} Кан на {bet_display.get(bet['bet_type'], bet['bet_type'])}\n"
        desc += f">\n> **🧊 Кручу через:** {int(lobby['remaining_time'])} сек"
        
        embed = create_embed("Рулетка | Идет набор ставок", desc, ctx)
        await lobby["message"].edit(embed=embed)
        
    else:
        desc = f"> **❄️ Текущие ставки:**\n> _ _\n> {ctx.author.display_name}: {amount:,} Кан на {bet_display.get(bet_type, bet_type)}\n> _ _\n> **🧊 Кручу через:** 30 сек"
        embed = create_embed("Рулетка | Идет набор ставок", desc, ctx)
        message = await ctx.send(embed=embed)
        
        roulette_lobbies[channel_id] = {
            "message": message,
            "bets": [{
                "user_id": ctx.author.id,
                "user_name": ctx.author.display_name,
                "bet_type": bet_type,
                "amount": amount
            }],
            "remaining_time": 30,
            "ctx": ctx
        }
        
        await asyncio.sleep(30)
        
        if channel_id not in roulette_lobbies:
            return
        
        lobby = roulette_lobbies[channel_id]
        winning_number = random.randint(0, 36)
        color = get_roulette_color(winning_number)
        
        color_emoji = "🔴" if color == "red" else "⚫" if color == "black" else "🟢"
        color_name = "Красное" if color == "red" else "Черное" if color == "black" else "Зеленое"
        
        results = []
        for bet in lobby["bets"]:
            won = check_roulette_win(bet["bet_type"], winning_number)
            if won:
                multiplier = get_roulette_multiplier(bet["bet_type"])
                winnings = bet["amount"] * multiplier
                user_data = await get_user(bet["user_id"], ctx.guild.id)
                await update_user(bet["user_id"], ctx.guild.id, {"balance": user_data["balance"] + winnings})
                results.append(f"> ✅ {bet['user_name']} выиграл **+{winnings:,} Кан** (x{multiplier})")
            else:
                results.append(f"> ❌ {bet['user_name']} проиграл {bet['amount']:,} Кан")
        
        desc = f"> **❄️ Выпало:**\n> {color_emoji} **{winning_number}** ({color_name})\n> _ _\n> **🧊 Результаты:**\n" + "\n".join(results)
        embed = create_embed("Рулетка | Результаты", desc, ctx)
        await lobby["message"].edit(embed=embed)
        
        del roulette_lobbies[channel_id]

# ==================== БЛЭКДЖЕК ====================

def create_deck() -> List[str]:
    deck = list(CARD_DECK_TEMPLATE)
    random.shuffle(deck)
    return deck

def calculate_hand_value(hand: List[str]) -> int:
    value = 0
    aces = 0
    for card in hand:
        card_value_str = card[:-2]
        value += CARD_VALUES[card_value_str]
        if card_value_str == "A":
            aces += 1
            
    while value > 21 and aces > 0:
        value -= 10
        aces -= 1
    return value

def format_hand(hand: List[str], hide_first: bool = False) -> str:
    if hide_first:
        return f"[{hand[0]}, ❓]"
    return f"[{', '.join(hand)}]"

async def end_blackjack_game(user_id: int, guild_id: int, game: dict, won: bool, reason: str, push: bool = False):
    if user_id not in blackjack_games:
        return
        
    user = await get_user(user_id, guild_id)
    bet = game["bet"]
    
    if won:
        winnings = bet * 2
        new_balance = user["balance"] + winnings
        result_text = f"**Вы выиграли +{winnings:,} Кан!**"
    elif push:
        new_balance = user["balance"] + bet
        result_text = f"**Ничья!** Ваша ставка {bet:,} Кан возвращена."
    else:
        new_balance = user["balance"] 
        result_text = f"**Вы проиграли -{bet:,} Кан!**"

    await update_user(user_id, guild_id, {"balance": new_balance})
    
    player_score = calculate_hand_value(game["player_hand"])
    dealer_score = calculate_hand_value(game["dealer_hand"])
    
    desc = (
        f"> **Ваша рука:** {format_hand(game['player_hand'])} (Очки: {player_score})\n"
        f"> **Рука дилера:** {format_hand(game['dealer_hand'])} (Очки: {dealer_score})\n"
        f"> _ _\n"
        f"> **{reason}**\n"
        f"> {result_text}\n"
        f"> _ _\n"
        f"> **💴 Новый баланс:** {new_balance:,} Кан"
    )
    embed = create_embed("Блэкджек | Игра Окончена", desc, game["ctx"])
    
    try:
        await game["message"].edit(embed=embed, view=None)
    except disnake.NotFound:
        await game["ctx"].send(embed=embed)
        
    del blackjack_games[user_id]

class BlackjackView(disnake.ui.View):
    def __init__(self, ctx: commands.Context, game: dict):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.game = game

    async def on_timeout(self):
        if self.ctx.author.id in blackjack_games:
            await self.dealer_turn(self.ctx.interaction)

    async def dealer_turn(self, interaction: disnake.Interaction):
        game = self.game
        
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        player_score = calculate_hand_value(game["player_hand"])
        dealer_score = calculate_hand_value(game["dealer_hand"])
        
        while dealer_score < 17:
            game["dealer_hand"].append(game["deck"].pop())
            dealer_score = calculate_hand_value(game["dealer_hand"])
            
            desc = (
                f"> **Ваша рука:** {format_hand(game['player_hand'])} (Очки: {player_score})\n"
                f"> **Рука дилера:** {format_hand(game['dealer_hand'])} (Очки: {dealer_score})\n"
                f"> _ _\n"
                f"> ...Дилер берет карту..."
            )
            embed = create_embed("Блэкджек | Ход Дилера", desc, self.ctx)
            await game["message"].edit(embed=embed)
            await asyncio.sleep(1.5)

        if dealer_score > 21:
            await end_blackjack_game(interaction.user.id, interaction.guild.id, game, won=True, reason="У дилера перебор!")
        elif dealer_score > player_score:
            await end_blackjack_game(interaction.user.id, interaction.guild.id, game, won=False, reason="У дилера больше очков!")
        elif player_score > dealer_score:
            await end_blackjack_game(interaction.user.id, interaction.guild.id, game, won=True, reason="У вас больше очков!")
        else:
            await end_blackjack_game(interaction.user.id, interaction.guild.id, game, won=False, reason="Ничья!", push=True)

    @disnake.ui.button(label="Взять (Hit)", style=disnake.ButtonStyle.success)
    async def hit_button(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Это не ваша игра!", ephemeral=True)
            return

        game = self.game
        game["player_hand"].append(game["deck"].pop())
        player_score = calculate_hand_value(game["player_hand"])
        
        if player_score > 21:
            await end_blackjack_game(interaction.user.id, interaction.guild.id, game, won=False, reason="У вас перебор!")
            return

        dealer_score = calculate_hand_value(game["dealer_hand"])
        desc = (
            f"> **Ваша рука:** {format_hand(game['player_hand'])} (Очки: {player_score})\n"
            f"> **Рука дилера:** {format_hand(game['dealer_hand'], hide_first=True)} (Очки: ?)\n"
            f"> _ _\n"
            f"> **🧊 Что делаете?**"
        )
        embed = create_embed("Блэкджек | Ваш Ход", desc, self.ctx)
        await interaction.response.edit_message(embed=embed, view=self)

    @disnake.ui.button(label="Стоп (Stand)", style=disnake.ButtonStyle.danger)
    async def stand_button(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Это не ваша игра!", ephemeral=True)
            return
            
        await self.dealer_turn(interaction)

@bot.command(name="blackjack", aliases=["bj"])
async def blackjack(ctx: commands.Context, amount: int):
    if not await check_command_cooldown(ctx, "blackjack"):
        return
        
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    if ctx.author.id in blackjack_games:
        await ctx.send("❌ Вы уже в игре! Завершите текущую партию.")
        return

    if amount < MIN_BET:
        await ctx.send(f"❌ Минимальная ставка: {MIN_BET:,} Кан!")
        return
        
    if amount <= 0:
        await ctx.send("❌ Ставка должна быть положительной!")
        return
        
    if user["balance"] < amount:
        desc = f"> **❄️ Недостаточно средств!**\n> Ваш баланс: {user['balance']:,} Кан\n> Требуется: {amount:,} Кан"
        embed = create_embed("Блэкджек", desc, ctx)
        await ctx.send(embed=embed)
        return
        
    await update_user(ctx.author.id, ctx.guild.id, {"balance": user["balance"] - amount})     
    # --- (ВОТ ИСПРАВЛЕНИЕ) ---
    # (Эта строка теперь имеет правильный отступ
    await update_quest_progress(ctx.author.id, ctx.guild.id, "daily_gambler")

    
    deck = create_deck()
    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]
    
    player_score = calculate_hand_value(player_hand)
    dealer_score = calculate_hand_value(dealer_hand)
    
    desc = (
        f"> **Ваша рука:** {format_hand(player_hand)} (Очки: {player_score})\n"
        f"> **Рука дилера:** {format_hand(dealer_hand, hide_first=True)} (Очки: ?)\n"
        f"> _ _\n"
        f"> **🧊 Что делаете?**"
    )
    embed = create_embed("Блэкджек | Ваш Ход", desc, ctx)
    message = await ctx.send(embed=embed)
    
    game_state = {
        "user_id": ctx.author.id,
        "guild_id": ctx.guild.id,
        "bet": amount,
        "player_hand": player_hand,
        "dealer_hand": dealer_hand,
        "deck": deck,
        "message": message,
        "ctx": ctx
    }
    
    if player_score == 21:
        if dealer_score == 21:
            await end_blackjack_game(ctx.author.id, ctx.guild.id, game_state, won=False, reason="Блэкджек у обоих!", push=True)
        else:
            await end_blackjack_game(ctx.author.id, ctx.guild.id, game_state, won=True, reason="🎉 Блэкджек!")
        return
        
    if dealer_score == 21:
        await end_blackjack_game(ctx.author.id, ctx.guild.id, game_state, won=False, reason="Блэкджек у дилера!")
        return

    view = BlackjackView(ctx, game_state)
    blackjack_games[ctx.author.id] = game_state
    await message.edit(view=view)

# ==================== СИСТЕМА РАБОТ ====================
# ==================== СИСТЕМА РАБОТ (ИСПРАВЛЕНО) ====================

JOBS = {
    "academy_guard": {
        "name": "🎓 Охрана Академии",
        "emoji": "🎓",  # ДОБАВЛЕНО
        "description": "Охрана территории Академии Шинигами",  # ДОБАВЛЕНО
        "pay_min": 80,
        "pay_max": 150,
        "cooldown_hours": 1,
        "messages": [
            "патрулировали территорию Академии Шинигами",
            "следили за порядком на тренировках студентов",
            "охраняли библиотеку Академии",
            "проверяли пропуска у входа в Академию"
        ]
    },
    "soul_reaper": {
        "name": "⚔️ Шинигами",
        "emoji": "⚔️",  # ДОБАВЛЕНО
        "description": "Зачистка территорий от холлоу",  # ДОБАВЛЕНО
        "pay_min": 120,
        "pay_max": 250,
        "cooldown_hours": 2,
        "messages": [
            "очистили район от слабых холлоу",
            "провели патруль в мире живых",
            "помогли плюсу перейти в Общество Душ",
            "отчитались капитану о проделанной работе"
        ]
    },
    "squad_member": {
        "name": "🏯 Член Отряда",
        "emoji": "🏯",  # ДОБАВЛЕНО
        "description": "Выполнение миссий отряда",  # ДОБАВЛЕНО
        "pay_min": 200,
        "pay_max": 400,
        "cooldown_hours": 3,
        "messages": [
            "участвовали в миссии отряда",
            "тренировались с капитаном",
            "помогали в расследовании инцидента",
            "выполнили спецзадание от Сейрейтей"
        ]
    },
    "prostitute": {
        "name": "💕 Проститутка",
        "emoji": "💕",  # ДОБАВЛЕНО
        "description": "Эротические услуги",  # ДОБАВЛЕНО
        "pay_min": 400,
        "pay_max": 1200,
        "cooldown_hours": 3,
        "messages": [
            "поебался с Кьёраку",
            "отлизал Унохане",
            "пососал маленький писюнчик Тоширо",
            "отсосал изюм Ямамото"
        ]
    },
    "hollow_hunter": {
        "name": "👹 Охотник на Холлоу",
        "emoji": "👹",  # ДОБАВЛЕНО
        "description": "Охота на опасных холлоу",  # ДОБАВЛЕНО
        "pay_min": 300,
        "pay_max": 600,
        "cooldown_hours": 4,
        "messages": [
            "уничтожили группу холлоу в Уэко Мундо",
            "выследили и нейтрализовали опасного холлоу",
            "защитили город от нашествия холлоу",
            "добыли ценную информацию о холлоу"
        ]
    }
}

# ==================== ИСПРАВЛЕННАЯ КОМАНДА !work ====================

@bot.command(name="work") 
async def work(ctx: commands.Context, job_id: Optional[str] = None):
    if not await check_command_cooldown(ctx, "work"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    now = datetime.utcnow()
    
    # --- Блок 1: Показ списка работ (если ID не указан) ---
    if not job_id:
        desc = "> **❄️ Доступные работы:**\n> _ _\n"
        for jid, job in JOBS.items():
            desc += f"> **{jid}.** {job['emoji']} {job['name']}\n"
            desc += f"> Оплата: {job['pay_min']}-{job['pay_max']} Кан\n"
            desc += f"> Кулдаун: {job['cooldown_hours']}ч\n"
            desc += f"> _ _\n"
        
        desc += "\n> Используй: `!work [номер]`"
        embed = create_embed("Работа", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # --- Блок 2: Проверка существования работы ---
    if job_id not in JOBS:
        desc = "> **❌ Такой работы не существует!**\n> Используй `!work` чтобы увидеть список"
        embed = create_embed("Ошибка", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    job = JOBS[job_id]
    
    # --- Блок 3: Проверка кулдауна работы ---
    work_cooldowns = user.get("work_cooldowns", {})
    if job_id in work_cooldowns:
        cooldown_time = work_cooldowns[job_id]
        if now < cooldown_time:
            remaining = cooldown_time - now
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            desc = f"> **❄️ Кулдаун активен!**\n> Работа: {job['name']}\n> Осталось: {hours}ч {minutes}м"
            embed = create_embed("Работа", desc, ctx)
            await ctx.send(embed=embed)
            return
    
    # --- Блок 4: Выполнение работы ---
    reward = random.randint(job['pay_min'], job['pay_max'])
    new_balance = user["balance"] + reward
    new_cooldown = now + timedelta(hours=job['cooldown_hours'])
    
    # Обновляем кулдауны работ
    work_cooldowns[job_id] = new_cooldown
    
    update_data = {
        "balance": new_balance,
        "work_cooldowns": work_cooldowns
    }
    
    # Взнос в казну клана
    clan_contribution_text = ""
    if user.get("clan_id"):
        clan = await get_clan(user["clan_id"])
        if clan:
            contribution_rate = calculate_contribution_bonus(clan.get("upgrades", []))
            contribution = int(reward * contribution_rate)
            new_clan_bank = clan.get("bank", 0) + contribution
            
            await update_clan(clan["_id"], {"bank": new_clan_bank})
            clan_contribution_text = f"> **🏛️ Взнос в казну клана:**\n> +{contribution:,} Кан\n> _ _\n"
    
    await update_user(ctx.author.id, ctx.guild.id, update_data)
    await update_quest_progress(ctx.author.id, ctx.guild.id, "daily_worker")  # ИСПРАВЛЕНО
    
    # Случайное сообщение
    message = random.choice(job['messages'])
    
    desc = (
        f"> **{job['emoji']} {job['name']}**\n"
        f"> {job['description']}\n"
        f"> _ _\n"
        f"> Вы {message}\n"
        f"> _ _\n"
        f"> **💰 Заработано:** +{reward:,} Кан\n"
        f"> _ _\n"
        f"{clan_contribution_text}"
        f"> **💼 Баланс:** {new_balance:,} Кан"
    )
    
    embed = create_embed("Работа выполнена!", desc, ctx)
    await ctx.send(embed=embed)

# ==================== НОВЫЕ ВИДЫ ЗАРАБОТКА ====================

# 1. ЕЖЕЧАСНАЯ НАГРАДА
@bot.command(name="hourly")
async def hourly(ctx: commands.Context):
    """Получить ежечасную награду"""
    if not await check_command_cooldown(ctx, "hourly"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    now = datetime.utcnow()
    
    hourly_cooldown = user.get("hourly_cooldown")
    if hourly_cooldown and now < hourly_cooldown:
        remaining = hourly_cooldown - now
        minutes = int(remaining.total_seconds() // 60)
        seconds = int(remaining.total_seconds() % 60)
        desc = f"> **❄️ Кулдаун активен!**\n> Осталось: {minutes}м {seconds}с"
        embed = create_embed("Ежечасная Награда", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    reward = random.randint(150, 350)
    new_balance = user["balance"] + reward
    new_cooldown = now + timedelta(hours=1)
    
    await update_user(ctx.author.id, ctx.guild.id, {
        "balance": new_balance,
        "hourly_cooldown": new_cooldown
    })
    
    desc = (
        f"> **❄️ Ежечасная награда получена!**\n"
        f"> +{reward:,} Кан\n"
        f"> _ _\n"
        f"> **💰 Баланс:** {new_balance:,} Кан"
    )
    embed = create_embed("Ежечасная Награда", desc, ctx)
    await ctx.send(embed=embed)

# 2. ПОПРОШАЙНИЧЕСТВО (НОВОЕ)
@bot.command(name="beg")
async def beg(ctx: commands.Context):
    """Попрошайничать деньги"""
    if not await check_command_cooldown(ctx, "beg"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    now = datetime.utcnow()
    
    beg_cooldown = user.get("beg_cooldown")
    if beg_cooldown and now < beg_cooldown:
        remaining = beg_cooldown - now
        minutes = int(remaining.total_seconds() // 60)
        seconds = int(remaining.total_seconds() % 60)
        desc = f"> **❄️ Кулдаун активен!**\n> Осталось: {minutes}м {seconds}с"
        embed = create_embed("Попрошайничество", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Случайная награда или отказ
    success_chance = random.randint(1, 100)
    
    if success_chance <= 70:  # 70% успеха
        reward = random.randint(50, 200)
        new_balance = user["balance"] + reward
        
        messages = [
            f"Добрый самаритянин дал вам {reward:,} Кан!",
            f"Вы нашли {reward:,} Кан на улице!",
            f"Кто-то пожалел вас и дал {reward:,} Кан!",
            f"Вы получили {reward:,} Кан от незнакомца!",
            f"Капитан Кьёраку небрежно бросил вам {reward:,} Кан!"
        ]
        
        desc = (
            f"> **✅ Успех!**\n"
            f"> _ _\n"
            f"> {random.choice(messages)}\n"
            f"> _ _\n"
            f"> **💰 Новый баланс:** {new_balance:,} Кан"
        )
        color = 0x00FF00
    else:  # 30% провал
        new_balance = user["balance"]
        
        messages = [
            "Все прошли мимо вас...",
            "Вас прогнали с улицы!",
            "Никто не обратил на вас внимания.",
            "Вы получили только презрительные взгляды.",
            "Ичиго назвал вас бездельником!"
        ]
        
        desc = (
            f"> **❌ Неудача!**\n"
            f"> _ _\n"
            f"> {random.choice(messages)}\n"
            f"> Вы ничего не получили."
        )
        color = 0xFF0000
    
    await update_user(ctx.author.id, ctx.guild.id, {
        "balance": new_balance,
        "beg_cooldown": now + timedelta(minutes=5)
    })
    
    embed = create_embed("Попрошайничество", desc, ctx)
    embed.color = color
    await ctx.send(embed=embed)

# 3. ПОИСК (НОВОЕ)
@bot.command(name="search")
async def search(ctx: commands.Context):
    """Поискать деньги в различных местах"""
    if not await check_command_cooldown(ctx, "search"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    now = datetime.utcnow()
    
    search_cooldown = user.get("search_cooldown")
    if search_cooldown and now < search_cooldown:
        remaining = search_cooldown - now
        minutes = int(remaining.total_seconds() // 60)
        seconds = int(remaining.total_seconds() % 60)
        desc = f"> **❄️ Кулдаун активен!**\n> Осталось: {minutes}м {seconds}с"
        embed = create_embed("Поиск", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Случайное место поиска
    locations = {
        "🏯 Казармы Отряда": (100, 400),
        "📚 Библиотека Академии": (150, 350),
        "🌃 Улицы Каракуры": (80, 300),
        "🌙 Пустыня Уэко Мундо": (200, 600),
        "🏛️ Сейрейтей": (250, 500),
        "💀 Руины": (50, 800),
        "🎋 Бамбуковый лес": (120, 380)
    }
    
    location, (min_reward, max_reward) = random.choice(list(locations.items()))
    reward = random.randint(min_reward, max_reward)
    new_balance = user["balance"] + reward
    
    # Случайная находка
    findings = [
        f"Вы нашли {reward:,} Кан в кармане старой куртки!",
        f"Вы обнаружили {reward:,} Кан под камнем!",
        f"Кто-то потерял {reward:,} Кан!",
        f"Вы нашли кошелек с {reward:,} Кан!",
        f"В старом ящике лежало {reward:,} Кан!"
    ]
    
    await update_user(ctx.author.id, ctx.guild.id, {
        "balance": new_balance,
        "search_cooldown": now + timedelta(minutes=10)
    })
    
    desc = (
        f"> **🔍 Вы обыскали: {location}**\n"
        f"> _ _\n"
        f"> {random.choice(findings)}\n"
        f"> _ _\n"
        f"> **💰 Новый баланс:** {new_balance:,} Кан"
    )
    embed = create_embed("Поиск", desc, ctx)
    await ctx.send(embed=embed)

# 4. ПРЕСТУПЛЕНИЕ (НОВОЕ, РИСКОВАННОЕ)
@bot.command(name="crime")
async def crime(ctx: commands.Context):
    """Совершить преступление (высокий риск, высокая награда)"""
    if not await check_command_cooldown(ctx, "crime"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    now = datetime.utcnow()
    
    crime_cooldown = user.get("crime_cooldown")
    if crime_cooldown and now < crime_cooldown:
        remaining = crime_cooldown - now
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)
        desc = f"> **❄️ Кулдаун активен!**\n> Осталось: {hours}ч {minutes}м"
        embed = create_embed("Преступление", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Типы преступлений
    crimes = {
        "💰 Ограбление банка": {"reward": (1000, 3000), "penalty": (800, 1500), "success": 35},
        "🏪 Кража в магазине": {"reward": (500, 1200), "penalty": (400, 800), "success": 50},
        "🚗 Угон машины": {"reward": (800, 2000), "penalty": (600, 1200), "success": 40},
        "💎 Кража драгоценностей": {"reward": (1500, 4000), "penalty": (1000, 2000), "success": 25},
        "🏛️ Ограбление Сейрейтей": {"reward": (3000, 6000), "penalty": (2000, 3500), "success": 15}
    }
    
    crime_name, crime_data = random.choice(list(crimes.items()))
    success_chance = random.randint(1, 100)
    
    if success_chance <= crime_data["success"]:
        # Успех
        reward = random.randint(*crime_data["reward"])
        new_balance = user["balance"] + reward
        
        desc = (
            f"> **✅ УСПЕХ!**\n"
            f"> _ _\n"
            f"> {crime_name}\n"
            f"> Вы успешно совершили преступление!\n"
            f"> _ _\n"
            f"> **💰 Награбили:** +{reward:,} Кан\n"
            f"> _ _\n"
            f"> **💼 Новый баланс:** {new_balance:,} Кан"
        )
        color = 0x00FF00
    else:
        # Провал
        penalty = random.randint(*crime_data["penalty"])
        new_balance = max(0, user["balance"] - penalty)
        
        desc = (
            f"> **❌ ПРОВАЛ!**\n"
            f"> _ _\n"
            f"> {crime_name}\n"
            f"> Вас поймали!\n"
            f"> _ _\n"
            f"> **🚨 Штраф:** -{penalty:,} Кан\n"
            f"> _ _\n"
            f"> **💼 Новый баланс:** {new_balance:,} Кан"
        )
        color = 0xFF0000
    
    await update_user(ctx.author.id, ctx.guild.id, {
        "balance": new_balance,
        "crime_cooldown": now + timedelta(hours=6)
    })
    
    embed = create_embed("Преступление", desc, ctx)
    embed.color = color
    await ctx.send(embed=embed)


# 1. КОСТИ (DICE)
@bot.command(name="dice")
async def dice(ctx: commands.Context, amount: int):
    """Бросить 2 кубика. Если сумма >= 7, вы выигрываете!"""
    if not await check_command_cooldown(ctx, "dice"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    if amount < MIN_BET:
        await ctx.send(f"❌ Минимальная ставка: {MIN_BET:,} Кан!")
        return
    
    if amount <= 0:
        await ctx.send("❌ Ставка должна быть положительной!")
        return
    
    if user["balance"] < amount:
        desc = f"> **❄️ Недостаточно средств!**\n> Ваш баланс: {user['balance']:,} Кан\n> Требуется: {amount:,} Кан"
        embed = create_embed("Кости", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Бросаем кости
    dice1 = random.randint(1, 6)
    dice2 = random.randint(1, 6)
    total = dice1 + dice2
    
    # Шанс победы ~25% (БЫЛО 30%)
    base_win_chance = random.randint(1, 100) <= 25
    won = base_win_chance and total >= 7
    
    if won:
        # Множители в зависимости от суммы
        if total == 12:  # Дабл 6
            multiplier = 5
        elif total == 2:  # Дабл 1
            multiplier = 4
        elif dice1 == dice2:  # Любой дабл
            multiplier = 3
        else:
            multiplier = 2
            
        winnings = amount * multiplier
        new_balance = user["balance"] + winnings
        result_text = f"Вы выиграли **+{winnings:,} Кан** (x{multiplier})"
        color = 0x00FF00
    else:
        new_balance = user["balance"] - amount
        result_text = f"Вы проиграли {amount:,} Кан"
        color = 0xFF0000
    
    await update_user(ctx.author.id, ctx.guild.id, {"balance": new_balance})
    await update_quest_progress(ctx.author.id, ctx.guild.id, "daily_gambler")
    
    dice_emoji = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}
    
    desc = (
        f"> **❄️ Результат:**\n"
        f"> {dice_emoji[dice1]} + {dice_emoji[dice2]} = **{total}**\n"
        f"> _ _\n"
        f"> **🧊 Итог:**\n"
        f"> {result_text}\n"
        f"> _ _\n"
        f"> **💴 Новый баланс:**\n"
        f"> {new_balance:,} Кан"
    )
    embed = create_embed("Кости", desc, ctx)
    embed.color = color
    await ctx.send(embed=embed)

# 2. КРАШ (CRASH)
crash_games: Dict[int, dict] = {}


# ==================== (НОВЫЙ) КЛАСС ДЛЯ КРАША ====================

class CrashView(disnake.ui.View):
    def __init__(self, ctx: commands.Context, bet: int):
        super().__init__(timeout=60.0) 
        self.ctx = ctx
        self.bet = bet
        self.multiplier = 1.00
        self.cashed_out = False 
        self.crashed = False      
        self.message: disnake.Message = None

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ Это не твоя игра!", ephemeral=True)
            return False
        return True

    @disnake.ui.button(label="💰 ЗАБРАТЬ", style=disnake.ButtonStyle.success)
    async def cash_out_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        if self.crashed:
            await interaction.response.send_message("❌ Слишком поздно!", ephemeral=True)
            return
            
        self.cashed_out = True
        self.stop() 

        button.disabled = True
        button.label = "УСПЕХ"
        
        winnings = int(self.bet * self.multiplier)
        
        # (Возвращаем деньги игроку: ставку + выигрыш)
        user = await get_user(self.ctx.author.id, self.ctx.guild.id)
        
        # (Используем $inc, чтобы он работал с твоей новой update_user)
        await update_user(self.ctx.author.id, self.ctx.guild.id, {"$inc": {"balance": winnings}})

        # (Получаем новый баланс для отображения)
        new_balance = user["balance"] + winnings

        desc = (
            f"> **✅ УСПЕХ!**\n"
            f"> _ _\n"
            f"> **🧊 Вы забрали на:** x{self.multiplier:.2f}\n"
            f"> **💰 Выигрыш:** +{winnings:,} Кан\n"
            f"> _ _\n"
            f"> **💴 Новый баланс:** {new_balance:,} Кан"
        )
        
        embed = create_embed("Краш | Победа", desc, self.ctx)
        embed.color = 0x00FF00
        
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        if not self.cashed_out and not self.crashed:
            self.crashed = True 
            
            desc = (
                f"> **💥 ОБРУШЕНИЕ! (Время вышло)**\n"
                f"> _ _\n"
                f"> **💰 Потеряно:** {self.bet:,} Кан\n"
                f"> _ _\n"
                f"> *Вы не нажали 'Забрать' вовремя!*"
            )
            embed = create_embed("Краш | Проигрыш", desc, self.ctx)
            embed.color = 0xFF0000
            
            try:
                if self.message:
                    await self.message.edit(embed=embed, view=None)
            except disnake.NotFound:
                pass


# ==================== (ПОЛНАЯ) КОМАНДА КРАШ (с КД 5 минут) ====================
@bot.command(name="crash")
async def crash(ctx: commands.Context, amount: int):
    """Начать игру в 'Краш'"""
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    now = datetime.utcnow()

    # === (ВОТ ИЗМЕНЕНИЕ: 5-МИНУТНЫЙ КУЛДАУН) ===
    crash_cooldown = user.get("crash_cooldown")
    if crash_cooldown and now < crash_cooldown:
        remaining = crash_cooldown - now
        minutes = int(remaining.total_seconds() // 60)
        seconds = int(remaining.total_seconds() % 60)
        desc = f"> **❄️ Кулдаун на 'Краш' активен!**\n> Осталось: {minutes}м {seconds}с"
        embed = create_embed("Краш", desc, ctx)
        await ctx.send(embed=embed)
        return
    # === (КОНЕЦ ИЗМЕНЕНИЯ) ===
        
    if amount < MIN_BET:
        await ctx.send(f"❌ Минимальная ставка: {MIN_BET:,} Кан!")
        return
        
    if amount <= 0:
        await ctx.send("❌ Ставка должна быть положительной!")
        return
        
    if user["balance"] < amount:
        desc = f"> **❄️ Недостаточно средств!**\n> Ваш баланс: {user['balance']:,} Кан"
        embed = create_embed("Краш", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Снимаем ставку и СТАВИМ КУЛДАУН
    await update_user(ctx.author.id, ctx.guild.id, {
        "$inc": {"balance": -amount},
        "$set": {"crash_cooldown": now + timedelta(minutes=5)} # <-- ВОТ ОН
    })
    await update_quest_progress(ctx.author.id, ctx.guild.id, "daily_gambler")
    
    view = CrashView(ctx, amount)
    
    desc = (
        f"> **❄️ ИГРА НАЧАЛАСЬ!**\n"
        f"> _ _\n"
        f"> **🧊 Множитель:** x1.00\n"
        f"> **💰 Ваш выигрыш:** {amount:,} Кан\n"
        f"> _ _\n"
        f"> **🔥 Шанс краша (сейчас):** 50%\n" 
        f"> *Нажмите 'ЗАБРАТЬ' до того, как обрушится!*"
    )
    embed = create_embed("Краш", desc, ctx)
    message = await ctx.send(embed=embed, view=view)
    view.message = message 
    
    # === (Динамический краш 50% -> 90% (рост 10%)) ===
    
    current_crash_chance = 50
    crash_chance_increase = 10 
    max_crash_chance = 90      
    
    while not view.cashed_out:
        await asyncio.sleep(1.5) 
        
        roll = random.randint(1, 100)
        
        if roll <= current_crash_chance:
            break # (КРАШ)
        
        view.multiplier += random.uniform(0.05, max(0.15, view.multiplier * 0.1))
        
        current_crash_chance += crash_chance_increase
        if current_crash_chance > max_crash_chance:
            current_crash_chance = max_crash_chance 
            
        if view.cashed_out: 
            break
            
        current_win = int(amount * view.multiplier)
        desc = (
            f"> **❄️ ИГРА ИДЕТ!**\n"
            f"> _ _\n"
            f"> **🧊 Множитель:** x{view.multiplier:.2f}\n"
            f"> **💰 Ваш выигрыш:** {current_win:,} Кан\n"
            f"> _ _\n"
            f"> **🔥 Шанс краша (след. тик): {current_crash_chance}%**\n"
            f"> *Нажмите 'ЗАБРАТЬ' до того, как обрушится!*"
        )
        embed = create_embed("Краш", desc, ctx)
        try:
            await message.edit(embed=embed)
        except disnake.NotFound:
            break 
        except Exception as e:
            print(f"Crash edit error: {e}")
            break
    
    # (Этот блок выполняется, ЕСЛИ цикл был прерван (краш) И юзер НЕ нажал "Забрать")
    if not view.cashed_out:
        view.crashed = True
        for item in view.children:
            item.disabled = True
        
        desc = (
            f"> **💥 ОБРУШЕНИЕ!**\n"
            f"> _ _\n"
            f"> **🧊 Обрушилось на:** x{view.multiplier:.2f}\n"
            f"> **💰 Потеряно:** {amount:,} Кан\n"
            f"> _ _\n"
            f"> *Вы не успели забрать!*"
        )
        embed = create_embed("Краш | Проигрыш", desc, ctx)
        embed.color = 0xFF0000
        
        try:
            await message.edit(embed=embed, view=view)
        except disnake.NotFound:
            pass
            


# 3. МИНЫ (MINES)
class MinesView(disnake.ui.View):
    def __init__(self, ctx: commands.Context, amount: int, mines_count: int):
        super().__init__(timeout=60.0)
        self.ctx = ctx
        self.amount = amount
        self.mines_count = mines_count
        self.grid_size = 25  # 5x5
        self.opened = []
        self.multiplier = 1.0
        
        # Размещаем мины
        all_positions = list(range(self.grid_size))
        self.mine_positions = set(random.sample(all_positions, mines_count))
        
        # Создаем кнопки
        for i in range(self.grid_size):
            button = disnake.ui.Button(
                label="❓",
                style=disnake.ButtonStyle.secondary,
                custom_id=f"mine_{i}",
                row=i // 5
            )
            button.callback = self.create_callback(i)
            self.add_item(button)
        
        # Кнопка "Забрать"
        cashout = disnake.ui.Button(
            label="💰 ЗАБРАТЬ",
            style=disnake.ButtonStyle.success,
            custom_id="cashout",
            row=4
        )
        cashout.callback = self.cashout_callback
        self.add_item(cashout)
    
    def create_callback(self, position: int):
        async def callback(interaction: disnake.MessageInteraction):
            if interaction.user.id != self.ctx.author.id:
                await interaction.response.send_message("❌ Это не ваша игра!", ephemeral=True)
                return
            
            if position in self.opened:
                await interaction.response.send_message("❌ Уже открыто!", ephemeral=True)
                return
            
            self.opened.append(position)
            
            # Попали на мину?
            if position in self.mine_positions:
                await self.game_over(interaction, hit_mine=True)
                return
            
            # Увеличиваем множитель
            safe_tiles = self.grid_size - self.mines_count
            progress = len(self.opened) / safe_tiles
            self.multiplier = 1.0 + (progress * 1.5)  # До x2.5 (БЫЛО 2.0)
            
            # Обновляем кнопку
            for item in self.children:
                if hasattr(item, 'custom_id') and item.custom_id == f"mine_{position}":
                    item.label = "💎"
                    item.style = disnake.ButtonStyle.success
                    item.disabled = True
            
            # Проверка победы (открыли все безопасные)
            if len(self.opened) == safe_tiles:
                await self.game_over(interaction, won=True)
                return
            
            winnings = int(self.amount * self.multiplier)
            desc = (
                f"> **❄️ БЕЗОПАСНО!**\n"
                f"> _ _\n"
                f"> **🧊 Множитель:** x{self.multiplier:.2f}\n"
                f"> **💰 Текущий выигрыш:** {winnings:,} Кан\n"
                f"> **📊 Открыто:** {len(self.opened)}/{safe_tiles}\n"
                f"> _ _\n"
                f"> *Продолжайте или заберите!*"
            )
            embed = create_embed("Мины", desc, self.ctx)
            await interaction.response.edit_message(embed=embed, view=self)
        
        return callback
    
    async def cashout_callback(self, interaction: disnake.MessageInteraction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ Это не ваша игра!", ephemeral=True)
            return
        
        await self.game_over(interaction, cashed_out=True)
    
    async def game_over(self, interaction: disnake.MessageInteraction, hit_mine=False, won=False, cashed_out=False):
        # Отключаем все кнопки
        for item in self.children:
            item.disabled = True
        
        # Показываем все мины
        for i, item in enumerate(self.children[:-1]):  # Все кроме "Забрать"
            if i in self.mine_positions:
                item.label = "💣"
                item.style = disnake.ButtonStyle.danger
        
        if hit_mine:
            desc = (
                f"> **💥 БУМ! ВЫ ПОПАЛИ НА МИНУ!**\n"
                f"> _ _\n"
                f"> **💰 Потеряно:** {self.amount:,} Кан\n"
                f"> **📊 Открыто:** {len(self.opened)}/{self.grid_size - self.mines_count}"
            )
            embed = create_embed("Мины | Взрыв", desc, self.ctx)
            embed.color = 0xFF0000
        else:
            winnings = int(self.amount * self.multiplier)
            user = await get_user(interaction.user.id, interaction.guild.id)
            new_balance = user["balance"] + winnings
            
            await update_user(interaction.user.id, interaction.guild.id, {"balance": new_balance})
            
            desc = (
                f"> **✅ ВЫ ЗАБРАЛИ!**\n"
                f"> _ _\n"
                f"> **🧊 Множитель:** x{self.multiplier:.2f}\n"
                f"> **💰 Выигрыш:** +{winnings:,} Кан\n"
                f"> **📊 Открыто:** {len(self.opened)}/{self.grid_size - self.mines_count}\n"
                f"> _ _\n"
                f"> **💴 Новый баланс:** {new_balance:,} Кан"
            )
            embed = create_embed("Мины | Успех", desc, self.ctx)
            embed.color = 0x00FF00
        
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

@bot.command(name="mines")
async def mines(ctx: commands.Context, amount: int, mines: int = 5):
    """Найдите алмазы, избегая мин! (5x5 поле)"""
    if not await check_command_cooldown(ctx, "mines"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    if amount < MIN_BET:
        await ctx.send(f"❌ Минимальная ставка: {MIN_BET:,} Кан!")
        return
    
    if mines < 3 or mines > 20:
        await ctx.send("❌ Количество мин должно быть от 3 до 20!")
        return
    
    if user["balance"] < amount:
        desc = f"> **❄️ Недостаточно средств!**\n> Ваш баланс: {user['balance']:,} Кан"
        embed = create_embed("Мины", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Снимаем ставку
    await update_user(ctx.author.id, ctx.guild.id, {"balance": user["balance"] - amount})
    await update_quest_progress(ctx.author.id, ctx.guild.id, "daily_gambler")
    
    desc = (
        f"> **❄️ ИГРА НАЧАЛАСЬ!**\n"
        f"> _ _\n"
        f"> **💣 Мин на поле:** {mines}\n"
        f"> **💎 Безопасных клеток:** {25 - mines}\n"
        f"> _ _\n"
        f"> *Открывайте клетки, избегая мин!*"
    )
    embed = create_embed("Мины", desc, ctx)
    view = MinesView(ctx, amount, mines)
    
    await ctx.send(embed=embed, view=view)

# 4. КОЛЕСО ФОРТУНЫ (WHEEL)
# Шансы изменены (сумма = 100)
WHEEL_SEGMENTS = {
    "x0": {"multiplier": 0, "chance": 31, "emoji": "💀", "color": "Черный"},      # Было 32
    "x0.5": {"multiplier": 0.5, "chance": 22.5, "emoji": "🔴", "color": "Красный"}, # Было 23.5
    "x1": {"multiplier": 1, "chance": 18.5, "emoji": "⚪", "color": "Белый"},     # Было 19
    "x2": {"multiplier": 2, "chance": 17.5, "emoji": "🔵", "color": "Синий"},     # Было 16.5
    "x3": {"multiplier": 3, "chance": 6.8, "emoji": "🟢", "color": "Зеленый"},   # Было 6.2
    "x5": {"multiplier": 5, "chance": 2.2, "emoji": "🟡", "color": "Желтый"},      # Было 1.7
    "x10": {"multiplier": 10, "chance": 1.2, "emoji": "🟣", "color": "Фиолетовый"}, # Было 0.9
    "x50": {"multiplier": 50, "chance": 0.3, "emoji": "🌟", "color": "Золотой"},
    "x100": {"multiplier": 100, "chance": 0.09, "emoji": "<:shinigami:1434615065243291708>", "color": "Синий"},
    "x150": {"multiplier": 150, "chance": 0.02, "emoji": "<:hollow:1434615019240161424>", "color": "Зеленый"}      # Было 0.2
}
# Проверка суммы: 31 + 22.5 + 18.5 + 17.5 + 6.8 + 2.2 + 1.2 + 0.3 = 100.0%

@bot.command(name="wheel")
async def wheel(ctx: commands.Context, amount: int):
    """Крутите колесо фортуны!"""
    if not await check_command_cooldown(ctx, "wheel"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    if amount < MIN_BET:
        await ctx.send(f"❌ Минимальная ставка: {MIN_BET:,} Кан!")
        return
    
    if user["balance"] < amount:
        desc = f"> **❄️ Недостаточно средств!**\n> Ваш баланс: {user['balance']:,} Кан"
        embed = create_embed("Колесо Фортуны", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Снимаем ставку
    await update_user(ctx.author.id, ctx.guild.id, {"balance": user["balance"] - amount})
    await update_quest_progress(ctx.author.id, ctx.guild.id, "daily_gambler")
    
    # "Крутим" колесо
    desc = (
        f"> **❄️ КОЛЕСО КРУТИТСЯ...**\n"
        f"> _ _\n"
        f"> 🎡 🎡 🎡\n"
        f"> _ _\n"
        f"> *Ожидайте результат...*"
    )
    embed = create_embed("Колесо Фортуны", desc, ctx)
    message = await ctx.send(embed=embed)
    
    await asyncio.sleep(3)
    
    # Выбираем сегмент
    roll = random.randint(1, 100)
    cumulative = 0
    result = "x1"
    
    for segment_id, segment_data in WHEEL_SEGMENTS.items():
        cumulative += segment_data["chance"]
        if roll <= cumulative:
            result = segment_id
            break
    
    segment = WHEEL_SEGMENTS[result]
    winnings = int(amount * segment["multiplier"])
    profit = winnings - amount
    
    new_balance = user["balance"] - amount + winnings # Баланс уже был уменьшен, так что просто прибавляем выигрыш
    await update_user(ctx.author.id, ctx.guild.id, {"balance": new_balance})
    
    if profit > 0:
        result_text = f"Вы выиграли **+{profit:,} Кан**"
        color = 0x00FF00
    elif profit == 0:
        result_text = "Возврат ставки"
        color = 0xFFFF00
    else:
        # profit будет отрицательным, например -100 (если amount 100 и x0)
        # но мы уже вычли amount, так что result_text должен быть другим
        if segment["multiplier"] == 0:
             result_text = f"Вы проиграли {amount:,} Кан"
        else:
             result_text = f"Вы потеряли **{abs(profit):,} Кан**"
        color = 0xFF0000
    
    # Корректировка логики отображения
    if segment["multiplier"] > 1:
        result_text = f"Вы выиграли **+{profit:,} Кан**"
        color = 0x00FF00
    elif segment["multiplier"] == 1:
        result_text = "Возврат ставки"
        color = 0xFFFF00
    elif segment["multiplier"] == 0.5:
        result_text = f"Вы потеряли **{abs(profit):,} Кан**" # abs(profit) = 0.5 * amount
        color = 0xFF0000
    else: # x0
        result_text = f"Вы проиграли {amount:,} Кан"
        color = 0xFF0000

    desc = (
        f"> **❄️ КОЛЕСО ОСТАНОВИЛОСЬ!**\n"
        f"> _ _\n"
        f"> {segment['emoji']} **{segment['color']}** (x{segment['multiplier']})\n"
        f"> _ _\n"
        f"> **🧊 Итог:**\n"
        f"> {result_text}\n"
        f"> _ _\n"
        f"> **💴 Новый баланс:** {new_balance:,} Кан"
    )
    embed = create_embed("Колесо Фортуны", desc, ctx)
    embed.color = color
    
    await message.edit(embed=embed)
    

# 5. РЕФЕРАЛЬНАЯ СИСТЕМА
@bot.command(name="referral")
async def referral(ctx: commands.Context, member: Optional[disnake.Member] = None):
    """Пригласить друга и получить бонус (или проверить свой код)"""
    if not await check_command_cooldown(ctx, "referral"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    # Если member не указан, показываем реферальный код
    if not member:
        referral_code = f"REF-{ctx.author.id}"
        referred_count = user.get("referred_count", 0)
        referral_bonus = referred_count * 50000  # 50000 за каждого приглашенного
        desc = (
            f"> **❄️ Ваш реферальный код:**\n"
            f"> `{referral_code}`\n"
            f"> _ _\n"
            f"> **📊 Статистика:**\n"
            f"> Приглашено: {referred_count} человек\n"
            f"> Заработано: {referral_bonus:,} Кан\n"
            f"> _ _\n"
            f"> **💡 Как использовать:**\n"
            f"> Попросите друга написать:\n"
            f"> `!referral @{ctx.author.name}`\n"
            f"> _ _\n"
            f"> Вы оба получите по 50,000 Кан!"
        )
        embed = create_embed("Реферальная Программа", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Проверки
    if member.id == ctx.author.id:
        await ctx.send("❌ Нельзя пригласить самого себя!")
        return
    
    if member.bot:
        await ctx.send("❌ Нельзя пригласить бота!")
        return
    
    referred_user = await get_user(member.id, ctx.guild.id)
    
    # Проверяем, был ли уже приглашен
    if referred_user.get("referred_by"):
        desc = f"> **❌ Ошибка!**\n> {member.display_name} уже был кем-то приглашен!"
        embed = create_embed("Реферальная Программа", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Проверяем, достаточно ли у приглашенного опыта (защита от твинков)
    if referred_user["balance"] + referred_user.get("bank", 0) < 5000:
        desc = f"> **❌ Ошибка!**\n> {member.display_name} должен иметь минимум 5,000 Кан (всего), чтобы быть приглашенным!"
        embed = create_embed("Реферальная Программа", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Выдаем бонусы
    referrer_bonus = 50000
    referred_bonus = 50000
    new_referrer_balance = user["balance"] + referrer_bonus
    new_referred_balance = referred_user["balance"] + referred_bonus
    referred_count = user.get("referred_count", 0) + 1
    
    await update_user(ctx.author.id, ctx.guild.id, {
        "balance": new_referrer_balance,
        "referred_count": referred_count
    })
    
    await update_user(member.id, ctx.guild.id, {
        "balance": new_referred_balance,
        "referred_by": ctx.author.id
    })
    
    desc = (
        f"> **✅ Реферал успешно активирован!**\n"
        f"> _ _\n"
        f"> {ctx.author.mention} пригласил {member.mention}!\n"
        f"> _ _\n"
        f"> **🎁 Награды:**\n"
        f"> {ctx.author.display_name}: +{referrer_bonus:,} Кан\n"
        f"> {member.display_name}: +{referred_bonus:,} Кан\n"
        f"> _ _\n"
        f"> **📊 Всего приглашено:** {referred_count}"
    )
    embed = create_embed("Реферальная Программа", desc, ctx)
    await ctx.send(embed=embed)
@bot.command(name="weekly")
async def weekly(ctx: commands.Context):
    if not await check_command_cooldown(ctx, "weekly"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    now = datetime.utcnow()
    
    if user.get("weekly_cooldown"):
        cooldown_time = user["weekly_cooldown"]
        if now < cooldown_time:
            remaining = cooldown_time - now
            
            # --- (ВОТ ИСПРАВЛЕНИЕ) ---
            days = int(remaining.total_seconds() // 86400)
            hours = int((remaining.total_seconds() % 86400) // 3600)
            desc = f"> **❄️ Кулдаун активен!**\n> Осталось: {days}д {hours}ч"
            embed = create_embed("Недельная Награда", desc, ctx)
            # --- (КОНЕЦ ИСПРАВЛЕНИЯ) ---
            
            await ctx.send(embed=embed)
            return
    
    reward = 7000
    new_balance = user["balance"] + reward
    new_cooldown = now + timedelta(days=7)
    
    await update_user(ctx.author.id, ctx.guild.id, {
        "balance": new_balance,
        "weekly_cooldown": new_cooldown
    })
    
    desc = (
        f"> **❄️ Недельная награда получена!**\n"
        f"> +{reward:,} Кан 💴\n"
        f"> _ _\n"
        f"> **🧊 Новый баланс:**\n"
        f"> {new_balance:,} Кан"
    )
    embed = create_embed("Недельная Награда", desc, ctx)
    await ctx.send(embed=embed)

# ==================== МАГАЗИН (НА РОЛЯХ) ====================

@bot.command(name="shop")
async def shop(ctx: commands.Context):
    if not await check_command_cooldown(ctx, "shop"):
        return
    
    desc = "> **❄️ Доступные улучшения (Фермы):**\n> _ _\n"
    
    for item_id, item in SHOP_ITEMS.items():
        # Проверяем, есть ли у юзера эта роль (чтобы пометить "КУПЛЕНО")
        role = ctx.guild.get_role(item["role_id"]) if item["role_id"] else None
        status = ""
        if role and role in ctx.author.roles:
            status = " ✅ **(Куплено)**"
            
        desc += f"> {item['emoji']} **{item['name']}**{status}\n"
        desc += f"> {item['description']}\n"
        desc += f"> Цена: **{item['price']:,} Кан**\n"
        desc += f"> ID: `{item_id}`\n>\n"
    
    embed = create_embed("Магазин Bleach World", desc, ctx)
    await ctx.send(embed=embed)

@bot.command(name="buy")
async def buy(ctx: commands.Context, item_id: str):
    if not await check_command_cooldown(ctx, "buy"):
        return
    
    item_id = item_id.lower()
    if item_id not in SHOP_ITEMS:
        await ctx.send(f"❌ Предмет `{item_id}` не найден! Используйте `!shop` для просмотра.")
        return
    
    item = SHOP_ITEMS[item_id]
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    # Проверка 1: Цена
    if user["balance"] < item["price"]:
        desc = f"> **❄️ Недостаточно средств!**\n> Ваш баланс: {user['balance']:,} Кан\n> Требуется: {item['price']:,} Кан"
        embed = create_embed("Покупка", desc, ctx)
        await ctx.send(embed=embed)
        return
        
    # Проверка 2: Наличие роли
    role_id = item.get("role_id")
    if not role_id:
        await ctx.send(f"❌ Ошибка: у предмета `{item_id}` не настроена роль. Свяжитесь с админом.")
        return
        
    role = ctx.guild.get_role(role_id)
    if not role:
        await ctx.send(f"❌ Ошибка: роль для `{item_id}` не найдена на сервере. Свяжитесь с админом.")
        return
        
    if role in ctx.author.roles:
        desc = f"> **❄️ У вас уже есть это улучшение!**\n> {item['emoji']} **{item['name']}**"
        embed = create_embed("Покупка", desc, ctx)
        await ctx.send(embed=embed)
        return

    # Покупка
    new_balance = user["balance"] - item["price"]
    
    try:
        # Выдаем роль
        await ctx.author.add_roles(role, reason=f"Покупка в !shop ({item_id})")
        
        # Снимаем деньги
        await update_user(ctx.author.id, ctx.guild.id, {"balance": new_balance})
        
        desc = f"> **❄️ Покупка успешна!**\n> _ _\n> {item['emoji']} **{item['name']}**\n> {item['description']}\n> _ _\n> **🧊 Потрачено:**\n> {item['price']:,} Кан\n> _ _\n> **💴 Новый баланс:**\n> {new_balance:,} Кан"
        embed = create_embed("Покупка", desc, ctx)
        await ctx.send(embed=embed)
        
    except disnake.Forbidden:
        await ctx.send("❌ **Ошибка прав:** У меня нет прав выдать эту роль. Пожалуйста, убедитесь, что моя роль (Бот) находится ВЫШЕ роли фермы в списке ролей.")
    except Exception as e:
        await ctx.send(f"❌ Произошла неизвестная ошибка: {e}")

# (ЗАМЕНИТЬ СТАРУЮ КОМАНДУ !inventory, ~строка 1007)

@bot.command(name="inventory", aliases=["inv"])
async def inventory(ctx: commands.Context):
    if not await check_command_cooldown(ctx, "inventory"):
        return
    
    member = ctx.author
    user_data = await get_user(member.id, ctx.guild.id)
    
    total_income = 0
    owned_farms_desc = []
    
    # 1. Считаем ФЕРМЫ (Роли)
    for item_id, item in SHOP_ITEMS.items():
        role_id = item.get("role_id")
        if role_id and any(role.id == role_id for role in member.roles):
            total_income += item["income"]
            owned_farms_desc.append(f"> {item['emoji']} **{item['name']}** (+{item['income']:,} Кан/час)")

    if not owned_farms_desc:
        owned_farms_desc.append("> *У вас нет ферм (ролей).*")
        
    # 2. Считаем ПРЕДМЕТЫ (Инвентарь)
    inventory_items = user_data.get("inventory", [])
    item_counts = Counter(inventory_items) # Считаем, сколько у нас купонов
    owned_items_desc = []
    
    if item_counts:
        for item_id, count in item_counts.items():
            item_data = CONSUMABLE_ITEMS.get(item_id)
            if item_data:
                owned_items_desc.append(f"> {item_data['emoji']} **{item_data['name']}** (x{count})")
            else:
                owned_items_desc.append(f"> 📦 **{item_id}** (x{count})")
    
    if not owned_items_desc:
        owned_items_desc.append("> *У вас нет предметов.*")
        
    # 3. Собираем Эмбед
    
    desc = "> **❄️ Ваши владения (Фермы):**\n> _ _\n"
    desc += "\n> \n".join(owned_farms_desc)
    desc += f"\n> _ _\n> **🧊 Общий пассивный доход:**\n> {total_income:,} Кан/час"
    
    embed = create_embed("Инвентарь", desc, ctx)
    
    # Добавляем предметы вторым полем
    embed.add_field(
        name="🎒 Ваши Предметы (Инвентарь):",
        value="\n> \n".join(owned_items_desc),
        inline=False
    )
    
    await ctx.send(embed=embed)# (ЗАМЕНИТЬ СТАРУЮ КОМАНДУ !inventory, ~строка 1007)

# ==================== АДМИНСКИЕ КОМАНДЫ (НА РОЛЯХ) ====================

@bot.command(name="givemoney", aliases=["gmoney"])
@commands.has_permissions(administrator=True)
async def givemoney(ctx: commands.Context, member: disnake.Member, amount: int):
    if amount <= 0:
        embed = create_embed("Ошибка", "> **❌ Ошибка:**\n> Сумма должна быть положительной!", ctx)
        await ctx.send(embed=embed)
        return
    
    user = await get_user(member.id, ctx.guild.id)
    new_balance = user["balance"] + amount
    
    await update_user(member.id, ctx.guild.id, {"balance": new_balance})
    
    desc = (
        f"> **🧊 Успех:**\n"
        f"> Вы выдали {amount:,} Кан пользователю {member.display_name}\n"
        f"> _ _\n"
        f"> **❄️ Новый баланс:**\n"
        f"> {new_balance:,} Кан 💴"
    )
    embed = create_embed("Выдача Средств", desc, ctx)
    await ctx.send(embed=embed)

@bot.command(name="takemoney", aliases=["removemoney"])
@commands.has_permissions(administrator=True)
async def takemoney(ctx: commands.Context, member: disnake.Member, amount: int):
    if amount <= 0:
        embed = create_embed("Ошибка", "> **❌ Ошибка:**\n> Сумма должна быть больше нуля.", ctx)
        await ctx.send(embed=embed)
        return

    try:
        user = await get_user(member.id, ctx.guild.id)
        current_balance = user.get("balance", 0)
        
        # (ГЛАВНОЕ ИЗМЕНЕНИЕ: НЕ используем max(0, ...), чтобы уйти в минус)
        new_balance = current_balance - amount
        
        # (Используем update_user из твоего кода)
        await update_user(member.id, ctx.guild.id, {"balance": new_balance})
        
        desc = (
            f"> **🧊 Успех:**\n"
            f"> Вы забрали {amount:,} 💴 у пользователя {member.mention}\n"
            f"> _ _\n"
            f"> **Новый баланс:** {new_balance:,} 💴"
        )
        embed = create_embed("Изъятие Средств", desc, ctx)
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Ошибка при обновлении баланса: {e}")

@bot.command(name="givefarm")
@commands.has_permissions(administrator=True)
async def givefarm(ctx: commands.Context, member: disnake.Member, item_id: str):
    item_id = item_id.lower()
    if item_id not in SHOP_ITEMS:
        embed = create_embed("Ошибка", f"> **❌ Ошибка:**\n> Улучшение `{item_id}` не найдено!", ctx)
        await ctx.send(embed=embed)
        return
    
    item = SHOP_ITEMS[item_id]
    role_id = item.get("role_id")
    
    if not role_id:
        await ctx.send(f"❌ Ошибка: у предмета `{item_id}` не настроена роль.")
        return
    
    role = ctx.guild.get_role(role_id)
    if not role:
        await ctx.send(f"❌ Ошибка: роль для `{item_id}` не найдена на сервере.")
        return
        
    try:
        await member.add_roles(role, reason=f"Выдано админом {ctx.author}")
        desc = (
            f"> **🧊 Успех:**\n"
            f"> Вы выдали улучшение пользователю {member.display_name}\n"
            f"> _ _\n"
            f"> {item['emoji']} **{item['name']}**"
        )
        embed = create_embed("Выдача Улучшения", desc, ctx)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Ошибка при выдаче роли: {e}")


@bot.command(name="takefarm")
@commands.has_permissions(administrator=True)
async def takefarm(ctx: commands.Context, member: disnake.Member, item_id: str):
    item_id = item_id.lower()
    if item_id not in SHOP_ITEMS:
        embed = create_embed("Ошибка", f"> **❌ Ошибка:**\n> Улучшение `{item_id}` не найдено!", ctx)
        await ctx.send(embed=embed)
        return
    
    item = SHOP_ITEMS[item_id]
    role_id = item.get("role_id")
    
    if not role_id:
        await ctx.send(f"❌ Ошибка: у предмета `{item_id}` не настроена роль.")
        return
    
    role = ctx.guild.get_role(role_id)
    if not role:
        await ctx.send(f"❌ Ошибка: роль для `{item_id}` не найдена на сервере.")
        return
        
    if role not in member.roles:
        embed = create_embed("Ошибка", f"> **❌ Ошибка:**\n> У пользователя {member.display_name} нет этой роли.", ctx)
        await ctx.send(embed=embed)
        return
        
    try:
        await member.remove_roles(role, reason=f"Забрано админом {ctx.author}")
        desc = (
            f"> **🧊 Успех:**\n"
            f"> Вы забрали улучшение у пользователя {member.display_name}\n"
            f"> _ _\n"
            f"> {item['emoji']} **{item['name']}**"
        )
        embed = create_embed("Изъятие Улучшения", desc, ctx)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Ошибка при снятии роли: {e}")
        
# ==================== СИСТЕМА КЛАНОВ ====================

@bot.group(name="clan", invoke_without_command=True)
async def clan(ctx: commands.Context):
    """Главная команда кланов"""
    desc = (
        "> **❄️ КОМАНДЫ КЛАНОВ**\n"
        "> _ _\n"
        "> **🏛️ ОСНОВНЫЕ**\n"
        "> `!clan create <тэг> <название>` - Создать клан\n"
        "> `!clan info [тэг]` - Информация о клане\n"
        "> `!clan list [страница]` - Список кланов\n"
        "> `!clan leave` - Покинуть клан\n"
        "> _ _\n"
        "> **👥 УПРАВЛЕНИЕ (Admin/Owner)**\n"
        "> `!clan invite @user` - Пригласить в клан\n"
        "> `!clan kick @user` - Исключить из клана\n"
        "> `!clan promote @user` - Повысить до админа\n"
        "> `!clan demote @user` - Понизить с админа\n"
        "> `!clan description <текст>` - Изменить описание\n"
        "> `!clan delete` - Удалить клан (Owner)\n"
        "> _ _\n"
        "> **💰 ЭКОНОМИКА**\n"
        "> `!clan deposit <сумма>` - Внести в казну\n"
        "> `!clan withdraw <сумма>` - Снять из казны (Owner)\n"
        "> `!clan shop` - Магазин апгрейдов\n"
        "> `!clan buy <id>` - Купить апгрейд\n"
    )
    embed = create_embed("Система Кланов", desc, ctx)
    await ctx.send(embed=embed)


# ==================== ИСПРАВЛЕННАЯ КОМАНДА !collect ====================
# (ЗАМЕНИ СТАРУЮ КОМАНДУ !collect, ~строка 620)
# (Ей БОЛЬШЕ НЕ НУЖЕН ROLE_INCOMES)

@bot.command(name="collect")
async def collect(ctx: commands.Context):
    if not await check_command_cooldown(ctx, "collect"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    now = datetime.utcnow()

    # 1. Проверяем 3-часовой кулдаун
    cooldown_time = user.get("collect_cooldown")
    if cooldown_time and now < cooldown_time:
        remaining = cooldown_time - now
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)
        desc = f"> **❄️ Кулдаун активен!**\n> Вы уже собрали доход.\n> Осталось: {hours}ч {minutes}м"
        embed = create_embed("Сбор Дохода", desc, ctx)
        await ctx.send(embed=embed)
        return

    # === ИЗМЕНЕНО: Считаем доход по РОЛЯМ из SHOP_ITEMS (как в !inventory) ===
    total_income_per_hour = 0
    member = ctx.author # (ctx.author - это участник, у него есть роли)
    
    for item_id, item in SHOP_ITEMS.items():
        role_id = item.get("role_id")
        if role_id is None:
            continue
            
        # Проверяем, есть ли у участника эта роль
        if any(role.id == role_id for role in member.roles):
            total_income_per_hour += item["income"]
    # === КОНЕЦ ИЗМЕНЕНИЙ ===
    
    # 3. Проверка, есть ли доход (роли)
    if total_income_per_hour == 0:
        desc = "> **❌ У вас нет доходных ролей!**\n> Вы не получаете пассивный доход."
        embed = create_embed("Сбор Дохода", desc, ctx)
        await ctx.send(embed=embed)
        return

    # 4. Начисляем награду за 3 часа
    reward = total_income_per_hour * 3
    new_balance = user["balance"] + reward
    new_cooldown = now + timedelta(hours=3)
    
    # (Используем $set, чтобы соответствовать новой функции update_user)
    await update_user(ctx.author.id, ctx.guild.id, {
        "$set": {
            "balance": new_balance,
            "collect_cooldown": new_cooldown
        }
    })
    
    # 5. Отправляем Успех
    desc = f"""
> **✅ Доход собран!**
> _ _
> **🧊 Ваш доход в час (от ролей):**
> {total_income_per_hour:,} Кан/час
> _ _
> **❄️ Собрано за 3 часа:**
> +{reward:,} Кан 💴
> _ _
> **💴 Новый баланс:**
> {new_balance:,} Кан
> _ _
> _Следующий сбор доступен через 3 часа._
"""
    embed = create_embed("Сбор Дохода", desc, ctx)
    await ctx.send(embed=embed)
    


@clan.command(name="create")
async def clan_create(ctx: commands.Context, tag: str, *, name: str):
    """Создание клана"""
    if not await check_command_cooldown(ctx, "clan_create"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    # Проверка: юзер не в клане
    if user.get("clan_id"):
        desc = "> **❌ Ошибка:**\n> Вы уже состоите в клане!\n> Используйте `!clan leave` чтобы выйти."
        embed = create_embed("Создание Клана", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Проверка длины тэга
    if len(tag) < 3 or len(tag) > 5:
        desc = "> **❌ Ошибка:**\n> Тэг должен быть от 3 до 5 символов!"
        embed = create_embed("Создание Клана", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    tag = tag.upper()
    
    # Проверка уникальности тэга
    existing_tag = await clans_collection.find_one({"guildId": ctx.guild.id, "tag": tag})
    if existing_tag:
        desc = f"> **❌ Ошибка:**\n> Тэг `{tag}` уже занят!"
        embed = create_embed("Создание Клана", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Проверка уникальности названия
    existing_name = await clans_collection.find_one({"guildId": ctx.guild.id, "name": name})
    if existing_name:
        desc = f"> **❌ Ошибка:**\n> Название `{name}` уже занято!"
        embed = create_embed("Создание Клана", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Создаем клан
    clan_data = {
        "guildId": ctx.guild.id,
        "name": name,
        "tag": tag,
        "description": "Новый клан в мире Bleach",
        "owner_id": ctx.author.id,
        "bank": 0,
        "upgrades": []
    }
    
    result = await clans_collection.insert_one(clan_data)
    clan_id = result.inserted_id
    
    # Обновляем юзера
    await update_user(ctx.author.id, ctx.guild.id, {
        "clan_id": clan_id,
        "clan_rank": "owner"
    })
    
    # Меняем ник
    await set_clan_nickname(ctx.author, tag)
    
    desc = (
        f"> **✅ Клан создан!**\n"
        f"> _ _\n"
        f"> **❄️ Название:**\n"
        f"> {name}\n"
        f"> _ _\n"
        f"> **🧊 Тэг:**\n"
        f"> [{tag}]\n"
        f"> _ _\n"
        f"> **👑 Владелец:**\n"
        f"> {ctx.author.display_name}"
    )
    embed = create_embed("Создание Клана", desc, ctx)
    await ctx.send(embed=embed)




@clan.command(name="invite")
async def clan_invite(ctx: commands.Context, member: disnake.Member):
    """Пригласить участника в клан"""
    if not await check_command_cooldown(ctx, "clan_invite"):
        return
        
    inviter_user = await get_user(ctx.author.id, ctx.guild.id)
    
    # 1. Проверка прав (кто приглашает)
    if not inviter_user.get("clan_id") or inviter_user.get("clan_rank") not in ["owner", "admin"]:
        desc = "> **❌ Ошибка:**\n> Только Владелец или Админ клана могут приглашать!"
        embed = create_embed("Приглашение", desc, ctx)
        await ctx.send(embed=embed)
        return
        
    clan = await get_clan(inviter_user["clan_id"])
    if not clan:
        # (На всякий случай, если клан удален, а юзер нет)
        await update_user(ctx.author.id, ctx.guild.id, {"clan_id": None, "clan_rank": None})
        return

    # 2. Проверка (кого приглашают)
    if member.id == ctx.author.id:
        await ctx.send("❌ Нельзя пригласить самого себя!")
        return
    if member.bot:
        await ctx.send("❌ Нельзя пригласить бота!")
        return
        
    invited_user = await get_user(member.id, ctx.guild.id)
    if invited_user.get("clan_id"):
        desc = f"> **❌ Ошибка:**\n> Участник **{member.display_name}** уже состоит в другом клане!"
        embed = create_embed("Приглашение", desc, ctx)
        await ctx.send(embed=embed)
        return
        
    # --- (ВОТ ИСПРАВЛЕНИЕ) ---
    # 3. Отправляем Эмбед и Кнопки В КАНАЛ (а не в ЛС)
    
    desc = f"> **❄️ Новое приглашение!**\n> \n> {ctx.author.mention} (Админ/Владелец) приглашает {member.mention} вступить в клан:\n> **{clan['name']} [{clan['tag']}]**\n> \n> *У {member.display_name} есть 2 минуты, чтобы принять.*"
    embed = create_embed("Приглашение в Клан", desc, ctx)
    
    # Создаем View (кнопки)
    view = ClanInviteView(inviter=ctx.author, invited=member, clan=clan)
    
    # Отправляем сообщение
    message = await ctx.send(embed=embed, view=view)
    view.message = message # Сохраняем сообщение для on_timeout@clan.command(name="invite")
async def clan_invite(ctx: commands.Context, member: disnake.Member):
    """Пригласить участника в клан"""
    if not await check_command_cooldown(ctx, "clan_invite"):
        return
        
    inviter_user = await get_user(ctx.author.id, ctx.guild.id)
    
    # 1. Проверка прав (кто приглашает)
    if not inviter_user.get("clan_id") or inviter_user.get("clan_rank") not in ["owner", "admin"]:
        desc = "> **❌ Ошибка:**\n> Только Владелец или Админ клана могут приглашать!"
        embed = create_embed("Приглашение", desc, ctx)
        await ctx.send(embed=embed)
        return
        
    clan = await get_clan(inviter_user["clan_id"])
    if not clan:
        # (На всякий случай, если клан удален, а юзер нет)
        await update_user(ctx.author.id, ctx.guild.id, {"clan_id": None, "clan_rank": None})
        return

    # 2. Проверка (кого приглашают)
    if member.id == ctx.author.id:
        await ctx.send("❌ Нельзя пригласить самого себя!")
        return
    if member.bot:
        await ctx.send("❌ Нельзя пригласить бота!")
        return
        
    invited_user = await get_user(member.id, ctx.guild.id)
    if invited_user.get("clan_id"):
        desc = f"> **❌ Ошибка:**\n> Участник **{member.display_name}** уже состоит в другом клане!"
        embed = create_embed("Приглашение", desc, ctx)
        await ctx.send(embed=embed)
        return
        
    # --- (ВОТ ИСПРАВЛЕНИЕ) ---
    # 3. Отправляем Эмбед и Кнопки В КАНАЛ (а не в ЛС)
    
    desc = f"> **❄️ Новое приглашение!**\n> \n> {ctx.author.mention} (Админ/Владелец) приглашает {member.mention} вступить в клан:\n> **{clan['name']} [{clan['tag']}]**\n> \n> *У {member.display_name} есть 2 минуты, чтобы принять.*"
    embed = create_embed("Приглашение в Клан", desc, ctx)
    
    # Создаем View (кнопки)
    view = ClanInviteView(inviter=ctx.author, invited=member, clan=clan)
    
    # Отправляем сообщение
    message = await ctx.send(embed=embed, view=view)
    view.message = message # Сохраняем сообщение для on_timeout

@clan.command(name="leave")
async def clan_leave(ctx: commands.Context):
    """Покинуть клан"""
    if not await check_command_cooldown(ctx, "clan_leave"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    if not user.get("clan_id"):
        desc = "> **❌ Ошибка:**\n> Вы не состоите в клане!"
        embed = create_embed("Выход из Клана", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    if user.get("clan_rank") == "owner":
        desc = "> **❌ Ошибка:**\n> Владелец не может покинуть клан!\n> Используйте `!clan delete` для удаления клана."
        embed = create_embed("Выход из Клана", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    clan = await get_clan(user["clan_id"])
    clan_name = clan["name"] if clan else "Неизвестный клан"
    clan_tag = clan["tag"] if clan else "???"
    
    # Убираем из клана
    await update_user(ctx.author.id, ctx.guild.id, {
        "clan_id": None,
        "clan_rank": None
    })
    
    # Убираем тэг из ника
    await remove_clan_nickname(ctx.author)
    
    desc = f"> **✅ Вы покинули клан**\n> {clan_name} [{clan_tag}]"
    embed = create_embed("Выход из Клана", desc, ctx)
    await ctx.send(embed=embed)

@clan.command(name="kick")
async def clan_kick(ctx: commands.Context, member: disnake.Member):
    """Исключить участника из клана"""
    if not await check_command_cooldown(ctx, "clan_kick"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    if not user.get("clan_id") or user.get("clan_rank") not in ["admin", "owner"]:
        desc = "> **❌ Ошибка:**\n> Вы должны быть админом или владельцем клана!"
        embed = create_embed("Исключение из Клана", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    target_user = await get_user(member.id, ctx.guild.id)
    
    if not target_user.get("clan_id") or target_user["clan_id"] != user["clan_id"]:
        desc = f"> **❌ Ошибка:**\n> {member.display_name} не состоит в вашем клане!"
        embed = create_embed("Исключение из Клана", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    if target_user.get("clan_rank") == "owner":
        desc = "> **❌ Ошибка:**\n> Нельзя исключить владельца клана!"
        embed = create_embed("Исключение из Клана", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Исключаем
    await update_user(member.id, ctx.guild.id, {
        "clan_id": None,
        "clan_rank": None
    })
    
    await remove_clan_nickname(member)
    
    desc = f"> **✅ Участник исключен**\n> {member.display_name}"
    embed = create_embed("Исключение из Клана", desc, ctx)
    await ctx.send(embed=embed)
@clan.command(name="delete")
async def clan_delete(ctx: commands.Context):
    """Удалить клан"""
    if not await check_command_cooldown(ctx, "clan_delete"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    if not user.get("clan_id") or user.get("clan_rank") != "owner":
        desc = "> **❌ Ошибка:**\n> Только владелец может удалить клан!"
        embed = create_embed("Удаление Клана", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    clan = await get_clan(user["clan_id"])
    if not clan:
        desc = "> **❌ Ошибка:**\n> Клан не найден!"
        embed = create_embed("Удаление Клана", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Получаем всех участников
    members = await get_clan_members(clan["_id"])
    
    # Убираем тэги у всех
    for member_data in members:
        try:
            member_obj = await ctx.guild.fetch_member(member_data["userId"])
            await remove_clan_nickname(member_obj)
        except:
            pass # Игнорируем, если участник покинул сервер
        
        # --- (ИСПРАВЛЕНИЕ) ---
        # Эта строка была сдвинута.
        # Она должна быть на этом уровне отступа (внутри 'for', но после 'try/except')
        await update_user(member_data["userId"], ctx.guild.id, {
            "clan_id": None,
            "clan_rank": None
        })
    
    # Удаляем клан
    await clans_collection.delete_one({"_id": clan["_id"]})
    
    desc = f"> **✅ Клан удален**\n> {clan['name']} [{clan['tag']}]\n> _ _\n> **🧊 Всего участников:**\n> {len(members)}"
    embed = create_embed("Удаление Клана", desc, ctx)
    await ctx.send(embed=embed)

@clan.command(name="promote")
async def clan_promote(ctx: commands.Context, member: disnake.Member):
    """Повысить участника до админа"""
    if not await check_command_cooldown(ctx, "clan_promote"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    if not user.get("clan_id") or user.get("clan_rank") != "owner":
        desc = "> **❌ Ошибка:**\n> Только владелец может повышать участников!"
        embed = create_embed("Повышение", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    target_user = await get_user(member.id, ctx.guild.id)
    
    if not target_user.get("clan_id") or target_user["clan_id"] != user["clan_id"]:
        desc = f"> **❌ Ошибка:**\n> {member.display_name} не состоит в вашем клане!"
        embed = create_embed("Повышение", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    if target_user.get("clan_rank") == "admin":
        desc = f"> **❌ Ошибка:**\n> {member.display_name} уже админ!"
        embed = create_embed("Повышение", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    if target_user.get("clan_rank") == "owner":
        desc = "> **❌ Ошибка:**\n> Нельзя повысить владельца!"
        embed = create_embed("Повышение", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    await update_user(member.id, ctx.guild.id, {"clan_rank": "admin"})
    
    desc = f"> **✅ Участник повышен до админа**\n> {member.display_name}"
    embed = create_embed("Повышение", desc, ctx)
    await ctx.send(embed=embed)

@clan.command(name="demote")
async def clan_demote(ctx: commands.Context, member: disnake.Member):
    """Понизить админа до участника"""
    if not await check_command_cooldown(ctx, "clan_demote"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    if not user.get("clan_id") or user.get("clan_rank") != "owner":
        desc = "> **❌ Ошибка:**\n> Только владелец может понижать участников!"
        embed = create_embed("Понижение", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    target_user = await get_user(member.id, ctx.guild.id)
    
    if not target_user.get("clan_id") or target_user["clan_id"] != user["clan_id"]:
        desc = f"> **❌ Ошибка:**\n> {member.display_name} не состоит в вашем клане!"
        embed = create_embed("Понижение", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    if target_user.get("clan_rank") != "admin":
        desc = f"> **❌ Ошибка:**\n> {member.display_name} не админ!"
        embed = create_embed("Понижение", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    await update_user(member.id, ctx.guild.id, {"clan_rank": "member"})
    
    desc = f"> **✅ Админ понижен до участника**\n> {member.display_name}"
    embed = create_embed("Понижение", desc, ctx)
    await ctx.send(embed=embed)

@clan.command(name="description")
async def clan_description(ctx: commands.Context, *, text: str):
    """Изменить описание клана"""
    if not await check_command_cooldown(ctx, "clan_description"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    if not user.get("clan_id") or user.get("clan_rank") not in ["admin", "owner"]:
        desc = "> **❌ Ошибка:**\n> Вы должны быть админом или владельцем клана!"
        embed = create_embed("Описание Клана", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    if len(text) > 200:
        desc = "> **❌ Ошибка:**\n> Описание не должно превышать 200 символов!"
        embed = create_embed("Описание Клана", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    await update_clan(user["clan_id"], {"description": text})
    
    desc = f"> **✅ Описание обновлено!**\n> _ _\n> {text}"
    embed = create_embed("Описание Клана", desc, ctx)
    await ctx.send(embed=embed)

@clan.command(name="info")
async def clan_info(ctx: commands.Context, clan_tag: Optional[str] = None):
    """Информация о клане"""
    if not await check_command_cooldown(ctx, "clan_info"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    # Если тэг не указан, показываем свой клан
    if not clan_tag:
        if not user.get("clan_id"):
            desc = "> **❌ Ошибка:**\n> Вы не состоите в клане!\n> Укажите тэг клана: `!clan info [ТЕГ]`"
            embed = create_embed("Информация о Клане", desc, ctx)
            await ctx.send(embed=embed)
            return
        clan = await get_clan(user["clan_id"])
    else:
        clan = await get_clan_by_tag(ctx.guild.id, clan_tag)
    
    if not clan:
        desc = "> **❌ Ошибка:**\n> Клан не найден!"
        embed = create_embed("Информация о Клане", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Получаем владельца
    try:
        owner = await ctx.guild.fetch_member(clan["owner_id"])
        owner_name = owner.display_name
    except:
        owner_name = f"User#{clan['owner_id']}"
    
    # Считаем админов
    admins = await users_collection.find({
        "clan_id": clan["_id"],
        "clan_rank": "admin"
    }).to_list(None)
    
    admin_names = []
    for admin_data in admins:
        try:
            admin_member = await ctx.guild.fetch_member(admin_data["userId"])
            admin_names.append(admin_member.display_name)
        except:
            admin_names.append(f"User#{admin_data['userId']}")
    
    admin_text = ", ".join(admin_names) if admin_names else "Нет"
    
    # Считаем участников
    member_count = await get_clan_member_count(clan["_id"])
    member_limit = calculate_member_limit(clan.get("upgrades", []))
    
    # Апгрейды
    upgrades_text = ""
    if clan.get("upgrades"):
        for upgrade_id in clan["upgrades"]:
            if upgrade_id in CLAN_UPGRADES:
                upgrade = CLAN_UPGRADES[upgrade_id]
                upgrades_text += f"> {upgrade['emoji']} {upgrade['name']}\n"
    else:
        upgrades_text = "> Нет апгрейдов\n"
    
    desc = (
        f"> **❄️ Название:**\n"
        f"> {clan['name']}\n"
        f"> _ _\n"
        f"> **🧊 Тэг:**\n"
        f"> [{clan['tag']}]\n"
        f"> _ _\n"
        f"> **👑 Владелец:**\n"
        f"> {owner_name}\n"
        f"> _ _\n"
        f"> **🛡️ Админы:**\n"
        f"> {admin_text}\n"
        f"> _ _\n"
        f"> **👥 Участники:**\n"
        f"> {member_count}/{member_limit}\n"
        f"> _ _\n"
        f"> **💰 Казна:**\n"
        f"> {clan.get('bank', 0):,} Кан\n"
        f"> _ _\n"
        f"> **📝 Описание:**\n"
        f"> {clan.get('description', 'Нет описания')}\n"
        f"> _ _\n"
        f"> **⭐ Апгрейды:**\n"
        f"{upgrades_text}"
    )
    embed = create_embed("Информация о Клане", desc, ctx)
    await ctx.send(embed=embed)

class ClanListView(disnake.ui.View):
    def __init__(self, ctx: commands.Context, pages: List[str]):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.pages = pages
        self.current_page = 0
        
    @disnake.ui.button(label="◀️", style=disnake.ButtonStyle.primary)
    async def previous_button(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return
        self.current_page = (self.current_page - 1) % len(self.pages)
        embed = create_embed(f"Список Кланов (Страница {self.current_page + 1}/{len(self.pages)})", 
                           self.pages[self.current_page], self.ctx)
        await interaction.response.edit_message(embed=embed)
    
    @disnake.ui.button(label="▶️", style=disnake.ButtonStyle.primary)
    async def next_button(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return
        self.current_page = (self.current_page + 1) % len(self.pages)
        embed = create_embed(f"Список Кланов (Страница {self.current_page + 1}/{len(self.pages)})", 
                           self.pages[self.current_page], self.ctx)
        await interaction.response.edit_message(embed=embed)

@clan.command(name="list")
async def clan_list(ctx: commands.Context, page: int = 1):
    """Список всех кланов"""
    clans = await clans_collection.find({"guildId": ctx.guild.id}).sort("bank", -1).to_list(None)
    
    if not clans:
        desc = "> **❄️ Нет кланов на сервере!**\n> Создайте первый: `!clan create <тэг> <название>`"
        embed = create_embed("Список Кланов", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    per_page = 10
    pages = []
    
    for i in range(0, len(clans), per_page):
        page_clans = clans[i:i+per_page]
        desc = ""
        
        for idx, clan_data in enumerate(page_clans, start=i+1):
            try:
                owner = await ctx.guild.fetch_member(clan_data["owner_id"])
                owner_name = owner.display_name
            except:
                owner_name = f"User#{clan_data['owner_id']}"
            
            member_count = await get_clan_member_count(clan_data["_id"])
            
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else "🏛️"
            
            desc += (
                f"> {medal} **#{idx}** {clan_data['name']} [{clan_data['tag']}]\n"
                f"> Владелец: {owner_name}\n"
                f"> Участников: {member_count}\n"
                f"> Казна: {clan_data.get('bank', 0):,} Кан\n"
                f"> _ _\n"
            )
        
        pages.append(desc)
    
    if page > len(pages):
        page = len(pages)
    if page < 1:
        page = 1
    
    view = ClanListView(ctx, pages)
    view.current_page = page - 1
    
    embed = create_embed(f"Список Кланов (Страница {page}/{len(pages)})", pages[page-1], ctx)
    await ctx.send(embed=embed, view=view)

class ClanDepositView(disnake.ui.View):
    def __init__(self, ctx: commands.Context, amount: int, user_data: dict, clan: dict):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.amount = amount
        self.user_data = user_data
        self.clan = clan
    
    @disnake.ui.button(label="Наличные", style=disnake.ButtonStyle.success)
    async def cash_button(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Это не ваша транзакция!", ephemeral=True)
            return
        
        if self.user_data["balance"] < self.amount:
            desc = f"> **❌ Недостаточно наличных!**\n> У вас: {self.user_data['balance']:,} Кан\n> Требуется: {self.amount:,} Кан"
            embed = create_embed("Внесение в Казну", desc, self.ctx)
            await interaction.response.edit_message(embed=embed, view=None)
            return
        
        # Снимаем с наличных
        new_balance = self.user_data["balance"] - self.amount
        await update_user(self.ctx.author.id, self.ctx.guild.id, {"balance": new_balance})
        
        # Добавляем в казну
        new_clan_bank = self.clan.get("bank", 0) + self.amount
        await update_clan(self.clan["_id"], {"bank": new_clan_bank})
        
        desc = (
            f"> **✅ Внесено в казну клана!**\n"
            f"> _ _\n"
            f"> **❄️ Сумма:**\n"
            f"> {self.amount:,} Кан\n"
            f"> _ _\n"
            f"> **🧊 Источник:**\n"
            f"> Наличные\n"
            f"> _ _\n"
            f"> **💰 Казна клана:**\n"
            f"> {new_clan_bank:,} Кан\n"
            f"> _ _\n"
            f"> **💴 Ваш баланс:**\n"
            f"> {new_balance:,} Кан"
        )
        embed = create_embed("Внесение в Казну", desc, self.ctx)
        await interaction.response.edit_message(embed=embed, view=None)
    
    @disnake.ui.button(label="Банк", style=disnake.ButtonStyle.primary)
    async def bank_button(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Это не ваша транзакция!", ephemeral=True)
            return
        
        user_bank = self.user_data.get("bank", 0)
        
        if user_bank < self.amount:
            desc = f"> **❌ Недостаточно средств в банке!**\n> В банке: {user_bank:,} Кан\n> Требуется: {self.amount:,} Кан"
            embed = create_embed("Внесение в Казну", desc, self.ctx)
            await interaction.response.edit_message(embed=embed, view=None)
            return
        
        # Снимаем с банка
        new_bank = user_bank - self.amount
        await update_user(self.ctx.author.id, self.ctx.guild.id, {"bank": new_bank})
        
        # Добавляем в казну
        new_clan_bank = self.clan.get("bank", 0) + self.amount
        await update_clan(self.clan["_id"], {"bank": new_clan_bank})
        
        desc = (
            f"> **✅ Внесено в казну клана!**\n"
            f"> _ _\n"
            f"> **❄️ Сумма:**\n"
            f"> {self.amount:,} Кан\n"
            f"> _ _\n"
            f"> **🧊 Источник:**\n"
            f"> Банк\n"
            f"> _ _\n"
            f"> **💰 Казна клана:**\n"
            f"> {new_clan_bank:,} Кан\n"
            f"> _ _\n"
            f"> **🏦 Ваш банк:**\n"
            f"> {new_bank:,} Кан"
        )
        embed = create_embed("Внесение в Казну", desc, self.ctx)
        await interaction.response.edit_message(embed=embed, view=None)
        
# ===============================================================================
# ==================== (ИСПРАВЛЕНИЕ) ХЕЛПЕР EMBED =============================
# ===============================================================================

# (ЗАМЕНИ СВОЮ СТАРУЮ ФУНКЦИЮ create_embed НА ЭТУ, ~строка 204)
def create_embed(title: str, description: str, ctx: commands.Context, color: int = EMBED_COLOR) -> disnake.Embed:
    """
    (ИСПРАВЛЕНО) Теперь принимает 'color'
    """
    embed = disnake.Embed(title=title, description=description, color=color) # (Теперь использует 'color')
    icon_url = ctx.guild.icon.url if ctx.guild and ctx.guild.icon else None
    embed.set_author(name=EMBED_AUTHOR, icon_url=icon_url)
    return embed

# ===================================================================
# ================== 2. КОНФИГУРАЦИЯ ИВЕНТА ========================
# ===================================================================

# Параметры игрока в авто-бою
PLAYER_DAMAGE_MIN = 75     # Мин. урон игрока по Квинси
PLAYER_DAMAGE_MAX = 150    # Макс. урон игрока по Квинси
BATTLE_TURN_DELAY = 2      # Секунды между ходами

# Типы Квинси (HP Квинси ВОЗВРАЩЕНЫ к оригиналу)
QUINCY_TYPES = {
    "soldat": {
        "name": "Солдат Ванденрейха",
        "emoji": "⚔️",
        "hp": 100, # (Оригинал)
        "reward_min": 4000,
        "reward_max": 6000,
        "penalty_min": 400,
        "penalty_max": 600,
        "hp_penalty_min": 15,
        "hp_penalty_max": 20,
        "difficulty": "easy",
        "chance": 35
    },
    "quilge": {
        "name": "Килге Опи 'J' (The Jail)",
        "emoji": "⛓️",
        "hp": 250, # (Оригинал)
        "reward_min": 8000,
        "reward_max": 12000,
        "penalty_min": 750,
        "penalty_max": 1000,
        "hp_penalty_min": 20,
        "hp_penalty_max": 25,
        "difficulty": "medium",
        "chance": 25
    },
    "bambietta": {
        "name": "Бамбиетта Бастербайн 'E' (The Explode)",
        "emoji": "💥",
        "hp": 750,       
        "reward_min": 15000, 
        "reward_max": 22500, 
        "penalty_min": 800,
        "penalty_max": 1000,
        "hp_penalty_min": 20,
        "hp_penalty_max": 25,
        "difficulty": "medium",
        "chance": 15
    },
    "aes_noedt": {
        "name": "Эс Нөдт 'F' (The Fear)",
        "emoji": "👻",
        "hp": 800, 
        "reward_min": 25000, 
        "reward_max": 35000,
        "penalty_min": 1500,
        "penalty_max": 2000,
        "hp_penalty_min": 30, 
        "hp_penalty_max": 40,
        "difficulty": "hard",
        "chance": 10
    },
    "askin": {
        "name": "Аскин Накк ле Вар 'D' (The Deathdealing)",
        "emoji": "☠️",
        "hp": 1000,
        "reward_min": 30000,
        "reward_max": 40000,
        "penalty_min": 2500,
        "penalty_max": 3000,
        "hp_penalty_min": 35,
        "hp_penalty_max": 45,
        "difficulty": "hard",
        "chance": 7
    },
    "lille_barro": {
        "name": "Лилль Барро 'X' (The X-Axis)",
        "emoji": "🎯",
        "hp": 1500,
        "reward_min": 40000,
        "reward_max": 50000,
        "penalty_min": 3500,
        "penalty_max": 4500,
        "hp_penalty_min": 40,
        "hp_penalty_max": 50,
        "difficulty": "legendary",
        "chance": 5
    },
    "haschwalth": {
        "name": "Юграм Хашвальт 'B' (The Balance)",
        "emoji": "⚖️",
        "hp": 2000,
        "reward_min": 50000,
        "reward_max": 65000,
        "penalty_min": 5000,
        "penalty_max": 6000,
        "hp_penalty_min": 50, 
        "hp_penalty_max": 65,
        "difficulty": "legendary",
        "chance": 2
    },
    "yhwach": {
        "name": "ЯХВЕ 'A' (The Almighty)",
        "emoji": "👁️",
        "hp": 9999,
        "reward_min": 0,      # (Награда заменена на купон)
        "reward_max": 0,
        "penalty_min": 7000,
        "penalty_max": 10000,
        "hp_penalty_min": 70, 
        "hp_penalty_max": 90,
        "difficulty": "boss",
        "chance": 1
    }
}

# Глобальное хранилище активных вторжений
active_quincy_invasions: Dict[int, dict] = {}

# ===================================================================
# ================= 3. ЛОГИКА БОЯ (ВНЕ КОГА) =======================
# ===================================================================

async def run_quincy_battle(bot: commands.Bot, ctx: (commands.Context | disnake.MessageInteraction), quincy_type: str, player_hp: int):
    """
    Запускает полный пошаговый бой между игроком и Квинси.
    (Исправлено: $set ошибка, лимит 500 HP, проигрыш 0 HP)
    """
    
    quincy = QUINCY_TYPES[quincy_type].copy()
    quincy_hp = quincy["hp"]
    is_boss = quincy["difficulty"] == "boss"
    
    user_id = ctx.author.id
    guild_id = ctx.guild.id
    # Используем ГЛОБАЛЬНУЮ функцию get_user
    user = await get_user(user_id, guild_id)
    
    battle_log = [f"❄️ {ctx.author.mention} вступает в бой с {quincy['name']}!"]
    
    async def format_embed(p_hp, q_hp, title="Битва..."):
        log_text = "\n> ".join(battle_log[-5:])
        desc = (
            f"> ❤️ **Ваше HP:** {p_hp} / 500\n" # (Лимит 500)
            f"> {quincy['emoji']} **HP Врага:** {q_hp} / {quincy['hp']}\n"
            f"> _ _\n"
            f"> **Ход Битвы:**\n"
            f"> {log_text}"
        )
        
        # Используем ГЛОБАЛЬНУЮ функцию create_embed
        if isinstance(ctx, commands.Context):
            return create_embed(title, desc, ctx)
        else:
            # (Если это interaction, нужен 'fake' ctx для create_embed)
            fake_ctx = await bot.get_context(ctx.message) 
            return create_embed(title, desc, fake_ctx)

    embed = await format_embed(player_hp, quincy_hp)
    battle_msg = None
    
    try:
        if isinstance(ctx, commands.Context):
            battle_msg = await ctx.send(embed=embed)
        else:
            battle_msg = await ctx.followup.send(embed=embed, wait=True)
    except Exception as e:
        print(f"Ошибка отправки стартового сообщения: {e}")
        return

    try:
        while player_hp > 0 and quincy_hp > 0:
            await asyncio.sleep(BATTLE_TURN_DELAY)
            
            # --- Ход Игрока ---
            player_dmg = random.randint(PLAYER_DAMAGE_MIN, PLAYER_DAMAGE_MAX)
            quincy_hp = max(0, quincy_hp - player_dmg)
            battle_log.append(f"⚔️ Вы нанесли {player_dmg} урона. (HP Врага: {quincy_hp})")
            
            embed = await format_embed(player_hp, quincy_hp, title="Битва: Ваш Ход")
            await battle_msg.edit(embed=embed)
            
            if quincy_hp <= 0:
                break

            await asyncio.sleep(BATTLE_TURN_DELAY)

            # --- Ход Квинси ---
            quincy_dmg = random.randint(quincy["hp_penalty_min"], quincy["hp_penalty_max"])
            # (ИСПРАВЛЕНО: Убрана защита, игрок может получить 0 HP)
            player_hp = max(0, player_hp - quincy_dmg)
            
            battle_log.append(f"🩸 {quincy['name']} нанес вам {quincy_dmg} урона. (Ваше HP: {player_hp})")

            embed = await format_embed(player_hp, quincy_hp, title="Битва: Ход Врага")
            await battle_msg.edit(embed=embed)

        # 5. Конец Боя
        # (Этот словарь будет содержать ТОЛЬКО поля для $set)
        update_set_data = {}
        
        if player_hp > 0:
            # ПОБЕДА
            if is_boss:
                update_set_data["fought_yhwach"] = True
                
                # (ИСПРАВЛЕНО: Используем users_collection.update_one для $inc / $push)
                await users_collection.update_one(
                    {"userId": user_id, "guildId": guild_id},
                    {
                        "$set": update_set_data,
                        "$inc": {"quincy_wins": 1},
                        "$push": {"inventory": "custom_farm_coupon"}
                    },
                    upsert=True # (На случай если юзера нет в БД, но он победил)
                )
                
                desc = (f"> **❄️ ВЫ ПОБЕДИЛИ ЯХВЕ!**\n> _ _\n> {quincy['emoji']} **{quincy['name']}** повержен!\n> _ _\n"
                        f"> **👑 Особая Награда:** `📜 Купон на Кастомную Ферму`!\n"
                        f"> (Проверьте `!inv` и используйте `!use custom_farm_coupon`)\n> _ _\n"
                        f"> ❤️ **Ваше HP:** {player_hp} / 500")
                embed = await format_embed(player_hp, quincy_hp, title="Битва | ПОБЕДА НАД БОССОМ")
                embed.description = desc
                embed.color = 0xF1C40F
                
                ping_text = f"<@{CUSTOM_PING_USER_ID}>"
                await ctx.channel.send(f"{ping_text} ПОЛЬЗОВАТЕЛЬ {ctx.author.mention} ПОБЕДИЛ ЯХВЕ!", allowed_mentions=disnake.AllowedMentions.users())
            else:
                reward = random.randint(quincy["reward_min"], quincy["reward_max"])
                new_balance = user.get("balance", 0) + reward
                update_set_data["balance"] = new_balance
                
                # (ИСПРАВЛЕНО: Используем users_collection.update_one для $inc)
                await users_collection.update_one(
                    {"userId": user_id, "guildId": guild_id},
                    {
                        "$set": update_set_data,
                        "$inc": {"quincy_wins": 1}
                    },
                    upsert=True
                )
                
                desc = (f"> **❄️ ПОБЕДА!**\n> _ _\n> {quincy['emoji']} **{quincy['name']}** повержен!\n> _ _\n"
                        f"> **🧊 Награда:** +{reward:,} Кан\n> **💴 Новый баланс:** {new_balance:,} Кан\n> _ _\n"
                        f"> ❤️ **Ваше HP:** {player_hp} / 500\n> _(Победа засчитана в `!eventlb`)_")
                embed = await format_embed(player_hp, quincy_hp, title="Битва | Победа")
                embed.description = desc
                embed.color = 0x00A3FF
        
        else: # (player_hp <= 0)
            # ПОРАЖЕНИЕ
            penalty = random.randint(quincy["penalty_min"], quincy["penalty_max"])
            new_balance = max(0, user.get("balance", 0) - penalty)
            update_set_data["balance"] = new_balance
            update_set_data["hp"] = player_hp # (Запишет 0 HP)
            
            if is_boss:
                update_set_data["fought_yhwach"] = True
            
            # (ИСПРАВЛЕНО: Используем ГЛОБАЛЬНУЮ update_user)
            await update_user(user_id, guild_id, update_set_data)
            
            desc = (f"> **❌ ПОРАЖЕНИЕ!**\n> _ _\n> {quincy['emoji']} **{quincy['name']}** победил!\n> _ _\n"
                    f"> **🧊 Штраф:** -{penalty:,} Кан\n> **💴 Новый баланс:** {new_balance:,} Кан\n> _ _\n"
                    f"> ❤️ **Ваше HP:** {player_hp} / 500")
            embed = await format_embed(player_hp, quincy_hp, title="Битва | Поражение")
            embed.description = desc
            embed.color = 0x34495E
        
        await battle_msg.edit(embed=embed)

    except Exception as e:
        print(f"BATTLE ERROR: {e}")
        traceback.print_exc()
        if battle_msg:
            try:
                await battle_msg.edit(content=f"Произошла ошибка в бою: {e}", embed=None, view=None)
            except disnake.NotFound:
                pass


# ===================================================================
# ================= 4. VIEW КНОПКИ (ВНЕ КОГА) =====================
# ===================================================================

class QuincySpawnView(disnake.ui.View):
    def __init__(self, bot: commands.Bot, channel: disnake.TextChannel, quincy_type: str):
        super().__init__(timeout=1800.0) # 30 минут
        self.bot = bot
        self.channel = channel
        self.quincy_type = quincy_type
        self.message: Optional[disnake.Message] = None
        self.battle_in_progress = False 
        
    @disnake.ui.button(label="⚔️ ВСТУПИТЬ В БОЙ", style=disnake.ButtonStyle.danger)
    async def enter_battle(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        # (Проверяем, не идет ли УЖЕ бой)
        if self.battle_in_progress:
            await interaction.response.send_message("❌ Битва с этим Квинси уже началась!", ephemeral=True)
            return
        
        # Используем ГЛОБАЛЬНУЮ функцию get_user
        user = await get_user(interaction.user.id, interaction.guild.id)
        now = datetime.utcnow()
        
        # (ИСПРАВЛЕНО: .get("hp", 500))
        player_hp = user.get("hp", 500) 
        if player_hp <= 0:
            await interaction.response.send_message(
                f"❌ Вы тяжело ранены и не можете сражаться! (❤️ HP: {player_hp})",
                ephemeral=True
            )
            return
            
        quincy = QUINCY_TYPES[self.quincy_type]
        if quincy["difficulty"] == "boss" and user.get("fought_yhwach", False):
            await interaction.response.send_message(
                f"❌ Вы уже сражались с {quincy['name']}! Вы не можете бросить ему вызов снова.",
                ephemeral=True
            )
            return

        quincy_cooldown = user.get("quincy_cooldown")
        if quincy_cooldown and now < quincy_cooldown:
            remaining = quincy_cooldown - now
            minutes = int(remaining.total_seconds() // 60)
            seconds = int(remaining.total_seconds() % 60)
            await interaction.response.send_message(
                f"❌ У вас кулдаун на битву с Квинси! Осталось: {minutes}м {seconds}с",
                ephemeral=True
            )
            return
        
        # Используем ГЛОБАЛЬНУЮ функцию update_user
        await update_user(interaction.user.id, interaction.guild.id, {
            "quincy_cooldown": now + timedelta(minutes=5)
        })
        
        # (Блокируем кнопку НАВСЕГДА)
        self.battle_in_progress = True
        button.disabled = True
        button.label = "Битва началась..."
        await interaction.response.edit_message(view=self)
        
        # (Удаляем из ГЛОБАЛЬНОГО хранилища)
        if self.channel.id in active_quincy_invasions:
            del active_quincy_invasions[self.channel.id]
            
        self.stop() # (Убиваем View, он больше не нужен)
        
        # (Запускаем ГЛОБАЛЬНУЮ функцию боя)
        await run_quincy_battle(self.bot, interaction, self.quincy_type, player_hp)

    async def on_timeout(self):
        if self.battle_in_progress:
            return 
            
        # (Удаляем из ГЛОБАЛЬНОГО хранилища)
        if self.channel.id in active_quincy_invasions:
            del active_quincy_invasions[self.channel.id]
        
        desc = (
            "> **❄️ Вторжение завершено!**\n"
            "> _ _\n"
            "> Квинси покинул район.\n"
            "> (Время истекло, никто не напал)"
        )
        
        embed = disnake.Embed(title="Вторжение Квинси | Завершено", description=desc, color=0x738A9C)
        embed.set_author(name=EMBED_AUTHOR)
        
        try:
            if self.message:
                await self.message.edit(embed=embed, view=None)
        except disnake.NotFound:
            pass

# ===================================================================
# ================= 5. ОСНОВНОЙ КОГ ИВЕНТА =========================
# ===================================================================

class QuincyInvasion(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # --- (ВАЖНО) ОПРЕДЕЛЯЕМ ГЛОБАЛЬНУЮ КОЛЛЕКЦИЮ ---
        global users_collection
        if users_collection is None:
            print("--- [Quincy Cog] Ищу 'users_collection' ---")
            # Попытка найти ее в боте
            if hasattr(bot, "db") and hasattr(bot.db, "users"):
                 users_collection = bot.db.users
                 print("--- [Quincy Cog] 'bot.db.users' найдена.")
            elif hasattr(bot, "users_collection"):
                 users_collection = bot.users_collection
                 print("--- [Quincy Cog] 'bot.users_collection' найдена.")
            else:
                 print("!!! [Quincy Cog] НЕ УДАЛОСЬ НАЙТИ 'users_collection'. РЕГЕНЕРАЦИЯ HP НЕ БУДЕТ РАБОТАТЬ.")
        # ----------------------------------------------
        
        # Запускаем фоновые задачи
        self.hp_regeneration.start()
        self.spawn_quincy_invasions.start()

    def cog_unload(self):
        """Вызывается при выгрузке кога"""
        self.hp_regeneration.cancel()
        self.spawn_quincy_invasions.cancel()

    # ============ РЕГЕНЕРАЦИЯ HP (Лимит 500) ============
    @tasks.loop(minutes=10)
    async def hp_regeneration(self):
        """Каждые 10 минут восстанавливает 50 HP всем, у кого < 500 HP"""
        if users_collection is None:
            print("[HP REGEN] Пропуск: users_collection не найдена.")
            return
            
        try:
            print(f"[HP REGEN] Начинаю регенерацию HP...")
            
            # (ИСПРАВЛЕНО: $lt: 500 и $gte: 0)
            query_filter = {"hp": {"$lt": 500, "$gte": 0}} 
            update_op = {"$inc": {"hp": 50}}
            result = await users_collection.update_many(query_filter, update_op)
            
            # (ИСПРАВЛЕНО: $gt: 500 и $set: 500)
            cap_filter = {"hp": {"$gt": 500}}
            cap_op = {"$set": {"hp": 500}}
            result_capped = await users_collection.update_many(cap_filter, cap_op)
            
            healed_count = result.modified_count
            capped_count = result_capped.modified_count
            
            print(f"[HP REGEN] ✅ Регенерация завершена. Исцелено: {healed_count} | Установлен лимит: {capped_count}")

        except Exception as e:
            print(f"[HP REGEN ERROR] {e}")
            traceback.print_exc()

    @hp_regeneration.before_loop
    async def before_hp_regen(self):
        await self.bot.wait_until_ready()

    # ============ ФОНОВАЯ ЗАДАЧА: СПАВН КВИНСИ ============
    @tasks.loop(minutes=30)
    async def spawn_quincy_invasions(self):
        """Каждые 30 минут спавнит 2 Квинси в случайных каналах категории"""
        try:
            print("[QUINCY SPAWN] Начинаю спавн Квинси...")
            
            for guild in self.bot.guilds: 
                category = guild.get_channel(QUINCY_SPAWN_CATEGORY_ID)
                
                if not category or not isinstance(category, disnake.CategoryChannel):
                    if guild.id == self.bot.guilds[0].id: # Логируем только для 1 сервера
                        print(f"[QUINCY SPAWN WARNING] Категория {QUINCY_SPAWN_CATEGORY_ID} не найдена на сервере {guild.name}")
                    continue
                
                text_channels = [ch for ch in category.channels if isinstance(ch, disnake.TextChannel)]
                
                if len(text_channels) < 2:
                    print(f"[QUINCY SPAWN WARNING] Недостаточно каналов (нужно >= 2) в категории на сервере {guild.name}")
                    continue
                
                # (Проверяем, сколько уже активно)
                active_in_guild = 0
                for ch_id in active_quincy_invasions:
                    if guild.get_channel(ch_id):
                        active_in_guild += 1
                
                if active_in_guild >= 2: # (Не спавним, если 2 уже висят)
                    print(f"[QUINCY SPAWN] Пропуск спавна в {guild.name}, 2 вторжения уже активны.")
                    continue
                    
                # (Выбираем каналы, где ЕЩЕ НЕТ вторжения)
                available_channels = [ch for ch in text_channels if ch.id not in active_quincy_invasions]
                if len(available_channels) < 2:
                    available_channels = available_channels[:1] # (Берем 1)
                else:
                    available_channels = random.sample(available_channels, 2) # (Берем 2)

                if not available_channels:
                    print(f"[QUINCY SPAWN] Пропуск спавна в {guild.name}, нет свободных каналов.")
                    continue

                for channel in available_channels:
                    roll = random.randint(1, 100)
                    cumulative = 0
                    quincy_type = "soldat"
                    
                    for q_type, q_data in QUINCY_TYPES.items():
                        cumulative += q_data["chance"]
                        if roll <= cumulative:
                            quincy_type = q_type
                            break
                    
                    quincy = QUINCY_TYPES[quincy_type]
                    
                    desc = (
                        f"> **❄️ ВНИМАНИЕ! ВТОРЖЕНИЕ!**\n"
                        f"> _ _\n"
                        f"> {quincy['emoji']} **{quincy['name']}** появился в этом районе!\n"
                        f"> HP: {quincy['hp']}\n"
                        f"> _ _\n"
                        f"> **🧊 Награда за победу:**\n"
                    )
                    
                    if quincy['difficulty'] == "boss":
                        desc += f"> 📜 **??? (Особая Награда)**\n"
                    else:
                        desc += f"> {quincy['reward_min']:,} - {quincy['reward_max']:,} Кан\n"
                        
                    desc += (
                        f"> _ _\n"
                        f"> **⚠️ Сложность:** {quincy['difficulty'].upper()}\n"
                        f"> _ _\n"
                        f"> *Нажмите кнопку, чтобы вступить в бой! (Бой 1 на 1)*"
                    )
                    
                    embed = disnake.Embed(
                        title="Вторжение Квинси",
                        description=desc,
                        color=0x00A3FF
                    )
                    embed.set_author(name=EMBED_AUTHOR)
                    
                    # Передаем self.bot в View
                    view = QuincySpawnView(self.bot, channel, quincy_type)
                    
                    try:
                        message = await channel.send(embed=embed, view=view)
                        view.message = message
                        
                        active_quincy_invasions[channel.id] = {
                            "type": quincy_type,
                            "message": message
                        }
                        print(f"[QUINCY SPAWN] ✅ {quincy['name']} появился в #{channel.name} ({guild.name})")
                    except Exception as e:
                        print(f"[QUINCY SPAWN ERROR] Не удалось отправить сообщение в #{channel.name}: {e}")
            
            print("[QUINCY SPAWN] Спавн завершен.")
            
        except Exception as e:
            print(f"--- [GLOBAL QUINCY SPAWN ERROR] ---")
            traceback.print_exc()

    @spawn_quincy_invasions.before_loop
    async def before_spawn_quincy(self):
        await self.bot.wait_until_ready()

    # ============ (ИЗМЕНЕНО) КОМАНДА !quincy (ТЕСТОВАЯ) ============
  
# ============ ЛИДЕРБОРД ИВЕНТА ============
@bot.command(name="eventlb", aliases=["quincylb", "лидербордквинси"])
async def event_leaderboard(ctx: commands.Context):
    """Показывает топ игроков по победам над Квинси"""
    
    leaderboard_data = await get_event_leaderboard() 
    
    if not leaderboard_data:
        desc = "> **❄️ Никто еще не победил Квинси!**\n> Будьте первым, кто бросит им вызов!"
        embed = create_embed("Лидерборд Вторжения", desc, ctx)
        await ctx.send(embed=embed)
        return
        
    desc = "> **Топ-10 победителей Квинси:**\n> _ _\n"
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    
    for i, user_data in enumerate(leaderboard_data, 1):
        user_id = user_data["userId"] 
        wins = user_data["quincy_wins"]
        
        member = ctx.guild.get_member(user_id)
        member_name = member.display_name if member else f"Неизвестный ({user_id})"
        
        medal = medals.get(i, f"**{i}.**")
        desc += f"> {medal} {member_name} — **{wins}** побед\n"
    
    # (ИСПРАВЛЕНО: Убрал 'color' отсюда)
    embed = create_embed("❄️ Лидерборд Вторжения Квинси ❄️", desc, ctx)
    await ctx.send(embed=embed)


@clan.command(name="deposit")
async def clan_deposit(ctx: commands.Context, amount: int):
    """Внести деньги в казну клана"""
    if not await check_command_cooldown(ctx, "clan_deposit"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    if not user.get("clan_id"):
        desc = "> **❌ Ошибка:**\n> Вы не состоите в клане!"
        embed = create_embed("Внесение в Казну", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    if amount <= 0:
        desc = "> **❌ Ошибка:**\n> Сумма должна быть положительной!"
        embed = create_embed("Внесение в Казну", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    clan = await get_clan(user["clan_id"])
    if not clan:
        desc = "> **❌ Ошибка:**\n> Клан не найден!"
        embed = create_embed("Внесение в Казну", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Проверяем, есть ли деньги хотя бы в одном месте
    total_available = user["balance"] + user.get("bank", 0)
    if total_available < amount:
        desc = (
            f"> **❌ Недостаточно средств!**\n"
            f"> _ _\n"
            f"> **💴 Наличные:** {user['balance']:,} Кан\n"
            f"> **🏦 Банк:** {user.get('bank', 0):,} Кан\n"
            f"> **💎 Всего:** {total_available:,} Кан\n"
            f"> _ _\n"
            f"> **🧊 Требуется:** {amount:,} Кан"
        )
        embed = create_embed("Внесение в Казну", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Отправляем выбор источника
    desc = (
        f"> **❄️ Выберите источник средств:**\n"
        f"> _ _\n"
        f"> **💴 Наличные:**\n"
        f"> {user['balance']:,} Кан\n"
        f"> _ _\n"
        f"> **🏦 Банк:**\n"
        f"> {user.get('bank', 0):,} Кан\n"
        f"> _ _\n"
        f"> **🧊 Сумма внесения:**\n"
        f"> {amount:,} Кан"
    )
    embed = create_embed("Внесение в Казну", desc, ctx)
    view = ClanDepositView(ctx, amount, user, clan)
    await ctx.send(embed=embed, view=view)

@clan.command(name="withdraw")
async def clan_withdraw(ctx: commands.Context, amount: int):
    """Снять деньги из казны (только owner)"""
    if not await check_command_cooldown(ctx, "clan_withdraw"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    if not user.get("clan_id") or user.get("clan_rank") != "owner":
        desc = "> **❌ Ошибка:**\n> Только владелец может снимать из казны!"
        embed = create_embed("Снятие из Казны", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    if amount <= 0:
        desc = "> **❌ Ошибка:**\n> Сумма должна быть положительной!"
        embed = create_embed("Снятие из Казны", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    clan = await get_clan(user["clan_id"])
    if not clan:
        desc = "> **❌ Ошибка:**\n> Клан не найден!"
        embed = create_embed("Снятие из Казны", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    clan_bank = clan.get("bank", 0)
    
    if clan_bank < amount:
        desc = f"> **❌ Недостаточно средств в казне!**\n> В казне: {clan_bank:,} Кан\n> Требуется: {amount:,} Кан"
        embed = create_embed("Снятие из Казны", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Снимаем с казны
    new_clan_bank = clan_bank - amount
    await update_clan(clan["_id"], {"bank": new_clan_bank})
    
    # Добавляем владельцу в наличные
    new_balance = user["balance"] + amount
    await update_user(ctx.author.id, ctx.guild.id, {"balance": new_balance})
    
    desc = (
        f"> **✅ Снято из казны!**\n"
        f"> _ _\n"
        f"> **❄️ Сумма:**\n"
        f"> {amount:,} Кан\n"
        f"> _ _\n"
        f"> **💰 Казна клана:**\n"
        f"> {new_clan_bank:,} Кан\n"
        f"> _ _\n"
        f"> **💴 Ваш баланс:**\n"
        f"> {new_balance:,} Кан"
    )
    embed = create_embed("Снятие из Казны", desc, ctx)
    await ctx.send(embed=embed)

@clan.command(name="shop")
async def clan_shop(ctx: commands.Context):
    """Магазин апгрейдов клана"""
    if not await check_command_cooldown(ctx, "clan_shop"):
        return
    
    desc = "> **❄️ Доступные апгрейды:**\n> _ _\n"
    
    for upgrade_id, upgrade in CLAN_UPGRADES.items():
        desc += f"> {upgrade['emoji']} **{upgrade['name']}**\n"
        desc += f"> {upgrade['description']}\n"
        desc += f"> Цена: **{upgrade['price']:,} Кан**\n"
        desc += f"> ID: `{upgrade_id}`\n> _ _\n"
    
    desc += "> **🧊 Использование:**\n> `!clan buy <upgrade_id>`"
    
    embed = create_embed("Магазин Апгрейдов Клана", desc, ctx)
    await ctx.send(embed=embed)

@clan.command(name="buy")
async def clan_buy(ctx: commands.Context, upgrade_id: str):
    """Купить апгрейд для клана"""
    if not await check_command_cooldown(ctx, "clan_buy"):
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    
    if not user.get("clan_id") or user.get("clan_rank") not in ["admin", "owner"]:
        desc = "> **❌ Ошибка:**\n> Вы должны быть админом или владельцем клана!"
        embed = create_embed("Покупка Апгрейда", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    if upgrade_id not in CLAN_UPGRADES:
        desc = f"> **❌ Ошибка:**\n> Апгрейд `{upgrade_id}` не найден!\n> Используйте `!clan shop` для просмотра."
        embed = create_embed("Покупка Апгрейда", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    upgrade = CLAN_UPGRADES[upgrade_id]
    clan = await get_clan(user["clan_id"])
    
    if not clan:
        desc = "> **❌ Ошибка:**\n> Клан не найден!"
        embed = create_embed("Покупка Апгрейда", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Проверяем, куплен ли уже
    if upgrade_id in clan.get("upgrades", []):
        desc = f"> **❌ Ошибка:**\n> Апгрейд **{upgrade['name']}** уже куплен!"
        embed = create_embed("Покупка Апгрейда", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    clan_bank = clan.get("bank", 0)
    
    if clan_bank < upgrade["price"]:
        desc = f"> **❌ Недостаточно средств в казне!**\n> В казне: {clan_bank:,} Кан\n> Требуется: {upgrade['price']:,} Кан"
        embed = create_embed("Покупка Апгрейда", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Покупаем
    new_clan_bank = clan_bank - upgrade["price"]
    new_upgrades = clan.get("upgrades", []) + [upgrade_id]
    
    await update_clan(clan["_id"], {
        "bank": new_clan_bank,
        "upgrades": new_upgrades
    })
    
    desc = (
        f"> **✅ Апгрейд куплен!**\n"
        f"> _ _\n"
        f"> {upgrade['emoji']} **{upgrade['name']}**\n"
        f"> {upgrade['description']}\n"
        f"> _ _\n"
        f"> **🧊 Потрачено:**\n"
        f"> {upgrade['price']:,} Кан\n"
        f"> _ _\n"
        f"> **💰 Казна клана:**\n"
        f"> {new_clan_bank:,} Кан"
    )
    embed = create_embed("Покупка Апгрейда", desc, ctx)
    await ctx.send(embed=embed)

           


# ==================== HELP ====================

# (ЗАМЕНИТЬ СТАРУЮ КОМАНДУ !help, ~строка 1177)


@bot.command(name="help")
async def help_command(ctx: commands.Context):
    desc = (
        "> **❄️ ЭКОНОМИКА**\n"
        "> `!balance` / `!bal` [@user] - Проверить баланс\n"
        "> `!daily` - Ежедневная награда (23ч)\n"
        "> `!hourly` - Ежечасная награда (1ч)\n"
        "> `!weekly` - Недельная награда (7д)\n"
        "> `!work [job_id]` - Работать\n"
        "> `!beg` - Попрошайничать (5м)\n"
        "> `!search` - Поискать деньги (10м)\n"
        "> `!crime` - Совершить преступление (6ч)\n"
        "> `!referral [@user]` - Реферальная программа\n"
        "> `!pay @user <сумма>` - Перевести деньги\n"
        "> `!leaderboard` / `!lb [cat]` - Лидерборды\n"
        "> `!collect` - Собрать доход с ферм (3ч)\n"
        "> _ _\n"
        "> **🏦 БАНК**\n"
        "> `!deposit` / `!dep <сумма/all>` - Положить в банк\n"
        "> `!withdraw` / `!with <сумма/all>` - Снять с банка\n"
        "> `!rob @user` - Ограбить игрока (кд 30м)\n"
        "> _ _\n"
        "> **🔄 ТРЕЙДЫ**\n"
        "> `!trade @user` - Безопасный обмен\n"
        "> _ _\n"
        "> **🏪 МАГАЗИН**\n"
        "> `!shop` - Магазин ферм\n"
        "> `!buy <id>` - Купить ферму\n"
        "> `!inventory` / `!inv` - Показать фермы и предметы\n"
        "> `!use <id>` - Использовать предмет\n"
        "> _ _\n"
        "> **🎮 МИНИ-ИГРЫ**\n"
        "> `!hunt` - Охота на Холлоу (10м)\n"
        "> `!fish` - Рыбалка (2м)\n"
        "> _ _\n"
        "> **⚔️ ИВЕНТ: ВТОРЖЕНИЕ КВИНСИ**\n"
        "> `!eventlb` - Лидерборд ивента\n"
        "> _ _\n"
        "> **🎰 КАЗИНО (Мин: 100)**\n"
        "> `!coinflip <сумма> <орел/решка>` - Подброс монеты\n"
        "> `!slots <сумма>` - Слоты\n"
        "> `!dice <сумма>` - Кости\n"
        "> `!crash <сумма>` - Краш\n"
        "> `!mines <сумма> [кол-во мин]` - Мины\n"
        "> `!wheel <сумма>` - Колесо фортуны\n"
        "> `!roulette <ставка> <сумма>` - Рулетка\n"
        "> `!blackjack <сумма>` - Блэкджек\n"
        "> _ _\n"
        "> **🏛️ КЛАНЫ**\n"
        "> `!clan` - Команды кланов\n"
        "> _ _\n"
        "> **🎁 ПРОМОКОДЫ**\n"
        "> `!promo <code>` - Активировать\n"
        "> _ _\n"
        "> **📋 КВЕСТЫ**\n"
        "> `!quests` - Список квестов\n"
        "> `!claim_quest <id>` - Получить награду"
    )
    
    embed = create_embed("Команды Bleach World", desc, ctx)
    await ctx.send(embed=embed)

# ===============================================================================
# ==================== СИСТЕМА ТРЕЙДОВ (v2.1 - ПОЧИНЕН БАГ 50035) ===============
# ===============================================================================

# Глобальное хранилище, чтобы юзеры не могли быть в двух трейдах
active_trades = set()

# --- Вспомогательный класс: Модальное окно для ввода КАН ---
class TradeCashModal(disnake.ui.Modal):
    def __init__(self, trade_view: "TradeView"):
        self.trade_view = trade_view
        components = [
            disnake.ui.TextInput(
                label="Сумма Кан для обмена",
                placeholder="Введите число, например: 10000",
                custom_id="cash_amount",
                style=disnake.TextInputStyle.short,
                max_length=12,
            ),
        ]
        super().__init__(title="Добавить Наличные", components=components, custom_id="trade_cash_modal")

    async def callback(self, interaction: disnake.ModalInteraction):
        try:
            amount = int(interaction.text_values["cash_amount"])
            if amount < 0:
                await interaction.response.send_message("❌ Сумма не может быть отрицательной!", ephemeral=True)
                return
            
            await self.trade_view.update_offer(interaction, cash=amount)

        except ValueError:
            await interaction.response.send_message("❌ Вы ввели не число!", ephemeral=True)

# --- Вспомогательный класс: Кнопки выбора Ролей (Ферм) ---
class RoleSelectView(disnake.ui.View):
    # (ПОЧИНЕН __init__ ДЛЯ ОШИБКИ HTTPException 50035)
    def __init__(self, trade_view: "TradeView", user: disnake.Member):
        super().__init__(timeout=180)
        self.trade_view = trade_view
        self.user_id = user.id
        
        owned_role_ids = {role.id for role in user.roles}
        options = []
        
        for item_id, item_data in SHOP_ITEMS.items():
            role_id = item_data.get("role_id")
            if role_id and role_id in owned_role_ids:
                current_offer = self.trade_view.trade_data[self.user_id]["roles"]
                if item_id not in current_offer:
                    options.append(
                        disnake.SelectOption(
                            label=item_data["name"],
                            value=f"shop_{item_id}", 
                            emoji=item_data["emoji"],
                            description=f"+{item_data['income']:,} Кан/час"
                        )
                    )
        
        if options:
            options_to_add = options[:25]
            self.add_item(
                disnake.ui.StringSelect(
                    custom_id="role_select",
                    placeholder="Выберите Ферму (Роль) для добавления",
                    options=options_to_add,
                    max_values=min(len(options_to_add), 5) 
                )
            )
        else:
            # (ВОТ ИСПРАВЛЕНИЕ - options не может быть пустым)
            self.add_item(
                disnake.ui.StringSelect(
                    custom_id="role_select_disabled",
                    placeholder="У вас нет доступных ферм для обмена",
                    options=[disnake.SelectOption(label="пусто", value="none")], 
                    disabled=True
                )
            )

    @disnake.ui.string_select(custom_id="role_select")
    async def select_callback(self, select: disnake.ui.StringSelect, interaction: disnake.MessageInteraction):
        current_roles = self.trade_view.trade_data[self.user_id]["roles"]
        for item_id_with_prefix in select.values:
            item_id = item_id_with_prefix.split("_", 1)[1]
            
            if item_id not in current_roles:
                current_roles.append(item_id)
                
        await self.trade_view.update_offer(interaction, roles=current_roles)
        await interaction.response.edit_message(content="✅ Ферма(ы) добавлены в трейд. Можете закрыть это сообщение.", view=None)

# --- Вспомогательный класс: Кнопки выбора Предметов (Инвентарь) ---
class InventoryItemSelectView(disnake.ui.View):
    # (ПОЧИНЕН __init__ ДЛЯ ОШИБКИ HTTPException 50035)
    def __init__(self, trade_view: "TradeView", user_data: dict):
        super().__init__(timeout=180)
        self.trade_view = trade_view
        self.user_id = user_data["userId"]
        
        inventory = user_data.get("inventory", [])
        current_offer = self.trade_view.trade_data[self.user_id]["inventory"]
        
        offer_counts = Counter(current_offer)
        inventory_counts = Counter(inventory)
        options = []
        
        for item_id, total_count in inventory_counts.items():
            count_in_offer = offer_counts.get(item_id, 0)
            available_count = total_count - count_in_offer
            
            if available_count > 0:
                item_data = CONSUMABLE_ITEMS.get(item_id)
                if item_data:
                    options.append(
                        disnake.SelectOption(
                            label=item_data["name"],
                            value=item_id,
                            emoji=item_data["emoji"],
                            description=f"Доступно: {available_count} шт."
                        )
                    )

        if options:
            options_to_add = options[:25]
            self.add_item(
                disnake.ui.StringSelect(
                    custom_id="inventory_item_select",
                    placeholder="Выберите Предмет (Инвентарь) для добавления",
                    options=options_to_add,
                    max_values=len(options_to_add)
                )
            )
        else:
            # (ВОТ ИСПРАВЛЕНИЕ - options не может быть пустым)
            self.add_item(
                disnake.ui.StringSelect(
                    custom_id="inv_select_disabled",
                    placeholder="У вас нет доступных предметов для обмена",
                    options=[disnake.SelectOption(label="пусто", value="none")],
                    disabled=True
                )
            )

    @disnake.ui.string_select(custom_id="inventory_item_select")
    async def select_callback(self, select: disnake.ui.StringSelect, interaction: disnake.MessageInteraction):
        current_items = self.trade_view.trade_data[self.user_id]["inventory"]
        
        for item_id in select.values:
            current_items.append(item_id)
                
        await self.trade_view.update_offer(interaction, inventory=current_items)
        await interaction.response.edit_message(content="✅ Предмет(ы) добавлены в трейд. Можете закрыть это сообщение.", view=None)


# --- ГЛАВНЫЙ КЛАСС: UI ДЛЯ ТРЕЙДА (v2.1) ---
class TradeView(disnake.ui.View):
    def __init__(self, inviter: disnake.Member, invited: disnake.Member, original_message: disnake.Message):
        super().__init__(timeout=300.0) 
        self.inviter = inviter
        self.invited = invited
        self.message = original_message
        self.ctx = None 
        
        self.trade_data = {
            inviter.id: {"cash": 0, "roles": [], "inventory": []},
            invited.id: {"cash": 0, "roles": [], "inventory": []}
        }
        self.ready_state = { inviter.id: False, invited.id: False }

    async def on_timeout(self):
        active_trades.discard(self.inviter.id)
        active_trades.discard(self.invited.id)
        
        if not self.message or not self.message.embeds:
            return

        embed = self.message.embeds[0]
        embed.description = "**❌ ТРЕЙД ОТМЕНЕН (Истекло время)**"
        embed.color = 0xFF0000 
        
        print(f"[TRADE TIMEOUT] Трейд между {self.inviter.name} и {self.invited.name} истек.")
        
        try:
            await self.message.edit(embed=embed, view=None)
        except disnake.NotFound:
            pass

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        if interaction.user.id not in [self.inviter.id, self.invited.id]:
            await interaction.response.send_message("❌ Это не ваш трейд!", ephemeral=True)
            return False
        
        if not self.ctx:
            self.ctx = await bot.get_context(interaction.message)
            
        return True

    def format_offer(self, user_id: int) -> str:
        """Форматирует предложение юзера для эмбеда"""
        offer = self.trade_data[user_id]
        parts = []
        
        if offer["cash"] > 0:
            parts.append(f"💰 **{offer['cash']:,}** Кан")
            
        if offer["roles"]:
            for item_id in offer["roles"]:
                item = SHOP_ITEMS.get(item_id) 
                if item:
                    parts.append(f"{item['emoji']} **{item['name']}**")
                else:
                    parts.append(f"📦 *Неизв. Роль ({item_id})*")
                    
        if offer["inventory"]:
            item_counts = Counter(offer["inventory"])
            for item_id, count in item_counts.items():
                item = CONSUMABLE_ITEMS.get(item_id)
                parts.append(f"{item['emoji']} **{item['name']}** (x{count})" if item else f"📦 *Неизв. Предмет ({item_id})* (x{count})")
        
        return "\n> ".join(parts) if parts else "> (Пусто)"

    async def update_embed(self, interaction: disnake.MessageInteraction, title: str = "Обмен"):
        """Перерисовывает эмбед трейда"""
        
        status1 = "✅ Готов" if self.ready_state[self.inviter.id] else "⏳ Ожидание"
        status2 = "✅ Готов" if self.ready_state[self.invited.id] else "⏳ Ожидание"
        
        desc = (
            f"> **❄️ Предложение {self.inviter.display_name}** ({status1}):\n"
            f"> {self.format_offer(self.inviter.id)}\n"
            f"> _ _\n"
            f"> **❄️ Предложение {self.invited.display_name}** ({status2}):\n"
            f"> {self.format_offer(self.invited.id)}\n"
            f"> _ _\n"
            f"> ⚠️ *Если вы меняете предложение, готовность сбрасывается у обоих!*"
        )
        
        embed = create_embed(f"Трейд | {title}", desc, self.ctx)
        await interaction.response.edit_message(embed=embed, view=self)

    async def reset_ready_states(self):
        """Сбрасывает готовность у обоих"""
        self.ready_state[self.inviter.id] = False
        self.ready_state[self.invited.id] = False

    async def update_offer(self, interaction: disnake.MessageInteraction, cash: int = -1, roles: list = None, inventory: list = None):
        """Обновляет предложение и сбрасывает готовность"""
        user_id = interaction.user.id
        
        if cash >= 0:
            self.trade_data[user_id]["cash"] = cash
        if roles is not None:
            self.trade_data[user_id]["roles"] = roles
        if inventory is not None:
            self.trade_data[user_id]["inventory"] = inventory
            
        await self.reset_ready_states()
        await self.update_embed(interaction, title="Предложение изменено")

    # --- КНОПКИ ---
    @disnake.ui.button(label="Наличные", style=disnake.ButtonStyle.secondary, emoji="💰", row=0)
    async def cash_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.send_modal(TradeCashModal(self))

    @disnake.ui.button(label="Ферму (Роль)", style=disnake.ButtonStyle.secondary, emoji="🏭", row=0)
    async def roles_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.send_message(
            "Выберите фермы (роли), которыми вы владеете:",
            view=RoleSelectView(self, interaction.user),
            ephemeral=True
        )

    @disnake.ui.button(label="Предмет (Инв.)", style=disnake.ButtonStyle.secondary, emoji="📦", row=0)
    async def items_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        user_data = await get_user(interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(
            "Выберите предметы из вашего инвентаря:",
            view=InventoryItemSelectView(self, user_data),
            ephemeral=True
        )

    @disnake.ui.button(label="Очистить...", style=disnake.ButtonStyle.grey, emoji="♻️", row=1)
    async def clear_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        user_id = interaction.user.id
        self.trade_data[user_id]["cash"] = 0
        self.trade_data[user_id]["roles"] = []
        self.trade_data[user_id]["inventory"] = []
        await self.update_offer(interaction, cash=0, roles=[], inventory=[])

    @disnake.ui.button(label="✅ Подтвердить", style=disnake.ButtonStyle.success, row=2)
    async def confirm_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        user_id = interaction.user.id
        
        if self.ready_state[user_id]:
            await interaction.response.send_message("❌ Вы уже подтвердили.", ephemeral=True)
            return
            
        self.ready_state[user_id] = True
        
        if all(self.ready_state.values()):
            await self.execute_trade(interaction)
        else:
            await self.update_embed(interaction, title="Игрок готов")

    @disnake.ui.button(label="❌ Отменить", style=disnake.ButtonStyle.danger, row=2)
    async def cancel_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        active_trades.discard(self.inviter.id)
        active_trades.discard(self.invited.id)
        
        embed = self.message.embeds[0]
        embed.description = f"**❌ ТРЕЙД ОТМЕНЕН**\n> (Отменил: {interaction.user.display_name})"
        embed.color = 0xFF0000 
        
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()

    # --- ФИНАЛ: ИСПОЛНЕНИЕ СДЕЛКИ (v2.1) ---
    async def execute_trade(self, interaction: disnake.MessageInteraction):
        """Выполняет обмен (v2.1)"""
        
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(embed=self.message.embeds[0], view=self)
        
        u1_id = self.inviter.id
        u2_id = self.invited.id
        u1_offer = self.trade_data[u1_id]
        u2_offer = self.trade_data[u2_id]
        
        try:
            # 3. ФИНАЛЬНАЯ ПРОВЕРКА
            user1_data = await get_user(u1_id, interaction.guild.id)
            user2_data = await get_user(u2_id, interaction.guild.id)
            
            # --- 3.1: Наличные ---
            if user1_data["balance"] < u1_offer["cash"]:
                await self.fail_trade("Сделка отменена!", f"У {self.inviter.display_name} не хватает {u1_offer['cash']:,} Кан!")
                return
            if user2_data["balance"] < u2_offer["cash"]:
                await self.fail_trade("Сделка отменена!", f"У {self.invited.display_name} не хватает {u2_offer['cash']:,} Кан!")
                return

            # --- 3.2: Роли (Фермы) ---
            user1_roles = {role.id for role in self.inviter.roles}
            user2_roles = {role.id for role in self.invited.roles}
            
            roles_to_remove_from_u1 = []
            for item_id in u1_offer["roles"]:
                item_data = SHOP_ITEMS.get(item_id)
                if not item_data: continue
                
                role_id = item_data.get("role_id")
                
                if role_id not in user1_roles:
                    await self.fail_trade("Сделка отменена!", f"У {self.inviter.display_name} больше нет фермы '{item_data['name']}'!")
                    return
                roles_to_remove_from_u1.append(disnake.Object(id=role_id))
                
            roles_to_remove_from_u2 = []
            for item_id in u2_offer["roles"]:
                item_data = SHOP_ITEMS.get(item_id)
                if not item_data: continue
                
                role_id = item_data.get("role_id")
                
                if role_id not in user2_roles:
                    await self.fail_trade("Сделка отменена!", f"У {self.invited.display_name} больше нет фермы '{item_data['name']}'!")
                    return
                roles_to_remove_from_u2.append(disnake.Object(id=role_id))

            # --- 3.3: Предметы (Инвентарь) ---
            u1_inv_counts = Counter(user1_data.get("inventory", []))
            u1_offer_counts = Counter(u1_offer["inventory"])
            for item_id, needed_count in u1_offer_counts.items():
                if u1_inv_counts.get(item_id, 0) < needed_count:
                    await self.fail_trade("Сделка отменена!", f"У {self.inviter.display_name} не хватает '{CONSUMABLE_ITEMS[item_id]['name']}' (Нужно: {needed_count}, Есть: {u1_inv_counts.get(item_id, 0)})!")
                    return
                    
            u2_inv_counts = Counter(user2_data.get("inventory", []))
            u2_offer_counts = Counter(u2_offer["inventory"])
            for item_id, needed_count in u2_offer_counts.items():
                if u2_inv_counts.get(item_id, 0) < needed_count:
                    await self.fail_trade("Сделка отменена!", f"У {self.invited.display_name} не хватает '{CONSUMABLE_ITEMS[item_id]['name']}' (Нужно: {needed_count}, Есть: {u2_inv_counts.get(item_id, 0)})!")
                    return

            # 4. ИСПОЛНЕНИЕ
            
            # 4.1. Обмен деньгами
            cash_change_u1 = u2_offer["cash"] - u1_offer["cash"]
            cash_change_u2 = u1_offer["cash"] - u2_offer["cash"]
            
            if cash_change_u1 != 0:
                await update_user(u1_id, interaction.guild.id, {"$inc": {"balance": cash_change_u1}})
            if cash_change_u2 != 0:
                await update_user(u2_id, interaction.guild.id, {"$inc": {"balance": cash_change_u2}})
            
            # 4.2. Обмен ролями
            roles_to_add_to_u2 = roles_to_remove_from_u1
            roles_to_add_to_u1 = roles_to_remove_from_u2
            
            if roles_to_remove_from_u1:
                await self.inviter.remove_roles(*roles_to_remove_from_u1, reason="Обмен !trade")
            if roles_to_add_to_u1:
                await self.inviter.add_roles(*roles_to_add_to_u1, reason="Обмен !trade")
                
            if roles_to_remove_from_u2:
                await self.invited.remove_roles(*roles_to_remove_from_u2, reason="Обмен !trade")
            if roles_to_add_to_u2:
                await self.invited.add_roles(*roles_to_add_to_u2, reason="Обмен !trade")

            # 4.3. Обмен предметами (ИСПОЛЬЗУЕМ $set и $push)
            
            # (Передаем предметы от U1 -> U2)
            if u1_offer["inventory"]:
                temp_inv = user1_data.get("inventory", [])
                for item_id_to_remove in u1_offer["inventory"]:
                    if item_id_to_remove in temp_inv:
                        temp_inv.remove(item_id_to_remove)
                
                await update_user(u1_id, interaction.guild.id, {"$set": {"inventory": temp_inv}})
                await update_user(u2_id, interaction.guild.id, {"$push": {"inventory": {"$each": u1_offer["inventory"]}}})

            # (Передаем предметы от U2 -> U1)
            if u2_offer["inventory"]:
                temp_inv = user2_data.get("inventory", [])
                for item_id_to_remove in u2_offer["inventory"]:
                    if item_id_to_remove in temp_inv:
                        temp_inv.remove(item_id_to_remove)
                
                await update_user(u2_id, interaction.guild.id, {"$set": {"inventory": temp_inv}})
                await update_user(u1_id, interaction.guild.id, {"$push": {"inventory": {"$each": u2_offer["inventory"]}}})
            
        except disnake.Forbidden:
            await self.fail_trade("ОШИБКА ПРАВ!", "У меня нет прав (`Manage Roles`) для передачи ролей. Трейд отменен.")
            return
        except Exception as e:
            await self.fail_trade("Внутренняя Ошибка!", f"Произошла ошибка: {e}. Трейд отменен.")
            return
            
        # 5. УСПЕХ
        active_trades.discard(self.inviter.id)
        active_trades.discard(self.invited.id)
        
        desc = (
            f"> **❄️ Предложение {self.inviter.display_name}**:\n"
            f"> {self.format_offer(self.inviter.id)}\n"
            f"> _ _\n"
            f"> **❄️ Предложение {self.invited.display_name}**:\n"
            f"> {self.format_offer(self.invited.id)}\n"
        )
        
        embed = create_embed("✅ Трейд Успешно Завершен", desc, self.ctx)
        embed.color = 0x00FF00 # Зеленый
        await self.message.edit(embed=embed, view=None)
        
    async def fail_trade(self, title: str, reason: str):
        active_trades.discard(self.inviter.id)
        active_trades.discard(self.invited.id)
        
        desc = (
            f"**❌ {title}**\n"
            f"> {reason}"
        )
        embed = create_embed("Трейд Отменен", desc, self.ctx)
        embed.color = 0xFF0000 # Красный
        await self.message.edit(embed=embed, view=None)

# --- КЛАСС: Кнопки Приглашения (v2.1) ---
class TradeInviteView(disnake.ui.View):
    def __init__(self, inviter: disnake.Member, invited: disnake.Member):
        super().__init__(timeout=60.0)
        self.inviter = inviter
        self.invited = invited
        self.message: disnake.Message = None

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        if interaction.user.id != self.invited.id:
            await interaction.response.send_message("❌ Это приглашение не для вас!", ephemeral=True)
            return False
        return True

    @disnake.ui.button(label="Принять", style=disnake.ButtonStyle.success)
    async def accept_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        if self.inviter.id in active_trades:
            await interaction.response.edit_message(content=f"❌ {self.inviter.display_name} уже начал другой трейд.", embed=None, view=None)
            self.stop()
            return
            
        if self.invited.id in active_trades:
            await interaction.response.edit_message(content=f"❌ Вы уже в другом трейде.", embed=None, view=None)
            self.stop()
            return
            
        active_trades.add(self.inviter.id)
        active_trades.add(self.invited.id)

        ctx = await bot.get_context(interaction.message)
        trade_view = TradeView(self.inviter, self.invited, self.message)
        trade_view.ctx = ctx 
        
        desc = (
            f"> **❄️ Предложение {self.inviter.display_name}** (⏳ Ожидание):\n"
            f"> (Пусто)\n"
            f"> _ _\n"
            f"> **❄️ Предложение {self.invited.display_name}** (⏳ Ожидание):\n"
            f"> (Пусто)\n"
            f"> _ _\n"
            f"> *Используйте кнопки, чтобы добавить наличные, фермы или предметы.*"
        )
        embed = create_embed("Трейд | Обмен", desc, ctx)
        
        await interaction.response.edit_message(embed=embed, view=trade_view)
        self.stop()

    @disnake.ui.button(label="Отклонить", style=disnake.ButtonStyle.danger)
    async def decline_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        if not self.message or not self.message.embeds:
            await interaction.response.edit_message(content="❌ Приглашение отклонено.", view=None)
            self.stop()
            return
            
        embed = self.message.embeds[0]
        embed.description = f"**❌ {self.invited.display_name} отклонил(а) приглашение.**"
        embed.color = 0xFF0000
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()
        
    async def on_timeout(self):
        if not self.message or not self.message.embeds:
            return
            
        embed = self.message.embeds[0]
        embed.description = f"**❌ Приглашение истекло.**\n> ({self.invited.display_name} не ответил вовремя)"
        embed.color = 0xAAAAAA
        try:
            await self.message.edit(embed=embed, view=None)
        except disnake.NotFound:
            pass

# --- ГЛАВНАЯ КОМАНДА: !trade (v2.1) ---
@bot.command(name="trade")
async def trade(ctx: commands.Context, member: disnake.Member):
    """Начать безопасный обмен с другим игроком"""
    
    if not await check_command_cooldown(ctx, "trade"):
        return

    if member.id == ctx.author.id:
        await ctx.send("❌ Нельзя торговать с самим собой!")
        return
    if member.bot:
        await ctx.send("❌ Нельзя торговать с ботом!")
        return
        
    user = await get_user(ctx.author.id, ctx.guild.id)
    now = datetime.utcnow()
    
    trade_cooldown = user.get("trade_cooldown")
    if trade_cooldown and now < trade_cooldown:
        remaining = int((trade_cooldown - now).total_seconds())
        await ctx.send(f"❌ У вас кулдаун на трейды! Осталось: {remaining} сек.")
        return
        
    if ctx.author.id in active_trades:
        await ctx.send("❌ Вы уже находитесь в другом трейде! Завершите или отмените его.")
        return
        
    if member.id in active_trades:
        await ctx.send(f"❌ {member.display_name} уже находится в другом трейде.")
        return

    await update_user(ctx.author.id, ctx.guild.id, {"$set": {
        "trade_cooldown": now + timedelta(seconds=60)
    }})
    
    desc = (
        f"> **❄️ Приглашение на Обмен!**\n"
        f"> _ _\n"
        f"> {ctx.author.mention} хочет начать обмен с {member.mention}!\n"
        f"> _ _\n"
        f"> *У {member.display_name} есть 60 секунд, чтобы принять.*"
    )
    embed = create_embed("Трейд | Приглашение", desc, ctx)
    view = TradeInviteView(inviter=ctx.author, invited=member)
    
    message = await ctx.send(embed=embed, view=view)
    view.message = message


HOLLOWS = {
    "weak": {
        "name": "Слабый Холлоу",
        "emoji": "👻",
        "hp": 1200,         # (Было 1000)
        "reward_min": 1200, # (Было 1000)
        "reward_max": 3600, # (Было 3000)
        "penalty": 600,     # (Было 500)
        "chance": 70        # (Шанс не изменен)
    },
    "normal": {
        "name": "Обычный Холлоу",
        "emoji": "👹",
        "hp": 3000,         # (Было 2500)
        "reward_min": 3600, # (Было 3000)
        "reward_max": 8400, # (Было 7000)
        "penalty": 1800,    # (Было 1500)
        "chance": 17       # (Шанс не изменен)
    },
    "strong": {
        "name": "Сильный Холлоу",
        "emoji": "😈",
        "hp": 6000,         # (Было 5000)
        "reward_min": 9600, # (Было 8000)
        "reward_max": 18000,# (Было 15000)
        "penalty": 3600,    # (Было 3000)
        "chance": 15        # (Шанс не изменен)
    },
    "menos": {
        "name": "Менос Гранде",
        "emoji": "💀",
        "hp": 12000,        # (Было 10000)
        "reward_min": 24000, # (Было 20000)
        "reward_max": 48000,# (Было 40000)
        "penalty": 6000,    # (Было 5000)
        "chance": 3       # (Шанс не изменен)
    }
} # (Сумма шансов по-прежнему 100: 35+30+25+10)HOLLOWS = {
 


# --- (НОВЫЙ) Класс для Кнопки Охоты ---
class HuntView(disnake.ui.View):
    def __init__(self, ctx: commands.Context, hollow_type: str):
        # (ВАЖНО) Кнопка "умрет" через 2 секунды!
        super().__init__(timeout=2.0) 
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.hollow = HOLLOWS[hollow_type]
        self.clicked = False # Флаг, чтобы знать, нажал ли юзер
        self.message: disnake.Message = None

    # Проверка, что нажал нужный юзер
    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Это не твой Холлоу!", ephemeral=True)
            return False
        return True

    @disnake.ui.button(label="⚔️ АТАКОВАТЬ!", style=disnake.ButtonStyle.danger) # (Красная кнопка)
    async def pull_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        # 1. Они успели!
        self.clicked = True
        self.stop() # Останавливаем View (и on_timeout)

        # 2. Определяем награду
        hollow = self.hollow
        reward = random.randint(hollow["reward_min"], hollow["reward_max"])
        
        # 3. Начисляем деньги
        user = await get_user(self.author_id, interaction.guild.id)
        new_balance = user["balance"] + reward
        await update_user(self.author_id, interaction.guild.id, {"balance": new_balance})
        
        # 4. "Красивый" эмбед успеха
        desc = (
            f"> **❄️ Вы встретили холлоу...**\n"
            f"> _ _\n"
            f"> {hollow['emoji']} **{hollow['name']}** (HP: {hollow['hp']})\n"
            f"> _ _\n"
            f"> **✅ Победа!**\n"
            f"> Вы успешно атаковали и победили!\n"
            f"> _ _\n"
            f"> **🧊 Награда:**\n"
            f"> +{reward:,} Кан\n"
            f"> _ _\n"
            f"> **💴 Новый баланс:**\n"
            f"> {new_balance:,} Кан"
        )
        # (Эмбед зеленый - победа)
        embed = disnake.Embed(title="Охота | Победа", description=desc, color=0x00FF00)
        icon_url = self.ctx.guild.icon.url if self.ctx.guild and self.ctx.guild.icon else None
        embed.set_author(name=EMBED_AUTHOR, icon_url=icon_url)
        
        # Редактируем сообщение (убираем кнопки)
        await interaction.response.edit_message(embed=embed, view=None)

    # Эта функция сработает, если юзер НЕ НАЖАЛ кнопку за 2 секунды
    async def on_timeout(self):
        if self.clicked: # Если он успел нажать, выходим
            return
            
        hollow = self.hollow
        
        # 1. Забираем штраф
        user = await get_user(self.author_id, self.ctx.guild.id)
        penalty = hollow["penalty"]
        new_balance = max(0, user["balance"] - penalty)
        await update_user(self.author_id, self.ctx.guild.id, {"balance": new_balance})

        # 2. "Красивый" эмбед провала
        desc = (
            f"> **❄️ Вы встретили холлоу...**\n"
            f"> _ _\n"
            f"> {hollow['emoji']} **{hollow['name']}** (HP: {hollow['hp']})\n"
            f"> _ _\n"
            f"> **❌ Поражение!**\n"
            f"> Холлоу был слишком быстр, вы не успели атаковать!\n"
            f"> _ _\n"
            f"> **🧊 Штраф:**\n"
            f"> -{penalty:,} Кан\n"
            f"> _ _\n"
            f"> **💴 Новый баланс:**\n"
            f"> {new_balance:,} Кан"
        )
        # (Эмбед красный - провал)
        embed = disnake.Embed(title="Охота | Неудача", description=desc, color=0xFF0000)
        icon_url = self.ctx.guild.icon.url if self.ctx.guild and self.ctx.guild.icon else None
        embed.set_author(name=EMBED_AUTHOR, icon_url=icon_url)
        
        # 3. Редактируем сообщение (убираем кнопки)
        try:
            if self.message:
                await self.message.edit(embed=embed, view=None)
        except disnake.NotFound:
            pass # Сообщение удалили

# --- (НОВАЯ) КОМАНДА ОХОТЫ (v2.0) ---
@bot.command(name="hunt")
async def hunt(ctx: commands.Context):
    """Охотиться на холлоу (Мини-игра на реакцию)"""
    if not await check_command_cooldown(ctx, "hunt"):
        return
        
    user = await get_user(ctx.author.id, ctx.guild.id)
    now = datetime.utcnow()
    
    # Кулдаун 10 минут
    hunt_cooldown = user.get("hunt_cooldown")
    if hunt_cooldown and now < hunt_cooldown:
        remaining = hunt_cooldown - now
        minutes = int(remaining.total_seconds() // 60)
        seconds = int(remaining.total_seconds() % 60)
        desc = f"> **❄️ Кулдаун активен!**\n> Осталось: {minutes}м {seconds}с"
        embed = create_embed("Охота", desc, ctx)
        await ctx.send(embed=embed)
        return
        
    # Сразу ставим кулдаун
    await update_user(ctx.author.id, ctx.guild.id, {
        "hunt_cooldown": now + timedelta(minutes=10)
    })
    
    # 1. Отправляем "ждущий" эмбед
    desc = "> **❄️ Вы выслеживаете Холлоу...**\n> _ _\n> 🧊 Ожидайте..."
    embed = create_embed("Охота", desc, ctx)
    message = await ctx.send(embed=embed)
    
    # 2. Ждем случайное время
    await asyncio.sleep(random.uniform(3.0, 8.0))
    
    # 3. Проверяем, не удалил ли юзер сообщение
    try:
        await message.channel.fetch_message(message.id)
    except disnake.NotFound:
        return # Сообщение удалено, отменяем охоту
        
    # 4. Определяем холлоу
    roll = random.randint(1, 100)
    cumulative = 0
    hollow_type = "weak" # По умолчанию
    for h_type, h_data in HOLLOWS.items():
        cumulative += h_data["chance"]
        if roll <= cumulative:
            hollow_type = h_type
            break
            
    hollow = HOLLOWS[hollow_type]
            
    # 5. Создаем View (кнопку)
    view = HuntView(ctx, hollow_type)
    view.message = message # Передаем сообщение в View

    # 6. Редактируем сообщение, ПОКАЗЫВАЯ ХОЛЛОУ и КНОПКУ
    bite_desc = (
        f"> **❄️ ВЫ НАШЛИ ХОЛЛОУ!**\n"
        f"> _ _\n"
        f"> {hollow['emoji']} **{hollow['name']}** (HP: {hollow['hp']})\n"
        f"> _ _\n"
        f"> 🧊 **Жми 'АТАКОВАТЬ!'**\n"
        f"> (У тебя 2 секунды!)"
    )
    bite_embed = create_embed("Охота | Враг замечен!", bite_desc, ctx)
    
    try:
        await message.edit(embed=bite_embed, view=view)
    except disnake.NotFound:
        return # Сообщение удалили, пока мы ждали


# ==================== РЫБАЛКА (НОВАЯ, УНИКАЛЬНАЯ) ====================

# ==================== РЫБАЛКА ====================

FISH_TYPES = {
    # (Обычные)
    "common": {
        "name": "Обычная рыба",
        "emoji": "🐟",
        "value_min": 270,
        "value_max": 630,
        "chance": 35         # (Не поднимал, оставил 30)
    },
    
    # (Редкие)
    "rare": {
        "name": "Редкая рыба",
        "emoji": "🐠",
        "value_min": 720,
        "value_max": 1800,
        "chance": 25          # (Уменьшил с 60)
    },
    "hollow_fish": {
        "name": "Рыба-Пустой",
        "emoji": "💀",
        "value_min": 1080,
        "value_max": 2160,
        "chance": 15          
    },
    
    # (Эпические)
    "epic": {
        "name": "Эпическая рыба",
        "emoji": "🐡",
        "value_min": 2160,
        "value_max": 4320,
        "chance": 10
    },
    
    # (Легендарные)
    "legendary": {
        "name": "Легендарная рыба",
        "emoji": "🦈",
        "value_min": 5400,
        "value_max": 10800,
        "chance": 5
    },
    "kons_lion": {
        "name": "Лев Кона",
        "emoji": "🦁",
        "value_min": 18000,
        "value_max": 18000,
        "chance": 3
    },
    
    # (Пасхалка)
    "ichigo_fish": {
        "name": "Рыбка Ичиго", 
        "emoji": "🍓",          
        "value_min": 54000,
        "value_max": 54000,
        "chance": 2
    },
    
    # (Мусор)
    "trash": {
        "name": "Мусор",
        "emoji": "🗑️",
        "value_min": 36,
        "value_max": 108,
        "chance": 5
    }
}

# --- (НОВЫЙ) Класс для Кнопки Рыбалки ---
class FishView(disnake.ui.View):
    def __init__(self, ctx: commands.Context):
        # (ВАЖНО) Кнопка "умрет" через 2 секунды!
        super().__init__(timeout=2.0) 
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.clicked = False # Флаг, чтобы знать, нажал ли юзер
        self.message: disnake.Message = None

    # Проверка, что нажал нужный юзер
    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Это не твоя удочка!", ephemeral=True)
            return False
        return True

    @disnake.ui.button(label="🎣 ТАЩИ!", style=disnake.ButtonStyle.success)
    async def pull_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        # 1. Они успели!
        self.clicked = True
        self.stop() # Останавливаем View (и on_timeout)

        # 2. Определяем улов
        roll = random.randint(1, 100)
        cumulative = 0
        caught = "common" # По умолчанию
        for fish_type, fish_data in FISH_TYPES.items():
            cumulative += fish_data["chance"]
            if roll <= cumulative:
                caught = fish_type
                break
        
        fish_data = FISH_TYPES[caught]
        value = random.randint(fish_data["value_min"], fish_data["value_max"])
        
        # 3. Начисляем деньги
        user = await get_user(self.author_id, interaction.guild.id)
        new_balance = user["balance"] + value
        await update_user(self.author_id, interaction.guild.id, {"balance": new_balance})
        
        # 4. "Красивый" эмбед успеха
        rarity_color = {
            "common": "⚪", "rare": "🔵", "epic": "🟣",
            "legendary": "🟡", "trash": "🟤"
        }
        
        desc = (
            f"> **❄️ Вы поймали!**\n"
            f"> _ _\n"
            f"> {fish_data['emoji']} **{fish_data['name']}** {rarity_color.get(caught, '')}\n"
            f"> _ _\n"
            f"> **🧊 Стоимость:**\n"
            f"> +{value:,} Кан\n"
            f"> _ _\n"
            f"> **💴 Новый баланс:**\n"
            f"> {new_balance:,} Кан"
        )
        embed = create_embed("Рыбалка | Успех", desc, self.ctx)
        
        # Редактируем сообщение (убираем кнопки)
        await interaction.response.edit_message(embed=embed, view=None)

    # Эта функция сработает, если юзер НЕ НАЖАЛ кнопку за 2 секунды
    async def on_timeout(self):
        if self.clicked: # Если он успел нажать, выходим
            return
            
        # 1. "Красивый" эмбед провала
        desc = (
            f"> **❄️ Вы закинули удочку...**\n"
            f"> _ _\n"
            f"> 🧊 ...но рыба сорвалась с крючка! 🎣\n"
            f"> (Вы не успели нажать кнопку вовремя)"
        )
        # (Делаем эмбед красным, т.к. это провал)
        embed = disnake.Embed(title="Рыбалка | Неудача", description=desc, color=0xFF0000)
        icon_url = self.ctx.guild.icon.url if self.ctx.guild and self.ctx.guild.icon else None
        embed.set_author(name=EMBED_AUTHOR, icon_url=icon_url)
        
        # 2. Редактируем сообщение (убираем кнопки)
        try:
            if self.message:
                await self.message.edit(embed=embed, view=None)
        except disnake.NotFound:
            pass # Сообщение удалили, и хуй с ним

# --- (НОВАЯ) КОМАНДА РЫБАЛКИ (v2.0) ---
@bot.command(name="fish")
async def fish(ctx: commands.Context):
    """Порыбачить (Мини-игра на реакцию)"""
    if not await check_command_cooldown(ctx, "fish"):
        return
        
    user = await get_user(ctx.author.id, ctx.guild.id)
    now = datetime.utcnow()
    
    # Кулдаун (давай 2 минуты, раз это мини-игра)
    fish_cooldown = user.get("fish_cooldown")
    if fish_cooldown and now < fish_cooldown:
        remaining = fish_cooldown - now
        minutes = int(remaining.total_seconds() // 60)
        seconds = int(remaining.total_seconds() % 60)
        desc = f"> **❄️ Кулдаун активен!**\n> Осталось: {minutes}м {seconds}с"
        embed = create_embed("Рыбалка", desc, ctx)
        await ctx.send(embed=embed)
        return
        
    # Сразу ставим кулдаун (чтобы не спамили !fish)
    await update_user(ctx.author.id, ctx.guild.id, {
        "fish_cooldown": now + timedelta(minutes=2)
    })
    
    # 1. Отправляем "ждущий" эмбед
    desc = "> **❄️ Вы закинули удочку...**\n> _ _\n> 🧊 Ожидайте поклевки..."
    embed = create_embed("Рыбалка", desc, ctx)
    message = await ctx.send(embed=embed)
    
    # 2. Ждем случайное время
    await asyncio.sleep(random.uniform(3.0, 8.0))
    
    # 3. Проверяем, не удалил ли юзер сообщение
    try:
        await message.channel.fetch_message(message.id)
    except disnake.NotFound:
        return # Сообщение удалено, отменяем рыбалку
        
    # 4. Создаем View (кнопку)
    view = FishView(ctx)
    view.message = message # Передаем сообщение в View

    # 5. Редактируем сообщение, ДОБАВЛЯЯ КНОПКУ
    bite_desc = (
        f"> **❄️ КЛЮЕТ!**\n"
        f"> _ _\n"
        f"> 🧊 **Жми кнопку 'ТАЩИ!'**\n"
        f"> (У тебя 2 секунды!)"
    )
    bite_embed = create_embed("Рыбалка | Поклевка!", bite_desc, ctx)
    
    try:
        await message.edit(embed=bite_embed, view=view)
    except disnake.NotFound:
        return # Сообщение удалили, пока мы
        


# (ВСТАВИТЬ ПОСЛЕ booster_income, ~строка 393)

# ==================== РЕГЕНЕРАЦИЯ HP ====================
@tasks.loop(minutes=10)
async def hp_regeneration():
    """Каждые 10 минут восстанавливает 50 HP всем, у кого < 100 HP"""
    try:
        print(f"[HP REGEN] Начинаю регенерацию HP...")
        
        # 1. Восстанавливаем 50 HP тем, у кого 0 < HP < 100
        # (Мы не лечим тех, у кого 0 HP, они "мертвы")
        query_filter = {"hp": {"$lt": 100, "$gt": 0}}
        update_op = {"$inc": {"hp": 50}}
        
        result = await users_collection.update_many(query_filter, update_op)
        
        # 2. Устанавливаем "потолок" в 100 HP
        # (Если у кого-то стало 90 + 50 = 140, возвращаем к 100)
        cap_filter = {"hp": {"$gt": 100}}
        cap_op = {"$set": {"hp": 100}}
        
        result_capped = await users_collection.update_many(cap_filter, cap_op)
        
        healed_count = result.modified_count
        capped_count = result_capped.modified_count
        
        print(f"[HP REGEN] ✅ Регенерация завершена. Исцелено: {healed_count} | Установлен лимит: {capped_count}")

    except Exception as e:
        print(f"[HP REGEN ERROR] {e}")
        import traceback
        traceback.print_exc()

@hp_regeneration.before_loop
async def before_hp_regen():
    await bot.wait_until_ready()# (ВСТАВИТЬ ПОСЛЕ booster_income, ~строка 393)

# ==================== КВЕСТЫ (v2.0 - РАБОЧИЕ) ====================

QUESTS = {
    "daily_gambler": {
        "name": "Азартный игрок",
        "description": "Сыграйте 5 раз в казино",
        "reward": 500,
        "type": "daily",
        "goal": 5,
        "icon": "🎰"
    },
    "daily_worker": {
        "name": "Трудяга",
        "description": "Выполните работу 3 раза",
        "reward": 750,
        "type": "daily",
        "goal": 3,
        "icon": "💼"
    },
    "daily_rich": {
        "name": "Накопитель",
        "description": "Накопите 10,000 Кан в банке",
        "reward": 1000,
        "type": "daily",
        "goal": 10000,
        "icon": "💰"
    },
    # (Я убрал "weekly_clan" из твоего примера,
    # так как у нас еще нет кланов в ЭТОМ боте.
    # Если кланы уже есть, просто добавь его обратно.)
}

# --- (НОВЫЙ) МОЗГ КВЕСТОВ: ТРЕКЕР ---
async def update_quest_progress(user_id: int, guild_id: int, quest_id: str, amount_to_add: int = 1):
    """
    Обновляет прогресс квеста.
    quest_id должен быть "daily_worker", "daily_gambler" и т.д.
    """
    try:
        if quest_id not in QUESTS:
            return

        user = await get_user(user_id, guild_id)
        quest = QUESTS[quest_id]
        
        # 1. Проверяем, не выполнен ли квест УЖЕ
        claimed_quests = user.get("claimed_quests", [])
        if quest_id in claimed_quests:
            return # Уже получили награду

        # 2. Обновляем прогресс
        quest_progress = user.get("quest_progress", {})
        current_progress = quest_progress.get(quest_id, 0)
        
        # (Особая логика для "Накопителя", он не суммирует, а ставит макс.)
        if quest_id == "daily_rich":
            current_progress = max(current_progress, amount_to_add)
        else:
            current_progress += amount_to_add
            
        # Не даем прогрессу уйти выше цели
        current_progress = min(current_progress, quest["goal"])
            
        quest_progress[quest_id] = current_progress
        
        await update_user(user_id, guild_id, {"quest_progress": quest_progress})

    except Exception as e:
        print(f"[QUEST ERROR] Не удалось обновить прогресс {quest_id} для {user_id}: {e}")


# --- (НОВЫЙ) СБРОС КВЕСТОВ (КАЖДЫЙ ДЕНЬ В ПОЛНОЧЬ) ---
@tasks.loop(hours=24) # (Можно настроить на (time=datetime.time(hour=0, minute=0, tzinfo=...))
async def reset_daily_quests():
    """Сбрасывает ежедневные квесты для ВСЕХ юзеров"""
    print("[QUEST RESET] Начинаю сброс ЕЖЕДНЕВНЫХ квестов...")
    
    # Собираем ID всех *дневных* квестов
    daily_quests_to_reset = [qid for qid, q in QUESTS.items() if q["type"] == "daily"]
    
    # Готовим запросы в БД
    pull_updates = {"$pull": {"claimed_quests": {"$in": daily_quests_to_reset}}}
    unset_updates = {}
    for qid in daily_quests_to_reset:
        unset_updates[f"quest_progress.{qid}"] = "" # Удаляем поле

    # Сбрасываем у ВСЕХ юзеров
    await users_collection.update_many({}, pull_updates)
    await users_collection.update_many({}, {"$unset": unset_updates})
    
    print("[QUEST RESET] Ежедневные квесты сброшены.")

@reset_daily_quests.before_loop
async def before_reset_quests():
    await bot.wait_until_ready()
    # (Тут можно добавить логику, чтобы он запускался ровно в 00:00 UTC)

# --- (ИСПРАВЛЕНО) КОМАНДА !quests ---
@bot.command(name="quests")
async def quests(ctx: commands.Context):
    """Показать доступные квесты"""
    if not await check_command_cooldown(ctx, "quests"):
        return
        
    user = await get_user(ctx.author.id, ctx.guild.id)
    quest_progress = user.get("quest_progress", {})
    claimed_quests = user.get("claimed_quests", [])
    
    # --- (КРАСИВЫЙ СТИЛЬ) ---
    desc_daily = ""
    for quest_id, quest in QUESTS.items():
        if quest["type"] == "daily":
            # --- (НАЧАЛО ИСПРАВЛЕНИЯ) ---
            # (Все строки ниже должны быть на одном уровне отступа)
            
            progress = quest_progress.get(quest_id, 0)
            
            # (У этой строки убран лишний отступ)
            if quest_id in claimed_quests:
                status = "✅ (Получено)"
            elif progress >= quest["goal"]:
                status = "🟩 (Готово к сдаче)"
            else:
                status = f"⏳ ({progress}/{quest['goal']})"
                
            # (Эта f-строка была неполной, теперь она полная)
            desc_daily += (
                f"> {quest['icon']} **{quest['name']}** {status}\n"
                f"> {quest['description']}\n"
                f"> Награда: {quest['reward']:,} Кан\n> _ _\n"
            )
            # --- (КОНЕЦ ИСПРАВЛЕНИЯ) ---
            
    # (Пока что у нас нет Недельных, но оставим заготовку)
    desc_weekly = ""
    for quest_id, quest in QUESTS.items():
        if quest["type"] == "weekly":
            # (Логика для недельных)
            pass 
            
    if not desc_weekly:
        desc_weekly = "> *Нет доступных недельных квестов.*"

    # Финальный эмбед
    embed = create_embed("Ежедневные Квесты", desc_daily, ctx)
    # (Мы не можем использовать 'description' дважды,
    # поэтому недельные квесты идут в 'field')
    embed.add_field(name="Недельные Квесты", value=desc_weekly, inline=False)
    
    await ctx.send(embed=embed)# --- (ИСПРАВЛЕНО) КОМАНДА !quests ---
# --- (ИСПРАВЛЕНО) КОМАНДА !claim_quest ---
@bot.command(name="claim_quest")
async def claim_quest(ctx: commands.Context, quest_id: str):
    """Получить награду за квест"""
    quest_id = quest_id.lower()
    if quest_id not in QUESTS:
        await ctx.send(f"❌ Квест `{quest_id}` не найден!")
        return
    
    user = await get_user(ctx.author.id, ctx.guild.id)
    quest_progress = user.get("quest_progress", {})
    claimed_quests = user.get("claimed_quests", [])
    
    quest = QUESTS[quest_id]
    progress = quest_progress.get(quest_id, 0)
    
    if quest_id in claimed_quests:
        desc = f"> **❌ Вы уже получили награду**\n> за квест **{quest['name']}**."
        embed = create_embed("Получение Награды", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    if progress < quest["goal"]:
        desc = (
            f"> **❌ Квест не завершён!**\n"
            f"> {quest['icon']} **{quest['name']}**\n"
            f"> _ _\n"
            f"> **🧊 Прогресс:**\n"
            f"> {progress}/{quest['goal']}"
        )
        embed = create_embed("Получение Награды", desc, ctx)
        await ctx.send(embed=embed)
        return
    
    # Выдаём награду
    new_balance = user["balance"] + quest["reward"]
    claimed_quests.append(quest_id)
    
    await update_user(ctx.author.id, ctx.guild.id, {
        "balance": new_balance,
        "claimed_quests": claimed_quests
    })
    
    desc = (
        f"> **✅ Квест завершён!**\n"
        f"> _ _\n"
        f"> {quest['icon']} **{quest['name']}**\n"
        f"> {quest['description']}\n"
        f"> _ _\n"
        f"> **🧊 Награда:**\n"
        f"> +{quest['reward']:,} Кан\n"
        f"> _ _\n"
        f"> **💴 Новый баланс:**\n"
        f"> {new_balance:,} Кан"
    )
    embed = create_embed("Получение Награды", desc, ctx)
    await ctx.send(embed=embed)    

# ==================== FASTAPI (UPTIMEROBOT) ====================

app = FastAPI()

@app.get("/")
async def healthcheck():
    return {"status": "ok", "bot": "Bleach World"}

# ==================== ЗАПУСК ===================

# ==================== ЗАПУСК ===================

@bot.event
async def on_ready():# ...existing code...
    print(f"✅ Бот {bot.user} запущен!")
    print(f"🧊 Guilds: {len(bot.guilds)}")
    
    # 1. СНАЧАЛА регистрируем Ког (систему) Квинси
    # (Это ИСПРАВЛЕНИЕ, которого не было в вашем коде)
    try:
        bot.add_cog(QuincyInvasion(bot))
        print("⚙️  Ког QuincyInvasion (Ивент) успешно загружен.")
    except Exception as e:
        print(f"❌ ОШИБКА загрузки кога QuincyInvasion: {e}")

    # 2. ТЕПЕРЬ запускаем фоновые задачи
    
    # Запускаем фоновые задачи из основного файла
    if not booster_income.is_running():
        booster_income.start()
        print("▶️  Задача 'booster_income' запущена.")
        
    if not reset_daily_quests.is_running():
        reset_daily_quests.start()
        print("▶️  Задача 'reset_daily_quests' запущена.")

    if not hp_regeneration.is_running():
        hp_regeneration.start()
        print("▶️  Задача 'hp_regeneration' (глобальная) запущена.")

    # (Закомментировано, так как в вашем коде @tasks.loop() выключен)
    # if not passive_income.is_running():
    #     passive_income.start()
    #     print("▶️  Задача 'passive_income' запущена.")
        
    # Запускаем задачи ИЗ КОГА (теперь он загружен)
    # (Нужно получить ког, чтобы запустить его задачи)
    quincy_cog = bot.get_cog("QuincyInvasion")
    if quincy_cog:
        if not quincy_cog.spawn_quincy_invasions.is_running():
            quincy_cog.spawn_quincy_invasions.start()
            print("▶️  Задача 'spawn_quincy_invasions' (из кога) запущена.")
            
        if not quincy_cog.hp_regeneration.is_running():
            quincy_cog.hp_regeneration.start()
            print("▶️  Задача 'hp_regeneration' (из кога, до 500 HP) запущена.")
    else:
        print("⚠️ Не удалось найти ког 'QuincyInvasion' для запуска его задач.")
    # ✨ НОВОЕ: Сообщаем keep_alive, что бот готов
def run_bot():
    """Запуск бота в основном потоке"""
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        print("🛑 Бот остановлен")

def run_fastapi():
    """Запуск FastAPI в отдельном потоке"""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")

if __name__ == "__main__":
    keep_alive()
    import threading
    
    # Запускаем FastAPI в фоновом потоке
    fastapi_thread = threading.Thread(target=run_fastapi, daemon=True)
    fastapi_thread.start()
    
    print("🌐 FastAPI запущен в фоновом режиме")
    print(f"🤖 Запуск Discord бота...")
    
    # Запускаем бота в основном потоке
    run_bot()