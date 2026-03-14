# Raspberry Pi 5 Setup Guide

One-time setup for deploying Flockbot to a Raspberry Pi 5 on your local network.

## How it works

```
You push to main
  → GitHub Actions runs tests, builds an ARM64 image, pushes to GHCR
  → Watchtower (on the Pi) detects the new image, pulls it, restarts the bot
```

No inbound network access to the Pi is required. Watchtower polls outbound to GHCR.

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

This saves credentials to `~/.docker/config.json`, which Watchtower also reads.

## 3. Set Up the Bot

```bash
# Create the project directory
mkdir -p ~/flockbot

# Create the .env file with your secrets
nano ~/flockbot/.env
```

Add to `.env`:

```
DISCORD_TOKEN=your-discord-token-here
PUBG_API_KEY=your-pubg-api-key-here
```

Lock down permissions:

```bash
chmod 600 ~/flockbot/.env
```

### Copy the compose file from your Windows machine

Using `pscp` (comes with PuTTY) from Command Prompt:

```cmd
pscp docker-compose.prod.yml pi-user@pi-ip:~/flockbot/docker-compose.yml
```

Then SSH in and edit the image name in `~/flockbot/docker-compose.yml` — replace `OWNER` with your GitHub username (lowercase):

```bash
nano ~/flockbot/docker-compose.yml
# Change: ghcr.io/OWNER/flockbot:latest
# To:     ghcr.io/yourusername/flockbot:latest
```

## 4. Start Everything

```bash
cd ~/flockbot
docker compose up -d
```

This starts both the bot and Watchtower. From now on, every push to `main` will automatically deploy within ~5 minutes.

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
docker compose logs -f flockbot             # Follow bot logs
docker compose logs -f watchtower            # Follow Watchtower logs
docker compose restart flockbot              # Restart the bot
docker compose down                          # Stop everything
docker compose pull && docker compose up -d  # Force an immediate update
```

## Network Notes

- The Pi only needs **outbound** internet access (Discord API, PUBG API, GHCR)
- No inbound ports need to be opened
- No SSH from the internet required — Watchtower pulls updates over HTTPS
