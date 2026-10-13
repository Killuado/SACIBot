from django.db import models


class DiscordUser(models.Model):
    discord_id = models.CharField(max_length=32, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.discord_id


class WatchlistItem(models.Model):
    user = models.ForeignKey(
        DiscordUser,
        on_delete=models.CASCADE,
        related_name="watchlist_items",
    )
    pattern = models.CharField(max_length=200)
    max_price = models.DecimalField(max_digits=10, decimal_places=2)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.pattern} (R$ {self.max_price})"


class Promotion(models.Model):
    title = models.CharField(max_length=300)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    url = models.URLField(max_length=2000, unique=True)
    marketplace = models.CharField(max_length=80)
    source = models.CharField(max_length=120, blank=True)
    discovered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-discovered_at"]

    def __str__(self):
        return self.title