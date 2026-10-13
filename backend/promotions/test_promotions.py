from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import DiscordUser, Promotion, WatchlistItem
from .services import matching_watchlists


@override_settings(BOT_API_TOKEN="test-service-token")
class WatchlistApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.headers = {
            "HTTP_X_BOT_TOKEN": "test-service-token",
            "HTTP_X_DISCORD_USER_ID": "123456789",
        }

    def test_creates_and_lists_items_for_discord_user(self):
        response = self.client.post(
            "/api/watchlist/",
            {"pattern": "rtx\\s?4060", "max_price": "2100.00"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 201)
        listed = self.client.get("/api/watchlist/", **self.headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data), 1)
        self.assertEqual(listed.data[0]["pattern"], "rtx\\s?4060")

    def test_rejects_invalid_regex(self):
        response = self.client.post(
            "/api/watchlist/",
            {"pattern": "[", "max_price": "100.00"},
            format="json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_requires_service_token(self):
        response = self.client.get(
            "/api/watchlist/",
            HTTP_X_DISCORD_USER_ID="123456789",
        )
        self.assertEqual(response.status_code, 403)

    def test_item_can_only_be_removed_by_its_owner(self):
        owner = DiscordUser.objects.create(discord_id="123456789")
        item = WatchlistItem.objects.create(
            user=owner,
            pattern="notebook",
            max_price=Decimal("3000.00"),
        )
        other_user_headers = {
            **self.headers,
            "HTTP_X_DISCORD_USER_ID": "987654321",
        }

        response = self.client.delete(
            f"/api/watchlist/{item.pk}/",
            **other_user_headers,
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(WatchlistItem.objects.filter(pk=item.pk).exists())


class WatchlistMatchingTests(TestCase):
    def test_matches_regex_and_respects_maximum_price(self):
        user = DiscordUser.objects.create(discord_id="123456789")
        matching = WatchlistItem.objects.create(
            user=user,
            pattern=r"rtx\s?4060",
            max_price=Decimal("2100.00"),
        )
        WatchlistItem.objects.create(
            user=user,
            pattern="notebook",
            max_price=Decimal("1000.00"),
        )
        promotion = Promotion.objects.create(
            title="Placa RTX 4060 em oferta",
            price=Decimal("1999.90"),
            url="https://example.com/rtx-4060",
            marketplace="Example",
        )

        self.assertEqual(matching_watchlists(promotion), [matching])