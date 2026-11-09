import json
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import httpx
from asgiref.sync import async_to_sync
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from promotions.models import DiscordUser, Promotion, WatchlistItem
from scrapers.dedup import TtlUrlCache
from scrapers.test_scrapers import FakeScraper

from .models import LiveSession, YouTubeSource
from .monitor import YouTubeLiveMonitor
from .youtube.client import LiveChatReader, YouTubeClient
from .youtube.parsing import (
    ChatMessage,
    ChatUnavailable,
    LiveStatus,
    parse_chat_actions,
    parse_chat_bootstrap,
    parse_chat_poll,
    parse_live_status,
    parse_source_input,
    unwrap_youtube_redirect,
)


def make_live_html(*, video_id="4t4AQ15yj1M", is_live=True, is_upcoming=False, title="Live Ofertas", author="KaBuM!"):
    player = {
        "videoDetails": {
            "videoId": video_id,
            "title": title,
            "author": author,
            "isLive": is_live,
            "isUpcoming": is_upcoming,
        },
        "microformat": {
            "playerMicroformatRenderer": {
                "liveBroadcastDetails": {"isLiveNow": is_live and not is_upcoming}
            }
        },
    }
    return f"<html><head><script>var ytInitialPlayerResponse = {json.dumps(player)};</script></head></html>"


def make_text_action(
    msg_id: str,
    runs: list[dict],
    *,
    author: str = "KaBuM!",
    badges: list[str] | None = None,
    paid: bool = False,
    pinned: bool = False,
) -> dict:
    badge_list = [
        {"liveChatAuthorBadgeRenderer": {"icon": {"iconType": b}}}
        for b in (badges or [])
    ]
    renderer = {
        "id": msg_id,
        "authorName": {"simpleText": author},
        "authorExternalChannelId": "UC1234567890123456789012",
        "authorBadges": badge_list,
        "message": {"runs": runs},
    }
    if pinned:
        return {
            "addBannerToLiveChatCommand": {
                "bannerRenderer": {
                    "liveChatBannerRenderer": {
                        "contents": {"liveChatTextMessageRenderer": renderer}
                    }
                }
            }
        }
    key = "liveChatPaidMessageRenderer" if paid else "liveChatTextMessageRenderer"
    return {"addChatItemAction": {"item": {key: renderer}}}


def make_chat_html(continuation="TOKEN_1", actions=None, all_chat_token=None):
    renderer: dict = {
        "continuations": [{"invalidationContinuationData": {"continuation": continuation, "timeoutMs": 4000}}],
        "actions": actions or [],
    }
    if all_chat_token:
        renderer["header"] = {
            "liveChatHeaderRenderer": {
                "viewSelector": {
                    "sortFilterSubMenuRenderer": {
                        "subMenuItems": [
                            {"title": "Principais mensagens"},
                            {
                                "title": "Chat ao vivo",
                                "continuation": {
                                    "reloadContinuationData": {"continuation": all_chat_token}
                                },
                            },
                        ]
                    }
                }
            }
        }
    initial = {"contents": {"liveChatRenderer": renderer}}
    ctx = {"client": {"clientName": "WEB", "clientVersion": "2.2026"}}
    return (
        '<html><script>ytcfg.set({"INNERTUBE_API_KEY":"KEY123",'
        f'"INNERTUBE_CONTEXT":{json.dumps(ctx)},"INNERTUBE_CONTEXT_CLIENT_NAME":1}});</script>'
        f"<script>var ytInitialData = {json.dumps(initial)};</script></html>"
    )


