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

# --- 3. ปุ่มกดปิดตั๋ว (Close Ticket) เฉพาะแอดมิน/เจ้าของร้าน ---
class CloseTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 ปิดตั๋ว", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn_v2")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        # เช็กว่าผู้กดมีสิทธิ์ Administrator หรือ Manage Channels หรือไม่
        if not interaction.user.guild_permissions.administrator and not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ เฉพาะแอดมินหรือเจ้าของร้านเท่านั้นที่สามารถปิดตั๋วนี้ได้!", ephemeral=True)
            return

        await interaction.response.send_message("🔒 กำลังปิดและลบห้องตั๋วนี้ภายใน 3 วินาที...")
        await asyncio.sleep(3)
        await interaction.channel.delete()

# --- 4. ปุ่มกดเปิดตั๋วหน้าร้าน ---
class OpenTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 เปิดตั๋วเช่าคอม", style=discord.ButtonStyle.primary, custom_id="ice_open_ticket_v4")
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        user = interaction.user

        if not guild:
            await interaction.followup.send("คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์ครับ", ephemeral=True)
            return

        channel_name = f"ticket-{user.name}".lower().replace(" ", "-")
        
        # 1. เช็กว่าลูกค้ามีห้องตั๋วเดิมอยู่แล้วหรือยัง
        existing_channel = discord.utils.get(guild.channels, name=channel_name)
        if existing_channel:
            await interaction.followup.send(f"คุณมีห้องตั๋วอยู่แล้วที่ {existing_channel.mention} โปรดตรวจสอบ", ephemeral=True)
            return

        # 2. ตั้งค่าสิทธิ์ความเป็นส่วนตัว (เฉพาะลูกค้า + แอดมิน + บอท ที่เห็น)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, view_channel=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True)
        }

        # หาหมวดหมู่ (Category) ของช่องปัจจุบันเพื่อเอาห้องตั๋วไปวางไว้ในหมวดหมู่เดียวกัน
        category = interaction.channel.category

        try:
            # 3. สร้างห้องตั๋วในหมวดหมู่ "จุดบริการเช่าคอม"
            ticket_channel = await guild.create_text_channel(
                name=channel_name, 
                overwrites=overwrites,
                category=category
            )

            # ข้อความต้อนรับ + ปุ่มปิดตั๋วภายในห้องใหม่
            embed = discord.Embed(
                title="❄️ ICE Cloud Gaming - ยินดีต้อนรับ",
                description=f"สวัสดีครับ {user.mention}\nกรุณาแจ้งรายละเอียดการเช่าคอม หรือพิมพ์ข้อความทิ้งไว้ แอดมินจะรีบมาตอบกลับครับ!",
                color=discord.Color.green()
            )
            await ticket_channel.send(content=f"{user.mention}", embed=embed, view=CloseTicketView())
            
            await interaction.followup.send(f"สร้างห้องตั๋วเรียบร้อยแล้ว: {ticket_channel.mention}", ephemeral=True)

        except Exception as e:
            print(f"ERROR CREATE CHANNEL: {e}")
            await interaction.followup.send(f"เกิดข้อผิดพลาดในการสร้างห้อง: {e}", ephemeral=True)

@bot.event
async def on_ready():
    bot.add_view(OpenTicketView())
    bot.add_view(CloseTicketView())
    print(f'บอท {bot.user} ออนไลน์พร้อมใช้งานแล้ว!')

@bot.command()
async def ticket(ctx):
    # ลบข้อความคำสั่ง !ticket
    try:
        await ctx.message.delete()
    except Exception:
        pass

    # --- Embed หน้าร้าน ---
    embed = discord.Embed(
        title="❄️ ICE Cloud Gaming | บริการเช่าเล่นเกม",
        description="กดเปิดแชทเพื่อเริ่มขอ Player ID และ OTP หรือสอบถามข้อมูลเพิ่มเติมครับ",
        color=discord.Color.blue()
    )
    
    # 📌 วาง URL รูปภาพของพี่ตรงนี้ได้เลยครับ
    embed.set_image(url="https://images.unsplash.com/photo-1542751371-adc38448a05e?q=80&w=1000&auto=format&fit=crop")
    embed.set_footer(text="Powered by ICE Cloud Gaming", icon_url=bot.user.avatar.url if bot.user.avatar else None)

    await ctx.send(embed=embed, view=OpenTicketView())

# --- 5. สั่งรันบอท ---
if __name__ == "__main__":
    keep_alive()
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("ERROR: ไม่พบ DISCORD_TOKEN")
        
