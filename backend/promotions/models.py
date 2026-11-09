from django.db import models


class DiscordUser(models.Model):
    discord_id = models.CharField(max_length=32, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def has_address(self):
        return hasattr(self, "address") and self.address is not None

    @property
    def has_marketplaces(self):
        return self.allowed_marketplaces.exists()

    def __str__(self):
        return self.discord_id


class Address(models.Model):
    user = models.OneToOneField(
        DiscordUser,
        on_delete=models.CASCADE,
        related_name="address",
    )
    recipient_name = models.CharField(max_length=150)
    street = models.CharField(max_length=200)
    number = models.CharField(max_length=20)
    complement = models.CharField(max_length=100, blank=True)
    neighborhood = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    zip_code = models.CharField(max_length=20)
    cpf = models.CharField(max_length=20, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Endereço"
        verbose_name_plural = "Endereços"

    def __str__(self):
        return f"{self.recipient_name} - {self.street}, {self.number} ({self.city}/{self.state})"


class MarketplaceChannel(models.Model):
    user = models.ForeignKey(
        DiscordUser,
        on_delete=models.CASCADE,
        related_name="allowed_marketplaces",
    )
    channel = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["channel"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "channel"],
                name="unique_user_marketplace_channel",
            )
        ]

    def __str__(self):
        return f"{self.user.discord_id} -> {self.channel}"


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
    image_url = models.URLField(max_length=2000, blank=True)
    source = models.CharField(max_length=120, blank=True)
    discovered_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # Atualizado a cada nova consulta de preço/estoque.
    last_checked_at = models.DateTimeField(auto_now=True)
    # None = a página não informou disponibilidade.
    in_stock = models.BooleanField(null=True, blank=True)

    class Meta:
        ordering = ["-discovered_at"]

    def __str__(self):
        return self.title