class SourceInputParsingTests(SimpleTestCase):
    def test_parses_channels_and_videos(self):
        cases = {
            "@kabum": ("channel", "@kabum"),
            "https://www.youtube.com/@kabum": ("channel", "@kabum"),
            "https://www.youtube.com/@kabum/live": ("channel", "@kabum"),
            "UC5S1CfC9-KTuRxMVoSV5b1g": ("channel", "UC5S1CfC9-KTuRxMVoSV5b1g"),
            "https://www.youtube.com/channel/UC5S1CfC9-KTuRxMVoSV5b1g/videos": (
                "channel",
                "UC5S1CfC9-KTuRxMVoSV5b1g",
            ),
            "https://www.youtube.com/c/KabumOficial": ("channel", "c/KabumOficial"),
            "https://www.youtube.com/watch?v=4t4AQ15yj1M&ab_channel=X": ("video", "4t4AQ15yj1M"),
            "https://youtu.be/4t4AQ15yj1M": ("video", "4t4AQ15yj1M"),
            "https://www.youtube.com/live/4t4AQ15yj1M?si=abc": ("video", "4t4AQ15yj1M"),
            "4t4AQ15yj1M": ("video", "4t4AQ15yj1M"),
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_source_input(raw), expected)

    def test_rejects_invalid_or_non_youtube_inputs(self):
        for raw in ("", "https://twitch.tv/kabum", "https://www.youtube.com/watch?v=curto", "@x"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_source_input(raw)


class LiveStatusAndChatParsingTests(SimpleTestCase):
    def test_detects_live_offline_and_upcoming(self):
        live = parse_live_status(make_live_html(is_live=True))
        self.assertTrue(live.is_live)
        self.assertEqual(live.video_id, "4t4AQ15yj1M")
        self.assertEqual(live.channel_name, "KaBuM!")

        upcoming = parse_live_status(make_live_status_html := make_live_html(is_live=True, is_upcoming=True))
        self.assertFalse(upcoming.is_live)
        self.assertTrue(upcoming.is_upcoming)

        offline = parse_live_status("<html><body>Canal sem live</body></html>")
        self.assertFalse(offline.is_live)
        self.assertIsNone(offline.video_id)

    def test_bootstrap_prefers_all_chat_tab_and_parses_initial_actions(self):
        action = make_text_action(
            "m1",
            [{"text": "Oferta https://loja.example/p1"}],
            badges=["OWNER"],
        )
        html = make_chat_html(continuation="TOP_TOKEN", actions=[action], all_chat_token="ALL_TOKEN")
        boot = parse_chat_bootstrap(html)
        self.assertEqual(boot.api_key, "KEY123")
        self.assertEqual(boot.continuation, "ALL_TOKEN")
        self.assertEqual(len(boot.initial_messages), 1)
        self.assertTrue(boot.initial_messages[0].is_trusted)
        self.assertEqual(boot.initial_messages[0].links, ["https://loja.example/p1"])

    def test_raises_when_chat_renderer_is_missing(self):
        with self.assertRaises(ChatUnavailable):
            parse_chat_bootstrap("<html><script>var ytInitialData = {};</script></html>")

    def test_unwraps_redirect_and_handles_truncated_run_text_and_pinned_banners(self):
        redirect_url = (
            "https://www.youtube.com/redirect?event=live_chat&redir_token=xyz"
            "&q=https%3A%2F%2Fwww.kabum.com.br%2Fproduto%2F497577"
        )
        self.assertEqual(
            unwrap_youtube_redirect(redirect_url),
            "https://www.kabum.com.br/produto/497577",
        )

        actions = [
            make_text_action(
                "msg-owner",
                [
                    {"text": "Corre: "},
                    {
                        "text": "https://www.kabum.com.br/pro...",
                        "navigationEndpoint": {"urlEndpoint": {"url": redirect_url}},
                    },
                ],
                badges=["MODERATOR"],
            ),
            make_text_action(
                "msg-pinned",
                [{"text": "Fixado https://loja.example/cupom"}],
                badges=["OWNER"],
                pinned=True,
            ),
            make_text_action(
                "msg-viewer",
                [{"text": "olha https://golpe.example/x"}],
                badges=[],
            ),
        ]
        parsed = parse_chat_actions(actions)
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0].links, ["https://www.kabum.com.br/produto/497577"])
        self.assertTrue(parsed[0].is_trusted)
        self.assertTrue(parsed[1].pinned)
        self.assertFalse(parsed[2].is_trusted)


