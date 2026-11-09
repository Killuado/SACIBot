from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from lives.models import LiveSession, YouTubeSource
from lives.youtube.parsing import parse_source_input


class Command(BaseCommand):
    help = "Gerencia canais e lives do YouTube monitorados pelo SACIBot."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)

        add_p = sub.add_parser("add", help="Cadastra um canal (@loja, UC...) ou live específica.")
        add_p.add_argument("target", help="Handle (@kabum), ID/URL de canal ou URL/ID de vídeo/live.")
        add_p.add_argument(
            "--any-author",
            action="store_true",
            help="Aceita links enviados por qualquer pessoa no chat (padrão: apenas dono/mod/verificado).",
        )

        sub.add_parser("list", help="Lista as fontes cadastradas.")
        logs_p = sub.add_parser("logs", help="Mostra últimos comentários e links recebidos nas lives.")
        logs_p.add_argument("--source-id", type=int, default=None, help="Filtra pelo ID da fonte.")

        for name, help_text in (
            ("remove", "Remove uma fonte pelo ID."),
            ("enable", "Reativa uma fonte pelo ID."),
            ("disable", "Desativa uma fonte pelo ID."),
        ):
            p = sub.add_parser(name, help=help_text)
            p.add_argument("source_id", type=int)

    def handle(self, *args, action, **options):
        if action == "add":
            self._handle_add(options["target"], any_author=options["any_author"])
        elif action == "list":
            self._handle_list()
        elif action == "logs":
            self._handle_logs(options.get("source_id"))
        elif action == "remove":
            self._handle_remove(options["source_id"])
        elif action in {"enable", "disable"}:
            self._handle_toggle(options["source_id"], enabled=(action == "enable"))

    def _handle_add(self, target: str, any_author: bool) -> None:
        try:
            kind, identifier = parse_source_input(target)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        existing = YouTubeSource.objects.filter(kind=kind, identifier=identifier).first()
        max_sources = getattr(settings, "YOUTUBE_MAX_SOURCES", 50)
        if existing is None and YouTubeSource.objects.count() >= max_sources:
            raise CommandError(f"Limite de {max_sources} fontes atingido.")

        source, created = YouTubeSource.objects.update_or_create(
            kind=kind,
            identifier=identifier,
            defaults={
                "enabled": True,
                "trusted_authors_only": not any_author,
                "note": "",
            },
        )
        verb = "cadastrada" if created else "reativada/atualizada"
        self.stdout.write(
            self.style.SUCCESS(
                f"Fonte #{source.pk} ({source.get_kind_display()} {source.identifier}) {verb}."
            )
        )

    def _handle_list(self) -> None:
        sources = list(YouTubeSource.objects.all())
        if not sources:
            self.stdout.write("Nenhuma fonte do YouTube cadastrada.")
            return
        for src in sources:
            if not src.enabled:
                status = "⏸ desativada"
            elif src.current_video_id:
                status = f"🔴 AO VIVO ({src.current_video_id})"
            else:
                status = "⚪ aguardando"
            authors = "confiáveis" if src.trusted_authors_only else "qualquer autor"
            label = f" [{src.label}]" if src.label else ""
            note = f" — {src.note}" if src.note else ""
            self.stdout.write(
                f"#{src.pk} [{src.kind}] {src.identifier}{label} | {status} | {authors}{note}"
            )

    def _handle_remove(self, source_id: int) -> None:
        deleted, _ = YouTubeSource.objects.filter(pk=source_id).delete()
        if not deleted:
            raise CommandError(f"Fonte #{source_id} não encontrada.")
        self.stdout.write(self.style.SUCCESS(f"Fonte #{source_id} removida."))

    def _handle_toggle(self, source_id: int, enabled: bool) -> None:
        updated = YouTubeSource.objects.filter(pk=source_id).update(enabled=enabled)
        if not updated:
            raise CommandError(f"Fonte #{source_id} não encontrada.")
        state = "ativada" if enabled else "desativada"
        self.stdout.write(self.style.SUCCESS(f"Fonte #{source_id} {state}."))

    def _handle_logs(self, source_id: int | None) -> None:
        qs = LiveSession.objects.select_related("source").filter(ended_at__isnull=True)
        if source_id is not None:
            qs = qs.filter(source_id=source_id)
        sessions = list(qs[:10])
        if not sessions:
            fallback = LiveSession.objects.select_related("source")
            if source_id is not None:
                fallback = fallback.filter(source_id=source_id)
            sessions = list(fallback[:3])
        if not sessions:
            self.stdout.write("Nenhuma sessão de live encontrada.")
            return

        for s in sessions:
            status = "🔴 ATIVA" if s.ended_at is None else "⚪ ENCERRADA"
            name = s.source.label or s.source.identifier
            self.stdout.write(
                f"=== {status} | Fonte #{s.source_id} {name} ({s.video_id}) — {s.title} ==="
            )
            self.stdout.write(
                f"Contadores: {s.messages_seen} comentários | {s.links_seen} links válidos | {s.links_ingested} ingeridos"
            )
            self.stdout.write("Últimos comentários:")
            msgs = (s.recent_messages or [])[-10:]
            if not msgs:
                self.stdout.write("  (nenhum comentário registrado)")
            for m in msgs:
                badges = f" [{','.join(m.get('badges') or [])}]" if m.get("badges") else ""
                self.stdout.write(f"  [{m.get('time', '')}] {m.get('author')}{badges}: {m.get('text')}")
            self.stdout.write("Últimos links recebidos:")
            links = (s.recent_links or [])[-10:]
            if not links:
                self.stdout.write("  (nenhum link recebido)")
            for lk in links:
                self.stdout.write(
                    f"  [{lk.get('time', '')}] {lk.get('author')} -> {lk.get('url')} ({lk.get('status')})"
                )
