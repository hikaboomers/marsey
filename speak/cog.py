import asyncio
import io
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

from ballsdex.core.utils.transformers import BallTransform
from ballsdex.settings import settings

FONT_FILE = Path(__file__).parent / "DeterminationMonoWebRegular-Z5oq.ttf"

WIDTH = 800
HEIGHT = 250
BORDER = 8
ART_SIZE = 170
TEXT_X = 250


def get_font():
    if FONT_FILE.exists():
        return ImageFont.truetype(str(FONT_FILE), 36)
    return ImageFont.load_default(36)


def find_art(wild_card):
    name = str(wild_card).lstrip("/")
    for folder in ("", "admin_panel/media", "static/uploads", "static"):
        path = Path(folder) / name
        if path.is_file():
            return path
        path = Path(folder) / Path(name).name
        if path.is_file():
            return path
    return None


def wrap_text(text, font, max_width):
    lines = []
    line = "* "
    for word in text.split():
        if font.getlength((line + word).strip()) > max_width and line.strip(" *"):
            lines.append(line.rstrip())
            line = "  " + word + " "
        else:
            line += word + " "
    lines.append(line.rstrip())
    return lines


def make_image(art_path, text):
    img = Image.new("RGB", (WIDTH, HEIGHT), "black")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, WIDTH - 1, HEIGHT - 1], outline="white", width=BORDER)

    if art_path:
        art = Image.open(art_path).convert("RGBA")
        art.thumbnail((ART_SIZE, ART_SIZE), Image.NEAREST)
        x = 36 + (ART_SIZE - art.width) // 2
        y = 40 + (ART_SIZE - art.height) // 2
        img.paste(art, (x, y), art)

    font = get_font()
    lines = wrap_text(text, font, WIDTH - TEXT_X - BORDER - 20)
    for i, line in enumerate(lines[:4]):
        draw.text((TEXT_X, 36 + i * 48), line, font=font, fill="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def is_admin(interaction):
    user = interaction.user
    if user.id in getattr(settings, "superuser_ids", []):
        return True
    role_ids = set(getattr(settings, "root_role_ids", [])) | set(
        getattr(settings, "admin_role_ids", [])
    )
    if isinstance(user, discord.Member):
        if any(role.id in role_ids for role in user.roles):
            return True
        return user.guild_permissions.administrator
    return False


class Say(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(description="eat your kids")
    @app_commands.describe(ball="i want to say this blah blah blah", text="this is 110th street")
    async def say(
        self,
        interaction: discord.Interaction,
        ball: BallTransform,
        text: app_commands.Range[str, 1, 120],
    ):
        if not is_admin(interaction):
            await interaction.response.send_message(
                "SORRY I CANNOT FUFILL THIS REQUEST", ephemeral=True
            )
            return
        if not isinstance(interaction.channel, discord.abc.Messageable):
            await interaction.response.send_message("SORRY I CANNOT FUFILL THIS REQUEST", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        art = find_art(ball.wild_card)
        image = await asyncio.to_thread(make_image, art, text)
        await interaction.channel.send(file=discord.File(image, filename="dialog.png"))
        await interaction.followup.send("Sent.", ephemeral=True)
