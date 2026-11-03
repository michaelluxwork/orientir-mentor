from getpass import getpass
from django.contrib.auth.forms import UserCreationForm
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = 'Create a local mentor account interactively; no email or public signup.'
    def add_arguments(self, parser): parser.add_argument('username')
    def handle(self, *args, **options):
        password = getpass('Пароль, минимум12 символов: ')
        confirmation = getpass('Повторите пароль: ')
        form = UserCreationForm({'username': options['username'], 'password1': password, 'password2': confirmation})
        if not form.is_valid(): raise CommandError('; '.join(str(e) for values in form.errors.values() for e in values))
        form.save()
        self.stdout.write('Аккаунт наставника создан. Пароль в файлы или журналы не записан.')
