"""Utilidades para extrair e normalizar links de mensagens e páginas."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Captura http(s)://... até um espaço ou caractere que normalmente encerra o
# link em mensagens de chat.
_URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_TRAILING_PUNCTUATION = ".,;:!?)]}>*_~"

_TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref_src",
    "si",
}

# Domínio -> nome amigável do marketplace. Subdomínios também casam.
_MARKETPLACE_NAMES = {
    "amazon.com.br": "Amazon",
    "amzn.to": "Amazon",
    "mercadolivre.com.br": "Mercado Livre",
    "mercadolibre.com": "Mercado Livre",
    "kabum.com.br": "KaBuM!",
    "magazineluiza.com.br": "Magazine Luiza",
    "magalu.com": "Magazine Luiza",
    "pichau.com.br": "Pichau",
    "terabyteshop.com.br": "Terabyte",
    "aliexpress.com": "AliExpress",
    "shopee.com.br": "Shopee",
    "americanas.com.br": "Americanas",
    "casasbahia.com.br": "Casas Bahia",
}


def extract_urls(text: str | None) -> list[str]:
    """Retorna as URLs http(s) de um texto, sem duplicatas e na ordem original."""
    if not text:
        return []
    seen: dict[str, None] = {}
    for match in _URL_RE.findall(text):
        url = match.rstrip(_TRAILING_PUNCTUATION)
        if url and url not in seen:
            seen[url] = None
    return list(seen)


def clean_url(url: str) -> str:
    """Remove fragmento e parâmetros de rastreamento (utm_*, fbclid...)."""
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMS
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path or "/",
            urlencode(query, doseq=True),
            "",
        )
    )


def marketplace_from_url(url: str) -> str:
    """Nome do marketplace a partir do domínio (ou o próprio domínio)."""
    host = (urlsplit(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    for domain, name in _MARKETPLACE_NAMES.items():
        if host == domain or host.endswith("." + domain):
            return name
    return host[:80] or "desconhecido"
