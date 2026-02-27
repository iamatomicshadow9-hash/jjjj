import re

with open('guilds.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Заменить db = _load(); gd = db["guilds"].get(gid) на gd = get_guild(gid)
content = re.sub(
    r'db\s*=\s*_load\(\)\s*\n\s*gd\s*=\s*db\["guilds"\]\.get\(gid\)',
    'gd  = get_guild(gid)',
    content
)

# 2. Заменить db = _load(); gd = db["guilds"][gid] на gd = get_guild(gid)
content = re.sub(
    r'db\s*=\s*_load\(\)\s*\n\s*gd\s*=\s*db\["guilds"\]\[gid\]',
    'gd  = get_guild(gid)',
    content
)

# 3. Заменить _load()["guilds"].values() на list(db["guilds"].find({"server_id": sid}))
# Но это нужен контекст, поэтому оставим для ручной замены

# 4. Для остающихся случаев где нужна вся БД, заменить на collection.find()
content = re.sub(
    r'db\s*=\s*_load\(\)\s*\n\s*(\s+)if tag is None:',
    r'''sid = str(ctx.guild.id)
        tag = None
        \1if tag is None:''',
    content
)

# 5. Заменить использование db["guilds"] на database queries через get_guild
# Это сложнее, нужно скрипт который понимает контекст

with open('guilds.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Заменены паттерны _load()")
