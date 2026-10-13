import logging

import regex

from .models import Promotion, WatchlistItem


logger = logging.getLogger(__name__)


def matching_watchlists(promotion: Promotion):
    matches = []
    candidates = WatchlistItem.objects.filter(
        enabled=True,
        max_price__gte=promotion.price,
    ).select_related("user")

    for item in candidates:
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