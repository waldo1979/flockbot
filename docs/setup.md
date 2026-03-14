# Flockbot Setup Guide

Everything you need to get Flockbot running: API credentials, Discord server, and bot installation.

---

## 1. Create a Discord Bot

1. Go to https://discord.com/developers/applications
2. Click **New Application** → name it **Flockbot** → Create
3. Go to **Bot** (left sidebar)
4. Click **Reset Token** → copy the token — this is your `DISCORD_TOKEN`
5. Save the token in 1Password (you won't be able to see it again)
6. Under **Privileged Gateway Intents**, leave everything **off** (Flockbot only needs voice state, which is non-privileged)

## 2. Get a PUBG API Key

1. Go to https://developer.pubg.com
2. Sign up or log in (you can use your Steam account)
3. Go to your dashboard and click **Get Your Own API Key** (or create a new app)
4. Name it anything (e.g., "Flockbot")
5. Copy the API key — this is your `PUBG_API_KEY`
6. Save the key in 1Password

The free tier allows 10 requests/minute, which is what Flockbot is designed around.

## 3. Create a Discord Server

1. Open Discord → click the **+** button (bottom of the server list)
2. Choose **Create My Own** → **For me and my friends**
3. Name it whatever you like (e.g., "PUBG LFG")

### Set up the channel structure

Delete the default channels, then create the following:

**Categories and channels:**

| Category | Channel | Type |
|---|---|---|
| INFO | #rules | Text |
| INFO | #announcements | Text |
| GENERAL | #general | Text |
| GENERAL | #bot-commands | Text |
| LFG | LFG Squad | Voice |
| LFG | LFG Duo | Voice |
| SQUADS | *(leave empty — bot creates temp channels here)* | *(category only)* |

To create a category: right-click the server name → **Create Category**.
To create a channel: click the **+** next to a category name.

The bot detects channels by name, so the voice channels must be named exactly **"LFG Squad"** and **"LFG Duo"**. The **SQUADS** category is where the bot creates temporary voice channels for matched groups.

## 4. Invite the Bot to Your Server

1. Go back to https://discord.com/developers/applications → select Flockbot
2. Go to **OAuth2** (left sidebar)
3. Under **OAuth2 URL Generator**:
   - **Scopes**: check `bot` and `applications.commands`
   - **Bot Permissions**: check the following:

| Permission | Why |
|---|---|
| Manage Channels | Create/delete temporary voice channels |
| Manage Nicknames | Set player nicknames to their PUBG name |
| Manage Roles | Set permissions on temporary channels |
| View Channels | Read server channel structure |
| Connect | Join voice channels |
| Move Members | Move matched players into squad channels |
| Send Messages | Post match announcements, buddy notifications |
| Embed Links | Rich embed responses |

4. Copy the generated URL at the bottom
5. Open it in your browser → select your server → **Authorize**

## 5. Get Your Server (Guild) ID

For development, you'll want instant slash command sync instead of waiting up to an hour for global sync.

1. In Discord, go to **User Settings → Advanced → Developer Mode** → enable it
2. Right-click your server name → **Copy Server ID**
3. This is your `GUILD_ID` (optional, for dev use)

## 6. Configure Environment

Create a `.env` file wherever you're running the bot.

**For local development** (in the project root, already gitignored):

```
DISCORD_TOKEN=your-discord-token
PUBG_API_KEY=your-pubg-api-key
GUILD_ID=your-server-id
```

**For production on the Pi** (at `~/flockbot/.env`):

```
DISCORD_TOKEN=your-discord-token
PUBG_API_KEY=your-pubg-api-key
```

`GUILD_ID` is omitted in production so commands sync globally.

## 7. Verify It Works

Run locally:

```bash
uv run python bot.py
```

You should see:

```
Flockbot ready as Flockbot#1234
Synced commands to guild <your-guild-id>
```

Then in Discord, type `/` in the #bot-commands channel — you should see Flockbot's slash commands appear (register, stats, feedback, etc.).
