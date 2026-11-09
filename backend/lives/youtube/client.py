"""Cliente assíncrono para verificar lives e ler o chat ao vivo do YouTube (innertube)."""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

import httpx

from .parsing import (
    ChatBootstrap,
    ChatMessage,
    ChatPollBatch,
    ChatUnavailable,
    LiveStatus,
    parse_chat_bootstrap,
    parse_chat_poll,
    parse_live_status,
)

logger = logging.getLogger(__name__)

YOUTUBE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6",
}
YOUTUBE_COOKIES = {"SOCS": "CAI", "CONSENT": "YES+"}

MIN_POLL_SECONDS = 3.0
MAX_POLL_SECONDS = 15.0
MAX_CONSECUTIVE_POLL_ERRORS = 5
MAX_CHAT_REOPENS = 3


def build_youtube_async_client(**kwargs) -> httpx.AsyncClient:
    headers = {**YOUTUBE_HEADERS, **kwargs.pop("headers", {})}
    cookies = {**YOUTUBE_COOKIES, **kwargs.pop("cookies", {})}
    return httpx.AsyncClient(
        headers=headers,
        cookies=cookies,
        follow_redirects=True,
        timeout=httpx.Timeout(15.0, connect=5.0),
        **kwargs,
    )


class YouTubeClient:
    """Encapsula chamadas HTTP assíncronas ao YouTube."""

    def __init__(self, http: httpx.AsyncClient | None = None):
        self._http = http
        self._owns_http = http is None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = build_youtube_async_client()
        return self._http

    async def aclose(self) -> None:
        if self._owns_http and self._http is not None:
            await self._http.aclose()
            self._http = None

    async def __aenter__(self) -> "YouTubeClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()

    async def check_live(self, live_url: str) -> LiveStatus:
        """Consulta ``/<canal>/live`` ou ``/watch?v=<id>`` e retorna o estado da live."""
        try:
            response = await self.http.get(live_url)
            if response.status_code >= 400:
                logger.warning("HTTP %s ao verificar live em %s", response.status_code, live_url)
                return LiveStatus(is_live=False)
            return parse_live_status(response.text)
        except httpx.HTTPError as exc:
            logger.warning("Erro de rede ao verificar %s: %s", live_url, exc)
            return LiveStatus(is_live=False)

    async def open_chat(self, video_id: str) -> ChatBootstrap:
        """Abre ``/live_chat?v=<video_id>&is_popout=1`` e extrai o bootstrap."""
        try:
            response = await self.http.get(
                "https://www.youtube.com/live_chat",
                params={"v": video_id, "is_popout": "1"},
            )
        except httpx.HTTPError as exc:
            raise ChatUnavailable(f"Erro ao abrir chat de {video_id}: {exc}") from exc

        if response.status_code >= 400:
            raise ChatUnavailable(f"HTTP {response.status_code} ao abrir chat de {video_id}")
        return parse_chat_bootstrap(response.text)

    async def poll_chat(
        self,
        context: dict,
        continuation: str,
        api_key: str = "",
    ) -> ChatPollBatch:
        """Executa um poll em ``/youtubei/v1/live_chat/get_live_chat``."""
        params = {"prettyPrint": "false"}
        if api_key:
            params["key"] = api_key
        response = await self.http.post(
            "https://www.youtube.com/youtubei/v1/live_chat/get_live_chat",
            params=params,
            json={"context": context, "continuation": continuation},
        )
        if response.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {response.status_code}",
                request=response.request,
                response=response,
            )
        return parse_chat_poll(response.json())


class LiveChatReader:
    """Itera sobre lotes de mensagens de uma live até ela acabar."""

    def __init__(
        self,
        yt: YouTubeClient,
        video_id: str,
        sleep_fn=asyncio.sleep,
    ):
        self.yt = yt
        self.video_id = video_id
        self._sleep = sleep_fn
        self._seen_ids: set[str] = set()

    def _filter_new(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        fresh: list[ChatMessage] = []
        for msg in messages:
            if msg.id:
                if msg.id in self._seen_ids:
                    continue
                self._seen_ids.add(msg.id)
                if len(self._seen_ids) > 5000:
                    # Evita crescimento infinito em lives de muitas horas.
                    self._seen_ids.clear()
            fresh.append(msg)
        return fresh

    async def iter_batches(self) -> AsyncIterator[list[ChatMessage]]:
        """Gera listas de :class:`ChatMessage` novas até a live terminar."""
        reopens = 0
        bootstrap = await self.yt.open_chat(self.video_id)
        initial = self._filter_new(bootstrap.initial_messages)
        if initial:
            yield initial

        continuation: str | None = bootstrap.continuation
        context = bootstrap.context
        api_key = bootstrap.api_key
        consecutive_errors = 0

        while continuation:
            try:
                batch = await self.yt.poll_chat(context, continuation, api_key=api_key)
                consecutive_errors = 0
            except (httpx.HTTPError, ValueError) as exc:
                consecutive_errors += 1
                backoff = min(60.0, float(2**consecutive_errors))
                logger.warning(
                    "Falha no poll do chat %s (%d/%d): %s — aguardando %.0fs",
                    self.video_id,
                    consecutive_errors,
                    MAX_CONSECUTIVE_POLL_ERRORS,
                    exc,
                    backoff,
                )
                await self._sleep(backoff)
                if consecutive_errors < MAX_CONSECUTIVE_POLL_ERRORS:
                    continue
                reopens += 1
                if reopens > MAX_CHAT_REOPENS:
                    raise ChatUnavailable(
                        f"Chat de {self.video_id} instável após {MAX_CHAT_REOPENS} reaberturas."
                    ) from exc
                bootstrap = await self.yt.open_chat(self.video_id)
                continuation = bootstrap.continuation
                context = bootstrap.context
                api_key = bootstrap.api_key
                consecutive_errors = 0
                continue

            fresh = self._filter_new(batch.messages)
            if fresh:
                yield fresh

            if not batch.continuation:
                break

            continuation = batch.continuation
            wait_seconds = max(
                MIN_POLL_SECONDS,
                min(MAX_POLL_SECONDS, batch.timeout_ms / 1000.0),
            )
            await self._sleep(wait_seconds)
