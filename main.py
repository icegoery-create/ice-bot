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
intents.members = True # เปิดใช้งาน Intent สมาชิกเพื่อตรวจจับการเข้าเซิร์ฟเวอร์/ให้ยศ
bot = commands.Bot(command_prefix="!", intents=intents)

# --- 3. ปุ่มกดรับยศ (Verification View) ---
class VerifyView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ รับยศลูกค้า", style=discord.ButtonStyle.success, custom_id="verify_role_btn")
    async def verify_role(self, interaction: discord.Interaction, button: Button):
        role_id = 1530869786169442426  # ID ยศลูกค้าของพี่
        role = interaction.guild.get_role(role_id)

        if not role:
            await interaction.response.send_message("❌ ไม่พบยศนี้ในระบบ กรุณาติดต่อแอดมิน", ephemeral=True)
            return

        # ตรวจสอบว่ามีรอยส์อยู่แล้วหรือยัง
        if role in interaction.user.roles:
            await interaction.response.send_message("⚠️ คุณได้รับยศลูกค้าเรียบร้อยแล้วครับ!", ephemeral=True)
            return

        # ทำการเพิ่มยศให้สมาชิก
        try:
            await interaction.user.add_roles(role)
            await interaction.response.send_message("🎉 ยืนยันตัวตนสำเร็จ! ปลดล็อกห้องทั้งหมดเรียบร้อยแล้วครับ", ephemeral=True)
        except Exception as e:
            print(f"Error assigning role: {e}")
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการมอบยศ กรุณาแจ้งแอดมิน", ephemeral=True)

# --- 4. ปุ่มกดปิดตั๋ว (Close Ticket) เฉพาะแอดมิน/เจ้าของร้าน ---
class CloseTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 ปิดตั๋ว", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn_v2")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator and not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ เฉพาะแอดมินหรือเจ้าของร้านเท่านั้นที่สามารถปิดตั๋วนี้ได้!", ephemeral=True)
            return

        await interaction.response.send_message("🔒 กำลังปิดและลบห้องตั๋วนี้ภายใน 3 วินาที...")
        await asyncio.sleep(3)
        await interaction.channel.delete()

# --- 5. ปุ่มกดเปิดตั๋วหน้าร้าน ---
class OpenTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 เปิดตั๋วเช่าคอม", style=discord.ButtonStyle.primary, custom_id="ice_open_ticket_v9")
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        user = interaction.user

        if not guild:
            await interaction.followup.send("คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์ครับ", ephemeral=True)
            return

        display_name = user.display_name.lower().replace(" ", "-")
        channel_name = f"ห้องตั๋วเช่าเกม-{display_name}"
        
        existing_channel = discord.utils.get(guild.channels, name=channel_name)
        if existing_channel:
            await interaction.followup.send(f"คุณมีช่องตั๋วอยู่แล้วโปรดคลิกที่นี่เพื่อใช้งาน 👉🏻\n{existing_channel.mention}", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, view_channel=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True)
        }

        category = interaction.channel.category

        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name, 
                overwrites=overwrites,
                category=category
            )

            role_id_admin = "1524631721641771050"
            role_mention = f"<@&{role_id_admin}>"

            embed = discord.Embed(
                title="❄️ ICE Cloud Gaming - ยินดีต้อนรับ",
                description=f"กรุณารอเจ้าของร้านสักครู่ {role_mention} ถ้ามีคำถามอะไรให้พิมพ์ทิ้งไว้ เจ้าของร้านจะรีบมาตอบครับ!",
                color=discord.Color.green()
            )
            
            await ticket_channel.send(content=f"{role_mention}", embed=embed, view=CloseTicketView())
            await interaction.followup.send(f"สร้างตั๋วเช่าเกมเรียบร้อยแล้ว\nคลิกที่นี่เพื่อใช้งานห้อง\n👉🏻{ticket_channel.mention}", ephemeral=True)

        except Exception as e:
            print(f"ERROR CREATE CHANNEL: {e}")
            await interaction.followup.send(f"เกิดข้อผิดพลาดในการสร้างห้อง: {e}", ephemeral=True)

