"""Cliente HTTP leve e seguro para baixar páginas de produto."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from .base import ScraperError

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MAX_RESPONSE_BYTES = 3 * 1024 * 1024
MAX_REDIRECTS = 8

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6",
}


@dataclass(frozen=True)
class FetchedPage:
    url: str
    """URL final, depois de seguir redirecionamentos (encurtadores etc.)."""
    html: str
    status_code: int


def ensure_public_url(url: str) -> None:
    """Bloqueia esquemas não-HTTP e destinos em redes privadas/locais.

    Os links chegam de mensagens de terceiros (Telegram), então o servidor não
    pode ser usado para acessar serviços internos (SSRF).
    """
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise ScraperError(f"Esquema não permitido: {parts.scheme or '(vazio)'}")
    host = parts.hostname
    if not host:
        raise ScraperError("URL sem host")

    try:
        infos = socket.getaddrinfo(host, parts.port or None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ScraperError(f"Não foi possível resolver {host}") from exc

    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        if not address.is_global:
            raise ScraperError(f"Destino não permitido: {host} ({address})")


def _guard_request(request: httpx.Request) -> None:
    try:
        ensure_public_url(str(request.url))
    except ScraperError as exc:
        raise httpx.RequestError(str(exc), request=request) from exc


def build_client(**kwargs) -> httpx.Client:
    """Cria o cliente padrão, com bloqueio de redes privadas em cada redirect."""
    hooks = kwargs.pop("event_hooks", {})
    hooks.setdefault("request", []).append(_guard_request)
    return httpx.Client(
        headers=DEFAULT_HEADERS,
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
        max_redirects=MAX_REDIRECTS,
        event_hooks=hooks,
        **kwargs,
    )


def fetch_page(client: httpx.Client, url: str) -> FetchedPage:
    """Baixa a página limitando o tamanho da resposta."""
    try:
        with client.stream("GET", url) as response:
            if response.status_code >= 400:
                raise ScraperError(f"HTTP {response.status_code} ao acessar {url}")

            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                chunks.append(chunk)
                total += len(chunk)
                if total >= MAX_RESPONSE_BYTES:
                    break

            html = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
            return FetchedPage(
                url=str(response.url),
                html=html,
                status_code=response.status_code,
            )
    except httpx.HTTPError as exc:
        raise ScraperError(f"Falha ao baixar {url}: {exc}") from exc
