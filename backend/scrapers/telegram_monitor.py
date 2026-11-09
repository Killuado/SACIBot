"""Monitor de canais do Telegram (Telethon).

Escuta mensagens novas dos canais configurados, extrai os links (texto,
links "escondidos" em palavras e botões inline) e envia cada um para a
ingestão de produtos.

Observação: um *bot* só recebe mensagens de canais onde é administrador. Para
ouvir canais públicos de promoção de terceiros, use uma conta de usuário
(sessão Telethon autenticada por telefone).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable

from asgiref.sync import sync_to_async
from django.conf import settings as django_settings
from django.db import close_old_connections

from .base import BaseScraper
from .dedup import TtlUrlCache
from .ingestion import IngestionResult, ingest_url
from .links import clean_url, extract_urls
from .registry import default_scrapers, get_scraper

logger = logging.getLogger(__name__)

MAX_URLS_PER_MESSAGE = 5


def message_urls(message: Any) -> list[str]:
    """Extrai as URLs de uma mensagem do Telethon (duck typing, sem import)."""
    found: list[str] = []

    found.extend(extract_urls(getattr(message, "message", None) or getattr(message, "text", None)))

    # MessageEntityTextUrl: link associado a um texto ("Clique aqui").
    for entity in getattr(message, "entities", None) or []:
        url = getattr(entity, "url", None)
        if isinstance(url, str):
            found.extend(extract_urls(url))

    # Botões inline ("🛒 Comprar").
    markup = getattr(message, "reply_markup", None)
    for row in getattr(markup, "rows", None) or []:
        for button in getattr(row, "buttons", None) or []:
            url = getattr(button, "url", None)
            if isinstance(url, str):
                found.extend(extract_urls(url))

    return list(dict.fromkeys(found))


@dataclass
class TelegramSettings:
    api_id: int
    api_hash: str
    session: str
    channels: list[str]
    bot_token: str = ""
    link_ttl_seconds: float | None = None


class TelegramMonitor:
    def __init__(
        self,
        settings: TelegramSettings,
        scrapers: list[BaseScraper] | None = None,
        recent_cache: TtlUrlCache | None = None,
    ):
        self.settings = settings
        self.scrapers = scrapers if scrapers is not None else default_scrapers()
        ttl = (
            settings.link_ttl_seconds
            if settings.link_ttl_seconds is not None
            else getattr(django_settings, "TELEGRAM_LINK_TTL_SECONDS", 180)
        )
        self.recent = recent_cache or TtlUrlCache(ttl_seconds=ttl)

    # -- Processamento (testável sem Telegram) ------------------------------ #

    def _ingest_sync(self, url: str, source: str) -> IngestionResult:
        close_old_connections()
        try:
            return ingest_url(url, source=source, scraper=get_scraper(url, self.scrapers))
        finally:
            close_old_connections()

    async def handle_message(self, message: Any, source: str) -> list[IngestionResult]:
        results = []
        urls = [clean_url(url) for url in message_urls(message)]
        for url in urls[:MAX_URLS_PER_MESSAGE]:
            if not self.recent.should_process(url):
                continue
            result = await sync_to_async(self._ingest_sync, thread_sensitive=True)(url, source)
            logger.info("[%s] %s -> %s %s", source, url, result.status, result.reason)
            results.append(result)
        return results

    # -- Conexão com o Telegram -------------------------------------------- #

    async def run(self) -> None:
        from telethon import TelegramClient, events  # import tardio: opcional nos testes

        client = TelegramClient(self.settings.session, self.settings.api_id, self.settings.api_hash)
        if self.settings.bot_token:
            await client.start(bot_token=self.settings.bot_token)
        else:
            await client.start()

        chats: Iterable[str] | None = self.settings.channels or None

        @client.on(events.NewMessage(chats=chats))
        async def on_message(event):  # pragma: no cover - depende do Telegram
            chat = await event.get_chat()
            name = getattr(chat, "username", None) or getattr(chat, "title", None) or event.chat_id
            try:
                await self.handle_message(event.message, source=f"telegram:{name}")
            except Exception:
                logger.exception("Erro ao processar mensagem de %s", name)

        logger.info("Monitor do Telegram ativo em: %s", ", ".join(chats or ["todos os chats"]))
        try:
            await client.run_until_disconnected()
        finally:
            for scraper in self.scrapers:
                scraper.close()
