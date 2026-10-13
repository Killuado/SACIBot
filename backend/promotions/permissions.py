import secrets

from django.conf import settings
from rest_framework.permissions import BasePermission


class HasBotServiceToken(BasePermission):
    message = "Token de serviço inválido ou não configurado."

    def has_permission(self, request, view):
        configured_token = settings.BOT_API_TOKEN
        provided_token = request.headers.get("X-Bot-Token", "")
        return bool(configured_token) and secrets.compare_digest(
            configured_token,
            provided_token,
        )