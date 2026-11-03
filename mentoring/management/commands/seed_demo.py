import os
import secrets
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from mentoring.models import Mentee, Goal, Session, Checkin

class Command(BaseCommand):
    help = 'Create invented mentor records and random local credentials, never overwrite existing account.'
    def handle(self, *args, **options):
        User = get_user_model()
        path = settings.STATE_DIR / 'demo-access.txt'
        if User.objects.filter(username='mentor').exists():
            if path.exists(): self.stdout.write('Пример уже существует, данные и пароль не изменены.'); return
            raise CommandError('Аккаунт mentor уже существует без файла доступа. Он не изменён. Создайте другой аккаунт через create_mentor.')
        password = secrets.token_urlsafe(22)
        try:
            with path.open('x', encoding='utf-8') as stream:
                stream.write('Локальный учебный аккаунт\nЛогин: mentor\nПароль: ' + password + '\nТолько вымышленные записи; файл не входит в ZIP.\n')
                stream.flush(); os.fsync(stream.fileno())
        except FileExistsError: raise CommandError('Файл доступа уже существует. Проверьте завершение предыдущего seed; исходный файл сохранён.')
        try:
            with transaction.atomic():
                user = User.objects.create_user(username='mentor', password=password)
                today = timezone.localdate()
                samples = [
                    ('Александра Примерова', 'Портфолио и уверенная презентация проектов', [('Подготовить два проекта для портфолио', 'Два законченных проекта с описанием задачи и результата'), ('Провести пробное собеседование', 'Самостоятельно объяснить решения и ответить на вопросы')], [25, 45, 70]),
                    ('Михаил Учебный', 'Первые выступления на технических встречах', [('Подготовить короткий доклад', 'Понятная структура и репетиция с обратной связью'), ('Выступить перед небольшой группой', 'Выступление и разбор обратной связи')], [20, 55, 45]),
                    ('Виктория Примерова', 'План развития навыков Python', [('Закончить учебный веб-проект', 'Работающий проект с инструкцией запуска')], []),
                ]
                for name, focus, titles, scores in samples:
                    p = Mentee.objects.create(owner=user, name=name, focus=focus, create_digest='seed-v1')
                    goals = [Goal.objects.create(mentee=p, title=title, description=description, target_date=today + timedelta(days=30), create_digest='seed-v1') for title, description in titles]
                    for index, score in enumerate(scores):
                        s = Session.objects.create(mentee=p, held_on=today - timedelta(days=21 - index * 7), topic=['Старт и договорённости', 'Промежуточный разбор', 'Практика и следующий шаг'][index], notes=['Обсудили исходную точку и критерий результата.', 'Разобрали подготовленный материал и трудности.', 'Проверили изменения на конкретном примере.'][index], next_steps='Подготовить следующий небольшой результат и записать вопросы.', create_digest='seed-v1')
                        Checkin.objects.create(session=s, goal=goals[0], progress=score)
                    if len(goals) > 1:
                        s = Session.objects.create(mentee=p, held_on=today - timedelta(days=2), topic='Отдельный разбор второй цели', notes='Проверили первый самостоятельный шаг по согласованной цели.', next_steps='Повторить практику и записать, что получилось.', create_digest='seed-v1')
                        Checkin.objects.create(session=s, goal=goals[1], progress=35)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        self.stdout.write('Вымышленный пример создан. Локальный доступ находится в .state/demo-access.txt; пароль не выводится в журнал.')
