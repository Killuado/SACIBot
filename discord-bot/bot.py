import os

from aiohttp import web
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

from cogs.address import Address
from cogs.marketplace import Marketplace
from cogs.watchlist import Watchlist
from cogs.youtube import YouTube


class SACIBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="/", intents=discord.Intents.default())
        self.http_runner = None

    async def setup_hook(self):
        await self.add_cog(Watchlist(self))
        await self.add_cog(Address(self))
        await self.add_cog(Marketplace(self))
        await self.add_cog(YouTube(self))
        await self.tree.sync()
        await self.start_http_server()

    async def on_ready(self):
        print(
            f"Bot conectado como {self.user} (ID: {self.user.id}) — comandos sincronizados!",
            flush=True,
        )

    async def start_http_server(self):
        app = web.Application()
        app.router.add_post("/notify", self.handle_notify)
        host = os.getenv("BOT_HTTP_HOST", "0.0.0.0")
        port = int(os.getenv("BOT_HTTP_PORT", 8001))
        self.http_runner = web.AppRunner(app)
        await self.http_runner.setup()
        site = web.TCPSite(self.http_runner, host, port)
        await site.start()
        print(f"[HTTP] Micro-servidor de notificações ativo em http://{host}:{port}/notify", flush=True)

    async def close(self):
        if self.http_runner:
            await self.http_runner.cleanup()
        await super().close()

    async def handle_notify(self, request):
        token = request.headers.get("X-Bot-Token", "")
        configured_token = os.getenv("BOT_API_TOKEN", "")
        if not configured_token or token != configured_token:
            return web.json_response({"error": "Unauthorized"}, status=401)

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        discord_user_id = data.get("discord_user_id")
        if not discord_user_id:
            return web.json_response({"error": "Missing discord_user_id"}, status=400)

        promo = data.get("promotion", {})
        watchlist_info = data.get("watchlist_item", {})

        title = promo.get("title", "Produto em Promoção")
        price = promo.get("price", "0.00")
        url = promo.get("url", "https://discord.com")
        marketplace = promo.get("marketplace", "Marketplace")
        image_url = promo.get("image_url", "")
        max_price = watchlist_info.get("max_price") if watchlist_info else None

        try:
            user = await self.fetch_user(int(discord_user_id))
            if not user:
                return web.json_response({"error": "User not found"}, status=404)

            embed = discord.Embed(
                title="🎯 Promoção Encontrada!",
                description="Uma oferta compatível com a sua watchlist foi detectada!",
                color=0x2ECC71,
                url=url,
            )
            embed.add_field(name="📦 Produto", value=f"**{title}**", inline=False)

            try:
                price_float = float(price)
                preco_text = (
                    f"**R$ {price_float:,.2f}**"
                    .replace(",", "X")
                    .replace(".", ",")
                    .replace("X", ".")
                )
            except (ValueError, TypeError):
                preco_text = f"**R$ {price}**"

            if max_price:
                try:
                    max_float = float(max_price)
                    max_text = (
                        f" *(Seu limite: R$ {max_float:,.2f})*"
                        .replace(",", "X")
                        .replace(".", ",")
                        .replace("X", ".")
                    )
                    preco_text += max_text
                except (ValueError, TypeError):
                    pass

            embed.add_field(name="💰 Preço Encontrado", value=preco_text, inline=True)
            embed.add_field(name="🏬 Loja", value=f"`{marketplace.upper()}`", inline=True)
            embed.add_field(
                name="🔗 Link Direto da Oferta",
                value=f"[Clique aqui para abrir a promoção no navegador]({url})",
                inline=False,
            )

            if image_url:
                embed.set_thumbnail(url=image_url)

            embed.add_field(
                name="ℹ️ Status do SACIBot",
                value=(
                    "*Nota: Nesta fase o alerta é de descoberta de preço. Quando a etapa de scraping "
                    "e automação de boletagem estiver completa, você receberá esta confirmação por DM "
                    "assim que o SACIBot tiver efetuado a boletagem automática no seu preço desejado.*"
                ),
                inline=False,
            )
            embed.set_footer(text="SACIBot — Sistema Automático de Boletagem")

            await user.send(embed=embed)
            return web.json_response({"status": "sent", "recipient": str(discord_user_id)})
        except discord.Forbidden:
            return web.json_response(
                {"error": "Cannot send DM to user (DMs disabled)"}, status=403
            )
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)


def main():
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("Configure DISCORD_BOT_TOKEN no arquivo .env.")
    SACIBot().run(token)


if __name__ == "__main__":
    main()
