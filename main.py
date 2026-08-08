import os
import json
import asyncio
from datetime import datetime, timedelta, timezone
from flask import Flask
from threading import Thread
import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, TextInput

# --- ⚙️ สวิตช์ Testing Mode (เปิด True เพื่อย่อเวลาไว้เทสระบบ / ปิด False เมื่อใช้งานจริง) ---
TESTING_MODE = True

if TESTING_MODE:
    YELLOW_THRESHOLD = timedelta(minutes=1)   # โหมดเทส: 1 นาทีกลายเป็นสีเหลือง
    RED_THRESHOLD = timedelta(minutes=3)      # โหมดเทส: 3 นาทีกลายเป็นสีแดง
    COUNTDOWN_DURATION = timedelta(seconds=30)# โหมดเทส: นับถอยหลัง 30 วินาที
    DM_COOLDOWN = 5                            # โหมดเทส: เว้นระยะส่ง DM 5 วินาที
else:
    YELLOW_THRESHOLD = timedelta(days=105)    # 3 เดือน 15 วัน
    RED_THRESHOLD = timedelta(days=180)       # 6 เดือน
    COUNTDOWN_DURATION = timedelta(days=5)    # 5 วัน
    DM_COOLDOWN = 900                         # 15 นาที

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
GUILD_ID = 1524627599416889397            # ID เซิร์ฟเวอร์ ICE Cloud Gaming
LOG_CHANNEL_ID = 1524639966162845787      # ช่องบันทึกข้อมูลลูกค้า
ALERT_CHANNEL_ID = 1535506088152010783    # ช่องแจ้งเตือน
WELCOME_CHANNEL_ID = 1524635764556697680  # ช่องยินดีต้อนรับ
LEAVE_CHANNEL_ID = 1533091589532942526    # ช่องแจ้งคนออกจากเซิร์ฟเวอร์
CUSTOMER_ROLE_ID = 1530869786169442426    # ID ยศลูกค้า
ADMIN_ROLE_ID = 1524631721641771050       # ID ยศเจ้าของร้าน/แอดมิน

# ตัวแปรจำ Player ID ชั่วคราวระหว่างเปิดตั๋ว
temp_ticket_data = {}

# --- 3. ระบบจัดการไฟล์ฐานข้อมูล local JSON ---
DATA_FILE = "player_ids.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                migrated_data = {}
                for uid, val in raw_data.items():
                    if isinstance(val, str):
                        migrated_data[uid] = {
                            "player_id": val,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                            "status": "green",
                            "dm_sent": False,
                            "dm_blocked": False,
                            "countdown_start": None
                        }
                    else:
                        migrated_data[uid] = val
                        if "dm_blocked" not in migrated_data[uid]:
                            migrated_data[uid]["dm_blocked"] = False
                return migrated_data
        except Exception:
            return {}
    return {}

def save_data(data):
    clean_data = {}
    for uid, info in data.items():
        clean_data[uid] = info.copy()
        if isinstance(clean_data[uid].get("updated_at"), datetime):
            clean_data[uid]["updated_at"] = clean_data[uid]["updated_at"].isoformat()
        if isinstance(clean_data[uid].get("countdown_start"), datetime):
            clean_data[uid]["countdown_start"] = clean_data[uid]["countdown_start"].isoformat()
            
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(clean_data, f, ensure_ascii=False, indent=4)

player_db = load_data()

# --- ฟังก์ชัน Autocomplete ค้นหารายชื่อ ป้องกัน Error ปลอดภัย 100% ---
async def player_id_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    choices = []
    try:
        db_items = list(player_db.items())
        
        for user_id_str, info in db_items:
            if isinstance(info, dict):
                pid = info.get("player_id", "-")
            else:
                pid = str(info)

            try:
                user_id_int = int(user_id_str)
            except ValueError:
                continue

            member = interaction.guild.get_member(user_id_int) if interaction.guild else None
            user = bot.get_user(user_id_int)

            if member:
                display_name = member.display_name
            elif user:
                display_name = user.name
            else:
                display_name = f"ID: {user_id_str}"

            label = f"👤 {display_name} | Player ID: {pid}"
            if len(label) > 100:
                label = label[:97] + "..."

            search_target = f"{display_name} {pid} {user_id_str}".lower()
            if not current or current.lower() in search_target:
                choices.append(app_commands.Choice(name=label, value=user_id_str))

            if len(choices) >= 25:
                break
    except Exception as e:
        print(f"⚠️ Autocomplete Error Handled: {e}")

    return choices

