import os
import asyncio
from flask import Flask
from threading import Thread
import discord
from discord.ext import commands

# --- 1. สร้าง Web Server หลอก Render ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run_web():
    # Render จะส่ง PORT มาให้ทาง Environment Variables
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- 2. ส่วนของ Discord Bot ---
# (ใส่โค้ดตั้งค่า Intent และ Bot ของพี่ตามปกติ)
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'บอท {bot.user} ออนไลน์พร้อมใช้งานแล้ว!')

# --- โค้ดคำสั่ง !ticket ของพี่ใส่ไว้ตรงนี้ ---

# --- 3. เรียกใช้งานทั้ง Web Server และ บอท ---
if __name__ == "__main__":
    keep_alive()  # สั่งเปิดเว็บหลอก Render
    token = os.environ.get("DISCORD_TOKEN")
    bot.run(token)
    
