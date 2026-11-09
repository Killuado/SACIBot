"""Cache de URLs com tempo de expiração (TTL) para evitar re-scraping de links repetidos."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Callable

from .links import clean_url


class TtlUrlCache:
    """Guarda URLs normalizadas vistas recentemente.

    Quando lojas ou canais de promoção enviam o mesmo link várias vezes seguidas,
    este cache evita refazer a requisição HTTP dentro da janela ``ttl_seconds``.
    Depois que o TTL expira, o link volta a ser aceito (útil para re-checar se o
    preço baixou ou se o estoque voltou).
    """

    def __init__(
        self,
        ttl_seconds: float = 180.0,
        max_size: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.ttl_seconds = float(ttl_seconds)
        self.max_size = max(1, int(max_size))
        self._clock = clock
        self._items: OrderedDict[str, float] = OrderedDict()

    def _prune(self, now: float) -> None:
        if self.ttl_seconds <= 0:
            self._items.clear()
            return
        cutoff = now - self.ttl_seconds
        while self._items:
            _, timestamp = next(iter(self._items.items()))
            if timestamp <= cutoff:
                self._items.popitem(last=False)
            else:
                break

    def should_process(self, url: str) -> bool:
        """Retorna ``True`` se a URL não foi vista nos últimos ``ttl_seconds`` e a registra."""
        key = clean_url(url)
        now = self._clock()
        self._prune(now)

        if self.ttl_seconds <= 0:
            return True

        seen_at = self._items.get(key)
        if seen_at is not None and (now - seen_at) < self.ttl_seconds:
            return False

        self._items[key] = now
        self._items.move_to_end(key)
        while len(self._items) > self.max_size:
            self._items.popitem(last=False)
        return True

    def seen(self, url: str) -> bool:
        """Compatibilidade: retorna ``True`` se já foi vista dentro do TTL."""
        return not self.should_process(url)

    def __bool__(self) -> bool:
        return True

    def __len__(self) -> int:
        self._prune(self._clock())
        return len(self._items)
