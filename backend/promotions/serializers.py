import regex
from rest_framework import serializers

from .models import WatchlistItem


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