import json
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from asgiref.sync import async_to_sync
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from promotions.models import DiscordUser, Promotion, WatchlistItem

from .base import BaseScraper, ScraperError
from .dedup import TtlUrlCache
from .fetch import ensure_public_url
from .ingestion import ingest_url
from .jsonld import JsonLdScraper, extract_product, parse_availability, parse_price
from .links import clean_url, extract_urls, marketplace_from_url
from .telegram_monitor import TelegramMonitor, TelegramSettings, message_urls


def html_with_json_ld(*blocks, extra_head=""):
    scripts = "".join(
        f'<script type="application/ld+json">{json.dumps(block)}</script>' for block in blocks
    )
    return f"<html><head>{scripts}{extra_head}</head><body></body></html>"


PRODUCT_JSON_LD = {
    "@context": "https://schema.org",
    "@type": "Product",
    "name": "Placa de Vídeo RTX 4060 8GB",
    "image": ["https://loja.example/rtx.jpg"],
    "offers": {
        "@type": "Offer",
        "price": "1999.90",
        "priceCurrency": "BRL",
        "availability": "https://schema.org/InStock",
    },
}


class PriceAndAvailabilityParsingTests(SimpleTestCase):
    def test_parses_common_price_formats(self):
        cases = {
            1999.9: Decimal("1999.90"),
            "1999.90": Decimal("1999.90"),
            "1.999,90": Decimal("1999.90"),
            "R$ 2.099": Decimal("2099.00"),
            "1,999.90": Decimal("1999.90"),
            "349,9": Decimal("349.90"),
            "1.299.990,00": Decimal("1299990.00"),
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_price(raw), expected)

    def test_invalid_prices_return_none(self):
        for raw in (None, "", "grátis", True, -5):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_price(raw))

    def test_parses_availability(self):
        self.assertTrue(parse_availability("https://schema.org/InStock"))
        self.assertTrue(parse_availability("http://schema.org/LimitedAvailability"))
        self.assertTrue(parse_availability("in stock"))
        self.assertFalse(parse_availability("https://schema.org/OutOfStock"))
        self.assertFalse(parse_availability("schema:SoldOut"))
        self.assertIsNone(parse_availability("algo estranho"))


class JsonLdExtractionTests(SimpleTestCase):
    def test_extracts_simple_product(self):
        data = extract_product(
            html_with_json_ld(PRODUCT_JSON_LD), "https://www.kabum.com.br/produto/1"
        )
        self.assertEqual(data["title"], "Placa de Vídeo RTX 4060 8GB")
        self.assertEqual(data["price"], Decimal("1999.90"))
        self.assertEqual(data["currency"], "BRL")
        self.assertIs(data["in_stock"], True)
        self.assertEqual(data["marketplace"], "KaBuM!")
        self.assertEqual(data["image_url"], "https://loja.example/rtx.jpg")

    def test_finds_product_inside_graph_and_aggregate_offer(self):
        block = {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "BreadcrumbList", "itemListElement": []},
                {
                    "@type": ["Product"],
                    "name": "SSD 1TB NVMe",
                    "offers": {
                        "@type": "AggregateOffer",
                        "lowPrice": 399.0,
                        "priceCurrency": "BRL",
                        "offers": [
                            {"price": 450, "availability": "InStock"},
                            {"price": 380, "availability": "OutOfStock"},
                            {"price": 399, "availability": "InStock"},
                        ],
                    },
                },
            ],
        }
        data = extract_product(html_with_json_ld(block), "https://loja.example/ssd")
        self.assertEqual(data["title"], "SSD 1TB NVMe")
        # Menor preço entre as ofertas disponíveis.
        self.assertEqual(data["price"], Decimal("399.00"))
        self.assertIs(data["in_stock"], True)

    def test_detects_out_of_stock(self):
        product = {
            **PRODUCT_JSON_LD,
            "offers": {"price": "100", "availability": "https://schema.org/OutOfStock"},
        }
        data = extract_product(html_with_json_ld(product), "https://loja.example/p")
        self.assertIs(data["in_stock"], False)

    def test_ignores_invalid_json_ld_and_falls_back_to_open_graph(self):
        html = (
            '<html><head><script type="application/ld+json">{quebrado</script>'
            '<meta property="og:title" content="Monitor 27&quot; 165Hz">'
            '<meta property="product:price:amount" content="1.299,00">'
            '<meta property="product:price:currency" content="brl">'
            '<meta property="product:availability" content="in stock">'
            "</head></html>"
        )
        data = extract_product(html, "https://loja.example/monitor")
        self.assertEqual(data["title"], 'Monitor 27" 165Hz')
        self.assertEqual(data["price"], Decimal("1299.00"))
        self.assertEqual(data["currency"], "BRL")
        self.assertIs(data["in_stock"], True)

    def test_raises_when_page_has_no_product(self):
        with self.assertRaises(ScraperError):
            extract_product("<html><body>nada</body></html>", "https://loja.example/")


