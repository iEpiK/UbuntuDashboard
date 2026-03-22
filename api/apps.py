from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        import sys

        # Only start the background scheduler when running the web server,
        # not during management commands like migrate, test, shell, etc.
        argv = sys.argv
        if len(argv) >= 2 and argv[1] == 'runserver':
            from . import scheduler
            scheduler.start()

