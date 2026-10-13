import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="DiscordUser",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("discord_id", models.CharField(max_length=32, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="Promotion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=300)),
                (
                    "price",
                    models.DecimalField(decimal_places=2, max_digits=10),
                ),
                ("url", models.URLField(max_length=2000, unique=True)),
                ("marketplace", models.CharField(max_length=80)),
                ("source", models.CharField(blank=True, max_length=120)),
                ("discovered_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-discovered_at"]},
        ),
        migrations.CreateModel(
            name="WatchlistItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("pattern", models.CharField(max_length=200)),
                (
                    "max_price",
                    models.DecimalField(decimal_places=2, max_digits=10),
                ),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="watchlist_items",
                        to="promotions.discorduser",
                    ),
                ),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
    ]