import os

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands


class Address(commands.GroupCog, group_name="endereco"):
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

    @app_commands.command(name="set", description="Cadastra ou atualiza seu endereço para entrega e boletagem")
    @app_commands.describe(
        destinatario="Nome completo de quem vai receber a encomenda",
        cep="CEP no formato 00000-000",
        rua="Nome da rua ou avenida",
        numero="Número da residência",
        bairro="Bairro",
        cidade="Cidade",
        uf="Sigla do estado com 2 letras (ex: SP, RJ, MG)",
        complemento="Apartamento, bloco, lote, etc. (opcional)",
        cpf="CPF para emissão de nota/boleto (opcional)",
    )
    async def set_address(
        self,
        interaction: discord.Interaction,
        destinatario: str,
        cep: str,
        rua: str,
        numero: str,
        bairro: str,
        cidade: str,
        uf: str,
        complemento: str = "",
        cpf: str = "",
    ):
        await interaction.response.defer(ephemeral=True)
        payload = {
            "recipient_name": destinatario.strip(),
            "zip_code": cep.strip(),
            "street": rua.strip(),
            "number": numero.strip(),
            "neighborhood": bairro.strip(),
            "city": cidade.strip(),
            "state": uf.strip().upper(),
            "complement": complemento.strip(),
            "cpf": cpf.strip(),
        }
        result = await self.request(interaction, "POST", "/api/address/", json=payload)
        if not result or "_error" in result:
            await interaction.followup.send(
                "❌ Não foi possível salvar o endereço. Verifique os dados (UF com 2 letras, etc.) e tente novamente.",
                ephemeral=True,
            )
            return

        comp_text = f" ({result['complement']})" if result.get("complement") else ""
        cpf_text = f"\n📄 **CPF:** {result['cpf']}" if result.get("cpf") else ""

        await interaction.followup.send(
            f"✅ **Endereço salvo com sucesso!**\n"
            f"👤 **Destinatário:** {result['recipient_name']}\n"
            f"📍 **Logradouro:** {result['street']}, {result['number']}{comp_text}\n"
            f"🏘️ **Bairro:** {result['neighborhood']}\n"
            f"🏙️ **Cidade/UF:** {result['city']}/{result['state']} — CEP: {result['zip_code']}"
            f"{cpf_text}",
            ephemeral=True,
        )

    @app_commands.command(name="show", description="Exibe seu endereço atualmente cadastrado")
    async def show_address(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await self.request(interaction, "GET", "/api/address/")
        if isinstance(result, dict) and result.get("_error") == 404:
            await interaction.followup.send(
                "ℹ️ Você ainda não possui endereço cadastrado. Use `/endereco set` para cadastrar.",
                ephemeral=True,
            )
            return
        if not result or "_error" in result:
            await interaction.followup.send(
                "❌ Não foi possível carregar seu endereço no momento.",
                ephemeral=True,
            )
            return

        comp_text = f" ({result['complement']})" if result.get("complement") else ""
        cpf_text = f"\n📄 **CPF:** {result['cpf']}" if result.get("cpf") else ""

        await interaction.followup.send(
            f"📦 **Seu Endereço Cadastrado:**\n"
            f"👤 **Destinatário:** {result['recipient_name']}\n"
            f"📍 **Logradouro:** {result['street']}, {result['number']}{comp_text}\n"
            f"🏘️ **Bairro:** {result['neighborhood']}\n"
            f"🏙️ **Cidade/UF:** {result['city']}/{result['state']} — CEP: {result['zip_code']}"
            f"{cpf_text}",
            ephemeral=True,
        )
