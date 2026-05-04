from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Start the Telegram bot (long-polling mode)"

    def handle(self, *args, **options):
        from tgbot.bot import build_application

        self.stdout.write(self.style.SUCCESS("Bot ishga tushmoqda..."))
        app = build_application()
        app.run_polling(drop_pending_updates=True)
