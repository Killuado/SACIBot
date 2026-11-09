"""Funções puras para interpretar entradas do usuário, páginas do YouTube e JSON do chat (innertube)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterator
from urllib.parse import parse_qs, unquote, urlsplit

from scrapers.links import extract_urls

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
_HANDLE_RE = re.compile(r"^@[A-Za-z0-9_.-]{3,60}$")
_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]{2,80}$")

TRUSTED_BADGES = frozenset({"OWNER", "MODERATOR", "VERIFIED"})


class ChatUnavailable(Exception):
    """A live não possui chat ativo ou a página do chat não pôde ser interpretada."""


@dataclass(frozen=True)
class LiveStatus:
    is_live: bool
    video_id: str | None = None
    title: str = ""
    channel_name: str = ""
    is_upcoming: bool = False


@dataclass(frozen=True)
class ChatBootstrap:
    api_key: str
    context: dict[str, Any]
    continuation: str
    initial_messages: list[ChatMessage]


@dataclass(frozen=True)
class ChatPollBatch:
    messages: list[ChatMessage]
    continuation: str | None
    timeout_ms: int = 5000


@dataclass(frozen=True)
class ChatMessage:
    id: str
    author: str
    author_channel_id: str
    badges: frozenset[str]
    text: str
    links: list[str]
    pinned: bool = False

    @property
    def is_trusted(self) -> bool:
        return bool(self.badges & TRUSTED_BADGES)


# --------------------------------------------------------------------------- #
# 1. Entrada do usuário -> (kind, identifier)
# --------------------------------------------------------------------------- #


def parse_source_input(raw: str) -> tuple[str, str]:
    """Normaliza um canal ou live informada pelo usuário para ``(kind, identifier)``.

    ``kind`` é ``"channel"`` ou ``"video"``.
    Levanta :class:`ValueError` quando a entrada não é reconhecida.
    """
    value = (raw or "").strip()
    if not value:
        raise ValueError("Informe um canal (@loja, UC...) ou link de live do YouTube.")

    if _HANDLE_RE.fullmatch(value):
        return ("channel", value)
    if _CHANNEL_ID_RE.fullmatch(value):
        return ("channel", value)
    if _VIDEO_ID_RE.fullmatch(value):
        return ("video", value)
    if value.startswith(("c/", "user/")):
        prefix, _, slug = value.partition("/")
        if _SLUG_RE.fullmatch(slug):
            return ("channel", f"{prefix}/{slug}")

    url_text = value
    if not url_text.lower().startswith(("http://", "https://")):
        if url_text.lower().startswith(("youtube.com/", "www.youtube.com/", "m.youtube.com/", "youtu.be/")):
            url_text = "https://" + url_text
        else:
            raise ValueError(f"Fonte do YouTube inválida: {raw}")

    parts = urlsplit(url_text)
    host = (parts.hostname or "").lower()
    if host not in _YOUTUBE_HOSTS:
        raise ValueError("Apenas links do YouTube são permitidos.")

    segments = [unquote(seg) for seg in parts.path.split("/") if seg]

    if host == "youtu.be":
        if segments and _VIDEO_ID_RE.fullmatch(segments[0]):
            return ("video", segments[0])
        raise ValueError("Link encurtado do YouTube inválido.")

    query = parse_qs(parts.query)
    if not segments or segments[0] == "watch":
        vid = (query.get("v") or [""])[0]
        if _VIDEO_ID_RE.fullmatch(vid):
            return ("video", vid)
        raise ValueError("Link de vídeo do YouTube sem parâmetro v válido.")

    first = segments[0]
    if first in {"live", "shorts", "embed"} and len(segments) >= 2:
        vid = segments[1]
        if _VIDEO_ID_RE.fullmatch(vid):
            return ("video", vid)
        raise ValueError("ID da live inválido na URL.")

    if first.startswith("@") and _HANDLE_RE.fullmatch(first):
        return ("channel", first)

    if first == "channel" and len(segments) >= 2 and _CHANNEL_ID_RE.fullmatch(segments[1]):
        return ("channel", segments[1])

    if first in {"c", "user"} and len(segments) >= 2 and _SLUG_RE.fullmatch(segments[1]):
        return ("channel", f"{first}/{segments[1]}")

    raise ValueError(f"Não foi possível identificar o canal ou live em: {raw}")


# --------------------------------------------------------------------------- #
# 2. Extração segura de objetos JSON embutidos em HTML
# --------------------------------------------------------------------------- #


def _extract_json_after(text: str, marker: str) -> dict[str, Any] | None:
    idx = text.find(marker)
    if idx < 0:
        return None
    brace = text.find("{", idx + len(marker))
    if brace < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text, brace)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _extract_initial_player_response(html: str) -> dict[str, Any] | None:
    for marker in (
        "var ytInitialPlayerResponse =",
        'window["ytInitialPlayerResponse"] =',
        "ytInitialPlayerResponse =",
    ):
        data = _extract_json_after(html, marker)
        if data:
            return data
    return None


def _extract_initial_data(html: str) -> dict[str, Any] | None:
    for marker in (
        'window["ytInitialData"] =',
        "var ytInitialData =",
        "ytInitialData =",
    ):
        data = _extract_json_after(html, marker)
        if data:
            return data
    return None


# --------------------------------------------------------------------------- #
# 3. Detectar se está ao vivo
# --------------------------------------------------------------------------- #


def parse_live_status(html: str) -> LiveStatus:
    """Interpreta o HTML de ``/<canal>/live`` ou ``/watch?v=<id>``."""
    player = _extract_initial_player_response(html)
    if not player:
        return LiveStatus(is_live=False)

    details = player.get("videoDetails")
    if not isinstance(details, dict):
        return LiveStatus(is_live=False)

    video_id = details.get("videoId")
    if not isinstance(video_id, str) or not _VIDEO_ID_RE.fullmatch(video_id):
        return LiveStatus(is_live=False)

    is_live_detail = bool(details.get("isLive"))
    is_upcoming = bool(details.get("isUpcoming"))
    broadcast = (
        player.get("microformat", {})
        .get("playerMicroformatRenderer", {})
        .get("liveBroadcastDetails", {})
    )
    is_live_now = broadcast.get("isLiveNow") if isinstance(broadcast, dict) else None

    # Se liveBroadcastDetails existir e disser explicitamente False, a live já acabou.
    if is_live_now is False:
        is_live = False
    else:
        is_live = bool(is_live_detail and not is_upcoming)

    return LiveStatus(
        is_live=is_live,
        video_id=video_id,
        title=str(details.get("title") or "").strip(),
        channel_name=str(details.get("author") or "").strip(),
        is_upcoming=is_upcoming,
    )


# --------------------------------------------------------------------------- #
# 4. Abrir e fazer polling do chat (innertube)
# --------------------------------------------------------------------------- #


def _extract_continuation(continuations: Any) -> tuple[str | None, int]:
    if not isinstance(continuations, list):
        return None, 5000
    for entry in continuations:
        if not isinstance(entry, dict):
            continue
        for key in (
            "invalidationContinuationData",
            "timedContinuationData",
            "reloadContinuationData",
            "liveChatReplayContinuationData",
        ):
            data = entry.get(key)
            if isinstance(data, dict) and isinstance(data.get("continuation"), str):
                timeout = data.get("timeoutMs")
                timeout_ms = int(timeout) if isinstance(timeout, (int, float)) else 5000
                return data["continuation"], timeout_ms
    return None, 5000


def _prefer_all_chat_continuation(renderer: dict[str, Any]) -> str | None:
    """Seleciona a aba 'Chat ao vivo' (todas as mensagens) quando disponível."""
    items = (
        renderer.get("header", {})
        .get("liveChatHeaderRenderer", {})
        .get("viewSelector", {})
        .get("sortFilterSubMenuRenderer", {})
        .get("subMenuItems", [])
    )
    if isinstance(items, list) and len(items) >= 2:
        last = items[-1]
        if isinstance(last, dict):
            token = (
                last.get("continuation", {})
                .get("reloadContinuationData", {})
                .get("continuation")
            )
            if isinstance(token, str) and token:
                return token
    return None


def parse_chat_bootstrap(html: str) -> ChatBootstrap:
    """Extrai chave, contexto, continuation token e mensagens iniciais de ``/live_chat``."""
    key_match = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"', html)
    api_key = key_match.group(1) if key_match else ""

    context = _extract_json_after(html, '"INNERTUBE_CONTEXT":') or {
        "client": {"clientName": "WEB", "clientVersion": "2.20260101.00.00", "hl": "pt-BR"}
    }

    initial = _extract_initial_data(html)
    if not initial:
        raise ChatUnavailable("ytInitialData não encontrado na página do chat.")

    renderer = initial.get("contents", {}).get("liveChatRenderer")
    if not isinstance(renderer, dict):
        raise ChatUnavailable("liveChatRenderer ausente (chat desativado ou indisponível).")

    continuation = _prefer_all_chat_continuation(renderer)
    if not continuation:
        continuation, _ = _extract_continuation(renderer.get("continuations"))
    if not continuation:
        raise ChatUnavailable("Token de continuation não encontrado no chat.")

    initial_messages = parse_chat_actions(renderer.get("actions") or [])
    return ChatBootstrap(
        api_key=api_key,
        context=context,
        continuation=continuation,
        initial_messages=initial_messages,
    )


def parse_chat_poll(payload: dict[str, Any]) -> ChatPollBatch:
    """Interpreta a resposta JSON de ``/youtubei/v1/live_chat/get_live_chat``."""
    if not isinstance(payload, dict):
        return ChatPollBatch(messages=[], continuation=None)

    live_cont = payload.get("continuationContents", {}).get("liveChatContinuation")
    if not isinstance(live_cont, dict):
        return ChatPollBatch(messages=[], continuation=None)

    messages = parse_chat_actions(live_cont.get("actions") or [])
    continuation, timeout_ms = _extract_continuation(live_cont.get("continuations"))
    return ChatPollBatch(messages=messages, continuation=continuation, timeout_ms=timeout_ms)


# --------------------------------------------------------------------------- #
# 5. Extração de mensagens, autores, badges e links do chat
# --------------------------------------------------------------------------- #


def unwrap_youtube_redirect(url: str) -> str:
    """Desembrulha ``https://www.youtube.com/redirect?...&q=<url real>``."""
    raw = (url or "").strip()
    if raw.startswith("//"):
        raw = "https:" + raw
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    if host in _YOUTUBE_HOSTS and parts.path == "/redirect":
        target = (parse_qs(parts.query).get("q") or [""])[0]
        if target.lower().startswith(("http://", "https://")):
            return target
    return raw


