from django.db import connection
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Address, DiscordUser, MarketplaceChannel, Promotion, WatchlistItem
from .permissions import HasBotServiceToken, IsDiscordAdmin
from .serializers import (
    AddressSerializer,
    MarketplaceChannelSerializer,
    PromotionSerializer,
    WatchlistItemSerializer,
)
from .services import process_and_notify_promotion, send_bot_notification


class BaseDiscordUserView(APIView):
    permission_classes = [HasBotServiceToken]

    def get_user(self, request):
        discord_id = request.headers.get("X-Discord-User-ID", "")
        if not discord_id.isdecimal() or len(discord_id) > 32:
            raise ValidationError(
                {"discord_user_id": "Informe um ID Discord numérico válido."}
            )
        user, _ = DiscordUser.objects.get_or_create(discord_id=discord_id)
        return user


class WatchlistView(BaseDiscordUserView):
    def get(self, request):
        user = self.get_user(request)
        items = WatchlistItem.objects.filter(user=user)
        return Response(WatchlistItemSerializer(items, many=True).data)

    def post(self, request):
        user = self.get_user(request)
        serializer = WatchlistItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save(user=user)
        data = WatchlistItemSerializer(item).data
        data["user_status"] = {
            "has_address": user.has_address,
            "has_marketplaces": user.has_marketplaces,
        }
        return Response(data, status=status.HTTP_201_CREATED)


class WatchlistItemView(BaseDiscordUserView):
    def delete(self, request, item_id):
        user = self.get_user(request)
        deleted, _ = WatchlistItem.objects.filter(
            pk=item_id,
            user=user,
        ).delete()
        if not deleted:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class WatchlistClearAllView(APIView):
    """Admin endpoint: limpa TODA a watchlist de todos os usuários e reseta o ID para 1."""

    permission_classes = [HasBotServiceToken, IsDiscordAdmin]

    def delete(self, request):
        deleted, _ = WatchlistItem.objects.all().delete()

        table_name = WatchlistItem._meta.db_table
        try:
            with connection.cursor() as cursor:
                if connection.vendor == "sqlite":
                    cursor.execute("DELETE FROM sqlite_sequence WHERE name = %s", [table_name])
                elif connection.vendor == "postgresql":
                    cursor.execute(f"ALTER SEQUENCE {table_name}_id_seq RESTART WITH 1;")
        except Exception:
            pass

        return Response(
            {"deleted": deleted, "reset_sequence": True},
            status=status.HTTP_200_OK,
        )


