from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DiscordUser, WatchlistItem
from .permissions import HasBotServiceToken
from .serializers import WatchlistItemSerializer


class WatchlistView(APIView):
    permission_classes = [HasBotServiceToken]

    def get_user(self, request):
        discord_id = request.headers.get("X-Discord-User-ID", "")
        if not discord_id.isdecimal() or len(discord_id) > 32:
            raise ValidationError(
                {"discord_user_id": "Informe um ID Discord numérico válido."}
            )
        user, _ = DiscordUser.objects.get_or_create(discord_id=discord_id)
        return user

    def get(self, request):
        user = self.get_user(request)
        items = WatchlistItem.objects.filter(user=user)
        return Response(WatchlistItemSerializer(items, many=True).data)

    def post(self, request):
        user = self.get_user(request)
        serializer = WatchlistItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save(user=user)
        return Response(
            WatchlistItemSerializer(item).data,
            status=status.HTTP_201_CREATED,
        )


class WatchlistItemView(APIView):
    permission_classes = [HasBotServiceToken]

    def delete(self, request, item_id):
        discord_id = request.headers.get("X-Discord-User-ID", "")
        if not discord_id.isdecimal() or len(discord_id) > 32:
            raise ValidationError(
                {"discord_user_id": "Informe um ID Discord numérico válido."}
            )
        deleted, _ = WatchlistItem.objects.filter(
            pk=item_id,
            user__discord_id=discord_id,
        ).delete()
        if not deleted:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)