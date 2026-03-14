"""Parse discord-welcome.md and post messages to the #rules channel."""

import logging
from pathlib import Path

import discord

log = logging.getLogger(__name__)

WELCOME_PATH = Path(__file__).parent.parent / "docs" / "discord-welcome.md"
RULES_CHANNEL_NAME = "rules"
# Marker used to identify messages posted by the bot for cleanup
WELCOME_MARKER = "\u200b"  # zero-width space appended to each message


def parse_welcome_messages(text: str) -> list[str]:
    """Split the welcome markdown into individual messages.

    Messages are delimited by lines containing only '---'.
    The header (before the first '---') and the '**MESSAGE N:**' labels are stripped.
    """
    sections = text.split("\n---\n")
    messages = []
    for section in sections[1:]:  # skip the file header
        lines = section.strip().splitlines()
        # Drop the **MESSAGE N:** label line
        if lines and lines[0].startswith("**MESSAGE"):
            lines = lines[1:]
        body = "\n".join(lines).strip()
        if body:
            messages.append(body)
    return messages


async def post_welcome_messages(bot: discord.Client) -> None:
    """Purge old welcome messages and post fresh ones to #rules."""
    text = WELCOME_PATH.read_text(encoding="utf-8")
    messages = parse_welcome_messages(text)
    if not messages:
        log.warning("No welcome messages parsed from %s", WELCOME_PATH)
        return

    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name=RULES_CHANNEL_NAME)
        if not channel:
            log.debug("No #%s channel in %s", RULES_CHANNEL_NAME, guild.name)
            continue

        # Purge all messages sent by the bot in this channel
        deleted = 0
        async for msg in channel.history(limit=200):
            if msg.author == bot.user:
                await msg.delete()
                deleted += 1
        if deleted:
            log.info("Deleted %d old welcome messages in #%s", deleted, RULES_CHANNEL_NAME)

        # Post fresh messages
        for body in messages:
            await channel.send(body + WELCOME_MARKER)
        log.info(
            "Posted %d welcome messages to #%s in %s",
            len(messages), RULES_CHANNEL_NAME, guild.name,
        )
