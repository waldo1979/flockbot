import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN: str = os.environ["DISCORD_TOKEN"]
PUBG_API_KEY: str = os.environ["PUBG_API_KEY"]
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/flockbot.db")
GUILD_ID: int | None = int(g) if (g := os.getenv("GUILD_ID")) else None
PUBG_PLATFORM_SHARD: str = "steam"
