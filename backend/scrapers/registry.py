"""Escolha do scraper adequado para cada URL.

Scrapers específicos de loja (ex.: um ``KabumScraper`` usando a API interna)
devem ser adicionados *antes* do :class:`JsonLdScraper`, que é o fallback
genérico e aceita qualquer URL http(s).
"""

from __future__ import annotations

from .base import BaseScraper, ScraperError
from .jsonld import JsonLdScraper


def default_scrapers() -> list[BaseScraper]:
    return [JsonLdScraper()]


def get_scraper(url: str, scrapers: list[BaseScraper] | None = None) -> BaseScraper:
    for scraper in scrapers if scrapers is not None else default_scrapers():
        if scraper.can_handle(url):
            return scraper
    raise ScraperError(f"Nenhum scraper disponível para {url}")