# --- ฟังก์ชันช่วยคำนวณเวลาอยู่ในดิสคอร์ด ---
def get_time_string(joined_at):
    if not joined_at:
        return "ไม่ทราบข้อมูล"
    now = datetime.now(timezone.utc)
    if joined_at.tzinfo is None:
        joined_at = joined_at.replace(tzinfo=timezone.utc)
    duration = now - joined_at
    days = duration.days
    hours = duration.seconds // 3600
    minutes = (duration.seconds % 3600) // 60
    if days >= 30:
        months = days // 30
        rem_days = days % 30
        return f"{months} เดือน {rem_days} วัน ({days} วัน)"
    elif days > 0:
        return f"{days} วัน {hours} ชม."
    elif hours > 0:
        return f"{hours} ชม. {minutes} นาที"
    else:
        return f"{minutes} นาที"

# --- ฟังก์ชันช่วยคำนวณระยะเวลาในสถานะปัจจุบัน ---
def get_status_duration_string(updated_at_str):
    if not updated_at_str:
        return "ไม่ทราบข้อมูล"
    try:
        updated_at = datetime.fromisoformat(updated_at_str)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        duration = now - updated_at
        days = duration.days
        hours = duration.seconds // 3600
        minutes = (duration.seconds % 3600) // 60
        if days >= 30:
            months = days // 30
            rem_days = days % 30
            return f"{months} เดือน {rem_days} วัน"
        elif days > 0:
            return f"{days} วัน {hours} ชม."
        elif hours > 0:
            return f"{hours} ชม. {minutes} นาที"
        else:
            return f"{minutes} นาที"
    except Exception:
        return "ไม่ทราบข้อมูล"

# --- 4. ปุ่มกดตอบกลับใน DM ของลูกค้า ---
class DMResponseView(View):
    def __init__(self, user_id_str):
        super().__init__(timeout=None)
        self.user_id_str = user_id_str

    @discord.ui.button(label="📁 เก็บไว้ก่อน", style=discord.ButtonStyle.success, custom_id="dm_keep_file")
    async def keep_file(self, interaction: discord.Interaction, button: Button):
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        if self.user_id_str in player_db:
            player_db[self.user_id_str]["status"] = "green"
            player_db[self.user_id_str]["updated_at"] = datetime.now(timezone.utc).isoformat()
            player_db[self.user_id_str]["dm_sent"] = False
            player_db[self.user_id_str]["dm_blocked"] = False
            player_db[self.user_id_str]["countdown_start"] = None
            save_data(player_db)

        await interaction.response.send_message("✅ ระบบได้ทำการเก็บเซฟต่อให้เรียบร้อยแล้วครับ ถ้าต้องการใช้บริการเช่าเกม ICE Cloud Gaming พร้อมต้อนรับเสมอครับ!", ephemeral=True)

    @discord.ui.button(label="🗑️ ไม่ต้องเก็บไว้", style=discord.ButtonStyle.danger, custom_id="dm_delete_file")
    async def delete_file(self, interaction: discord.Interaction, button: Button):
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        if self.user_id_str in player_db:
            pid = player_db[self.user_id_str].get("player_id", "ไม่ทราบ")
            guild = bot.guilds[0]
            alert_channel = guild.get_channel(ALERT_CHANNEL_ID)
            if alert_channel:
                await alert_channel.send(f"🚨 **แจ้งเตือนจากลูกค้า:** ลูกค้า <@{self.user_id_str}> (Player ID: `{pid}`) กดเลือก **'ไม่ต้องเก็บไฟล์เซฟไว้'** แอดมินสามารถดำเนินการลบไฟล์ได้เลยครับ!")

        await interaction.response.send_message("เข้าใจแล้วครับ ไว้โอกาสหน้ามาใช้บริการเช่าเกมได้นะครับ ICE Cloud Gaming พร้อมต้อนรับครับ!", ephemeral=True)

# --- 5. Modal กรอก Player ID ---
class PlayerIDModal(Modal, title="กรอก Player ID ให้ลูกค้า"):
    player_id_input = TextInput(
        label="Player ID",
        placeholder="กรอกเลข Player ID ที่นี่...",
        required=True,
        max_length=50
    )

    def __init__(self, target_user_id: int):
        super().__init__()
        self.target_user_id = target_user_id

    async def on_submit(self, interaction: discord.Interaction):
        pid = self.player_id_input.value.strip()
        user_id_str = str(self.target_user_id)
        
        for existing_uid, info in player_db.items():
            existing_pid = info.get("player_id") if isinstance(info, dict) else str(info)
            if existing_uid != user_id_str and existing_pid == pid:
                await interaction.response.send_message(
                    f"❌ **ข้อผิดพลาด (Player ID ซ้ำ!):**\n"
                    f"Player ID `{pid}` ถูกใช้งานไปแล้วโดยสมาชิก <@{existing_uid}>\n"
                    f"⚠️ กรุณาใช้ Player ID อื่นครับ!",
                    ephemeral=True
                )
                return

        player_db[user_id_str] = {
            "player_id": pid,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "green",
            "dm_sent": False,
            "dm_blocked": False,
            "countdown_start": None
        }
        save_data(player_db)
        
        temp_ticket_data[interaction.channel_id] = {
            "user_id": self.target_user_id,
            "player_id": pid
        }

        if interaction.guild:
            log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                log_embed = discord.Embed(
                    title="📌 บันทึกข้อมูล Player ID ลูกค้า",
                    description=f"**ลูกค้า:** <@{user_id_str}> (`{user_id_str}`)\n**Player ID:** `{pid}`",
                    color=discord.Color.gold()
                )
                await log_channel.send(embed=log_embed)

        embed = discord.Embed(
            description="หากคุณลูกค้าต้องการเช่าเล่นเกมให้กดปุ่มด้านล่างนี้เพื่อดำเนินการต่อได้เลยครับ :",
            color=discord.Color.blue()
        )

        await interaction.response.send_message(
            f"ตอนนี้เจ้าของร้านได้กรอกแล้ว \n Player IDคุณคือ `{pid}`",
            embed=embed,
            view=HasIDToRentView(),
            ephemeral=False
        )

