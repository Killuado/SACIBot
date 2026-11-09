import asyncio

from django.core.management.base import BaseCommand

from lives.monitor import YouTubeLiveMonitor


class Command(BaseCommand):
    help = "Verifica canais/lives do YouTube e monitora o chat ao vivo em busca de links de promoções."

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=float,
            default=None,
            help="Segundos entre verificações de canais (padrão: YOUTUBE_CHECK_INTERVAL).",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Faz apenas uma varredura das fontes e aguarda as lives encontradas terminarem.",
        )
        parser.add_argument(
            "--print-chat",
            action="store_true",
            help="Exibe no terminal todas as mensagens recebidas do chat ao vivo.",
        )

    def handle(self, *args, interval, once, print_chat, **options):
        monitor = YouTubeLiveMonitor(check_interval=interval, print_chat=print_chat)
        try:
            if once:
                asyncio.run(self._run_once(monitor))
            else:
                asyncio.run(monitor.run())
        except KeyboardInterrupt:
            self.stdout.write("Monitor de lives do YouTube encerrado.")

    async def _run_once(self, monitor: YouTubeLiveMonitor) -> None:
        try:
            await monitor.scan_once()
            if monitor.active_tasks:
                await asyncio.gather(*list(monitor.active_tasks.values()))
        finally:
            await monitor.yt.aclose()
