import sqlite3
import time
from contextlib import closing
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

def verified(path):
    try:
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            required = {'auth_user', 'mentoring_mentee', 'mentoring_goal', 'mentoring_session', 'mentoring_checkin', 'django_migrations'}
            return required.issubset(tables) and db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
    except sqlite3.Error:
        return False

class Command(BaseCommand):
    help = 'Online SQLite backup with integrity verification; keep last5 valid copies.'
    def handle(self, *args, **options):
        source = settings.STATE_DIR / 'mentor.sqlite3'
        if not source.is_file(): raise CommandError('База данных ещё не создана.')
        directory = settings.STATE_DIR / 'backups'
        directory.mkdir(exist_ok=True)
        stamp = time.time_ns()
        destination = directory / f'mentor-{stamp}.sqlite3'
        partial = directory / f'mentor-{stamp}.partial'
        try:
            with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=5)) as src, closing(sqlite3.connect(partial)) as dst:
                src.backup(dst)
            if not verified(partial): raise CommandError('Копия не прошла проверку схемы и целостности; исходная база не изменена. Неподтверждённый файл сохранён отдельно.')
            partial.replace(destination)
        except sqlite3.Error as exc: raise CommandError('Не удалось создать подтверждённую копию. Исходная база не изменена.') from exc
        valid = []
        for path in sorted(directory.glob('mentor-*.sqlite3'), reverse=True):
            if verified(path): valid.append(path)
        for path in valid[5:]: path.unlink()
        self.stdout.write('Копия создана и проверена: ' + destination.name)
