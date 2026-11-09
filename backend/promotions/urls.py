from django.urls import path

from .views import (
    AddressView,
    MarketplaceChannelDetailView,
    MarketplaceChannelListView,
    PromotionIngestView,
    PromotionTestNotifyView,
    WatchlistClearAllView,
    WatchlistItemView,
    WatchlistView,
)


urlpatterns = [
    path("watchlist/", WatchlistView.as_view(), name="watchlist"),
    path(
        "watchlist/<int:item_id>/",
        WatchlistItemView.as_view(),
        name="watchlist-item",
    ),
    path(
        "watchlist/clear-all/",
        WatchlistClearAllView.as_view(),
        name="watchlist-clear-all",
    ),
    path("address/", AddressView.as_view(), name="address"),
    path("marketplace/", MarketplaceChannelListView.as_view(), name="marketplace-list"),
    path(
        "marketplace/<str:channel>/",
        MarketplaceChannelDetailView.as_view(),
        name="marketplace-detail",
    ),
    path("promotions/ingest/", PromotionIngestView.as_view(), name="promotion-ingest"),
    path(
        "promotions/test-notify/",
        PromotionTestNotifyView.as_view(),
        name="promotion-test-notify",
    ),
]
