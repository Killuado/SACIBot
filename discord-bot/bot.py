import os

import discord
from dotenv import load_dotenv

from cogs.watchlist import Watchlist


load_dotenv()


class SACIBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = discord.app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.add_cog(Watchlist(self))
        await self.tree.sync()


def main():
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("Configure DISCORD_BOT_TOKEN no arquivo .env.")
    SACIBot().run(token)


if __name__ == "__main__":
    main()