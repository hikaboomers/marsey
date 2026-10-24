"""
TalkAs - /say lets admins talk as a ball of their choice.

The message is sent through a channel webhook, so it shows up with the
ball's name and picture instead of the bot's.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Optional, Union

import discord
from discord import app_commands
from discord.ext import commands

try:
    from ballsdex.settings import settings
except Exception:  # pragma: no cover
    settings = None

from ballsdex.core.utils.transformers import BallTransform

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.talkas")

WEBHOOK_NAME = "TalkAs"
LOG_CHANNEL_ID = int(os.environ.get("TALKAS_LOG_CHANNEL_ID", "0") or 0)

SendableChannel = Union[discord.TextChannel, discord.Thread]


class TalkAs(commands.Cog):
    """Talk as kerns, objects and balls."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self._webhooks: dict[int, discord.Webhook] = {}

    # ------------------------------------------------------------------ checks

    async def _is_staff(self, interaction: discord.Interaction) -> bool:
        user = interaction.user
        if await self.bot.is_owner(user):
            return True
        if not isinstance(user, discord.Member):
            return False
        if user.guild_permissions.administrator:
            return True
        role_ids: set[int] = set()
        if settings is not None:
            for attr in ("root_role_ids", "admin_role_ids"):
                role_ids |= set(getattr(settings, attr, []) or [])
        return any(r.id in role_ids for r in user.roles)

    # ----------------------------------------------------------------- helpers

    def _ball_avatar(self, ball) -> Optional[str]:
        emoji_id = getattr(ball, "emoji_id", None)
        emoji = self.bot.get_emoji(emoji_id) if emoji_id else None
        return emoji.url if emoji else None

    async def _get_webhook(self, channel: SendableChannel) -> discord.Webhook:
        parent = channel.parent if isinstance(channel, discord.Thread) else channel
        assert parent is not None
        cached = self._webhooks.get(parent.id)
        if cached:
            return cached
        for hook in await parent.webhooks():
            if hook.name == WEBHOOK_NAME and hook.user == self.bot.user:
                self._webhooks[parent.id] = hook
                return hook
        hook = await parent.create_webhook(name=WEBHOOK_NAME, reason="TalkAs package")
        self._webhooks[parent.id] = hook
        return hook

    # ----------------------------------------------------------------- command

    @app_commands.command(name="say", description="Send a message as a ball of your choice")
    @app_commands.describe(
        ball="The ball to talk as",
        message="What the ball says. Type \\n for a new line",
        channel="Where to send it (default: this channel)",
        attachment="Optional image/file to send with the message",
    )
    @app_commands.guild_only()
    async def say(
        self,
        interaction: discord.Interaction,
        ball: BallTransform,
        message: app_commands.Range[str, 1, 2000],
        channel: Optional[SendableChannel] = None,
        attachment: Optional[discord.Attachment] = None,
    ):
        if not await self._is_staff(interaction):
            await interaction.response.send_message("You need to be an admin to use this.", ephemeral=True)
            return

        target = channel or interaction.channel
        if not isinstance(target, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message("Pick a text channel or thread.", ephemeral=True)
            return
        if not target.permissions_for(target.guild.me).manage_webhooks:
            await interaction.response.send_message(
                f"I need the **Manage Webhooks** permission in {target.mention}.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        name = ball.country
        avatar = self._ball_avatar(ball)

        kwargs: dict = dict(
            content=message.replace("\\n", "\n"),
            username=name[:80],
            # user and role pings work, @everyone / @here never do
            allowed_mentions=discord.AllowedMentions(everyone=False, users=True, roles=True),
            wait=True,
        )
        if avatar:
            kwargs["avatar_url"] = avatar
        if attachment:
            kwargs["file"] = await attachment.to_file()
        if isinstance(target, discord.Thread):
            kwargs["thread"] = target

        try:
            hook = await self._get_webhook(target)
            sent = await hook.send(**kwargs)
        except discord.NotFound:
            self._webhooks.clear()
            await interaction.followup.send("The webhook vanished, please try again.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.followup.send(f"Discord refused the message: `{e.text}`", ephemeral=True)
            return

        await interaction.followup.send(f"Sent as **{name}**: {sent.jump_url}", ephemeral=True)

        log.info("%s (%s) spoke as %s: %s", interaction.user, interaction.user.id, name, sent.jump_url)
        if LOG_CHANNEL_ID:
            log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if isinstance(log_channel, discord.abc.Messageable):
                try:
                    await log_channel.send(
                        f"{interaction.user.mention} spoke as **{name}** in {target.mention}: {sent.jump_url}",
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except discord.HTTPException:
                    pass
