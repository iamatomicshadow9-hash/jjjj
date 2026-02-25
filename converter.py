#!/usr/bin/env python3
"""
Конвертер guilds.py из текстовых команд в slash-команды с Components V2
- @commands.command() → @commands.slash_command()
- ctx → inter
- ctx.send() → inter.response.send_message()
- Сохраняет secret-команды без изменений
"""

import re
import sys

def convert_guilds():
    with open('/workspaces/jjjj/guilds.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    result = []
    i = 0
    skip_until_next_command = False
    secret_commands = ['secret_guild_ascend', 'fortune', 'pivo_boost', 'pivo_farm_boost', 'auto_pivo_boost']
    
    while i < len(lines):
        line = lines[i]
        
        # Проверяем, начинается ли это secret-команда
        is_secret = any(cmd in line for cmd in secret_commands)
        
        if '@commands.command' in line and not is_secret:
            # Заменяем текстовую команду на slash
            line = line.replace('@commands.command', '@commands.slash_command')
            # Убираем name= из slash
            line = re.sub(r'\(\s*name\s*=\s*["\']([^"\']+)["\']\s*(?:,\s*)?', '(', line)
            line = re.sub(r',\s*aliases\s*=\s*\[[^\]]*\]\s*\)', ')', line)
            result.append(line)
            i += 1
            
            # Ищем определение функции
            while i < len(lines) and 'async def' not in lines[i]:
                result.append(lines[i])
                i += 1
            
            # Преобразуем сигнатуру функции: (ctx: commands.Context, ...) → (inter: disnake.AppCommandInteraction, ...)
            if i < len(lines) and 'async def' in lines[i]:
                func_def = lines[i]
                func_def = func_def.replace('ctx: commands.Context', 'inter: disnake.AppCommandInteraction')
                result.append(func_def)
                i += 1
                
                # Тело команды - преобразуем ctx → inter
                while i < len(lines):
                    func_line = lines[i]
                    
                    # Проверяем не начнется ли новая команда
                    if func_line.strip().startswith('@commands') or func_line.strip().startswith('@tasks'):
                        break
                    
                    # Трансформируем вызовы
                    # await ctx.send → await inter.response.send_message
                    func_line = re.sub(
                        r'await\s+ctx\.send\(\s*embed\s*=\s*',
                        'container = _embed_to_container(',
                        func_line
                    )
                    func_line = re.sub(
                        r'await\s+ctx\.send\(',
                        'await inter.response.send_message(',
                        func_line
                    )
                    # ctx.guild → inter.guild
                    func_line = func_line.replace('ctx.guild', 'inter.guild')
                    # ctx.author → inter.author
                    func_line = func_line.replace('ctx.author', 'inter.author')
                    # ctx.channel → inter.channel
                    func_line = func_line.replace('ctx.channel', 'inter.channel')
                    
                    result.append(func_line)
                    
                    # Выходим если закончилась команда (новый декоратор или class)
                    if func_line.strip() and not func_line.startswith(' ' * 4):
                        break
                    
                    i += 1
        else:
            # Секретные команды - копируем как есть
            result.append(line)
            i += 1
    
    return '\n'.join(result)

if __name__ == '__main__':
    try:
        converted = convert_guilds()
        with open('/workspaces/jjjj/guilds_converted.py', 'w', encoding='utf-8') as f:
            f.write(converted)
        print("✅ Конверсия завершена! Файл: guilds_converted.py")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)
