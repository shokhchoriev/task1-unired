from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Start the Telegram bot (long-polling mode)"

    def handle(self, *args, **options):
        from tgbot.bot import run_bot

        self.stdout.write(self.style.SUCCESS("Bot ishga tushmoqda..."))
        run_bot()