class JsonLdScraperHttpTests(SimpleTestCase):
    def make_client(self, handler):
        return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)

    def test_follows_redirect_and_reports_final_url(self):
        def handler(request):
            if request.url.host == "short.example":
                return httpx.Response(302, headers={"Location": "https://loja.example/rtx"})
            return httpx.Response(200, html=html_with_json_ld(PRODUCT_JSON_LD))

        with JsonLdScraper(client=self.make_client(handler)) as scraper:
            data = scraper.parse_url("https://short.example/abc")
            stock = scraper.check_stock_and_price("https://loja.example/rtx")

        self.assertEqual(data["url"], "https://loja.example/rtx")
        self.assertEqual(stock["price"], Decimal("1999.90"))
        self.assertIs(stock["in_stock"], True)

    def test_http_error_becomes_scraper_error(self):
        client = self.make_client(lambda request: httpx.Response(404))
        with self.assertRaises(ScraperError):
            JsonLdScraper(client=client).parse_url("https://loja.example/x")

    def test_blocks_private_and_non_http_destinations(self):
        for url in (
            "http://127.0.0.1:8000/admin",
            "http://10.0.0.5/",
            "http://[::1]/",
            "file:///etc/passwd",
        ):
            with self.subTest(url=url), self.assertRaises(ScraperError):
                ensure_public_url(url)

    def test_default_client_refuses_localhost(self):
        with JsonLdScraper() as scraper, self.assertRaises(ScraperError):
            scraper.parse_url("http://127.0.0.1:9/produto")


class LinkUtilsTests(SimpleTestCase):
    def test_extracts_urls_from_message_text(self):
        text = (
            "🔥 RTX 4060 por R$ 1.999! https://amzn.to/abc123.\n"
            "Cupom: SACI10 (https://www.kabum.com.br/produto/1?utm_source=tg) "
            "repetido https://amzn.to/abc123"
        )
        self.assertEqual(
            extract_urls(text),
            [
                "https://amzn.to/abc123",
                "https://www.kabum.com.br/produto/1?utm_source=tg",
            ],
        )

    def test_clean_url_removes_tracking(self):
        self.assertEqual(
            clean_url("https://WWW.Loja.example/p?id=1&utm_source=tg&fbclid=x#reviews"),
            "https://www.loja.example/p?id=1",
        )

    def test_marketplace_names(self):
        self.assertEqual(marketplace_from_url("https://produto.mercadolivre.com.br/x"), "Mercado Livre")
        self.assertEqual(marketplace_from_url("https://www.loja.example/x"), "loja.example")


class TtlUrlCacheTests(SimpleTestCase):
    def test_respects_ttl_and_normalizes_urls(self):
        now = 100.0
        cache = TtlUrlCache(ttl_seconds=180.0, max_size=2, clock=lambda: now)

        self.assertTrue(cache.should_process("https://loja.example/p?id=1&utm_source=yt"))
        self.assertFalse(cache.should_process("https://loja.example/p?id=1"))

        now = 279.0
        self.assertFalse(cache.should_process("https://loja.example/p?id=1"))

        now = 281.0
        self.assertTrue(cache.should_process("https://loja.example/p?id=1"))

    def test_evicts_oldest_when_max_size_is_exceeded(self):
        cache = TtlUrlCache(ttl_seconds=180.0, max_size=2)
        self.assertTrue(cache.should_process("https://loja.example/1"))
        self.assertTrue(cache.should_process("https://loja.example/2"))
        self.assertTrue(cache.should_process("https://loja.example/3"))
        self.assertEqual(len(cache), 2)
        self.assertTrue(cache.should_process("https://loja.example/1"))


class FakeScraper(BaseScraper):
    name = "fake"

    def __init__(self, **data):
        self.data = {
            "url": "https://loja.example/rtx-4060",
            "title": "Placa RTX 4060 em oferta",
            "price": Decimal("1999.90"),
            "currency": "BRL",
            "in_stock": True,
            "marketplace": "loja.example",
            "image_url": None,
        }
        self.data.update(data)
        self.calls = []

    def can_handle(self, url):
        return True

    def parse_url(self, url):
        self.calls.append(url)
        if isinstance(self.data.get("error"), Exception):
            raise self.data["error"]
        return dict(self.data)


