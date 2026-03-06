import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from database import feedback_repo, player_repo

log = logging.getLogger(__name__)

# Track when players joined voice channels: {(guild_id, channel_id, user_id): join_time}
_voice_sessions: dict[tuple[int, int, int], datetime] = {}

MIN_CO_PLAY_MINUTES = 15


class VoiceTracker(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        guild_id = member.guild.id
        user_id = member.id

        # Player joined a channel
        if after.channel and (before.channel is None or before.channel.id != after.channel.id):
            _voice_sessions[(guild_id, after.channel.id, user_id)] = datetime.now(timezone.utc)

        # Player left a channel
        if before.channel and (after.channel is None or after.channel.id != before.channel.id):
            key = (guild_id, before.channel.id, user_id)
            join_time = _voice_sessions.pop(key, None)
            if join_time is None:
                return

            elapsed = (datetime.now(timezone.utc) - join_time).total_seconds() / 60
            if elapsed < MIN_CO_PLAY_MINUTES:
                return

            # Find other registered players still in that channel (or who were)
            await self._log_co_play(member, before.channel, join_time)

    async def _log_co_play(
        self,
        leaving_member: discord.Member,
        channel: discord.VoiceChannel,
        join_time: datetime,
    ) -> None:
        leaving_id = str(leaving_member.id)
        player = await player_repo.get_player(self.bot.db, leaving_id)
        if not player:
            return

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Check all other members currently in the channel
        for other in channel.members:
            if other.id == leaving_member.id:
                continue
            other_id = str(other.id)
            other_player = await player_repo.get_player(self.bot.db, other_id)
            if not other_player:
                continue
            await feedback_repo.record_co_play(self.bot.db, leaving_id, other_id, today)
            log.debug("Co-play logged: %s + %s", player["pubg_name"], other_player["pubg_name"])


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceTracker(bot))
