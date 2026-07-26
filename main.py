import os
import json
import asyncio
from flask import Flask
from threading import Thread
import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput

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
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- ID ค่าคงที่ของระบบ ---
LOG_CHANNEL_ID = 1524639966169442427  # ช่องบันทึกข้อมูลลูกค้า
WELCOME_CHANNEL_ID = 1524635764556697680  # ช่องยินดีต้อนรับ
CUSTOMER_ROLE_ID = 1530869786169442426  # ID ยศลูกค้า
ADMIN_ROLE_ID = 1524631721641771050  # ID ยศเจ้าของร้าน/แอดมิน

# ตัวแปรจำ Player ID ชั่วคราวระหว่างเปิดตั๋ว {channel_id: {"user_id": int, "player_id": str}}
temp_ticket_data = {}

# --- 3. ระบบจัดการไฟล์ฐานข้อมูล local JSON ---
DATA_FILE = "player_ids.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

player_db = load_data()

# --- 4. Modal ป๊อปอัปให้เจ้าของร้านกรอก Player ID ---
class PlayerIDModal(Modal, title="กรอก Player ID ให้ลูกค้า"):
    player_id_input = TextInput(
        label="Player ID",
        placeholder="กรอกเลข Player ID ที่นี่...",
        required=True,
        max_length=50
    )

    def __init__(self, target_user: discord.User):
        super().__init__()
        self.target_user = target_user

    async def on_submit(self, interaction: discord.Interaction):
        pid = self.player_id_input.value.strip()
        temp_ticket_data[interaction.channel_id] = {
            "user_id": self.target_user.id,
            "player_id": pid
        }
        await interaction.response.send_message(
            f"✅ บันทึก Player ID: `{pid}` ให้คุณ {self.target_user.mention} เรียบร้อยแล้ว!\n(ระบบจะเซฟลงฐานข้อมูลถาวรเมื่อกดปิดตั๋ว)",
            ephemeral=False
        )

