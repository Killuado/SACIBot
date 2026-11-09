"""Scraper genérico baseado em dados estruturados (JSON-LD / OpenGraph).

A maioria das lojas publica ``<script type="application/ld+json">`` com um nó
``Product`` contendo nome, preço e disponibilidade. Ler esses metadados com
httpx + BeautifulSoup é muito mais rápido e leve do que abrir um navegador.
"""

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper, ProductData, ScraperError
from .fetch import build_client, fetch_page
from .links import marketplace_from_url

logger = logging.getLogger(__name__)

_MAX_DEPTH = 8

_IN_STOCK = {
    "instock",
    "limitedavailability",
    "onlineonly",
    "preorder",
    "presale",
    "backorder",
    "in stock",
    "available for order",
}
_OUT_OF_STOCK = {
    "outofstock",
    "soldout",
    "discontinued",
    "instoreonly",
    "out of stock",
}


# --------------------------------------------------------------------------- #
# Conversões
# --------------------------------------------------------------------------- #


def parse_price(value: Any) -> Decimal | None:
    """Converte preços como ``1999.9``, ``"1.999,90"`` ou ``"R$ 2.099"``."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            price = Decimal(str(value))
        except InvalidOperation:
            return None
        return price.quantize(Decimal("0.01")) if price >= 0 else None

    text = re.sub(r"[^\d.,]", "", str(value))
    if not text or not any(ch.isdigit() for ch in text):
        return None

    if "," in text and "." in text:
        # O separador que aparece por último é o decimal.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        integer, _, decimals = text.rpartition(",")
        if len(decimals) in (1, 2):
            text = integer.replace(",", "") + "." + decimals
        else:
            text = text.replace(",", "")
    elif text.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", text):
        # "1.999.990" ou "2.099": pontos como separador de milhar (padrão BR).
        text = text.replace(".", "")

    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def parse_availability(value: Any) -> bool | None:
    """Interpreta ``https://schema.org/InStock``, ``"in stock"`` etc."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, list):
        results = [parse_availability(item) for item in value]
        return next((r for r in results if r is not None), None)
    text = str(value).strip().lower()
    token = re.split(r"[/:#]", text)[-1].strip()
    if token in _IN_STOCK or text in _IN_STOCK:
        return True
    if token in _OUT_OF_STOCK or text in _OUT_OF_STOCK:
        return False
    return None


def _first_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        for item in value:
            text = _first_text(item)
            if text:
                return text
    if isinstance(value, dict):
        return _first_text(value.get("url") or value.get("contentUrl") or value.get("@id"))
    return None


def _has_type(node: dict, wanted: str) -> bool:
    types = node.get("@type")
    if isinstance(types, str):
        types = [types]
    if not isinstance(types, list):
        return False
    return any(isinstance(t, str) and t.split(":")[-1].lower() == wanted for t in types)


# --------------------------------------------------------------------------- #
# JSON-LD
# --------------------------------------------------------------------------- #


def _load_json_ld_blocks(soup: BeautifulSoup) -> Iterator[Any]:
    for script in soup.find_all("script"):
        script_type = (script.get("type") or "").lower()
        if not script_type.startswith("application/ld+json"):
            continue
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue
        try:
            yield json.loads(raw, strict=False)
        except json.JSONDecodeError:
            logger.debug("JSON-LD inválido ignorado")


def _iter_products(node: Any, depth: int = 0) -> Iterator[dict]:
    if depth > _MAX_DEPTH:
        return
    if isinstance(node, list):
        for item in node:
            yield from _iter_products(item, depth + 1)
    elif isinstance(node, dict):
        if _has_type(node, "product"):
            yield node
            # Variações costumam vir em "hasVariant"; o produto pai basta.
            return
        if _has_type(node, "productgroup"):
            variants = node.get("hasVariant")
            if variants:
                yield from _iter_products(variants, depth + 1)
                return
        for value in node.values():
            if isinstance(value, (dict, list)):
                yield from _iter_products(value, depth + 1)


def _iter_offers(offers: Any, depth: int = 0) -> Iterator[dict]:
    if depth > _MAX_DEPTH:
        return
    if isinstance(offers, list):
        for item in offers:
            yield from _iter_offers(item, depth + 1)
    elif isinstance(offers, dict):
        nested = offers.get("offers")
        if nested and _has_type(offers, "aggregateoffer"):
            yield offers
            yield from _iter_offers(nested, depth + 1)
        else:
            yield offers


