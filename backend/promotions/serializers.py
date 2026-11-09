import regex
from rest_framework import serializers

from .models import Address, MarketplaceChannel, Promotion, WatchlistItem


class WatchlistItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = WatchlistItem
        fields = ["id", "pattern", "max_price", "enabled", "created_at"]
        read_only_fields = ["id", "enabled", "created_at"]

    def validate_pattern(self, value):
        if not value.strip():
            raise serializers.ValidationError("A expressão não pode ficar vazia.")
        try:
            regex.compile(value, regex.IGNORECASE)
        except regex.error as error:
            raise serializers.ValidationError("A expressão regular é inválida.") from error
        return value

    def validate_max_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("O preço máximo deve ser maior que zero.")
        return value


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            "id",
            "recipient_name",
            "street",
            "number",
            "complement",
            "neighborhood",
            "city",
            "state",
            "zip_code",
            "cpf",
            "updated_at",
        ]
        read_only_fields = ["id", "updated_at"]

    def validate_state(self, value):
        val = value.strip().upper()
        if len(val) != 2:
            raise serializers.ValidationError("Informe a sigla do estado em 2 letras (ex: SP, RJ, MG).")
        return val


class MarketplaceChannelSerializer(serializers.ModelSerializer):
    user_index = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = MarketplaceChannel
        fields = ["id", "user_index", "channel", "created_at"]
        read_only_fields = ["id", "user_index", "created_at"]

    def validate_channel(self, value):
        val = value.strip().lower()
        if not val:
            raise serializers.ValidationError("O nome do marketplace/canal não pode ficar vazio.")
        return val


class PromotionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Promotion
        fields = [
            "id",
            "title",
            "price",
            "url",
            "marketplace",
            "image_url",
            "source",
            "in_stock",
            "discovered_at",
            "last_checked_at",
        ]
        read_only_fields = ["id", "discovered_at", "last_checked_at"]

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("O preço deve ser maior que zero.")
        return value
