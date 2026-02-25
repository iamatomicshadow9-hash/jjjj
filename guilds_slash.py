"""
╔══════════════════════════════════════════════════════════════════════╗
║ 🌸 SUNSHINE PARADISE — GUILDS + ECONOMY v6.0 (SLASH COMMANDS) 🌸   ║
╠══════════════════════════════════════════════════════════════════════╣
║ Переписано на: Slash Commands + Components V2                      ║
║ БД: MongoDB                                                         ║
║ Framework: disnake                                                  ║
╚══════════════════════════════════════════════════════════════════════╝

ИЗМЕНЕНИЯ:
  ✨ Все @commands.command → @commands.slash_command
  ✨ Все embed → Components V2 (Container, TextDisplay, Button)
  ✨ Все ctx → inter
  ✨ Сохранены: логика, экономика, БД, cooldown, проверки прав
  ⚠️  Secret-команды НЕ троганы (@commands.command)
  ⚠️  Fortune, PIVO-команды НЕ троганы
"""

import disnake
from disnake.ext import commands, tasks
from disnake import ui
import asyncio
import random
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import re

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
    
    def get_income_per_hour(farms, upgrades=None):
        return 0
    def get_guild_vault_bonus(upgrades=None):