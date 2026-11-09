import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from scrapers.telegram_monitor import TelegramMonitor, TelegramSettings


class Command(BaseCommand):
    help = "Escuta canais do Telegram e envia os links de produtos para a ingestão."

    def add_arguments(self, parser):
        parser.add_argument(
            "--channel",
            action="append",
            dest="channels",
            help="Canal a monitorar (@usuario, link t.me ou ID). Pode repetir. "
            "Padrão: TELEGRAM_CHANNELS do .env.",
        )

    def handle(self, *args, channels, **options):
        if not settings.TELEGRAM_API_ID or not settings.TELEGRAM_API_HASH:
            raise CommandError(
                "Defina TELEGRAM_API_ID e TELEGRAM_API_HASH no .env "
                "(obtidos em https://my.telegram.org)."
            )
        try:
            api_id = int(settings.TELEGRAM_API_ID)
        except ValueError as exc:
            raise CommandError("TELEGRAM_API_ID deve ser numérico.") from exc

        monitor = TelegramMonitor(
            TelegramSettings(
                api_id=api_id,
                api_hash=settings.TELEGRAM_API_HASH,
                session=settings.TELEGRAM_SESSION,
                channels=channels or settings.TELEGRAM_CHANNELS,
                bot_token=settings.TELEGRAM_BOT_TOKEN,
            )
        )
        try:
            asyncio.run(monitor.run())
        except KeyboardInterrupt:
            self.stdout.write("Monitor do Telegram encerrado.")