# --- 5. ปุ่มสำหรับแอดมินกรอก ID ในห้องตั๋ว ---
class AdminSetIDView(View):
    def __init__(self, target_user: discord.User):
        super().__init__(timeout=None)
        self.target_user = target_user

    @discord.ui.button(label="📝 กรอก Player ID ให้ลูกค้า", style=discord.ButtonStyle.success, custom_id="admin_set_id_btn")
    async def set_id(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator and not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ เฉพาะแอดมินหรือเจ้าของร้านเท่านั้นที่กดปุ่มนี้ได้!", ephemeral=True)
            return

        await interaction.response.send_modal(PlayerIDModal(self.target_user))

# --- 6. ปุ่มเลือกประเภทตั๋ว (Player ID / สอบถามทั่วไป) ---
class TicketTopicView(View):
    def __init__(self, target_user: discord.User):
        super().__init__(timeout=None)
        self.target_user = target_user

    @discord.ui.button(label="Player ID", style=discord.ButtonStyle.primary, custom_id="topic_player_id")
    async def topic_player_id(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.target_user.id:
            await interaction.response.send_message("❌ เฉพาะเจ้าของตั๋วเท่านั้นที่เลือกได้ครับ", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎮 หมวดหมู่: ขอ Player ID / เช่าเกม",
            description=f"กรุณารอเจ้าของร้านสักครู่ <@&{ADMIN_ROLE_ID}>\nเจ้าของร้านจะมารับเรื่องและกรอก Player ID ให้ครับ",
            color=discord.Color.blue()
        )
        # ปิดการเลือก และส่งปุ่มกรอก ID ให้แอดมิน
        self.disable_all_items()
        await interaction.response.edit_message(embed=interaction.message.embeds[0], view=self)
        await interaction.channel.send(embed=embed, view=AdminSetIDView(self.target_user))

    @discord.ui.button(label="สอบถามเรื่องทั่วไป", style=discord.ButtonStyle.secondary, custom_id="topic_general")
    async def topic_general(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.target_user.id:
            await interaction.response.send_message("❌ เฉพาะเจ้าของตั๋วเท่านั้นที่เลือกได้ครับ", ephemeral=True)
            return

        embed = discord.Embed(
            title="💬 หมวดหมู่: สอบถามเรื่องทั่วไป",
            description=f"พิมพ์ข้อความหรือคำถามทิ้งไว้ได้เลยครับ เจ้าของร้าน <@&{ADMIN_ROLE_ID}> จะรีบมาตอบกลับ!",
            color=discord.Color.green()
        )
        self.disable_all_items()
        await interaction.response.edit_message(embed=interaction.message.embeds[0], view=self)
        await interaction.channel.send(embed=embed)

# --- 7. ปุ่มปิดตั๋ว (Close Ticket) ---
class CloseTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 ปิดตั๋ว", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn_v3")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator and not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ เฉพาะแอดมินหรือเจ้าของร้านเท่านั้นที่สามารถปิดตั๋วนี้ได้!", ephemeral=True)
            return

        channel_id = interaction.channel_id

        # หากมีการกรอก Player ID ไว้ในห้องนี้ ให้ทำการบันทึกข้อมูลถาวร
        if channel_id in temp_ticket_data:
            data = temp_ticket_data[channel_id]
            user_id = str(data["user_id"])
            pid = data["player_id"]

            # เซฟลงฐานข้อมูล local
            player_db[user_id] = pid
            save_data(player_db)

            # ส่งเข้าช่อง #บันทึกข้อมูลลูกค้า
            log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                log_embed = discord.Embed(
                    title="📌 บันทึกข้อมูล Player ID ลูกค้า",
                    description=f"**ลูกค้า:** <@{user_id}> (`{user_id}`)\n**Player ID:** `{pid}`",
                    color=discord.Color.gold()
                )
                await log_channel.send(embed=log_embed)

            # ลบข้อมูลชั่วคราวออก
            del temp_ticket_data[channel_id]

        await interaction.response.send_message("🔒 กำลังปิดและลบห้องตั๋วนี้ภายใน 3 วินาที...")
        await asyncio.sleep(3)
        await interaction.channel.delete()

# --- 8. ปุ่มกดเปิดตั๋วหน้าร้าน + ปุ่มเช็ก Player ID ของฉัน ---
class OpenTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 เปิดตั๋วเช่าคอม", style=discord.ButtonStyle.primary, custom_id="ice_open_ticket_v10")
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

            role_mention = f"<@&{ADMIN_ROLE_ID}>"

            embed = discord.Embed(
                title="❄️ ICE Cloud Gaming - ยินดีต้อนรับ",
                description=f"สวัสดีครับ {user.mention}\n**Bot : คุณลูกค้าต้องการคุยเกี่ยวกับอะไรครับ?**\nกรุณากดเลือกหัวข้อที่ต้องการด้านล่างได้เลยครับ",
                color=discord.Color.green()
            )
            
            await ticket_channel.send(content=f"{role_mention}", embed=embed, view=TicketTopicView(user))
            await ticket_channel.send(view=CloseTicketView())
            
            await interaction.followup.send(f"สร้างตั๋วเช่าเกมเรียบร้อยแล้ว\nคลิกที่นี่เพื่อใช้งานห้อง\n👉🏻{ticket_channel.mention}", ephemeral=True)

        except Exception as e:
            print(f"ERROR CREATE CHANNEL: {e}")
            await interaction.followup.send(f"เกิดข้อผิดพลาดในการสร้างห้อง: {e}", ephemeral=True)

    @discord.ui.button(label="🔎 Player ID ของฉันคือ...", style=discord.ButtonStyle.secondary, custom_id="check_my_player_id_btn")
    async def check_my_id(self, interaction: discord.Interaction, button: Button):
        user_id = str(interaction.user.id)
        
        # ค้นหาในฐานข้อมูล
        if user_id in player_db:
            pid = player_db[user_id]
            await interaction.response.send_message(f"🎮 **Player ID ของคุณคือ:** `{pid}`", ephemeral=True)
        else:
            await interaction.response.send_message("❌ คุณลูกค้ายังไม่ได้ขอ Player ID จากเจ้าของร้าน กรุณาไปขอ Player ID ก่อนครับ!", ephemeral=True)

# --- 9. ปุ่มรับยศลูกค้า ---
class VerifyView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ รับยศลูกค้า", style=discord.ButtonStyle.success, custom_id="verify_role_btn")
    async def verify_role(self, interaction: discord.Interaction, button: Button):
        role = interaction.guild.get_role(CUSTOMER_ROLE_ID)
        welcome_channel = interaction.guild.get_channel(WELCOME_CHANNEL_ID)

        if not role:
            await interaction.response.send_message("❌ ไม่พบยศนี้ในระบบ กรุณาติดต่อแอดมิน", ephemeral=True)
            return

        if role in interaction.user.roles:
            welcome_link = welcome_channel.mention if welcome_channel else "หน้ายินดีต้อนรับ"
            await interaction.response.send_message(f"⚠️ คุณได้รับยศลูกค้าเรียบร้อยแล้วครับ!\n👉🏻 ไปที่ {welcome_link}", ephemeral=True)
            return

        try:
            await interaction.user.add_roles(role)
            welcome_link = welcome_channel.mention if welcome_channel else "หน้ายินดีต้อนรับ"
            await interaction.response.send_message(f"🎉 ยืนยันตัวตนสำเร็จ!\n👉🏻 คลิกที่นี่เพื่อไปหน้ายินดีต้อนรับ: {welcome_link}", ephemeral=True)
        except Exception as e:
            print(f"Error assigning role: {e}")
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการมอบยศ กรุณาแจ้งแอดมิน", ephemeral=True)

# --- 10. ระบบซิงค์ข้อมูลย้อนหลังเมื่อบอทออนไลน์ ---
async def sync_data_from_channel():
    await bot.wait_until_ready()
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        return

    print("🔄 กำลังสแกนซิงค์ข้อมูล Player ID จากช่องบันทึกข้อมูล...")
    async for msg in log_channel.history(limit=500):
        if msg.embeds:
            for embed in msg.embeds:
                if embed.description and "**Player ID:**" in embed.description:
                    try:
                        # ดึง user_id และ player_id จาก embed
                        desc = embed.description
                        user_id_part = desc.split("(`")[1].split("`)")[0]
                        pid_part = desc.split("`")[3]
                        player_db[user_id_part] = pid_part
                    except Exception:
                        pass
    save_data(player_db)
    print("✅ ซิงค์ข้อมูลเรียบร้อยแล้ว!")

@bot.event
async def on_ready():
    bot.add_view(OpenTicketView())
    bot.add_view(CloseTicketView())
    bot.add_view(VerifyView())
    bot.loop.create_task(sync_data_from_channel())
    print(f'บอท {bot.user} ออนไลน์พร้อมใช้งานแล้ว!')

# --- 11. ต้อนรับสมาชิกใหม่เมื่อได้รับยศ ---
@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    role = after.guild.get_role(CUSTOMER_ROLE_ID)
    if not role:
        return

    if role not in before.roles and role in after.roles:
        welcome_channel = after.guild.get_channel(WELCOME_CHANNEL_ID)
        if welcome_channel:
            embed = discord.Embed(
                title="✨ สมาชิกใหม่รับยศสำเร็จ!",
                description=f"ยินดีต้อนรับคุณ **{after.display_name}** ลูกค้าใหม่เข้าสู่เซิร์ฟเวอร์ ICE Cloud Gaming! 🎮\n\nหากต้องการเช่าเกมหรือสอบถามข้อมูล สามารถเปิดตั๋วติดต่อแอดมินได้เลยนะครับ ขอให้สนุกกับการเล่นเกมครับ!",
                color=discord.Color.blue()
            )
            if after.avatar:
                embed.set_thumbnail(url=after.avatar.url)
            else:
                embed.set_thumbnail(url=after.default_avatar.url)

            embed.set_footer(text="ICE Cloud Gaming Community", icon_url=after.guild.icon.url if after.guild.icon else None)
            await welcome_channel.send(embed=embed)

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

# --- 12. สั่งรันบอท ---
if __name__ == "__main__":
    keep_alive()
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("ERROR: ไม่พบ DISCORD_TOKEN")
        
