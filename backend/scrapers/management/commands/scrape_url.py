import json

from django.core.management.base import BaseCommand, CommandError

from scrapers.base import ScraperError
from scrapers.ingestion import ingest_url
from scrapers.registry import get_scraper


class Command(BaseCommand):
    help = "Raspa uma URL de produto e mostra (ou salva) os dados extraídos."

    def add_arguments(self, parser):
        parser.add_argument("url")
        parser.add_argument(
            "--save",
            action="store_true",
            help="Salva/atualiza a promoção no banco e aplica as watchlists.",
        )
        parser.add_argument("--source", default="manual", help="Origem registrada ao salvar.")

    def handle(self, *args, url, save, source, **options):
        if save:
            result = ingest_url(url, source=source)
            if result.status == "skipped":
                raise CommandError(f"Ignorada: {result.reason}")
            self.stdout.write(
                self.style.SUCCESS(
                    f"Promoção {result.promotion.pk} {result.status}: "
                    f"{result.promotion.title} - R$ {result.promotion.price} "
                    f"({len(result.matches)} watchlist(s) correspondente(s))"
                )
            )
            return

        scraper = get_scraper(url)
        try:
            data = scraper.parse_url(url)
        except ScraperError as exc:
            raise CommandError(str(exc)) from exc
        finally:
            scraper.close()
        self.stdout.write(json.dumps(data, default=str, ensure_ascii=False, indent=2))
