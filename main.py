import os
import asyncio
from flask import Flask
from threading import Thread
import discord
from discord.ext import commands
from discord.ui import Button, View

# --- 1. Web Server หลอก Render ให้บอทออนไลน์ตลอด 24 ชม. ---
app = Flask('')

@app.route('/', methods=['GET', 'HEAD'])
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- 2. ตั้งค่า Intent และ Bot ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- 3. ปุ่มกดเปิดตั๋วหน้าร้าน ---
class OpenTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 เปิดตั๋วเช่าคอม", style=discord.ButtonStyle.primary, custom_id="ice_open_ticket_v2")
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        # 1. ตอบรับ Discord ทันทีในมิลลิวินาทีแรก (กันการโต้ตอบล้มเหลว 100%)
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception as e:
            print(f"Defer Error: {e}")

        guild = interaction.guild
        user = interaction.user

        if not guild:
            await interaction.followup.send("คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์ครับ", ephemeral=True)
            return

        channel_name = f"ticket-{user.name}".lower().replace(" ", "-")
        
        # เช็กว่ามีห้องเดิมอยู่แล้วหรือไม่
        existing_channel = discord.utils.get(guild.channels, name=channel_name)
        if existing_channel:
            await interaction.followup.send(f"คุณมีห้องตั๋วอยู่แล้วที่ {existing_channel.mention}", ephemeral=True)
            return

        # ตั้งค่าสิทธิ์ห้องตั๋ว
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        # ลองสร้างห้องตั๋ว
        try:
            ticket_channel = await guild.create_text_channel(name=channel_name, overwrites=overwrites)
            await ticket_channel.send(f"สวัสดีครับ {user.mention} แจ้งรายละเอียดการเช่าคอมหรือติดต่อแอดมินในห้องนี้ได้เลยครับ!")
            await interaction.followup.send(f"สร้างห้องตั๋วเรียบร้อยแล้ว: {ticket_channel.mention}", ephemeral=True)
            print(f"SUCCESS: สร้างห้อง {channel_name} ให้กับ {user.name} สำเร็จ!")
        except Exception as e:
            print(f"ERROR CREATE CHANNEL: {e}")
            await interaction.followup.send(f"บอทไม่สามารถสร้างห้องได้ โปรดเช็กสิทธิ์ 'Administrator' หรือ 'Manage Channels': {e}", ephemeral=True)

@bot.event
async def on_ready():
    bot.add_view(OpenTicketView())
    print(f'บอท {bot.user} ออนไลน์พร้อมใช้งานแล้ว!')

@bot.command()
async def ticket(ctx):
    # ลบข้อความคำสั่ง !ticket
    try:
        await ctx.message.delete()
    except Exception as e:
        print(f"Delete message error: {e}")

    embed = discord.Embed(
        title="❄️ ICE Cloud Gaming - ระบบเปิดตั๋ว",
        description="กดปุ่มด้านล่างเพื่อเปิดตั๋วติดต่อเช่าคอมหรือสอบถามข้อมูลครับ",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed, view=OpenTicketView())

# --- 4. สั่งรันบอท ---
if __name__ == "__main__":
    keep_alive()
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("ERROR: ไม่พบ DISCORD_TOKEN")
