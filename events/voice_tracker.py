import itertools
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from database import feedback_repo, player_repo

log = logging.getLogger(__name__)

# In-memory tracking: {(guild_id, channel_id): {user_id, ...}}
_voice_presence: dict[tuple[int, int], set[int]] = {}
# Cache of registered discord_ids to avoid DB queries every minute
_registered_ids: set[str] = set()


class VoiceTracker(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_unload(self) -> None:
        self.accumulate_hangout.cancel()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Rebuild voice presence from current state and start accumulation."""
        await self.bot.wait_until_ready()

        # Refresh registered player cache
        players = await player_repo.get_all_players(self.bot.db)
        _registered_ids.clear()
        _registered_ids.update(p["discord_id"] for p in players)

        # Scan all voice channels for current members
        _voice_presence.clear()
        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                if vc.members:
                    key = (guild.id, vc.id)
                    _voice_presence[key] = {m.id for m in vc.members}

        if not self.accumulate_hangout.is_running():
            self.accumulate_hangout.start()
        log.info("Voice tracker ready, tracking %d channels", len(_voice_presence))

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        guild_id = member.guild.id

        # Left a channel
        if before.channel and (after.channel is None or before.channel.id != after.channel.id):
            key = (guild_id, before.channel.id)
            if key in _voice_presence:
                _voice_presence[key].discard(member.id)
                if not _voice_presence[key]:
                    del _voice_presence[key]

        # Joined a channel
        if after.channel and (before.channel is None or before.channel.id != after.channel.id):
            key = (guild_id, after.channel.id)
            if key not in _voice_presence:
                _voice_presence[key] = set()
            _voice_presence[key].add(member.id)

    @tasks.loop(minutes=1)
    async def accumulate_hangout(self) -> None:
        """Every minute, accumulate 1 minute of hangout time for each registered pair."""
        for (_guild_id, _channel_id), user_ids in _voice_presence.items():
            # Filter to registered players only
            registered = [uid for uid in user_ids if str(uid) in _registered_ids]
            if len(registered) < 2:
                continue

            for a_id, b_id in itertools.combinations(registered, 2):
                await feedback_repo.upsert_hangout_time(
                    self.bot.db, str(a_id), str(b_id), 1.0
                )

    @accumulate_hangout.before_loop
    async def before_accumulate(self) -> None:
        await self.bot.wait_until_ready()


def refresh_registered_cache(discord_id: str) -> None:
    """Call when a new player registers to update the cache."""
    _registered_ids.add(discord_id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceTracker(bot))