def _iter_message_renderers(actions: list[Any]) -> Iterator[tuple[dict[str, Any], bool]]:
    """Produz ``(renderer, pinned)`` a partir da lista de ``actions`` do innertube."""
    for action in actions:
        if not isinstance(action, dict):
            continue

        item = action.get("addChatItemAction", {}).get("item")
        if not isinstance(item, dict):
            item = action.get("replaceChatItemAction", {}).get("replacementItem")
        if isinstance(item, dict):
            for key in ("liveChatTextMessageRenderer", "liveChatPaidMessageRenderer"):
                renderer = item.get(key)
                if isinstance(renderer, dict):
                    yield renderer, False

        banner_contents = (
            action.get("addBannerToLiveChatCommand", {})
            .get("bannerRenderer", {})
            .get("liveChatBannerRenderer", {})
            .get("contents")
        )
        if isinstance(banner_contents, dict):
            renderer = banner_contents.get("liveChatTextMessageRenderer")
            if isinstance(renderer, dict):
                yield renderer, True


def _extract_badges(renderer: dict[str, Any]) -> frozenset[str]:
    badges: set[str] = set()
    for entry in renderer.get("authorBadges") or []:
        if not isinstance(entry, dict):
            continue
        icon_type = (
            entry.get("liveChatAuthorBadgeRenderer", {})
            .get("icon", {})
            .get("iconType")
        )
        if isinstance(icon_type, str) and icon_type:
            badges.add(icon_type.upper())
    return frozenset(badges)


