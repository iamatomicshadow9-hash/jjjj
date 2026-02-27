# replit.md

## Overview

Sunshine Paradise is a Discord bot built with the `disnake` library (a fork of discord.py). It provides guild/clan management, an economy system (XP, coins, levels, daily rewards, work, pay, leaderboards), seasonal events, and admin commands. The bot runs alongside a Flask-based web server that acts as a health-check endpoint (originally designed for Koyeb hosting) and monitors/auto-restarts the bot process.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Entry Point & Process Management
- **`main.py`** is the Replit entry point. It delegates to `run.py` (if present) or falls back to running `bot.py` directly.
- **`web.py`** is a Flask web server that serves as a health-check endpoint and bot process monitor. It runs on the port defined by the `PORT` environment variable (defaults to 8000, but main.py sets it to 5000 for Replit). It can auto-restart `bot.py` if it crashes.
- **`bot.py`** defines the Discord bot using `disnake.ext.commands.Bot` with a custom `CustomBot` subclass that includes rate limit handling and basic telemetry (command count, error count, uptime).

### Bot Architecture
- **Framework**: `disnake` (discord.py fork with built-in slash command and component support)
- **Extension system**: The bot uses disnake's cog/extension pattern. `guilds.py` is the main extension, loaded via `setup(bot)`.
- **Components**: Uses Discord Components V1 with `custom_id` strings rather than `disnake.ui.View` classes.
- **Rate limiting**: Custom `RateLimitHandler` class with exponential backoff (capped at 60 seconds).

### Guild System (`guilds.py`)
This is the core feature module containing:
- **Economy**: XP and coins earned per message, level-up system, daily/work commands, payments, leaderboards
- **Guild/Clan management**: Creation (requires 300 messages), DM-based creation dialog, tag validation, colored emoji channels
- **Channel templates**: Structured clan channel creation with specific formatting patterns
- **War system**: Inter-guild wars
- **Admin commands**: 15+ administrative commands
- **Seasonal events**: Auto-announced events (e.g., End of Winter / Start of Spring)
- **Pagination**: Button-based list pagination for any user

### Data Storage
- **MongoDB** is used as the primary database via `pymongo` (synchronous driver). Connection string is read from the `MONGODB_URI` environment variable.
- **Legacy**: The codebase was migrated from a JSON file-based storage system to MongoDB (evidenced by `fix_load.py` migration script and code comments). Some migration artifacts may remain.
- **Logs**: JSON metrics files in `logs/` directory track uptime, restarts, health checks, and errors.

### Environment Variables Required
| Variable | Purpose |
|----------|---------|
| `TOKEN` | Discord bot token |
| `MONGODB_URI` | MongoDB connection string (with SRV support) |
| `PORT` | Web server port (defaults to 8000/5000) |
| `BOT_FILE` | Optional override for bot script filename (defaults to `bot.py`) |

## External Dependencies

### Python Packages
- **`disnake`** — Discord API wrapper (fork of discord.py with interaction support)
- **`python-dotenv`** — Loads `.env` file into environment variables
- **`pymongo[srv]`** — MongoDB driver with SRV DNS support for Atlas clusters
- **`Flask`** — Lightweight web framework for health-check server
- **`psutil`** — System/process monitoring utilities (used in web.py)
- **`aiohttp`** — Async HTTP client (used by disnake internally and potentially for external API calls)

### External Services
- **Discord API** — Core bot functionality via disnake
- **MongoDB Atlas** — Cloud-hosted MongoDB database (connection via SRV URI)
- **Koyeb** (or similar PaaS) — The web server was designed for Koyeb's health-check system, but works on Replit too

### Note on Database
The project uses `pymongo` (synchronous MongoDB driver). The `MONGODB_URI` environment variable must be set with a valid MongoDB connection string. If MongoDB is unavailable, the bot's guild and economy features will not function. The `requirements.txt` has duplicate entries that should be cleaned up.