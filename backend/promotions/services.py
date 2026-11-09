import json
import logging
import urllib.request
from typing import Optional

from django.conf import settings
import regex

from .models import Promotion, WatchlistItem


logger = logging.getLogger(__name__)


def _normalize_store(value: str) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def matching_watchlists(promotion: Promotion, require_user_readiness: bool = False):
    """
    Retorna os itens de watchlist que dão match com a promoção.
    Se require_user_readiness=True, só inclui usuários com endereço cadastrado e cuja loja está permitida.
    """
    matches = []
    candidates = WatchlistItem.objects.filter(
        enabled=True,
        max_price__gte=promotion.price,
    ).select_related("user")

    promo_marketplace = promotion.marketplace.strip().lower()
    promo_marketplace_norm = _normalize_store(promo_marketplace)

    for item in candidates:
        user = item.user

        if require_user_readiness:
            # Requisito 1: Usuário precisa ter endereço cadastrado
            if not user.has_address:
                continue

            # Requisito 2: Usuário precisa ter lojas cadastradas e a loja da promo deve ser permitida
            raw_channels = list(
                user.allowed_marketplaces.values_list("channel", flat=True)
            )
            allowed_channels = {c.strip().lower() for c in raw_channels}
            allowed_norm = {_normalize_store(c) for c in raw_channels}
            if not allowed_channels or (
                promo_marketplace not in allowed_channels
                and promo_marketplace_norm not in allowed_norm
            ):
                continue

        try:
            matched = regex.search(
                item.pattern,
                promotion.title,
                regex.IGNORECASE,
                timeout=0.05,
            )
        except (regex.error, TimeoutError):
            logger.warning("Regex inválida ou lenta na watchlist %s", item.pk)
            continue

        if matched:
            matches.append(item)

    return matches


def send_bot_notification(
    discord_user_id: str,
    promotion: Promotion,
    watchlist_item: Optional[WatchlistItem] = None,
) -> bool:
    """
    Envia uma notificação HTTP para o micro-servidor do bot do Discord (porta 8001).
    O bot receberá o payload e enviará uma DM com Embed para o usuário.
    """
    notify_url = getattr(settings, "BOT_NOTIFY_URL", "http://127.0.0.1:8001/notify")
    token = getattr(settings, "BOT_API_TOKEN", "")

    payload = {
        "discord_user_id": str(discord_user_id),
        "promotion": {
            "id": promotion.id if promotion.id else None,
            "title": promotion.title,
            "price": str(promotion.price),
            "url": promotion.url,
            "marketplace": promotion.marketplace,
            "image_url": getattr(promotion, "image_url", "") or "",
        },
        "watchlist_item": {
            "id": watchlist_item.id if watchlist_item else None,
            "pattern": watchlist_item.pattern if watchlist_item else "",
            "max_price": str(watchlist_item.max_price) if watchlist_item else str(promotion.price),
        } if watchlist_item else None,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        notify_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Bot-Token": token,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status in (200, 201)
    except Exception as exc:
        logger.warning("Não foi possível enviar DM para o usuário %s via %s: %s", discord_user_id, notify_url, exc)
        return False


def process_and_notify_promotion(promotion: Promotion) -> dict:
    """
    Verifica matches para uma promoção e envia notificações via webhook/HTTP para os usuários qualificados.
    """
    matches = matching_watchlists(promotion, require_user_readiness=True)
    notified_users = []

    for item in matches:
        ok = send_bot_notification(
            discord_user_id=item.user.discord_id,
            promotion=promotion,
            watchlist_item=item,
        )
        if ok:
            notified_users.append(item.user.discord_id)

    return {
        "matched_count": len(matches),
        "notified_count": len(notified_users),
        "notified_users": notified_users,
    }