class AddressView(BaseDiscordUserView):
    def get(self, request):
        user = self.get_user(request)
        if not user.has_address:
            return Response(
                {"detail": "Nenhum endereço cadastrado para este usuário."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(AddressSerializer(user.address).data)

    def post(self, request):
        user = self.get_user(request)
        serializer = AddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        address, created = Address.objects.update_or_create(
            user=user,
            defaults=serializer.validated_data,
        )
        return Response(
            AddressSerializer(address).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class MarketplaceChannelListView(BaseDiscordUserView):
    def get(self, request):
        user = self.get_user(request)
        channels = user.allowed_marketplaces.order_by("created_at", "id")
        result = []
        for idx, obj in enumerate(channels, start=1):
            data = MarketplaceChannelSerializer(obj).data
            data["user_index"] = idx
            result.append(data)
        return Response(result)

    def post(self, request):
        user = self.get_user(request)

        # Suporta {"channels": ["kabum", "pichau"]} ou {"channel": "kabum, pichau"} ou {"channel": "kabum"}
        raw_channels = request.data.get("channels")
        if raw_channels is None:
            raw_channel = request.data.get("channel", "")
            if isinstance(raw_channel, str):
                raw_channels = [c.strip().lower() for c in raw_channel.split(",") if c.strip()]
            else:
                raw_channels = []

        if isinstance(raw_channels, list):
            cleaned_channels = [str(c).strip().lower() for c in raw_channels if str(c).strip()]
        else:
            cleaned_channels = []

        if not cleaned_channels:
            raise ValidationError({"channel": "Informe pelo menos uma loja ou canal válido."})

        created_objs = []
        for ch in cleaned_channels:
            obj, _ = MarketplaceChannel.objects.get_or_create(
                user=user,
                channel=ch,
            )
            created_objs.append(obj)

        all_channels = list(user.allowed_marketplaces.order_by("created_at", "id"))
        id_to_index = {obj.id: idx for idx, obj in enumerate(all_channels, start=1)}

        return Response(
            {
                "channels": [obj.channel for obj in created_objs],
                "items": [
                    {"id": obj.id, "user_index": id_to_index[obj.id], "channel": obj.channel}
                    for obj in created_objs
                ],
                "channel": created_objs[0].channel,
                "added_count": len(created_objs),
            },
            status=status.HTTP_201_CREATED,
        )


class MarketplaceChannelDetailView(BaseDiscordUserView):
    def delete(self, request, channel):
        user = self.get_user(request)
        user_channels = list(user.allowed_marketplaces.order_by("created_at", "id"))

        index_map = {str(idx): obj for idx, obj in enumerate(user_channels, start=1)}
        db_id_map = {str(obj.id): obj for obj in user_channels}
        channel_name_map = {obj.channel.lower(): obj for obj in user_channels}

        raw_ident = channel.strip().lower()
        to_delete_ids = set()

        # 1. Verifica se bate exatamente com o nome de um canal (mesmo se contiver vírgula)
        if raw_ident in channel_name_map:
            to_delete_ids.add(channel_name_map[raw_ident].id)
        else:
            # 2. Separa por vírgula para suportar múltiplos números ou nomes: "1, 2" ou "kabum, pichau"
            parts = [p.strip().lower() for p in raw_ident.split(",") if p.strip()]
            for p in parts:
                if p in index_map:
                    to_delete_ids.add(index_map[p].id)
                elif p in db_id_map:
                    to_delete_ids.add(db_id_map[p].id)
                elif p in channel_name_map:
                    to_delete_ids.add(channel_name_map[p].id)

        if not to_delete_ids:
            return Response(
                {"detail": "Nenhuma loja ou número correspondente foi encontrado na sua lista."},
                status=status.HTTP_404_NOT_FOUND,
            )

        deleted_objs = [obj for obj in user_channels if obj.id in to_delete_ids]
        MarketplaceChannel.objects.filter(id__in=to_delete_ids).delete()

        return Response(
            {
                "deleted": [obj.channel for obj in deleted_objs],
                "count": len(deleted_objs),
            },
            status=status.HTTP_200_OK,
        )


class PromotionIngestView(APIView):
    """
    Ingestão de promoções: salva a promoção e dispara notificações para
    os usuários com watchlist correspondente, endereço configurado e loja permitida.
    """

    permission_classes = [HasBotServiceToken]

    def post(self, request):
        serializer = PromotionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        url = serializer.validated_data["url"]
        promotion, _ = Promotion.objects.update_or_create(
            url=url,
            defaults=serializer.validated_data,
        )
        dispatch_result = process_and_notify_promotion(promotion)
        return Response(
            {
                "promotion": PromotionSerializer(promotion).data,
                "matches": dispatch_result,
            },
            status=status.HTTP_201_CREATED,
        )


class PromotionTestNotifyView(APIView):
    """
    Endpoint de teste de notificação: envia uma DM direta de teste para o Discord User ID informado.
    """

    permission_classes = [HasBotServiceToken]

    def post(self, request):
        discord_user_id = request.data.get("discord_user_id") or request.headers.get("X-Discord-User-ID")
        if not discord_user_id or not str(discord_user_id).isdecimal():
            raise ValidationError({"discord_user_id": "Informe um discord_user_id numérico válido."})

        title = request.data.get("title", "Placa de Vídeo RTX 4060 Ti 8GB")
        price = request.data.get("price", "1899.90")
        url = request.data.get("url", "https://www.kabum.com.br/produto/exemplo-rtx-4060")
        marketplace = request.data.get("marketplace", "kabum")
        image_url = request.data.get(
            "image_url",
            "https://images.kabum.com.br/produtos/fotos/475438/placa-de-video-rtx-4060-ti-ventus-3x-8g-oc-msi-nvidia-geforce-8gb-gddr6-dlss-3-ray-tracing-912-v515-024_1685023963_m.jpg",
        )

        dummy_promo = Promotion(
            title=title,
            price=price,
            url=url,
            marketplace=marketplace,
            image_url=image_url,
        )

        ok = send_bot_notification(
            discord_user_id=str(discord_user_id),
            promotion=dummy_promo,
        )

        if ok:
            return Response({"status": "sent", "recipient": str(discord_user_id)})
        return Response(
            {"status": "error", "detail": "Não foi possível entregar a notificação ao bot Discord."},
            status=status.HTTP_502_BAD_GATEWAY,
        )