class IngestionTests(TestCase):
    def setUp(self):
        user = DiscordUser.objects.create(discord_id="123")
        self.watch = WatchlistItem.objects.create(
            user=user, pattern=r"rtx\s?4060", max_price=Decimal("2100.00")
        )

    def test_creates_promotion_and_matches_watchlist(self):
        result = ingest_url("https://loja.example/rtx-4060?utm_source=tg", "telegram:ofertas", FakeScraper())

        self.assertEqual(result.status, "created")
        self.assertEqual(result.matches, [self.watch])
        promotion = Promotion.objects.get()
        self.assertEqual(promotion.url, "https://loja.example/rtx-4060")
        self.assertEqual(promotion.source, "telegram:ofertas")
        self.assertIs(promotion.in_stock, True)

    def test_only_rematches_on_price_drop_or_restock(self):
        ingest_url("https://loja.example/rtx-4060", scraper=FakeScraper())

        same = ingest_url("https://loja.example/rtx-4060", scraper=FakeScraper())
        self.assertEqual(same.status, "updated")
        self.assertEqual(same.matches, [])

        cheaper = ingest_url("https://loja.example/rtx-4060", scraper=FakeScraper(price=Decimal("1899.00")))
        self.assertEqual(cheaper.matches, [self.watch])
        self.assertEqual(Promotion.objects.get().price, Decimal("1899.00"))

    def test_out_of_stock_is_saved_without_matches_until_restock(self):
        sold_out = ingest_url("https://loja.example/rtx-4060", scraper=FakeScraper(in_stock=False))
        self.assertEqual(sold_out.status, "created")
        self.assertEqual(sold_out.matches, [])

        restocked = ingest_url("https://loja.example/rtx-4060", scraper=FakeScraper(in_stock=True))
        self.assertEqual(restocked.matches, [self.watch])

    def test_skips_pages_without_price_or_with_errors(self):
        no_price = ingest_url("https://loja.example/a", scraper=FakeScraper(price=None))
        failed = ingest_url("https://loja.example/b", scraper=FakeScraper(error=ScraperError("HTTP 503")))

        self.assertEqual(no_price.status, "skipped")
        self.assertEqual(failed.status, "skipped")
        self.assertEqual(failed.reason, "HTTP 503")
        self.assertFalse(Promotion.objects.exists())


@patch("scrapers.telegram_monitor.close_old_connections", lambda: None)
class TelegramMonitorTests(TestCase):
    def test_message_urls_reads_text_hidden_links_and_buttons(self):
        message = SimpleNamespace(
            message="Oferta! https://loja.example/a",
            entities=[SimpleNamespace(url="https://loja.example/b"), SimpleNamespace()],
            reply_markup=SimpleNamespace(
                rows=[SimpleNamespace(buttons=[SimpleNamespace(url="https://loja.example/c")])]
            ),
        )
        self.assertEqual(
            message_urls(message),
            ["https://loja.example/a", "https://loja.example/b", "https://loja.example/c"],
        )

    def test_handle_message_ingests_each_new_link_once(self):
        scraper = FakeScraper()
        monitor = TelegramMonitor(
            TelegramSettings(api_id=1, api_hash="x", session="test", channels=[]),
            scrapers=[scraper],
        )
        message = SimpleNamespace(message="RTX 4060 https://loja.example/rtx-4060", entities=None)

        first = async_to_sync(monitor.handle_message)(message, "telegram:canal")
        repeated = async_to_sync(monitor.handle_message)(message, "telegram:canal")

        self.assertEqual([r.status for r in first], ["created"])
        self.assertEqual(repeated, [])
        self.assertEqual(scraper.calls, ["https://loja.example/rtx-4060"])
        self.assertEqual(Promotion.objects.get().source, "telegram:canal")


class PurgeOldPromotionsTests(TestCase):
    def create(self, slug, days_ago):
        promotion = Promotion.objects.create(
            title=slug, price=Decimal("10.00"), url=f"https://loja.example/{slug}", marketplace="x"
        )
        Promotion.objects.filter(pk=promotion.pk).update(
            discovered_at=timezone.now() - timedelta(days=days_ago)
        )

    def test_deletes_only_promotions_older_than_three_days(self):
        self.create("nova", 1)
        self.create("quase", 2.9)
        self.create("velha", 3.1)
        self.create("muito-velha", 10)

        out = StringIO()
        call_command("purge_old_promotions", stdout=out)

        self.assertEqual(
            sorted(Promotion.objects.values_list("title", flat=True)), ["nova", "quase"]
        )
        self.assertIn("2 promoção(ões) apagadas", out.getvalue())

    def test_dry_run_and_custom_days(self):
        self.create("velha", 5)

        call_command("purge_old_promotions", "--dry-run", stdout=StringIO())
        self.assertEqual(Promotion.objects.count(), 1)

        call_command("purge_old_promotions", "--days", "7", stdout=StringIO())
        self.assertEqual(Promotion.objects.count(), 1)