class YouTubeClientAndReaderTests(SimpleTestCase):
    def test_reader_iterates_initial_and_polled_batches_until_stream_ends(self):
        init_action = make_text_action("m1", [{"text": "https://loja.example/1"}], badges=["OWNER"])
        poll_action = make_text_action("m2", [{"text": "https://loja.example/2"}], badges=["OWNER"])
        dup_action = make_text_action("m1", [{"text": "https://loja.example/1"}], badges=["OWNER"])

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/live_chat":
                return httpx.Response(200, text=make_chat_html("CONT_1", actions=[init_action]))
            body = json.loads(request.content.decode())
            if body["continuation"] == "CONT_1":
                return httpx.Response(
                    200,
                    json={
                        "continuationContents": {
                            "liveChatContinuation": {
                                "actions": [dup_action, poll_action],
                                "continuations": [
                                    {"timedContinuationData": {"continuation": "CONT_2", "timeoutMs": 3000}}
                                ],
                            }
                        }
                    },
                )
            # Último poll sem continuation -> live encerrada.
            return httpx.Response(
                200,
                json={"continuationContents": {"liveChatContinuation": {"actions": []}}},
            )

        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
                yt = YouTubeClient(http=http)
                reader = LiveChatReader(yt, "4t4AQ15yj1M", sleep_fn=lambda _: self._noop_async())
                batches = []
                async for batch in reader.iter_batches():
                    batches.append([m.id for m in batch])
                return batches

        self.assertEqual(async_to_sync(run)(), [["m1"], ["m2"]])

    @staticmethod
    async def _noop_async():
        return None


