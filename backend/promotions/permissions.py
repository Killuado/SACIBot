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


class IsDiscordAdmin(BasePermission):
    message = "Você não tem permissão de usar esse comando."

    def has_permission(self, request, view):
        admin_ids = set(getattr(settings, "DISCORD_ADMIN_IDS", set()) or set())
        discord_id = (request.headers.get("X-Discord-User-ID") or "").strip()
        return bool(admin_ids and discord_id and discord_id in admin_ids)