def _offer_price(offer: dict) -> Decimal | None:
    for key in ("price", "lowPrice"):
        price = parse_price(offer.get(key))
        if price is not None:
            return price
    spec = offer.get("priceSpecification")
    for item in spec if isinstance(spec, list) else [spec]:
        if isinstance(item, dict):
            price = parse_price(item.get("price"))
            if price is not None:
                return price
    return None


def _offer_currency(offer: dict) -> str | None:
    currency = offer.get("priceCurrency")
    if not currency:
        spec = offer.get("priceSpecification")
        if isinstance(spec, dict):
            currency = spec.get("priceCurrency")
    return str(currency).upper() if currency else None


def _summarize_offers(offers: Any) -> tuple[Decimal | None, str | None, bool | None]:
    """Escolhe o menor preço, priorizando ofertas disponíveis."""
    parsed = []
    for offer in _iter_offers(offers):
        parsed.append(
            (
                _offer_price(offer),
                _offer_currency(offer),
                parse_availability(offer.get("availability")),
            )
        )
    if not parsed:
        return None, None, None

    priced = [item for item in parsed if item[0] is not None]
    available = [item for item in priced if item[2] is True]
    pool = available or priced
    if pool:
        price, currency, _ = min(pool, key=lambda item: item[0])
    else:
        price, currency = None, next((c for _, c, _ in parsed if c), None)

    availabilities = [a for _, _, a in parsed if a is not None]
    if any(availabilities):
        in_stock: bool | None = True
    elif availabilities:
        in_stock = False
    else:
        in_stock = None
    return price, currency, in_stock


def _product_from_json_ld(soup: BeautifulSoup) -> dict | None:
    best: dict | None = None
    for block in _load_json_ld_blocks(soup):
        for product in _iter_products(block):
            price, currency, in_stock = _summarize_offers(product.get("offers"))
            candidate = {
                "title": _first_text(product.get("name")),
                "price": price,
                "currency": currency,
                "in_stock": in_stock,
                "image_url": _first_text(product.get("image")),
            }
            if candidate["title"] and candidate["price"] is not None:
                return candidate
            if best is None and candidate["title"]:
                best = candidate
    return best


# --------------------------------------------------------------------------- #
# Fallback: OpenGraph / microdata
# --------------------------------------------------------------------------- #


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def _itemprop(soup: BeautifulSoup, prop: str) -> str | None:
    tag = soup.find(attrs={"itemprop": prop})
    if not tag:
        return None
    for attr in ("content", "href", "src"):
        if tag.get(attr):
            return str(tag[attr]).strip()
    return tag.get_text(strip=True) or None


def _product_from_meta(soup: BeautifulSoup) -> dict:
    title = _meta(soup, "og:title", "twitter:title") or _itemprop(soup, "name")
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()
    return {
        "title": title,
        "price": parse_price(
            _meta(soup, "product:price:amount", "og:price:amount") or _itemprop(soup, "price")
        ),
        "currency": (
            _meta(soup, "product:price:currency", "og:price:currency")
            or _itemprop(soup, "priceCurrency")
        ),
        "in_stock": parse_availability(
            _meta(soup, "product:availability", "og:availability")
            or _itemprop(soup, "availability")
        ),
        "image_url": _meta(soup, "og:image") or _itemprop(soup, "image"),
    }


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #


def extract_product(html: str, url: str) -> ProductData:
    """Extrai os dados do produto de um HTML já baixado."""
    soup = BeautifulSoup(html, "html.parser")
    data = _product_from_json_ld(soup) or {}
    fallback = _product_from_meta(soup)
    for key, value in fallback.items():
        if data.get(key) is None:
            data[key] = value

    if not data.get("title"):
        raise ScraperError(f"Nenhum dado de produto encontrado em {url}")

    currency = data.get("currency")
    return {
        "url": url,
        "title": " ".join(data["title"].split())[:300],
        "price": data.get("price"),
        "currency": currency.upper() if currency else None,
        "in_stock": data.get("in_stock"),
        "marketplace": marketplace_from_url(url),
        "image_url": data.get("image_url"),
    }


class JsonLdScraper(BaseScraper):
    """Scraper HTTP genérico. Funciona como fallback para qualquer loja."""

    name = "jsonld"

    def __init__(self, client: httpx.Client | None = None):
        self._client = client
        self._owns_client = client is None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = build_client()
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "JsonLdScraper":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def can_handle(self, url: str) -> bool:
        return url.lower().startswith(("http://", "https://"))

    def parse_url(self, url: str) -> ProductData:
        page = fetch_page(self.client, url)
        return extract_product(page.html, page.url)
