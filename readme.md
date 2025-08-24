# TotB_Bot

A modular Discord bot for **Techno on The Block** – supports slash commands, embed creation, and role-restricted usage.

## Features

- `/ping` – Check if the bot is online
- `/hilfe` – Help command
- `/create_embed` – Sends a styled embed (title, color, image, thumbnail)

## Setup

```bash
git clone https://github.com/freddy2726/TotB_Bot.git
cd TotB_Bot
pip install -r requirements.txt
```

Create a `.env` file:

```env
DISCORD_TOKEN=your_token
GUILD_ID=your_guild_id
```

Run the bot:

```bash
python app.py
```

## Structure

```
app.py
cogs/
├── basic.py
└── embed_creator.py
```

## Requirements

- Python 3.11+
- `discord.py`
- `python-dotenv`