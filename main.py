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

    @discord.ui.button(label="🎫 เปิดตั๋วเช่าคอม", style=discord.ButtonStyle.primary, custom_id="ice_open_ticket_v8")
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        user = interaction.user

        if not guild:
            await interaction.followup.send("คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์ครับ", ephemeral=True)
            return

        # ใช้ชื่อแสดงผล (display_name) แทน username
        display_name = user.display_name.lower().replace(" ", "-")
        channel_name = f"ห้องตั๋วเช่าเกม-{display_name}"
        
        # 1. เช็กว่าลูกค้ามีห้องตั๋วเดิมอยู่แล้วหรือยัง
        existing_channel = discord.utils.get(guild.channels, name=channel_name)
        if existing_channel:
            await interaction.followup.send(f"คุณมีช่องตั๋วอยู่แล้วโปรดคลิกที่นี่เพื่อใช้งาน /n👉🏻{existing_channel.mention}", ephemeral=True)
            return

        # 2. ตั้งค่าสิทธิ์ความเป็นส่วนตัว (เฉพาะลูกค้า + แอดมิน + บอท ที่เห็น)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, view_channel=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True)
        }

        # หาหมวดหมู่ (Category) ของช่องปัจจุบัน
        category = interaction.channel.category

        try:
            # 3. สร้างห้องตั๋วในหมวดหมู่เดียวกับช่องเปิดตั๋ว
            ticket_channel = await guild.create_text_channel(
                name=channel_name, 
                overwrites=overwrites,
                category=category
            )

            # 📌 [ตั้งค่าตรงนี้] ใส่ ID ยศเจ้าของร้าน/แอดมิน ที่ต้องการให้บอทแท็กเรียก
            role_id = "1524631721641771050"  # <--- เปลี่ยนเลขในเครื่องหมายคำพูดนี้เป็น ID ยศของพี่
            role_mention = f"<@&{role_id}>"

            # ข้อความต้อนรับ + แท็กยศเจ้าของร้าน + ปุ่มปิดตั๋วภายในห้องใหม่
            embed = discord.Embed(
                title="❄️ ICE Cloud Gaming - ยินดีต้อนรับ",
                description=f"กรุณารอเจ้าของร้านสักครู่ ถ้ามีคำถามอะไรให้พิมพ์ทิ้งไว้ เจ้าของร้านจะรีบมาตอบครับ!",
                color=discord.Color.green()
            )
            
            # ส่งข้อความพร้อมแท็กยศออกไป
            await ticket_channel.send(content=f"{role_mention}", embed=embed, view=CloseTicketView())
            
            await interaction.followup.send(f"สร้างตั๋วเช่าเกมเรียบร้อยแล้ว /nคลิกที่นี่เพื่อใช้งานห้อง/n👉🏻{ticket_channel.mention} ", ephemeral=True)

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
    
    embed.set_image(url="https://cdn.discordapp.com/attachments/1525449388212748328/1525711847817478215/5035230a3313e71c85e3a8c8e9d63174e547958b99d80015c52c3233eecbb7ab.png?ex=6a638aa2&is=6a623922&hm=3100db3f8c1af503c8df06a3cac534578b7b28415265f208d16d87797426a875&")
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
        
