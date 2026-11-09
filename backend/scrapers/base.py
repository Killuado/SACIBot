"""Interface comum para todos os scrapers do SACIBot.

Cada scraper devolve dicionários com o mesmo formato, para que o restante do
backend (ingestão, watchlist, retentativas) não precise saber de qual loja o
produto veio.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import TypedDict


class ScraperError(Exception):
    """Falha ao baixar ou interpretar uma página de produto."""


class ProductData(TypedDict):
    """Resultado de :meth:`BaseScraper.parse_url`."""

    url: str
    title: str
    price: Decimal | None
    currency: str | None
    in_stock: bool | None
    marketplace: str
    image_url: str | None


class StockAndPrice(TypedDict):
    """Resultado de :meth:`BaseScraper.check_stock_and_price`."""

    url: str
    price: Decimal | None
    currency: str | None
    in_stock: bool | None


class BaseScraper(ABC):
    """Contrato mínimo de um scraper.

    ``in_stock`` é ``None`` quando a página não informa disponibilidade;
    ``price`` é ``None`` quando não foi possível encontrar o preço.
    """

    #: Nome curto usado em logs e no registro de scrapers.
    name: str = "base"

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Indica se este scraper sabe lidar com a URL."""

    @abstractmethod
    def parse_url(self, url: str) -> ProductData:
        """Baixa a página e extrai os dados completos do produto."""

    def close(self) -> None:
        """Libera recursos (conexões HTTP, sessões). Padrão: nada a fazer."""

    def check_stock_and_price(self, url: str) -> StockAndPrice:
        """Consulta rápida de preço/estoque, usada pela fila de retentativa.

        A implementação padrão reaproveita :meth:`parse_url`; scrapers
        específicos podem sobrescrever com uma chamada mais barata (API interna
        da loja, por exemplo).
        """
        data = self.parse_url(url)
        return {
            "url": data["url"],
            "price": data["price"],
            "currency": data["currency"],
            "in_stock": data["in_stock"],
        }
