from django.db import models


class YouTubeSource(models.Model):
    class Kind(models.TextChoices):
        CHANNEL = "channel", "Canal"
        VIDEO = "video", "Live específica"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    identifier = models.CharField(max_length=120)
    label = models.CharField(max_length=120, blank=True)
    enabled = models.BooleanField(default=True)
    trusted_authors_only = models.BooleanField(default=True)
    added_by = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_live_at = models.DateTimeField(null=True, blank=True)
    current_video_id = models.CharField(max_length=16, blank=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "identifier"],
                name="unique_youtube_source_kind_identifier",
            )
        ]

    def __str__(self) -> str:
        prefix = "Canal" if self.kind == self.Kind.CHANNEL else "Live"
        display = self.label or self.identifier
        return f"{prefix}: {display}"

    @property
    def live_url(self) -> str:
        """URL consultada pelo supervisor para descobrir se está ao vivo."""
        if self.kind == self.Kind.VIDEO:
            return f"https://www.youtube.com/watch?v={self.identifier}"
        ident = self.identifier
        if ident.startswith("@") or ident.startswith("c/") or ident.startswith("user/"):
            return f"https://www.youtube.com/{ident}/live"
        return f"https://www.youtube.com/channel/{ident}/live"


class LiveSession(models.Model):
    source = models.ForeignKey(
        YouTubeSource,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    video_id = models.CharField(max_length=16, db_index=True)
    title = models.CharField(max_length=300, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    messages_seen = models.PositiveIntegerField(default=0)
    links_seen = models.PositiveIntegerField(default=0)
    links_ingested = models.PositiveIntegerField(default=0)
    promotions_matched = models.PositiveIntegerField(default=0)
    recent_messages = models.JSONField(default=list, blank=True)
    recent_links = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]

    def __str__(self) -> str:
        return f"{self.video_id} ({self.source.identifier})"
