import os

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands


def load_admin_ids() -> set[str]:
    raw = (
        os.getenv("DISCORD_ADMIN_IDS")
        or os.getenv("ADMIN_USER_IDS")
        or os.getenv("ADMIN_DISCORD_IDS")
        or ""
    )
    return {uid.strip() for uid in raw.split(",") if uid.strip()}


class YouTube(commands.GroupCog, group_name="youtube"):
    """Gerencia canais de loja e lives do YouTube monitorados pelo SACIBot (restrito a DISCORD_ADMIN_IDS)."""

    def __init__(self, bot):
        self.bot = bot
        self.api_url = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000")
        self.api_token = os.getenv("BOT_API_TOKEN", "")
        self.admin_ids = load_admin_ids()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        admin_ids = self.admin_ids or load_admin_ids()
        if str(interaction.user.id) not in admin_ids:
            await interaction.response.send_message(
                "Você não tem permissão de usar esse comando.",
                ephemeral=True,
            )
            return False
        return True

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

    @app_commands.command(
        name="add",
        description="Adiciona um canal (@loja, URL) ou live específica do YouTube para monitorar",
    )
    @app_commands.describe(
        canal_ou_live="Handle (@kabum), link do canal ou link/ID da live no YouTube",
        qualquer_autor="Aceitar links enviados por qualquer pessoa no chat (padrão: apenas dono/moderador)",
    )
    async def add(
        self,
        interaction: discord.Interaction,
        canal_ou_live: str,
        qualquer_autor: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)
        result = await self.request(
            interaction,
            "POST",
            "/api/youtube/sources/",
            json={
                "source": canal_ou_live,
                "trusted_authors_only": not qualquer_autor,
            },
        )
        if not result:
            return
        if result.get("_error") == 403:
            await interaction.followup.send(
                "Você não tem permissão de usar esse comando.",
                ephemeral=True,
            )
            return
        if "_error" in result:
            await interaction.followup.send(
                "Não foi possível cadastrar a fonte. Confira o link/@handle do YouTube e a conexão com a API.",
                ephemeral=True,
            )
            return

        kind_label = "Canal" if result.get("kind") == "channel" else "Live"
        await interaction.followup.send(
            f"{kind_label} `#{result['id']}` (`{result['identifier']}`) monitorado pelo SACIBot.",
            ephemeral=True,
        )

    @app_commands.command(
        name="list",
        description="Lista os canais e lives do YouTube monitorados",
    )
    async def list_sources(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await self.request(interaction, "GET", "/api/youtube/sources/")
        if result is None:
            return
        if isinstance(result, dict) and result.get("_error") == 403:
            await interaction.followup.send(
                "Você não tem permissão de usar esse comando.",
                ephemeral=True,
            )
            return
        if isinstance(result, dict) and "_error" in result:
            await interaction.followup.send(
                "Não foi possível consultar a API do SACIBot.",
                ephemeral=True,
            )
            return
        if not result:
            await interaction.followup.send(
                "Nenhum canal ou live do YouTube cadastrado.",
                ephemeral=True,
            )
            return

        lines = []
        for item in result:
            if not item.get("enabled"):
                badge = "⏸"
            elif item.get("is_live"):
                badge = f"🔴 AO VIVO (`{item['current_video_id']}`)"
            else:
                badge = "⚪"
            kind = "Canal" if item.get("kind") == "channel" else "Live"
            label = f" ({item['label']})" if item.get("label") else ""
            note = f" — {item['note']}" if item.get("note") else ""
            lines.append(
                f"`#{item['id']}` [{kind}] `{item['identifier']}`{label} {badge}{note}"
            )
        await interaction.followup.send("\n".join(lines)[:1900], ephemeral=True)

    @app_commands.command(
        name="remove",
        description="Remove um canal ou live do YouTube monitorado",
    )
    @app_commands.describe(source_id="ID exibido em /youtube list")
    async def remove(self, interaction: discord.Interaction, source_id: int):
        await interaction.response.defer(ephemeral=True)
        result = await self.request(
            interaction,
            "DELETE",
            f"/api/youtube/sources/{source_id}/",
        )
        if result is None:
            return
        if isinstance(result, dict) and result.get("_error") == 403:
            message = "Você não tem permissão de usar esse comando."
        elif isinstance(result, dict) and result.get("_error") == 404:
            message = "Essa fonte não existe."
        elif isinstance(result, dict) and "_error" in result:
            message = "Não foi possível remover a fonte. Confira a conexão com a API."
        else:
            message = f"Fonte `#{source_id}` removida."
        await interaction.followup.send(message, ephemeral=True)

    @app_commands.command(
        name="logs",
        description="Mostra os últimos comentários e links recebidos nas lives do YouTube",
    )
    @app_commands.describe(source_id="Opcional: ID da fonte em /youtube list para filtrar")
    async def logs(
        self,
        interaction: discord.Interaction,
        source_id: int | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        path = "/api/youtube/logs/"
        if source_id is not None:
            path += f"?source_id={source_id}"
        result = await self.request(interaction, "GET", path)
        if result is None:
            return
        if isinstance(result, dict) and result.get("_error") == 403:
            await interaction.followup.send(
                "Você não tem permissão de usar esse comando.",
                ephemeral=True,
            )
            return
        if isinstance(result, dict) and "_error" in result:
            await interaction.followup.send(
                "Não foi possível consultar os logs na API do SACIBot.",
                ephemeral=True,
            )
            return

        sessions = (result or {}).get("sessions") or []
        if not sessions:
            await interaction.followup.send(
                "Nenhuma live ativa (ou sessão recente) encontrada no momento.",
                ephemeral=True,
            )
            return

        blocks = []
        for s in sessions[:3]:
            status = "🔴 AO VIVO" if s.get("is_active") else "⚪ ENCERRADA"
            name = s.get("label") or s.get("identifier")
            header = (
                f"**{status} — `#{s['source_id']}` {name} (`{s['video_id']}`)**\n"
                f"📊 `{s['messages_seen']}` comentários | `{s['links_seen']}` links válidos | `{s['links_ingested']}` enviados p/ scraper"
            )

            msgs = s.get("recent_messages") or []
            if msgs:
                msg_lines = [
                    f"• `{m.get('time', '')}` **{m.get('author', '')}**: {m.get('text', '')[:90]}"
                    for m in msgs[-6:]
                ]
                msg_section = "💬 **Últimos comentários:**\n" + "\n".join(msg_lines)
            else:
                msg_section = "💬 **Últimos comentários:** *(nenhum ainda)*"

            links = s.get("recent_links") or []
            if links:
                link_lines = [
                    f"• `{lk.get('time', '')}` **{lk.get('author', '')}** → <{lk.get('url', '')}> (`{lk.get('status', '')}`)"
                    for lk in links[-6:]
                ]
                link_section = "🔗 **Últimos links recebidos:**\n" + "\n".join(link_lines)
            else:
                link_section = "🔗 **Últimos links recebidos:** *(nenhum link enviado no chat)*"

            blocks.append(f"{header}\n{msg_section}\n{link_section}")

        text = "\n\n".join(blocks)
        if len(text) > 1900:
            text = text[:1900] + "\n..."
        await interaction.followup.send(text, ephemeral=True)
