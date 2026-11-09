"""Supervisor assíncrono que monitora canais/lives do YouTube e ingere os links do chat."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from scrapers.base import BaseScraper
from scrapers.dedup import TtlUrlCache
from scrapers.ingestion import IngestionResult, ingest_url
from scrapers.links import clean_url
from scrapers.registry import default_scrapers, get_scraper

from .models import LiveSession, YouTubeSource
from .youtube.client import LiveChatReader, YouTubeClient
from .youtube.parsing import ChatMessage, ChatUnavailable, LiveStatus

logger = logging.getLogger(__name__)

MAX_QUEUE_SIZE = 500
SESSION_FLUSH_INTERVAL = 5.0
MAX_RECENT_MESSAGES = 15
MAX_RECENT_LINKS = 15


@dataclass
class IngestJob:
    url: str
    source_tag: str
    session_id: int | None = None


@dataclass
class SessionCounters:
    messages_seen: int = 0
    links_seen: int = 0
    links_ingested: int = 0
    promotions_matched: int = 0
    recent_messages: deque[dict] = field(
        default_factory=lambda: deque(maxlen=MAX_RECENT_MESSAGES)
    )
    recent_links: deque[dict] = field(
        default_factory=lambda: deque(maxlen=MAX_RECENT_LINKS)
    )


class YouTubeLiveMonitor:
    """Coordena a verificação periódica de lives, leitura de chats e fila de ingestão."""

    def __init__(
        self,
        yt_client: YouTubeClient | None = None,
        url_cache: TtlUrlCache | None = None,
        scrapers_factory: Callable[[], list[BaseScraper]] = default_scrapers,
        check_interval: float | None = None,
        recheck_live_seconds: float | None = None,
        ingest_workers: int | None = None,
        print_chat: bool = False,
    ):
        self.yt = yt_client or YouTubeClient()
        self._owns_yt = yt_client is None
        ttl = getattr(settings, "YOUTUBE_LINK_TTL_SECONDS", 180)
        self.url_cache = url_cache or TtlUrlCache(ttl_seconds=ttl)
        self.scrapers_factory = scrapers_factory
        self.print_chat = print_chat
        self.check_interval = (
            float(check_interval)
            if check_interval is not None
            else float(getattr(settings, "YOUTUBE_CHECK_INTERVAL", 120))
        )
        self.recheck_live_seconds = (
            float(recheck_live_seconds)
            if recheck_live_seconds is not None
            else float(getattr(settings, "YOUTUBE_RECHECK_LIVE_SECONDS", 300))
        )
        self.ingest_workers = (
            int(ingest_workers)
            if ingest_workers is not None
            else int(getattr(settings, "YOUTUBE_INGEST_WORKERS", 4))
        )

        self.queue: asyncio.Queue[IngestJob] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self.active_tasks: dict[str, asyncio.Task] = {}
        self.session_counters: dict[int, SessionCounters] = {}
        self._check_sem = asyncio.Semaphore(3)

    # ----------------------------------------------------------------------- #
    # Operações de banco (síncronas, chamadas via sync_to_async)
    # ----------------------------------------------------------------------- #

    def _close_orphan_sessions_sync(self) -> int:
        close_old_connections()
        try:
            now = timezone.now()
            YouTubeSource.objects.exclude(current_video_id="").update(current_video_id="")
            return LiveSession.objects.filter(ended_at__isnull=True).update(ended_at=now)
        finally:
            close_old_connections()

    def _list_active_sources_sync(self) -> list[YouTubeSource]:
        close_old_connections()
        try:
            return list(YouTubeSource.objects.filter(enabled=True))
        finally:
            close_old_connections()

    def _get_source_sync(self, source_id: int) -> YouTubeSource | None:
        close_old_connections()
        try:
            return YouTubeSource.objects.filter(pk=source_id).first()
        finally:
            close_old_connections()

    def _mark_checked_offline_sync(
        self,
        source_id: int,
        disable: bool = False,
        note: str = "",
    ) -> None:
        close_old_connections()
        try:
            updates = {
                "last_checked_at": timezone.now(),
                "current_video_id": "",
            }
            if disable:
                updates["enabled"] = False
            if note:
                updates["note"] = note[:200]
            YouTubeSource.objects.filter(pk=source_id).update(**updates)
        finally:
            close_old_connections()

    def _start_session_sync(
        self,
        source_id: int,
        status: LiveStatus,
    ) -> tuple[YouTubeSource, LiveSession]:
        close_old_connections()
        try:
            now = timezone.now()
            source = YouTubeSource.objects.get(pk=source_id)
            source.last_checked_at = now
            source.last_live_at = now
            source.current_video_id = status.video_id or ""
            if status.channel_name:
                source.label = status.channel_name[:120]
            source.note = ""
            source.save(
                update_fields=[
                    "last_checked_at",
                    "last_live_at",
                    "current_video_id",
                    "label",
                    "note",
                ]
            )
            session = LiveSession.objects.create(
                source=source,
                video_id=status.video_id or "",
                title=(status.title or "")[:300],
            )
            return source, session
        finally:
            close_old_connections()

    def _flush_session_sync(
        self,
        session_id: int,
        counters: SessionCounters,
        ended: bool = False,
        source_id: int | None = None,
        disable_source: bool = False,
        note: str = "",
    ) -> None:
        close_old_connections()
        try:
            updates = {
                "messages_seen": counters.messages_seen,
                "links_seen": counters.links_seen,
                "links_ingested": counters.links_ingested,
                "promotions_matched": counters.promotions_matched,
                "recent_messages": list(counters.recent_messages),
                "recent_links": list(counters.recent_links),
            }
            if ended:
                updates["ended_at"] = timezone.now()
            LiveSession.objects.filter(pk=session_id).update(**updates)

            if ended and source_id is not None:
                src_updates: dict = {"current_video_id": ""}
                if disable_source:
                    src_updates["enabled"] = False
                if note:
                    src_updates["note"] = note[:200]
                YouTubeSource.objects.filter(pk=source_id).update(**src_updates)
        finally:
            close_old_connections()

    def _ingest_one_sync(
        self,
        url: str,
        source_tag: str,
        scrapers: list[BaseScraper],
    ) -> IngestionResult:
        close_old_connections()
        try:
            scraper = get_scraper(url, scrapers)
            return ingest_url(url, source=source_tag, scraper=scraper)
        finally:
            close_old_connections()

    # ----------------------------------------------------------------------- #
    # Filtragem de mensagens e enfileiramento (testável isoladamente)
    # ----------------------------------------------------------------------- #

    def handle_messages(
        self,
        messages: list[ChatMessage],
        *,
        source_tag: str,
        trusted_authors_only: bool = True,
        session_id: int | None = None,
    ) -> list[str]:
        """Filtra mensagens do chat, aplica o cache TTL e enfileira os links novos.

        Retorna a lista de URLs efetivamente enfileiradas nesta chamada.
        """
        counters = self.session_counters.setdefault(session_id or 0, SessionCounters())
        enqueued: list[str] = []

        for msg in messages:
            counters.messages_seen += 1
            now_str = timezone.localtime().strftime("%H:%M:%S")
            if msg.text or msg.links:
                counters.recent_messages.append(
                    {
                        "time": now_str,
                        "author": msg.author or "Anônimo",
                        "badges": sorted(msg.badges),
                        "text": (msg.text or "")[:180],
                        "pinned": msg.pinned,
                    }
                )
            badge_str = f" [{','.join(sorted(msg.badges))}]" if msg.badges else ""
            links_str = f" | links={msg.links}" if msg.links else ""
            if self.print_chat:
                logger.info("[%s] %s%s: %s%s", source_tag, msg.author, badge_str, msg.text, links_str)
            else:
                logger.debug("[%s] %s%s: %s%s", source_tag, msg.author, badge_str, msg.text, links_str)
            if not msg.links:
                continue

            author_ok = (not trusted_authors_only) or msg.is_trusted
            for raw_url in msg.links:
                url = clean_url(raw_url)
                if not author_ok:
                    counters.recent_links.append(
                        {
                            "time": now_str,
                            "author": msg.author or "Anônimo",
                            "url": url,
                            "status": "ignorado (autor)",
                        }
                    )
                    continue
                counters.links_seen += 1
                if not self.url_cache.should_process(url):
                    counters.recent_links.append(
                        {
                            "time": now_str,
                            "author": msg.author or "Anônimo",
                            "url": url,
                            "status": "ignorado (TTL)",
                        }
                    )
                    continue
                try:
                    self.queue.put_nowait(
                        IngestJob(url=url, source_tag=source_tag, session_id=session_id)
                    )
                    counters.links_ingested += 1
                    enqueued.append(url)
                    counters.recent_links.append(
                        {
                            "time": now_str,
                            "author": msg.author or "Anônimo",
                            "url": url,
                            "status": "enfileirado",
                        }
                    )
                except asyncio.QueueFull:
                    logger.warning("Fila de ingestão do YouTube cheia; descartando %s", url)

        return enqueued

    # ----------------------------------------------------------------------- #
    # Worker de ingestão
    # ----------------------------------------------------------------------- #

    async def process_next_job(self, scrapers: list[BaseScraper]) -> IngestionResult | None:
        """Processa um único item da fila (útil em testes)."""
        try:
            job = self.queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
        try:
            result = await sync_to_async(self._ingest_one_sync, thread_sensitive=True)(
                job.url, job.source_tag, scrapers
            )
            if job.session_id and result.matches:
                counters = self.session_counters.get(job.session_id)
                if counters is not None:
                    counters.promotions_matched += 1
            logger.info("[%s] %s -> %s %s", job.source_tag, job.url, result.status, result.reason)
            return result
        finally:
            self.queue.task_done()

    async def _worker_loop(self, worker_id: int) -> None:
        scrapers = self.scrapers_factory()
        try:
            while True:
                job = await self.queue.get()
                try:
                    result = await sync_to_async(self._ingest_one_sync, thread_sensitive=False)(
                        job.url, job.source_tag, scrapers
                    )
                    if job.session_id and result.matches:
                        counters = self.session_counters.get(job.session_id)
                        if counters is not None:
                            counters.promotions_matched += 1
                    logger.info(
                        "[worker-%d][%s] %s -> %s %s",
                        worker_id,
                        job.source_tag,
                        job.url,
                        result.status,
                        result.reason,
                    )
                except Exception:
                    logger.exception("Erro ao ingerir %s", job.url)
                finally:
                    self.queue.task_done()
        finally:
            for scraper in scrapers:
                scraper.close()

    # ----------------------------------------------------------------------- #
    # Task por live e ciclo do supervisor
    # ----------------------------------------------------------------------- #

    async def _watch_live_chat(self, source: YouTubeSource, status: LiveStatus) -> None:
        video_id = status.video_id or ""
        source, session = await sync_to_async(self._start_session_sync, thread_sensitive=True)(
            source.pk, status
        )
        counters = SessionCounters()
        self.session_counters[session.pk] = counters
        tag_name = source.label or source.identifier
        source_tag = f"youtube:{tag_name}"[:120]

        logger.info(
            "Conectado ao chat da live %s (%s) — %s",
            video_id,
            tag_name,
            status.title,
        )

        reader = LiveChatReader(self.yt, video_id)
        last_flush = 0.0
        last_live_recheck = time.monotonic()
        note = ""
        disable_source = source.kind == YouTubeSource.Kind.VIDEO

        try:
            async for batch in reader.iter_batches():
                self.handle_messages(
                    batch,
                    source_tag=source_tag,
                    trusted_authors_only=source.trusted_authors_only,
                    session_id=session.pk,
                )
                now = time.monotonic()
                if (now - last_flush) >= SESSION_FLUSH_INTERVAL:
                    src_now = await sync_to_async(self._get_source_sync, thread_sensitive=True)(
                        source.pk
                    )
                    if src_now is None or not src_now.enabled:
                        note = "Fonte desativada manualmente."
                        disable_source = False
                        break
                    await sync_to_async(self._flush_session_sync, thread_sensitive=True)(
                        session.pk, counters
                    )
                    last_flush = now

                if (now - last_live_recheck) >= self.recheck_live_seconds:
                    recheck = await self.yt.check_live(
                        f"https://www.youtube.com/watch?v={video_id}"
                    )
                    last_live_recheck = now
                    if not recheck.is_live:
                        note = "Live encerrada."
                        break
            else:
                note = "Live encerrada."
        except ChatUnavailable as exc:
            note = str(exc)
            logger.warning("Chat indisponível para %s: %s", video_id, exc)
        except asyncio.CancelledError:
            note = "Monitor encerrado."
            disable_source = False
            raise
        except Exception as exc:
            note = f"Erro inesperado: {exc}"
            disable_source = False
            logger.exception("Erro na task do chat %s", video_id)
        finally:
            await sync_to_async(self._flush_session_sync, thread_sensitive=True)(
                session.pk,
                counters,
                ended=True,
                source_id=source.pk,
                disable_source=disable_source,
                note=note,
            )
            self.session_counters.pop(session.pk, None)
            self.active_tasks.pop(video_id, None)
            logger.info(
                "Sessão da live %s encerrada (%d msgs, %d links, %d ingeridos).",
                video_id,
                counters.messages_seen,
                counters.links_seen,
                counters.links_ingested,
            )

    async def check_source_once(self, source: YouTubeSource) -> LiveStatus | None:
        """Verifica uma fonte e, se estiver ao vivo, garante que há uma task de chat."""
        if source.current_video_id and source.current_video_id in self.active_tasks:
            return None

        async with self._check_sem:
            status = await self.yt.check_live(source.live_url)

        if not status.is_live or not status.video_id:
            disable = source.kind == YouTubeSource.Kind.VIDEO and not status.is_upcoming
            note = "Live encerrada." if disable else ""
            await sync_to_async(self._mark_checked_offline_sync, thread_sensitive=True)(
                source.pk, disable=disable, note=note
            )
            return status

        if status.video_id in self.active_tasks:
            return status

        task = asyncio.create_task(
            self._watch_live_chat(source, status),
            name=f"yt-chat-{status.video_id}",
        )
        self.active_tasks[status.video_id] = task
        return status

    async def scan_once(self) -> None:
        """Executa uma varredura de todas as fontes ativas."""
        sources = await sync_to_async(self._list_active_sources_sync, thread_sensitive=True)()
        if not sources:
            return
        await asyncio.gather(*(self.check_source_once(src) for src in sources))

    async def run(self) -> None:
        """Loop principal do supervisor."""
        await sync_to_async(self._close_orphan_sessions_sync, thread_sensitive=True)()
        workers = [
            asyncio.create_task(self._worker_loop(i + 1), name=f"yt-ingest-{i + 1}")
            for i in range(self.ingest_workers)
        ]
        logger.info(
            "Monitor de lives do YouTube iniciado (intervalo=%.0fs, TTL=%.0fs, workers=%d).",
            self.check_interval,
            self.url_cache.ttl_seconds,
            self.ingest_workers,
        )
        try:
            while True:
                await self.scan_once()
                await asyncio.sleep(self.check_interval)
        finally:
            for task in list(self.active_tasks.values()):
                task.cancel()
            if self.active_tasks:
                await asyncio.gather(*self.active_tasks.values(), return_exceptions=True)
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            if self._owns_yt:
                await self.yt.aclose()
