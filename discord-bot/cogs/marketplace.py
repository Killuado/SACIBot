import os
import urllib.parse

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands


class Marketplace(commands.GroupCog, group_name="marketplace"):
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

    allow = app_commands.Group(name="allow", description="Gerencia os canais/marketplaces permitidos")

    @allow.command(name="add", description="Adiciona uma ou mais lojas permitidas (separadas por vírgula)")
    @app_commands.describe(canais="Nome da(s) loja(s) separadas por vírgula (ex: kabum, pichau, terabyte, amazon)")
    async def allow_add(self, interaction: discord.Interaction, canais: str):
        await interaction.response.defer(ephemeral=True)
        items = [c.strip().lower() for c in canais.split(",") if c.strip()]
        if not items:
            await interaction.followup.send("❌ Informe ao menos uma loja válida.", ephemeral=True)
            return

        result = await self.request(
            interaction,
            "POST",
            "/api/marketplace/",
            json={"channels": items},
        )
        if not result or "_error" in result:
            await interaction.followup.send(
                "❌ Não foi possível adicionar a(s) loja(s). Tente novamente.",
                ephemeral=True,
            )
            return

        added = result.get("channels", items)
        items_info = result.get("items", [])
        if items_info:
            lojas_str = "\n".join(f"`#{it['user_index']}` {it['channel']}" for it in items_info)
            await interaction.followup.send(
                f"✅ **Loja(s) adicionada(s) com sucesso:**\n{lojas_str}",
                ephemeral=True,
            )
        else:
            lojas_str = ", ".join(f"`{c}`" for c in added)
            await interaction.followup.send(
                f"✅ Loja(s) adicionada(s): {lojas_str}",
                ephemeral=True,
            )

    @allow.command(name="remove", description="Remove lojas permitidas pelo número (#1, #2...) ou pelo nome")
    @app_commands.describe(item="Número(#1, #2...) ou nome da loja (ex: 2 ou 1, 2 ou kabum)")
    async def allow_remove(self, interaction: discord.Interaction, item: str):
        await interaction.response.defer(ephemeral=True)
        raw_input = item.strip()
        if not raw_input:
            await interaction.followup.send("❌ Informe o número ou nome da loja a remover.", ephemeral=True)
            return

        cleaned = ",".join(
            part.strip().lstrip("#").strip()
            for part in raw_input.split(",")
            if part.strip()
        )
        encoded_channels = urllib.parse.quote(cleaned if cleaned else raw_input)

        result = await self.request(
            interaction,
            "DELETE",
            f"/api/marketplace/{encoded_channels}/",
        )
        if isinstance(result, dict) and result.get("_error") == 404:
            await interaction.followup.send(
                f"ℹ️ Nenhum item correspondente a `{raw_input}` foi encontrado na sua lista.\n"
                f"Use `/marketplace allow list` para conferir a numeração atual.",
                ephemeral=True,
            )
            return
        if isinstance(result, dict) and "_error" in result:
            await interaction.followup.send(
                "❌ Não foi possível remover as lojas informadas.",
                ephemeral=True,
            )
            return

        deleted_list = result.get("deleted", [raw_input])
        if len(deleted_list) == 1:
            await interaction.followup.send(
                f"🗑️ Loja `{deleted_list[0]}` removida dos seus marketplaces permitidos.",
                ephemeral=True,
            )
        else:
            lojas_str = ", ".join(f"`{c}`" for c in deleted_list)
            await interaction.followup.send(
                f"🗑️ **{len(deleted_list)} loja(s) removida(s):** {lojas_str}",
                ephemeral=True,
            )

    @allow.command(name="list", description="Lista todas as lojas permitidas com ID único para você")
    async def allow_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await self.request(interaction, "GET", "/api/marketplace/")
        if isinstance(result, dict) and "_error" in result:
            await interaction.followup.send(
                "❌ Não foi possível consultar suas lojas permitidas no momento.",
                ephemeral=True,
            )
            return
        if not result:
            await interaction.followup.send(
                "ℹ️ Você ainda não configurou nenhuma loja permitida.\n"
                "Use `/marketplace allow add <lojas>` para adicionar lojas como `kabum`, `pichau`, `terabyte`, `amazon`, etc.",
                ephemeral=True,
            )
            return

        lojas = [f"`#{item.get('user_index', idx)}` {item['channel']}" for idx, item in enumerate(result, start=1)]
        await interaction.followup.send(
            f"🏬 **Lojas / Marketplaces permitidos para você ({len(result)}):**\n"
            + "\n".join(lojas)
            + "\n\n💡 *Para remover, use `/marketplace allow remove <número ou nome>` (ex: `/marketplace allow remove 1` ou `/marketplace allow remove 1, 2`)*",
            ephemeral=True,
        )
