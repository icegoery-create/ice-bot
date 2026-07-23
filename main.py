import discord
from discord.ext import commands
from discord.ui import Button, View
import os
import asyncio

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ปุ่มกดเปิดตั๋วหน้าร้าน
class OpenTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 เปิดตั๋วเช่าคอม", style=discord.ButtonStyle.primary, custom_id="open_ticket_btn")
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        user = interaction.user
        
        # เช็กว่าเคยเปิดห้องไว้แล้วหรือยัง
        existing_channel = discord.utils.get(guild.text_channels, name=f"ticket-{user.name.lower()}")
        if existing_channel:
            await interaction.response.send_message(f"คุณมีห้องตั๋วอยู่นะครับที่ {existing_channel.mention}", ephemeral=True)
            return

        # ตั้งค่าสิทธิ์ห้องตั๋ว (เห็นแค่ลูกค้ากับแอดมิน)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        channel = await guild.create_text_channel(f"ticket-{user.name}", overwrites=overwrites)
        
        # ข้อความต้อนรับในห้องตั๋ว
        embed = discord.Embed(
            title="❄ ICE Cloud Gaming - บริการเช่าคอม",
            description="กรุณาส่งสลิปโอนเงิน และแจ้งข้อมูล/Player ID ไว้ได้เลยครับ\nรอแอดมินส่งรหัสให้สักครู่นะครับ!",
            color=discord.Color.blue()
        )
        await channel.send(embed=embed, view=CloseTicketView())
        await interaction.response.send_message(f"สร้างห้องตั๋วเรียบร้อยแล้ว: {channel.mention}", ephemeral=True)

# ปุ่มกดปิดตั๋ว (ไม่มี DM 100%)
class CloseTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 ปิดตั๋ว (สำหรับแอดมิน)", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("กำลังปิดและลบห้องนี้ใน 3 วินาที...")
        await asyncio.sleep(3)
        await interaction.channel.delete()

@bot.event
async def on_ready():
    bot.add_view(OpenTicketView())
    bot.add_view(CloseTicketView())
    print(f'บอท {bot.user} ออนไลน์พร้อมใช้งานแล้ว!')

# คำสั่งพิมพ์สร้างปุ่มหน้าร้าน (สำหรับแอดมินพิมพ์ !ticket)
@bot.command()
@commands.has_permissions(administrator=True)
async def ticket(ctx):
    await ctx.message.delete()
    embed = discord.Embed(
        title="❄ ICE Cloud Gaming ❄",
        description="กดปุ่มด้านล่างเพื่อเปิดตั๋วเช่าคอม หรือติดต่อแอดมินได้เลยครับ!",
        color=discord.Color.teal()
    )
    await ctx.send(embed=embed, view=OpenTicketView())

# ดึง Token มาใช้งาน
bot.run(os.getenv('DISCORD_TOKEN'))
