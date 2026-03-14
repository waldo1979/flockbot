# Raspberry Pi 5 Setup Guide

One-time setup for deploying Flockbot to a Raspberry Pi 5 on your local network.

## How it works

```
You push to main
  → GitHub Actions runs tests, builds an ARM64 image, pushes to GHCR
  → Cron job (on the Pi) detects the new image, pulls it, restarts the bot
```

No inbound network access to the Pi is required. The cron job polls outbound to GHCR every 5 minutes.

---

## 1. Install Docker on the Pi

SSH into the Pi (using PuTTY), then:

```bash
# Install prerequisites
sudo apt-get update
sudo apt-get install ca-certificates curl

# Add Docker's official GPG key and apt repository
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list

# Install Docker
sudo apt-get update
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Allow your user to run docker without sudo
sudo usermod -aG docker $USER
# Log out and back in for group change to take effect
```

Verify:

```bash
docker run --rm hello-world
```

## 2. GHCR Authentication on the Pi

The Pi needs to pull images from GitHub Container Registry.

If your repo is **public**, skip this step.

If your repo is **private**:

1. Create a Personal Access Token (classic) at https://github.com/settings/tokens with `read:packages` scope
2. Store the token in 1Password for safekeeping
3. Log in on the Pi:

```bash
echo "YOUR_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

This saves credentials to `~/.docker/config.json`.

## 3. Set Up the Bot

```bash
# Clone the repo
git clone https://github.com/waldo1979/flockbot.git ~/flockbot-repo

# Create the deployment directory and .env
mkdir -p ~/flockbot
nano ~/flockbot/.env
```

Add to `.env`:

```
DISCORD_TOKEN=your-discord-token-here
PUBG_API_KEY=your-pubg-api-key-here
```

Lock down permissions and symlink the compose file:

```bash
chmod 600 ~/flockbot/.env
ln -sf ~/flockbot-repo/docker-compose.prod.yml ~/flockbot/docker-compose.yml
```

## 4. Install the Auto-Update Cron Job

```bash
# Make the update script executable
chmod +x ~/flockbot-repo/scripts/update.sh

# Install cron job — checks for new images every 5 minutes
(crontab -l 2>/dev/null; echo "*/5 * * * * $HOME/flockbot-repo/scripts/update.sh") | crontab -
```

## 5. Start the Bot

```bash
cd ~/flockbot
docker compose up -d
```

From now on, every push to `main` will automatically deploy within ~5 minutes.

## 5. Personal SSH Access (with 1Password)

For your own SSH access from Windows using PuTTY:

1. In **1Password**, create a new SSH key item (or use an existing one)
2. Export the **public key** from 1Password
3. Append it to `~/.ssh/authorized_keys` on the Pi
4. In PuTTY, configure **Connection → SSH → Auth → Credentials** to use the key from 1Password (or use Pageant with 1Password's SSH agent)

Alternatively, use PuTTYgen to create a key pair, save the private key in 1Password, and add the public key to the Pi's `authorized_keys`.

---

## Useful Commands on the Pi

```bash
cd ~/flockbot
docker compose logs -f flockbot              # Follow bot logs
docker compose restart flockbot              # Restart the bot
docker compose down                          # Stop the bot
docker compose pull && docker compose up -d  # Force an immediate update
cat ~/flockbot/update.log                    # View auto-update history
crontab -l                                   # Verify cron job is installed
```

To sync compose file changes from the repo:

```bash
cd ~/flockbot-repo && git pull
# The symlink picks up changes automatically; restart if needed:
cd ~/flockbot && docker compose up -d
```

## Network Notes

- The Pi only needs **outbound** internet access (Discord API, PUBG API, GHCR)
- No inbound ports need to be opened
- No SSH from the internet required — the cron job pulls updates over HTTPS
