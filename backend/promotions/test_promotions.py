from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Address, DiscordUser, MarketplaceChannel, Promotion, WatchlistItem
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
        self.assertIn("user_status", response.data)
        self.assertFalse(response.data["user_status"]["has_address"])
        self.assertFalse(response.data["user_status"]["has_marketplaces"])

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


@override_settings(BOT_API_TOKEN="test-service-token")
class AddressApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.headers = {
            "HTTP_X_BOT_TOKEN": "test-service-token",
            "HTTP_X_DISCORD_USER_ID": "123456789",
        }

    def test_get_address_not_found(self):
        response = self.client.get("/api/address/", **self.headers)
        self.assertEqual(response.status_code, 404)

    def test_create_and_update_address(self):
        payload = {
            "recipient_name": "João Silva",
            "street": "Rua das Flores",
            "number": "123",
            "complement": "Apto 4B",
            "neighborhood": "Centro",
            "city": "São Paulo",
            "state": "SP",
            "zip_code": "01001-000",
            "cpf": "12345678900",
        }
        res_post = self.client.post("/api/address/", payload, format="json", **self.headers)
        self.assertEqual(res_post.status_code, 201)
        self.assertEqual(res_post.data["recipient_name"], "João Silva")
        self.assertEqual(res_post.data["state"], "SP")

        res_get = self.client.get("/api/address/", **self.headers)
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.data["city"], "São Paulo")

        # Update address
        payload["number"] = "456"
        res_put = self.client.post("/api/address/", payload, format="json", **self.headers)
        self.assertEqual(res_put.status_code, 200)
        self.assertEqual(res_put.data["number"], "456")


@override_settings(BOT_API_TOKEN="test-service-token")
class MarketplaceChannelApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.headers = {
            "HTTP_X_BOT_TOKEN": "test-service-token",
            "HTTP_X_DISCORD_USER_ID": "123456789",
        }

    def test_add_list_and_remove_marketplaces(self):
        res_empty = self.client.get("/api/marketplace/", **self.headers)
        self.assertEqual(res_empty.status_code, 200)
        self.assertEqual(len(res_empty.data), 0)

        res_add = self.client.post(
            "/api/marketplace/",
            {"channel": "kabum, pichau, amazon"},
            format="json",
            **self.headers,
        )
        self.assertEqual(res_add.status_code, 201)
        self.assertEqual(res_add.data["added_count"], 3)
        self.assertIn("kabum", res_add.data["channels"])
        self.assertIn("pichau", res_add.data["channels"])
        self.assertIn("amazon", res_add.data["channels"])

        res_list = self.client.get("/api/marketplace/", **self.headers)
        self.assertEqual(res_list.status_code, 200)
        self.assertEqual(len(res_list.data), 3)

        res_del = self.client.delete("/api/marketplace/kabum,amazon/", **self.headers)
        self.assertEqual(res_del.status_code, 200)

        res_list_after = self.client.get("/api/marketplace/", **self.headers)
        self.assertEqual(len(res_list_after.data), 1)
        self.assertEqual(res_list_after.data[0]["channel"], "pichau")


@override_settings(BOT_API_TOKEN="test-service-token")
class PromotionIngestApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.headers = {
            "HTTP_X_BOT_TOKEN": "test-service-token",
            "HTTP_X_DISCORD_USER_ID": "123456789",
        }

    @patch("promotions.services.send_bot_notification", return_value=True)
    def test_ingests_promotion_and_notifies_matching_ready_user(self, mock_notify):
        user = DiscordUser.objects.create(discord_id="123456789")
        Address.objects.create(
            user=user,
            recipient_name="Tester",
            street="Rua 1",
            number="10",
            neighborhood="Centro",
            city="SP",
            state="SP",
            zip_code="01000-000",
        )
        MarketplaceChannel.objects.create(user=user, channel="kabum")
        WatchlistItem.objects.create(
            user=user,
            pattern=r"rtx\s?4060",
            max_price=Decimal("2000.00"),
        )

        payload = {
            "title": "Placa de Vídeo RTX 4060 8GB",
            "price": "1899.90",
            "url": "https://www.kabum.com.br/produto/123",
            "marketplace": "kabum",
            "image_url": "https://example.com/rtx.jpg",
        }

        res = self.client.post("/api/promotions/ingest/", payload, format="json", **self.headers)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["matches"]["matched_count"], 1)
        self.assertEqual(res.data["matches"]["notified_count"], 1)
        self.assertIn("123456789", res.data["matches"]["notified_users"])
        mock_notify.assert_called_once()


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
