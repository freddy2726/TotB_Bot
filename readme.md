# TotB_Bot

A modular Discord bot for **Techno on The Block** – supports slash commands, embed creation, role-restricted usage, automated member greetings, and self-assignable roles.

## Features

- `/ping` – Check if the bot is online  
- `/hilfe` – Help command  
- `/create_embed` – Sends a styled embed (title, color, image, thumbnail)  
- **Welcome System** – Automatically greets new members in the welcome channel  
- **Self-Roles System** – Lets members assign/remove roles by reacting to panel messages  

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
├── embed_creator.py
├── welcome.py
└── self_roles.py
data/
└── selfroles.json
```

## Requirements

- Python 3.11+  
- `discord.py`  
- `python-dotenv`  

## Notes

- `welcome.py` posts a welcome message for each new member in the configured channel.  
- `self_roles.py` provides an admin-only slash-command suite (`/selfroles_create`, `/selfroles_bind`, `/selfroles_unbind`, `/selfroles_list`, `/selfroles_refresh`, `/selfroles_delete`) and handles role assignment via emoji reactions.  
- Role/emoji assignments are persisted in `data/selfroles.json`.  