def _extract_text_and_links(renderer: dict[str, Any]) -> tuple[str, list[str]]:
    runs = renderer.get("message", {}).get("runs")
    if not isinstance(runs, list):
        return "", []

    parts: list[str] = []
    links: list[str] = []

    for run in runs:
        if not isinstance(run, dict):
            continue
        text = run.get("text")
        if isinstance(text, str):
            parts.append(text)

        nav_url = (
            run.get("navigationEndpoint", {})
            .get("urlEndpoint", {})
            .get("url")
        )
        if isinstance(nav_url, str) and nav_url:
            real_url = unwrap_youtube_redirect(nav_url)
            links.extend(extract_urls(real_url))
        elif isinstance(text, str):
            # Só extrai URL do texto da run quando não há navigationEndpoint,
            # evitando capturar a versão truncada ("kabum.com.br/produto/12…").
            links.extend(extract_urls(text))

    full_text = "".join(parts).strip()
    deduped = list(dict.fromkeys(links))
    return full_text, deduped


def parse_chat_actions(actions: list[Any]) -> list[ChatMessage]:
    """Converte as ``actions`` do chat do YouTube em :class:`ChatMessage`."""
    messages: list[ChatMessage] = []
    for renderer, pinned in _iter_message_renderers(actions):
        msg_id = str(renderer.get("id") or "").strip()
        author = str(renderer.get("authorName", {}).get("simpleText") or "").strip()
        channel_id = str(renderer.get("authorExternalChannelId") or "").strip()
        badges = _extract_badges(renderer)
        text, links = _extract_text_and_links(renderer)
        if not msg_id and not text and not links:
            continue
        messages.append(
            ChatMessage(
                id=msg_id,
                author=author,
                author_channel_id=channel_id,
                badges=badges,
                text=text,
                links=links,
                pinned=pinned,
            )
        )
    return messages
