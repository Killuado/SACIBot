from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from promotions.models import Promotion


class Command(BaseCommand):
    help = "Apaga promoções descobertas há mais de N dias (padrão: 3)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=getattr(settings, "PROMOTION_RETENTION_DAYS", 3),
            help="Idade máxima, em dias, das promoções mantidas.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Apenas mostra quantas promoções seriam apagadas.",
        )

    def handle(self, *args, days, dry_run, **options):
        if days < 1:
            raise CommandError("--days deve ser maior ou igual a 1.")

        cutoff = timezone.now() - timedelta(days=days)
        old = Promotion.objects.filter(discovered_at__lt=cutoff)
        label = f"antes de {timezone.localtime(cutoff):%d/%m/%Y %H:%M}"

        if dry_run:
            self.stdout.write(f"{old.count()} promoção(ões) seriam apagadas ({label}).")
            return

        deleted, _ = old.delete()
        self.stdout.write(self.style.SUCCESS(f"{deleted} promoção(ões) apagadas ({label})."))
