import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from cogs.watchlist import Watchlist
from cogs.youtube import YouTube


load_dotenv()


class SACIBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())

    async def setup_hook(self):
        await self.add_cog(Watchlist(self))
        await self.add_cog(YouTube(self))
        await self.tree.sync()

    async def on_ready(self):
        print(f"Bot conectado como {self.user} (ID: {self.user.id}) — comandos sincronizados!", flush=True)


def main():
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("Configure DISCORD_BOT_TOKEN no arquivo .env.")
    SACIBot().run(token)


if __name__ == "__main__":
    main()