class AdminSetIDView(View):
    def __init__(self, target_user_id: int = None):
        super().__init__(timeout=None)
        self.target_user_id = target_user_id

    @discord.ui.button(label="📝 กรอก Player ID ให้ลูกค้า", style=discord.ButtonStyle.success, custom_id="admin_set_id_btn_v5")
    async def set_id(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator and not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ เฉพาะแอดมินหรือเจ้าของร้านเท่านั้นที่กดปุ่มนี้ได้!", ephemeral=True)
            return

        user_id = self.target_user_id
        if not user_id and interaction.channel_id in temp_ticket_data:
            user_id = temp_ticket_data[interaction.channel_id].get("user_id")

        if not user_id:
            user_id = interaction.user.id

        await interaction.response.send_modal(PlayerIDModal(user_id))

# --- 6. ระบบเช็ก ID และตัวเลือกเช่าเกม ---
class CheckIDInTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔎 Player ID ของฉันคือ...", style=discord.ButtonStyle.secondary, custom_id="check_my_id_in_ticket_btn")
    async def check_id_in_ticket(self, interaction: discord.Interaction, button: Button):
        user_id = str(interaction.user.id)
        
        if user_id in player_db:
            info = player_db[user_id]
            pid = info.get("player_id", info) if isinstance(info, dict) else str(info)
            await interaction.response.send_message(f"🎮 **Player ID ของคุณคือ:** `{pid}`", ephemeral=True)
            
            embed = discord.Embed(
                description="หากคุณลูกค้าต้องการเช่าเล่นเกมให้กดปุ่มนี้เพื่อดำเนินการ :",
                color=discord.Color.blue()
            )
            await interaction.channel.send(embed=embed, view=HasIDToRentView())
        else:
            await interaction.response.send_message("❌ คุณลูกค้ายังไม่ได้ขอ Player ID จากเจ้าของร้าน กรุณาไปขอ Player ID ก่อนครับ!", ephemeral=True)

class HasIDToRentView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="มีPlayer ID ต้องการเช่า", style=discord.ButtonStyle.success, custom_id="has_id_to_rent_btn")
    async def has_id_to_rent(self, interaction: discord.Interaction, button: Button):
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        role_mention = f"<@&{ADMIN_ROLE_ID}>"
        embed = discord.Embed(
            title="🎮 ดำเนินการเช่าเล่นเกม",
            description=f"โปรดรอเจ้าของร้าน {role_mention} มาพูดคุยเพื่อเริ่มการเช่า",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

class RentGameSubTopicView(View):
    def __init__(self, user_has_id: bool = False):
        super().__init__(timeout=None)

        self.btn_request = Button(
            label="ขอPlayer ID",
            style=discord.ButtonStyle.primary,
            custom_id="sub_request_player_id",
            disabled=user_has_id
        )
        self.btn_request.callback = self.sub_request_player_id
        self.add_item(self.btn_request)

        self.btn_has_id = Button(
            label="มีPlayer ID ต้องการเช่า",
            style=discord.ButtonStyle.success,
            custom_id="sub_has_player_id",
            disabled=not user_has_id
        )
        self.btn_has_id.callback = self.sub_has_player_id
        self.add_item(self.btn_has_id)

    async def sub_request_player_id(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if user_id in player_db:
            await interaction.response.send_message("⚠️ คุณมี Player ID ในระบบอยู่แล้วครับ ไม่สามารถขอเพิ่มได้!", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        role_mention = f"<@&{ADMIN_ROLE_ID}>"
        embed = discord.Embed(
            title="🎮 หมวดหมู่: ขอ Player ID / เช่าเกม",
            description=f"เกี่ยวกับการเช่าเกม\nกรุณารอเจ้าของร้านสักครู่ {role_mention}\nเจ้าของร้านจะมารับเรื่องและกรอก Player ID ให้ครับ",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=AdminSetIDView(interaction.user.id))

    async def sub_has_player_id(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if user_id not in player_db:
            await interaction.response.send_message("❌ คุณยังไม่มี Player ID ในระบบ กรุณากดปุ่ม 'ขอPlayer ID' ก่อนครับ!", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        role_mention = f"<@&{ADMIN_ROLE_ID}>"
        embed = discord.Embed(
            title="🎮 ดำเนินการเช่าเล่นเกม",
            description=f"โปรดรอเจ้าของร้าน {role_mention} มาพูดคุยเพื่อเริ่มการเช่า",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

class TicketTopicView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="เช่าเล่นเกม", style=discord.ButtonStyle.primary, custom_id="topic_rent_game_v1")
    async def topic_rent_game(self, interaction: discord.Interaction, button: Button):
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        user_id = str(interaction.user.id)
        user_has_id = user_id in player_db

        embed = discord.Embed(
            title="🎮 เลือกตัวเลือกการเช่าเล่นเกม",
            description="กรุณาเลือกตัวเลือกที่ต้องการด้านล่างได้เลยครับ",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=RentGameSubTopicView(user_has_id=user_has_id))

    @discord.ui.button(label="สอบถามเรื่องทั่วไป", style=discord.ButtonStyle.primary, custom_id="topic_general_v4")
    async def topic_general(self, interaction: discord.Interaction, button: Button):
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        role_mention = f"<@&{ADMIN_ROLE_ID}>"
        embed = discord.Embed(
            title="💬 หมวดหมู่: สอบถามเรื่องทั่วไป",
            description=f"สอบถามเรื่องที่ไม่เข้าใจหรือเรื่องทั่วไปอื่นๆ...\nพิมพ์ข้อความทิ้งไว้ได้เลยครับ เจ้าของร้าน {role_mention} จะรีบมาตอบกลับ!",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

class CloseTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 ปิดตั๋ว", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn_v3")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator and not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ เฉพาะแอดมินหรือเจ้าของร้านเท่านั้นที่สามารถปิดตั๋วนี้ได้!", ephemeral=True)
            return

        channel_id = interaction.channel_id
        if channel_id in temp_ticket_data:
            del temp_ticket_data[channel_id]

        await interaction.response.send_message("🔒 กำลังปิดและลบห้องตั๋วนี้ภายใน 3 วินาที...")
        await asyncio.sleep(3)
        await interaction.channel.delete()

class OpenTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 เปิดตั๋วเช่าคอม", style=discord.ButtonStyle.primary, custom_id="ice_open_ticket_v13")
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
                description=(
                    f"กรุณารอเจ้าของร้านสักครู่ {role_mention} โปรดเลือกหัวข้อคุยที่ด้านล่างเลย เจ้าของร้านจะรีบมาตอบครับ!\n\n"
                    "**Bot : คุณลูกค้าต้องการคุยเกี่ยวกับอะไรครับ?**\n\n"
                    "กรุณากดเลือกหัวข้อที่ต้องการรอเจ้าของร้านก่อนได้เลยครับ"
                ),
                color=discord.Color.green()
            )
            await ticket_channel.send(content=f"{role_mention}", embed=embed, view=TicketTopicView())
            await ticket_channel.send(view=CloseTicketView())
            await interaction.followup.send(f"สร้างตั๋วเช่าเกมเรียบร้อยแล้ว\nคลิกที่นี่เพื่อใช้งานห้อง\n👉🏻{ticket_channel.mention}", ephemeral=True)
        except Exception as e:
            print(f"ERROR CREATE CHANNEL: {e}")
            await interaction.followup.send(f"เกิดข้อผิดพลาดในการสร้างห้อง: {e}", ephemeral=True)

    @discord.ui.button(label="🔎 Player ID ของฉันคือ...", style=discord.ButtonStyle.secondary, custom_id="check_my_player_id_btn_v4")
    async def check_my_id(self, interaction: discord.Interaction, button: Button):
        user_id = str(interaction.user.id)
        if user_id in player_db:
            info = player_db[user_id]
            pid = info.get("player_id", info) if isinstance(info, dict) else str(info)
            await interaction.response.send_message(f"🎮 **Player ID ของคุณคือ:** `{pid}`", ephemeral=True)
        else:
            await interaction.response.send_message("❌ คุณลูกค้ายังไม่ได้ขอ Player ID จากเจ้าของร้าน กรุณาไปขอ Player ID ก่อนครับ!", ephemeral=True)

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

# --- 7. พื้นหลังอัจฉริยะ: เช็กสถานะเวลาและคิวส่ง DM ---
@tasks.loop(seconds=10)
async def background_status_checker():
    if not bot.guilds:
        return
    guild = bot.guilds[0]
    now = datetime.now(timezone.utc)

    for user_id_str, info in list(player_db.items()):
        if not isinstance(info, dict):
            continue

        member = guild.get_member(int(user_id_str))
        if not member:
            continue

        updated_at_str = info.get("updated_at")
        if not updated_at_str:
            continue
        
        updated_at = datetime.fromisoformat(updated_at_str)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)

        elapsed = now - updated_at
        status = info.get("status", "green")
        dm_sent = info.get("dm_sent", False)
        dm_blocked = info.get("dm_blocked", False)
        countdown_start = info.get("countdown_start")

        if status == "green" and elapsed >= YELLOW_THRESHOLD and not dm_sent:
            try:
                embed_dm = discord.Embed(
                    title="🔔 แจ้งเตือนสถานะการใช้งาน ICE Cloud Gaming",
                    description=(
                        "คุณไม่ได้ใช้งาน ICE Cloud Gaming มาสักพักแล้ว\n"
                        "(ขอให้ลูกค้าตอบตามความจริง)\n\n"
                        "หากยังต้องการให้เก็บไฟล์เซฟไว้อยู่ กรุณาเลือกคำสั่งข้างล่างนี้:\n"
                        "• **เก็บไว้ก่อน**\n"
                        "• **ไม่ต้องเก็บไว้**"
                    ),
                    color=discord.Color.gold()
                )
                await member.send(embed_dm, view=DMResponseView(user_id_str))
                
                info["status"] = "yellow"
                info["dm_sent"] = True
                info["dm_blocked"] = False
                save_data(player_db)
                
            except discord.Forbidden:
                info["status"] = "yellow"
                info["dm_sent"] = True
                info["dm_blocked"] = True
                save_data(player_db)
            
            await asyncio.sleep(DM_COOLDOWN)

        elif status == "yellow" and elapsed >= RED_THRESHOLD:
            if dm_blocked:
                info["status"] = "black"
                save_data(player_db)
            else:
                info["status"] = "red"
                info["countdown_start"] = now.isoformat()
                save_data(player_db)

        elif status == "red" and countdown_start:
            cd_start_time = datetime.fromisoformat(countdown_start)
            if cd_start_time.tzinfo is None:
                cd_start_time = cd_start_time.replace(tzinfo=timezone.utc)

            if now - cd_start_time >= COUNTDOWN_DURATION:
                alert_channel = guild.get_channel(ALERT_CHANNEL_ID)
                if alert_channel:
                    await alert_channel.send(
                        f"🚨 **แจ้งเตือนหมดเวลาตอบกลับ:** สมาชิก {member.mention} (Player ID: `{info.get('player_id')}`) "
                        "ไม่ตอบกลับการแจ้งเตือนภายในกำหนดเวลา ครบกำหนดลบไฟล์เซฟแล้วครับแอดมิน!"
                    )
                info["status"] = "expired"
                save_data(player_db)

@background_status_checker.before_loop
async def before_checker():
    await bot.wait_until_ready()

# --- 8. ระบบซิงค์ข้อมูลย้อนหลัง ---
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
                        desc = embed.description
                        user_id_part = desc.split("(`")[1].split("`)")[0]
                        pid_part = desc.split("`")[3]
                        if user_id_part not in player_db:
                            player_db[user_id_part] = {
                                "player_id": pid_part,
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                                "status": "green",
                                "dm_sent": False,
                                "dm_blocked": False,
                                "countdown_start": None
                            }
                    except Exception:
                        pass
    save_data(player_db)
    print("✅ ซิงค์ข้อมูลเรียบร้อยแล้ว!")

# --- 9. ระบบ Event หลักของบอท ---
@bot.event
async def on_ready():
    bot.add_view(OpenTicketView())
    bot.add_view(CloseTicketView())
    bot.add_view(VerifyView())
    bot.add_view(TicketTopicView())
    bot.add_view(AdminSetIDView())
    bot.add_view(RentGameSubTopicView())
    bot.add_view(CheckIDInTicketView())
    bot.add_view(HasIDToRentView())
    
    guild_obj = discord.Object(id=GUILD_ID)
    
    try:
        await bot.http.bulk_upsert_global_commands(bot.application_id, [])
        bot.tree.copy_global_to(guild=guild_obj)
        synced = await bot.tree.sync(guild=guild_obj)
        print(f"✅ Sync คำสั่งเข้าเซิร์ฟเวอร์เรียบร้อย จำนวน {len(synced)} คำสั่ง")
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการ Sync Slash Commands: {e}")

    if not background_status_checker.is_running():
        background_status_checker.start()
        
    bot.loop.create_task(sync_data_from_channel())
    print(f'บอท {bot.user} ออนไลน์พร้อมใช้งานแล้ว! (Testing Mode: {TESTING_MODE})')

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

@bot.event
async def on_member_remove(member: discord.Member):
    leave_channel = member.guild.get_channel(LEAVE_CHANNEL_ID)
    if not leave_channel:
        return
    time_spent = get_time_string(member.joined_at)
    user_id_str = str(member.id)
    player_id = "❌ ไม่มีข้อมูล / ไม่เคยขอ ID"
    if user_id_str in player_db:
        info = player_db[user_id_str]
        player_id = info.get("player_id", info) if isinstance(info, dict) else str(info)

    embed = discord.Embed(
        title="🚪 สมาชิกออกจากเซิร์ฟเวอร์!",
        description=f"คุณ **{member.display_name}** (`{member.name}`) ได้ออกจากเซิร์ฟเวอร์เรียบร้อยแล้ว",
        color=discord.Color.red()
    )
    avatar_url = member.display_avatar.url if member.display_avatar else member.default_avatar.url
    embed.set_thumbnail(url=avatar_url)
    embed.add_field(name="👤 ผู้ใช้งาน", value=f"{member.mention} (`ID: {member.id}`)", inline=False)
    embed.add_field(name="🎮 Player ID (สำหรับลบไฟล์เซฟ)", value=f"`{player_id}`", inline=False)
    embed.add_field(name="⏱️ ระยะเวลาที่เคยอยู่ในดิส", value=f"`{time_spent}`", inline=False)
    embed.set_footer(text="ICE Cloud Gaming - System Notification", icon_url=member.guild.icon.url if member.guild.icon else None)
    await leave_channel.send(embed=embed)

# --- 10. Slash Commands (คำสั่งรหัส /) ---

# 10.1 คำสั่งลบ Player ID รายบุคคล (ลบข้อมูล + ลบการ์ด Log ในช่องบันทึกข้อมูลเฉพาะของคนที่ถูกลบ)
@bot.tree.command(name="delete_id", description="ลบข้อมูล Player ID ของสมาชิกรายบุคคล (เฉพาะแอดมิน)")
@app_commands.describe(
    member1="เลือกสมาชิกคนที่ 1 ที่ต้องการลบ (หรือพิมพ์ค้นหา)",
    member2="เลือกสมาชิกคนที่ 2 (ถ้ามี)",
    member3="เลือกสมาชิกคนที่ 3 (ถ้ามี)",
    member4="เลือกสมาชิกคนที่ 4 (ถ้ามี)",
    member5="เลือกสมาชิกคนที่ 5 (ถ้ามี)"
)
@app_commands.autocomplete(
    member1=player_id_autocomplete,
    member2=player_id_autocomplete,
    member3=player_id_autocomplete,
    member4=player_id_autocomplete,
    member5=player_id_autocomplete
)
@app_commands.checks.has_permissions(administrator=True)
async def delete_user_id(
    interaction: discord.Interaction,
    member1: str,
    member2: str = None,
    member3: str = None,
    member4: str = None,
    member5: str = None
):
    raw_inputs = [m for m in [member1, member2, member3, member4, member5] if m is not None]
    guild = interaction.guild

    deleted_text_list = []
    not_found_text_list = []
    processed_uids = set()

    for inp in raw_inputs:
        clean_inp = inp.strip("<@!> ")
        target_uid = None

        if clean_inp.isdigit() and clean_inp in player_db:
            target_uid = clean_inp
        else:
            for uid, info in player_db.items():
                pid = info.get("player_id", "") if isinstance(info, dict) else str(info)
                mem = guild.get_member(int(uid)) if guild else None
                m_name = mem.display_name if mem else ""
                
                if inp == pid or inp.lower() == m_name.lower():
                    target_uid = uid
                    break

        if target_uid:
            if target_uid not in processed_uids:
                processed_uids.add(target_uid)
                info = player_db[target_uid]
                pid = info.get("player_id", "ไม่ทราบ") if isinstance(info, dict) else str(info)
                mem = guild.get_member(int(target_uid)) if guild else None
                mention_str = mem.mention if mem else f"<@{target_uid}>"
                deleted_text_list.append(f"{mention_str} (Player ID: `{pid}`)")
                del player_db[target_uid]
        else:
            not_found_text_list.append(f"`{inp}`")

    save_data(player_db)

    # ⚡ สแกนลบการ์ด Log ในช่อง #บันทึกข้อมูลลูกค้า เฉพาะของคนที่ถูกลบ
    if processed_uids and guild:
        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            try:
                async for msg in log_channel.history(limit=200):
                    if msg.embeds:
                        for embed in msg.embeds:
                            if embed.description:
                                for uid in processed_uids:
                                    if uid in embed.description:
                                        try:
                                            await msg.delete()
                                        except Exception:
                                            pass
                                        break
            except Exception as e:
                print(f"⚠️ Error deleting log embeds: {e}")

    if deleted_text_list:
        result_str = ", ".join(deleted_text_list)
        msg = f"ระบบได้ลบPlayer ID ของ {result_str} ให้แล้ว"
        if not_found_text_list:
            msg += f"\n(หมายเหตุ: {', '.join(not_found_text_list)} ไม่พบในระบบ)"
        await interaction.response.send_message(msg)
    else:
        await interaction.response.send_message("❌ ไม่พบข้อมูล Player ID ของสมาชิกที่เลือกในระบบครับ", ephemeral=True)

# 10.2 คำสั่งลบข้อความในช่องปัจจุบัน (/clear)
@bot.tree.command(name="clear", description="ลบข้อความในช่องปัจจุบันตามจำนวนที่กำหนด (เฉพาะแอดมิน)")
@app_commands.describe(amount="จำนวนข้อความที่ต้องการลบ (เช่น 10, 50, 100)")
@app_commands.checks.has_permissions(administrator=True)
async def clear_messages(interaction: discord.Interaction, amount: int):
    if amount <= 0:
        await interaction.response.send_message("❌ กรุณาระบุจำนวนข้อความที่มากกว่า 0 ครับ", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🧹 ลบข้อความไปทั้งหมด `{len(deleted)}` ข้อความเรียบร้อยแล้วครับ!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ เกิดข้อผิดพลาดในการลบข้อความ: {e}", ephemeral=True)

# 10.3 คำสั่งส่งไฟล์สรุปรายงานสถานะ
@bot.tree.command(name="idlist", description="ส่งไฟล์สรุปรายงานสถานะสมาชิกทั้งหมด (เฉพาะแอดมิน)")
@app_commands.checks.has_permissions(administrator=True)
async def export_id_list(interaction: discord.Interaction):
    await interaction.response.defer()
    guild = interaction.guild
    file_path = "player_ids_summary.txt"
    
    if TESTING_MODE:
        green_time_label = "น้อยกว่า 1 นาที"
        yellow_time_label = "1 - 3 นาที"
        red_time_label = "มากกว่า 3 นาทีขึ้นไป"
        black_time_label = "ถึงเวลา 3 นาทีขึ้นไปแต่ปิด DM"
    else:
        green_time_label = "น้อยกว่า 3 เดือน 15 วัน"
        yellow_time_label = "3 เดือน 15 วัน - 6 เดือน"
        red_time_label = "มากกว่า 6 เดือนขึ้นไป"
        black_time_label = "ถึงเวลา 6 เดือนขึ้นไปแต่ปิด DM"

    with open(file_path, "w", encoding="utf-8-sig") as f:
        f.write("=== รายงานสถานะ Player ID และสมาชิก ICE Cloud Gaming ===\n\n")
        
        black_list, red_list, yellow_list, green_list, gray_list = [], [], [], [], []

        for member in guild.members:
            if member.bot:
                continue
            uid = str(member.id)
            time_spent = get_time_string(member.joined_at)
            
            if uid in player_db:
                info = player_db[uid]
                if isinstance(info, dict):
                    status = info.get("status", "green")
                    pid = info.get("player_id", "-")
                    status_dur = get_status_duration_string(info.get("updated_at"))
                else:
                    status = "green"
                    pid = str(info)
                    status_dur = "ไม่ทราบข้อมูล"
                
                line = f"[{member.display_name}] | ID: {pid} | อยู่ในสถานะนี้: {status_dur} | อยู่ในดิส: {time_spent}"
                
                if status == "black":
                    black_list.append(f"🖤 {line}")
                elif status in ["red", "expired"]:
                    red_list.append(f"🔴 {line}")
                elif status == "yellow":
                    yellow_list.append(f"🟡 {line}")
                else:
                    green_list.append(f"🟢 {line}")
            else:
                gray_list.append(f"⚪ [{member.display_name}] | อยู่ในดิส: {time_spent}")

        f.write(f"--- 🖤 สถานะสีดำ (ปิด DM / ติดต่อไม่ได้) [เกณฑ์เวลา: {black_time_label}] ---\n" + ("\n".join(black_list) or "ไม่มี") + "\n\n")
        f.write(f"--- 🔴 สถานะสีแดง (นานมาก / รอการจัดการ) [เกณฑ์เวลา: {red_time_label}] ---\n" + ("\n".join(red_list) or "ไม่มี") + "\n\n")
        f.write(f"--- 🟡 สถานะสีเหลือง (กลางๆ / กำลังแจ้งเตือน) [เกณฑ์เวลา: {yellow_time_label}] ---\n" + ("\n".join(yellow_list) or "ไม่มี") + "\n\n")
        f.write(f"--- 🟢 สถานะสีเขียว (สบายๆ / ใช้งานปกติ) [เกณฑ์เวลา: {green_time_label}] ---\n" + ("\n".join(green_list) or "ไม่มี") + "\n\n")
        f.write("--- ⚪ สถานะสีเทา (ไม่มี Player ID) ---\n" + ("\n".join(gray_list) or "ไม่มี") + "\n")

    await interaction.followup.send("📊 **รายงานสรุปสถานะสมาชิกทั้งหมดจัดเรียงตามลำดับความสำคัญครับ:**", file=discord.File(file_path))
    if os.path.exists(file_path):
        os.remove(file_path)

# 10.4 คำสั่งเช็กข้อมูลผู้ใช้รายคน
@bot.tree.command(name="checkuser", description="ตรวจสอบข้อมูล Player ID และสถานะของสมาชิก (เฉพาะแอดมิน)")
@app_commands.describe(member="เลือกสมาชิกที่ต้องการตรวจสอบ")
@app_commands.checks.has_permissions(administrator=True)
async def check_user(interaction: discord.Interaction, member: discord.Member):
    user_id_str = str(member.id)
    time_spent = get_time_string(member.joined_at)
    
    if user_id_str in player_db:
        info = player_db[user_id_str]
        if isinstance(info, dict):
            pid = info.get("player_id", "-")
            status = info.get("status", "green")
            status_dur = get_status_duration_string(info.get("updated_at"))
        else:
            pid = str(info)
            status = "green"
            status_dur = "ไม่ทราบข้อมูล"
    else:
        pid = "❌ ไม่มีข้อมูล / ไม่เคยขอ ID"
        status = "gray (สีเทา)"
        status_dur = "ไม่มีข้อมูล"

    embed = discord.Embed(title="🔎 ตรวจสอบข้อมูลสมาชิก", color=discord.Color.blue())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 ชื่อสมาชิก", value=f"{member.mention} (`{member.name}`)", inline=False)
    embed.add_field(name="🎮 Player ID", value=f"`{pid}`", inline=False)
    embed.add_field(name="🎨 สถานะปัจจุบัน", value=f"`{status}` (อยู่ในสถานะนี้มา: `{status_dur}`)", inline=False)
    embed.add_field(name="⏱️ ระยะเวลาที่อยู่ในดิสคอร์ด", value=f"`{time_spent}`", inline=False)
    
    await interaction.response.send_message(embed=embed)

# 10.5 คำสั่งส่งแผงเปิดตั๋ว
@bot.tree.command(name="ticket", description="ส่งแผงข้อความกดเปิดตั๋วเช่าคอม/เช่าเกม (เฉพาะแอดมิน)")
@app_commands.checks.has_permissions(administrator=True)
async def ticket(interaction: discord.Interaction):
    embed = discord.Embed(
        title="❄️ ICE Cloud Gaming | บริการเช่าเล่นเกม",
        description="กดเปิดแชทเพื่อเริ่มขอ Player ID และ OTP หรือสอบถามข้อมูลเพิ่มเติมครับ",
        color=discord.Color.blue()
    )
    embed.set_image(url="https://cdn.discordapp.com/attachments/1525449388212748328/1525711847817478215/5035230a3313e71c85e3a8c8e9d63174e547958b99d80015c52c3233eecbb7ab.png?ex=6a638aa2&is=6a623922&hm=3100db3f8c1af503c8df06a3cac534578b7b28415265f208d16d87797426a875&")
    embed.set_footer(text="Powered by ICE Cloud Gaming", icon_url=bot.user.avatar.url if bot.user.avatar else None)
    
    await interaction.response.send_message("ส่งแผงกดตั๋วสำเร็จ!", ephemeral=True)
    await interaction.channel.send(embed=embed, view=OpenTicketView())

# 10.6 คำสั่งส่งแผงยืนยันตัวตนรับยศ
@bot.tree.command(name="setupverify", description="ส่งแผงข้อความกดยืนยันตัวตนรับยศลูกค้า (เฉพาะแอดมิน)")
@app_commands.checks.has_permissions(administrator=True)
async def setupverify(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛡️ ยืนยันตัวตนเพื่อเข้าสู่เซิร์ฟเวอร์",
        description="กรุณากดปุ่ม **'✅ รับยศลูกค้า'** ด้านล่าง เพื่อปลดล็อกช่องพูดคุยและบริการทั้งหมดของ ICE Cloud Gaming ครับ!",
        color=discord.Color.gold()
    )
    await interaction.response.send_message("ส่งแผงยืนยันตัวตนสำเร็จ!", ephemeral=True)
    await interaction.channel.send(embed=embed, view=VerifyView())

# 10.7 คำสั่งรีเซ็ตข้อมูลทั้งหมด
@bot.tree.command(name="reset_id", description="รีเซ็ตข้อมูล Player ID ทั้งหมดในระบบ (เฉพาะแอดมิน)")
@app_commands.checks.has_permissions(administrator=True)
async def reset_data(interaction: discord.Interaction):
    player_db.clear()
    temp_ticket_data.clear()
    save_data(player_db)
    
    log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        try:
            await log_channel.purge(limit=500)
        except Exception:
            pass
            
    await interaction.response.send_message("🧹 **รีเซ็ตข้อมูล Player ID ทั้งหมดเรียบร้อยแล้ว!**")

# --- 11. ตัวดักจับ Error กรณีผู้ใช้ไม่มีสิทธิ์กดใช้ Slash Command ---
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้ครับ! (เฉพาะแอดมินเท่านั้น)", ephemeral=True)
    else:
        print(f"AppCommand Error: {error}")

# --- 12. เริ่มต้นรันบอท ---
if __name__ == "__main__":
    keep_alive()
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("ERROR: ไม่พบ DISCORD_TOKEN")
