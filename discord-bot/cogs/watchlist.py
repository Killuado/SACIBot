import os

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands


class Watchlist(commands.GroupCog, group_name="watchlist"):
    def __init__(self, bot):
        self.bot = bot
        self.api_url = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000")
        self.api_token = os.getenv("BOT_API_TOKEN", "")

    def request_headers(self, discord_user_id):
        return {
            "X-Bot-Token": self.api_token,
            "X-Discord-User-ID": str(discord_user_id),
        }

    async def request(self, interaction, method, path, **kwargs):
        if not self.api_token:
            return {"_error": "configuration"}

        headers = self.request_headers(interaction.user.id)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method,
                    f"{self.api_url}{path}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                    **kwargs,
                ) as response:
                    if response.status >= 400:
                        return {"_error": response.status, "detail": await response.text()}
                    if response.status == 204:
                        return {}
                    return await response.json()
        except aiohttp.ClientError:
            return {"_error": "connection"}

    @app_commands.command(name="add", description="Adiciona um produto à sua watchlist")
    @app_commands.describe(
        regex="Expressão regular para identificar o produto",
        preco_maximo="Preço máximo em reais",
    )
    async def add(self, interaction: discord.Interaction, regex: str, preco_maximo: float):
        await interaction.response.defer(ephemeral=True)
        result = await self.request(
            interaction,
            "POST",
            "/api/watchlist/",
            json={"pattern": regex, "max_price": f"{preco_maximo:.2f}"},
        )
        if not result:
            return
        if "_error" in result:
            await interaction.followup.send(
                "Não foi possível adicionar. Confira o preço, a expressão e a conexão com a API.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            f"Watchlist #{result['id']} adicionada: `{result['pattern']}` até R$ {result['max_price']}.",
            ephemeral=True,
        )

    @app_commands.command(name="list", description="Lista seus produtos monitorados")
    async def list_items(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await self.request(interaction, "GET", "/api/watchlist/")
        if result is None:
            return
        if isinstance(result, dict) and "_error" in result:
            await interaction.followup.send(
                "Não foi possível consultar a API do SACIBot.",
                ephemeral=True,
            )
            return
        if not result:
            await interaction.followup.send("Sua watchlist está vazia.", ephemeral=True)
            return

        lines = [
            f"`#{item['id']}` `{item['pattern']}` até R$ {item['max_price']}"
            for item in result
        ]
        await interaction.followup.send("\n".join(lines)[:1900], ephemeral=True)

    @app_commands.command(name="remove", description="Remove um item da sua watchlist")
    @app_commands.describe(item_id="ID exibido no comando /watchlist list")
    async def remove(self, interaction: discord.Interaction, item_id: int):
        await interaction.response.defer(ephemeral=True)
        result = await self.request(
            interaction,
            "DELETE",
            f"/api/watchlist/{item_id}/",
        )
        if result is None:
            return
        if isinstance(result, dict) and result.get("_error") == 404:
            message = "Esse item não existe na sua watchlist."
        elif isinstance(result, dict) and "_error" in result:
            message = "Não foi possível remover o item. Confira a conexão com a API."
        else:
            message = f"Watchlist #{item_id} removida."
        await interaction.followup.send(message, ephemeral=True)