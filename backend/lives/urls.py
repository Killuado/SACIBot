from django.urls import path

from .views import (
    YouTubeLogsView,
    YouTubeSourceDetailView,
    YouTubeSourceListCreateView,
)

urlpatterns = [
    path("sources/", YouTubeSourceListCreateView.as_view(), name="youtube-sources"),
    path(
        "sources/<int:source_id>/",
        YouTubeSourceDetailView.as_view(),
        name="youtube-source-detail",
    ),
    path("logs/", YouTubeLogsView.as_view(), name="youtube-logs"),
]