@bot.event
async def on_ready():
    bot.add_view(OpenTicketView())
    bot.add_view(CloseTicketView())
    bot.add_view(VerifyView()) # ลงทะเบียนปุ่มรับยศให้อยู่ถาวร
    print(f'บอท {bot.user} ออนไลน์พร้อมใช้งานแล้ว!')

# --- 6. ระบบตรวจจับการรับยศ เพื่อส่งข้อความต้อนรับ ---
@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    role_id = 1530869786169442426  # ID ยศลูกค้า
    welcome_channel_id = 1524635764556697680  # ID ห้องยินดีต้อนรับ

    role = after.guild.get_role(role_id)
    if not role:
        return

    # เช็กว่าตอนแรกยังไม่มี แต่ตอนนี้ได้ยศนี้แล้ว
    if role not in before.roles and role in after.roles:
        welcome_channel = after.guild.get_channel(welcome_channel_id)
        if welcome_channel:
            # สร้าง Embed ต้อนรับพร้อมรูปโปรไฟล์ลูกค้า (Thumbnail)
            embed = discord.Embed(
                title="✨ สมาชิกใหม่รับยศสำเร็จ!",
                description=f"ยินดีต้อนรับคุณ **{after.display_name}** ลูกค้าใหม่เข้าสู่เซิร์ฟเวอร์ ICE Cloud Gaming! 🎮\n\nหากต้องการเช่าเกมหรือสอบถามข้อมูล สามารถเปิดตั๋วติดต่อแอดมินได้เลยนะครับ ขอให้สนุกกับการเล่นเกมครับ!",
                color=discord.Color.blue()
            )
            # ดึงรูปโปรไฟล์ลูกค้ามาแปะมุมขวาบน
            if after.avatar:
                embed.set_thumbnail(url=after.avatar.url)
            else:
                embed.set_thumbnail(url=after.default_avatar.url)

            embed.set_footer(text="ICE Cloud Gaming Community", icon_url=after.guild.icon.url if after.guild.icon else None)

            await welcome_channel.send(content=f"{after.mention}", embed=embed)

@bot.command()
async def ticket(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    embed = discord.Embed(
        title="❄️ ICE Cloud Gaming | บริการเช่าเล่นเกม",
        description="กดเปิดแชทเพื่อเริ่มขอ Player ID และ OTP หรือสอบถามข้อมูลเพิ่มเติมครับ",
        color=discord.Color.blue()
    )
    
    embed.set_image(url="https://cdn.discordapp.com/attachments/1525449388212748328/1525711847817478215/5035230a3313e71c85e3a8c8e9d63174e547958b99d80015c52c3233eecbb7ab.png?ex=6a638aa2&is=6a623922&hm=3100db3f8c1af503c8df06a3cac534578b7b28415265f208d16d87797426a875&")
    embed.set_footer(text="Powered by ICE Cloud Gaming", icon_url=bot.user.avatar.url if bot.user.avatar else None)

    await ctx.send(embed=embed, view=OpenTicketView())

# --- คำสั่งสำหรับสร้างปุ่มรับยศในห้อง #รับยศ (พิมพ์ครั้งเดียวแล้วลบได้) ---
@bot.command()
@commands.has_permissions(administrator=True)
async def setupverify(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    embed = discord.Embed(
        title="🛡️ ยืนยันตัวตนเพื่อเข้าสู่เซิร์ฟเวอร์",
        description="กรุณากดปุ่ม **'✅ รับยศลูกค้า'** ด้านล่าง เพื่อปลดล็อกช่องพูดคุยและบริการทั้งหมดของ ICE Cloud Gaming ครับ!",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed, view=VerifyView())

# --- 7. สั่งรันบอท ---
if __name__ == "__main__":
    keep_alive()
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("ERROR: ไม่พบ DISCORD_TOKEN")
    
