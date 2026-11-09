from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from promotions.permissions import HasBotServiceToken, IsDiscordAdmin

from .models import LiveSession, YouTubeSource
from .serializers import YouTubeSourceCreateSerializer, YouTubeSourceSerializer


class YouTubeSourceListCreateView(APIView):
    permission_classes = [HasBotServiceToken, IsDiscordAdmin]

    def get(self, request):
        sources = YouTubeSource.objects.all()
        return Response(YouTubeSourceSerializer(sources, many=True).data)

    def post(self, request):
        serializer = YouTubeSourceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        kind, identifier = serializer.validated_data["source"]
        trusted_only = serializer.validated_data.get("trusted_authors_only", True)
        discord_id = (request.headers.get("X-Discord-User-ID") or "").strip()[:32]

        existing = YouTubeSource.objects.filter(kind=kind, identifier=identifier).first()
        max_sources = getattr(settings, "YOUTUBE_MAX_SOURCES", 50)
        if existing is None and YouTubeSource.objects.count() >= max_sources:
            raise ValidationError(
                {"source": f"Limite de {max_sources} fontes cadastradas atingido."}
            )

        defaults = {
            "enabled": True,
            "trusted_authors_only": trusted_only,
            "note": "",
        }
        if discord_id:
            defaults["added_by"] = discord_id

        source, created = YouTubeSource.objects.update_or_create(
            kind=kind,
            identifier=identifier,
            defaults=defaults,
        )
        http_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(YouTubeSourceSerializer(source).data, status=http_status)


class YouTubeSourceDetailView(APIView):
    permission_classes = [HasBotServiceToken, IsDiscordAdmin]

    def delete(self, request, source_id: int):
        deleted, _ = YouTubeSource.objects.filter(pk=source_id).delete()
        if not deleted:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class YouTubeLogsView(APIView):
    permission_classes = [HasBotServiceToken, IsDiscordAdmin]

    def get(self, request):
        source_id = request.query_params.get("source_id")
        qs = LiveSession.objects.select_related("source").filter(ended_at__isnull=True)
        if source_id and source_id.isdecimal():
            qs = qs.filter(source_id=int(source_id))

        sessions = list(qs[:10])
        if not sessions:
            # Se nenhuma live estiver ativa no momento, mostra a última sessão recente
            fallback = LiveSession.objects.select_related("source")
            if source_id and source_id.isdecimal():
                fallback = fallback.filter(source_id=int(source_id))
            sessions = list(fallback[:3])

        payload = [
            {
                "session_id": s.pk,
                "source_id": s.source_id,
                "identifier": s.source.identifier,
                "label": s.source.label,
                "video_id": s.video_id,
                "title": s.title,
                "is_active": s.ended_at is None,
                "messages_seen": s.messages_seen,
                "links_seen": s.links_seen,
                "links_ingested": s.links_ingested,
                "promotions_matched": s.promotions_matched,
                "recent_messages": (s.recent_messages or [])[-10:],
                "recent_links": (s.recent_links or [])[-10:],
            }
            for s in sessions
        ]
        return Response({"sessions": payload})
