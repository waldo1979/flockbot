"""Per-user command cooldown decorator for app_commands."""

import time
from collections import defaultdict
from functools import wraps

import discord
from discord import app_commands


# Global tracker: command_name -> {discord_id -> last_used_timestamp}
_cooldowns: dict[str, dict[str, float]] = defaultdict(dict)


def cooldown(seconds: int):
    """Decorator that enforces a per-user cooldown on an app_command callback.

    Usage:
        @app_commands.command(...)
        @cooldown(30)
        async def my_command(self, interaction, ...):
            ...
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            user_id = str(interaction.user.id)
            key = func.__qualname__
            last = _cooldowns[key].get(user_id, 0)
            remaining = seconds - (time.time() - last)
            if remaining > 0:
                await interaction.response.send_message(
                    f"Cooldown: try again in {int(remaining)}s.",
                    ephemeral=True,
                )
                return
            _cooldowns[key][user_id] = time.time()
            return await func(self, interaction, *args, **kwargs)

        return wrapper

    return decorator
