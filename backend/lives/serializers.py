from rest_framework import serializers

from .models import YouTubeSource
from .youtube.parsing import parse_source_input


class YouTubeSourceSerializer(serializers.ModelSerializer):
    is_live = serializers.SerializerMethodField()

    class Meta:
        model = YouTubeSource
        fields = [
            "id",
            "kind",
            "identifier",
            "label",
            "enabled",
            "trusted_authors_only",
            "added_by",
            "created_at",
            "last_checked_at",
            "last_live_at",
            "current_video_id",
            "is_live",
            "note",
        ]
        read_only_fields = fields

    def get_is_live(self, obj: YouTubeSource) -> bool:
        return bool(obj.enabled and obj.current_video_id)


class YouTubeSourceCreateSerializer(serializers.Serializer):
    source = serializers.CharField(max_length=500)
    trusted_authors_only = serializers.BooleanField(default=True, required=False)

    def validate_source(self, value: str) -> tuple[str, str]:
        try:
            return parse_source_input(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