@patch("lives.monitor.close_old_connections", lambda: None)
@patch("scrapers.telegram_monitor.close_old_connections", lambda: None)
class YouTubeLiveMonitorTests(TestCase):
    def setUp(self):
        user = DiscordUser.objects.create(discord_id="999")
        self.watch = WatchlistItem.objects.create(
            user=user, pattern=r"rtx\s?4060", max_price=Decimal("2100.00")
        )

    def test_filters_untrusted_authors_deduplicates_links_and_ingests(self):
        clock_now = 100.0
        cache = TtlUrlCache(ttl_seconds=180.0, clock=lambda: clock_now)
        scraper = FakeScraper()
        monitor = YouTubeLiveMonitor(url_cache=cache, scrapers_factory=lambda: [scraper])

        messages = [
            ChatMessage(
                id="1",
                author="Espectador",
                author_channel_id="UCx",
                badges=frozenset(),
                text="",
                links=["https://loja.example/ignorar"],
            ),
            ChatMessage(
                id="2",
                author="KaBuM!",
                author_channel_id="UCk",
                badges=frozenset({"OWNER"}),
                text="",
                links=["https://loja.example/rtx-4060?utm_source=yt"],
            ),
            ChatMessage(
                id="3",
                author="Mod",
                author_channel_id="UCm",
                badges=frozenset({"MODERATOR"}),
                text="",
                links=["https://loja.example/rtx-4060"],
            ),
        ]

        enqueued = monitor.handle_messages(
            messages, source_tag="youtube:KaBuM!", trusted_authors_only=True
        )
        self.assertEqual(enqueued, ["https://loja.example/rtx-4060"])

        result = async_to_sync(monitor.process_next_job)([scraper])
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "created")
        self.assertEqual(result.matches, [self.watch])
        self.assertEqual(Promotion.objects.get().source, "youtube:KaBuM!")

        # Passados 3 minutos, o mesmo link pode ser re-checado.
        clock_now = 300.0
        enqueued_after_ttl = monitor.handle_messages(
            [messages[1]], source_tag="youtube:KaBuM!", trusted_authors_only=True
        )
        self.assertEqual(enqueued_after_ttl, ["https://loja.example/rtx-4060"])

    def test_supervisor_opens_and_closes_session_and_disables_finished_video_source(self):
        channel_src = YouTubeSource.objects.create(
            kind=YouTubeSource.Kind.CHANNEL, identifier="@kabum"
        )
        video_src = YouTubeSource.objects.create(
            kind=YouTubeSource.Kind.VIDEO, identifier="11111111111"
        )

        msg_action = make_text_action(
            "m1",
            [{"text": "https://loja.example/rtx-4060"}],
            badges=["OWNER"],
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/@kabum/live":
                return httpx.Response(200, text=make_live_html(video_id="4t4AQ15yj1M", is_live=True))
            if request.url.path == "/watch":
                return httpx.Response(200, text="<html>offline</html>")
            if request.url.path == "/live_chat":
                return httpx.Response(200, text=make_chat_html("C1", actions=[msg_action]))
            return httpx.Response(
                200,
                json={"continuationContents": {"liveChatContinuation": {"actions": []}}},
            )

        async def scenario():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
                yt = YouTubeClient(http=http)
                monitor = YouTubeLiveMonitor(yt_client=yt, scrapers_factory=lambda: [FakeScraper()])
                await monitor.scan_once()
                if monitor.active_tasks:
                    await asyncio.gather(*list(monitor.active_tasks.values()))
                await monitor.process_next_job([FakeScraper()])

        import asyncio

        async_to_sync(scenario)()

        channel_src.refresh_from_db()
        video_src.refresh_from_db()
        self.assertEqual(channel_src.label, "KaBuM!")
        self.assertEqual(channel_src.current_video_id, "")
        self.assertTrue(channel_src.enabled)
        self.assertFalse(video_src.enabled)
        self.assertIn("encerrada", video_src.note)

        session = LiveSession.objects.get(source=channel_src)
        self.assertEqual(session.video_id, "4t4AQ15yj1M")
        self.assertIsNotNone(session.ended_at)
        self.assertEqual(session.messages_seen, 1)
        self.assertEqual(session.links_ingested, 1)
        self.assertEqual(len(session.recent_messages), 1)
        self.assertEqual(len(session.recent_links), 1)
        self.assertEqual(session.recent_links[0]["url"], "https://loja.example/rtx-4060")


@override_settings(BOT_API_TOKEN="test-service-token", DISCORD_ADMIN_IDS={"123456789"})
class YouTubeSourcesApiAndCommandTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.headers = {
            "HTTP_X_BOT_TOKEN": "test-service-token",
            "HTTP_X_DISCORD_USER_ID": "123456789",
        }

    def test_rejects_user_not_in_discord_admin_ids(self):
        non_admin_headers = {
            "HTTP_X_BOT_TOKEN": "test-service-token",
            "HTTP_X_DISCORD_USER_ID": "999999999",
        }
        for method, path, data in (
            ("get", "/api/youtube/sources/", None),
            ("post", "/api/youtube/sources/", {"source": "@kabum"}),
            ("delete", "/api/youtube/sources/1/", None),
        ):
            with self.subTest(method=method):
                resp = getattr(self.client, method)(
                    path, data=data, format="json", **non_admin_headers
                )
                self.assertEqual(resp.status_code, 403)

    def test_api_creates_lists_reactivates_and_removes_source(self):
        resp = self.client.post(
            "/api/youtube/sources/",
            {"source": "https://www.youtube.com/@kabum/live"},
            format="json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["kind"], "channel")
        self.assertEqual(resp.data["identifier"], "@kabum")
        source_id = resp.data["id"]

        YouTubeSource.objects.filter(pk=source_id).update(enabled=False)
        again = self.client.post(
            "/api/youtube/sources/",
            {"source": "@kabum"},
            format="json",
            **self.headers,
        )
        self.assertEqual(again.status_code, 200)
        self.assertTrue(again.data["enabled"])

        listed = self.client.get("/api/youtube/sources/", **self.headers)
        self.assertEqual(len(listed.data), 1)

        logs_resp = self.client.get("/api/youtube/logs/", **self.headers)
        self.assertEqual(logs_resp.status_code, 200)
        self.assertIn("sessions", logs_resp.data)

        deleted = self.client.delete(f"/api/youtube/sources/{source_id}/", **self.headers)
        self.assertEqual(deleted.status_code, 204)

    def test_cli_command_add_list_disable_enable_remove(self):
        out = StringIO()
        call_command("youtube_sources", "add", "@pichauinfo", stdout=out)
        src = YouTubeSource.objects.get()
        self.assertEqual(src.identifier, "@pichauinfo")

        call_command("youtube_sources", "disable", str(src.pk), stdout=out)
        src.refresh_from_db()
        self.assertFalse(src.enabled)

        call_command("youtube_sources", "enable", str(src.pk), stdout=out)
        call_command("youtube_sources", "list", stdout=out)
        self.assertIn("@pichauinfo", out.getvalue())

        call_command("youtube_sources", "remove", str(src.pk), stdout=out)
        self.assertFalse(YouTubeSource.objects.exists())

        with self.assertRaises(CommandError):
            call_command("youtube_sources", "add", "https://example.com/nao-youtube")
