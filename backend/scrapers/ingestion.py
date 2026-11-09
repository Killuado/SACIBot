"""Ingestão: URL -> scraper -> Promotion -> correspondência com watchlists."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from promotions.models import Promotion, WatchlistItem
from promotions.services import matching_watchlists, send_bot_notification

from .base import BaseScraper, ScraperError
from .links import clean_url
from .registry import get_scraper

logger = logging.getLogger(__name__)

_URL_MAX_LENGTH = Promotion._meta.get_field("url").max_length


@dataclass
class IngestionResult:
    url: str
    status: Literal["created", "updated", "skipped"]
    promotion: Promotion | None = None
    matches: list[WatchlistItem] = field(default_factory=list)
    reason: str = ""


def ingest_url(
    url: str,
    source: str = "",
    scraper: BaseScraper | None = None,
) -> IngestionResult:
    """Raspa a URL e cria/atualiza a promoção correspondente.

    As watchlists só são avaliadas quando há novidade para o usuário: produto
    novo, queda de preço ou retorno ao estoque. Produtos sem preço ou
    explicitamente esgotados na primeira descoberta são salvos/ignorados sem
    gerar correspondência.
    """
    url = clean_url(url)
    owns_scraper = scraper is None

    try:
        scraper = scraper or get_scraper(url)
        data = scraper.parse_url(url)
    except ScraperError as exc:
        logger.info("Falha ao raspar %s: %s", url, exc)
        return IngestionResult(url=url, status="skipped", reason=str(exc))
    finally:
        if owns_scraper and scraper is not None:
            scraper.close()

    final_url = clean_url(data["url"])
    if len(final_url) > _URL_MAX_LENGTH:
        return IngestionResult(url=final_url, status="skipped", reason="URL longa demais")
    if data["price"] is None:
        return IngestionResult(url=final_url, status="skipped", reason="Preço não encontrado")

    previous = Promotion.objects.filter(url=final_url).values("price", "in_stock").first()
    promotion, created = Promotion.objects.update_or_create(
        url=final_url,
        defaults={
            "title": data["title"][:300],
            "price": data["price"],
            "marketplace": data["marketplace"][:80],
            "image_url": (data.get("image_url") or "")[:2000],
            "source": source[:120],
            "in_stock": data["in_stock"],
        },
    )

    is_news = created or (
        previous is not None
        and (
            promotion.price < previous["price"]
            or (previous["in_stock"] is False and promotion.in_stock is not False)
        )
    )
    matches: list[WatchlistItem] = []
    if is_news and promotion.in_stock is not False:
        matches = matching_watchlists(promotion)
        if matches:
            logger.info(
                "Promoção %s corresponde a %d watchlist(s)", promotion.pk, len(matches)
            )
            ready_ids = {
                item.pk for item in matching_watchlists(promotion, require_user_readiness=True)
            }
            for item in matches:
                if item.pk in ready_ids:
                    send_bot_notification(
                        discord_user_id=item.user.discord_id,
                        promotion=promotion,
                        watchlist_item=item,
                    )

    return IngestionResult(
        url=final_url,
        status="created" if created else "updated",
        promotion=promotion,
        matches=matches,
    )
