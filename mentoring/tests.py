import uuid
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import DatabaseError, IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from .forms import MenteeForm, GoalForm, SessionForm, ReportForm
from .models import Mentee, Goal, Session, Checkin
from .services import Conflict, mutate, remove, statistics

@override_settings(ALLOWED_HOSTS=['testserver', '127.0.0.1', 'localhost'])
class MentorCoreTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.a = User.objects.create_user('alpha', password='LocalOnly-Strong-123!')
        cls.b = User.objects.create_user('beta', password='LocalOnly-Strong-456!')
        cls.p = Mentee.objects.create(owner=cls.a, name='Подопечный А', focus='Учебная цель', create_digest='fixture')
        cls.other = Mentee.objects.create(owner=cls.b, name='Подопечный Б', create_digest='fixture')
        cls.g = Goal.objects.create(mentee=cls.p, title='Первый проект', create_digest='fixture')
        cls.foreign = Goal.objects.create(mentee=cls.other, title='Чужая цель', create_digest='fixture')

    def session_form(self, *, progress=None, goal=None, **overrides):
        self.p.refresh_from_db()
        data = {'version': self.p.version, 'create_nonce': str(uuid.uuid4()), 'held_on': timezone.localdate().isoformat(), 'topic': 'Разбор проекта', 'notes': 'Что получилось', 'next_steps': 'Следующий шаг', 'goal': self.g.pk if goal is None and progress is not None else goal or '', 'progress': '' if progress is None else progress}
        data.update(overrides)
        return SessionForm(data, aggregate=self.p)

    def test_create_mentee_normalized_and_retry(self):
        nonce = uuid.uuid4()
        data = {'name': '  Новый участник  ', 'focus': '  Согласованный фокус  ', 'create_nonce': nonce}
        f = MenteeForm(data); self.assertTrue(f.is_valid(), f.errors)
        p, created = mutate(f, owner=self.a); self.assertTrue(created); self.assertEqual(p.name, 'Новый участник')
        f = MenteeForm(data); self.assertTrue(f.is_valid()); same, created = mutate(f, owner=self.a)
        self.assertFalse(created); self.assertEqual(same.pk, p.pk); self.assertEqual(Mentee.objects.filter(owner=self.a, create_nonce=nonce).count(), 1)
        data['focus'] = 'Другое содержимое'; f = MenteeForm(data); self.assertTrue(f.is_valid())
        with self.assertRaises(Conflict): mutate(f, owner=self.a)

    def test_score_zero_is_real_and_missing_is_distinct(self):
        self.assertIsNone(statistics([self.p])[self.p.pk]['score'])
        f = self.session_form(progress=0); self.assertTrue(f.is_valid(), f.errors); s, _ = mutate(f, owner=self.a, aggregate=self.p)
        self.assertEqual(s.checkin.progress, 0); self.assertEqual(statistics([self.p])[self.p.pk]['score'], 0)
        f = self.session_form(); self.assertTrue(f.is_valid()); s, _ = mutate(f, owner=self.a, aggregate=self.p)
        self.assertFalse(Checkin.objects.filter(session=s).exists())

    def test_goal_and_score_pair_validation(self):
        for f in [self.session_form(goal=self.g.pk), self.session_form(progress=40, goal=''), self.session_form(progress=101), self.session_form(progress=-1), self.session_form(progress=42.5), self.session_form(progress=40, goal=self.foreign.pk)]:
            self.assertFalse(f.is_valid())
        self.assertEqual(Session.objects.count(), 0)

    def test_malformed_relation_ids_are_form_errors(self):
        for value in ['9' * 5000, '١٢٣', '-1', '9223372036854775808']:
            self.assertFalse(self.session_form(goal=value, progress=50).is_valid())

    def test_no_future_or_impossible_session_dates(self):
        for d in [(timezone.localdate() + timedelta(days=1)).isoformat(), '2026-02-30', '1899-12-31', '9999-01-01']:
            self.assertFalse(self.session_form(held_on=d).is_valid())

    def test_score_can_fall_and_same_day_tie_is_latest_id(self):
        for value in [60, 40]:
            f = self.session_form(progress=value); self.assertTrue(f.is_valid()); mutate(f, owner=self.a, aggregate=self.p)
        stats = statistics([self.p])[self.p.pk]
        self.assertEqual(stats['score'], 40)
        self.assertEqual([c.progress for c in stats['goals'][0].history], [60, 40])

    def test_average_half_up_excludes_unrated_goals(self):
        g2 = Goal.objects.create(mentee=self.p, title='Вторая цель', create_digest='fixture')
        Goal.objects.create(mentee=self.p, title='Ещё без оценки', create_digest='fixture')
        for goal, value in [(self.g, 50), (g2, 51)]:
            f = self.session_form(progress=value, goal=goal.pk); self.assertTrue(f.is_valid()); mutate(f, owner=self.a, aggregate=self.p)
        stats = statistics([self.p])[self.p.pk]
        self.assertEqual((stats['score'], stats['rated_count'], stats['goal_count']), (51, 2, 3))

    def test_report_baseline_and_range(self):
        today = timezone.localdate()
        for delta, score in [(20, 25), (5, 70)]:
            f = self.session_form(progress=score, held_on=(today - timedelta(days=delta)).isoformat()); self.assertTrue(f.is_valid()); mutate(f, owner=self.a, aggregate=self.p)
        g = statistics([self.p], start=today - timedelta(days=10), end=today)[self.p.pk]['goals'][0]
        self.assertEqual(g.score, 70); self.assertEqual(g.baseline.progress, 25); self.assertEqual([c.progress for c in g.history], [70])
        self.assertFalse(ReportForm({'start': today.isoformat(), 'end': (today - timedelta(days=1)).isoformat()}).is_valid())

    def test_session_retry_does_not_duplicate_or_bump_twice(self):
        f = self.session_form(progress=40); data = dict(f.data); self.assertTrue(f.is_valid()); s, _ = mutate(f, owner=self.a, aggregate=self.p)
        self.p.refresh_from_db(); version = self.p.version
        retry = SessionForm(data, aggregate=self.p); self.assertTrue(retry.is_valid()); duplicate, created = mutate(retry, owner=self.a, aggregate=self.p)
        self.assertFalse(created); self.assertEqual(duplicate.pk, s.pk); self.assertEqual(Checkin.objects.count(), 1)
        self.p.refresh_from_db(); self.assertEqual(self.p.version, version)

    def test_stale_create_and_delete_cannot_erase_new_history(self):
        f1, f2 = self.session_form(progress=50), self.session_form(progress=60)
        stale_version = self.p.version
        self.assertTrue(f1.is_valid()); self.assertTrue(f2.is_valid()); mutate(f1, owner=self.a, aggregate=self.p)
        with self.assertRaises(Conflict): mutate(f2, owner=self.a, aggregate=self.p)
        with self.assertRaises(Conflict): remove(self.p, mentee=self.p, owner=self.a, version=stale_version)
        self.assertTrue(Mentee.objects.filter(pk=self.p.pk).exists()); self.assertEqual(Session.objects.count(), 1)

    def test_session_checkin_failure_rolls_back_parent_version(self):
        f = self.session_form(progress=60); self.assertTrue(f.is_valid()); initial = self.p.version
        with patch.object(Checkin.objects, 'update_or_create', side_effect=DatabaseError('simulated')):
            with self.assertRaises(DatabaseError): mutate(f, owner=self.a, aggregate=self.p)
        self.assertEqual(Session.objects.count(), 0); self.p.refresh_from_db(); self.assertEqual(self.p.version, initial)

    def test_edit_can_clear_score_atomically(self):
        f = self.session_form(progress=25); self.assertTrue(f.is_valid()); s, _ = mutate(f, owner=self.a, aggregate=self.p)
        self.p.refresh_from_db(); data = {'version': self.p.version, 'held_on': s.held_on.isoformat(), 'topic': s.topic, 'notes': s.notes, 'next_steps': '', 'goal': '', 'progress': ''}
        edit = SessionForm(data, instance=s, aggregate=self.p); self.assertTrue(edit.is_valid(), edit.errors); mutate(edit, owner=self.a, aggregate=self.p)
        self.assertFalse(Checkin.objects.exists()); self.assertIsNone(statistics([self.p])[self.p.pk]['score'])

    def test_database_rejects_out_of_range_score(self):
        s = Session.objects.create(mentee=self.p, held_on=timezone.localdate(), topic='Тест', create_digest='fixture')
        with self.assertRaises(IntegrityError), transaction.atomic(): Checkin.objects.create(session=s, goal=self.g, progress=101)

    def test_ownership_isolation_in_service_context(self):
        f = self.session_form(progress=25); self.assertTrue(f.is_valid())
        with self.assertRaises(Conflict): mutate(f, owner=self.b, aggregate=self.p)
        self.assertFalse(Session.objects.exists())

    def test_deleted_parent_between_form_and_commit_is_conflict(self):
        f = self.session_form(progress=30); self.assertTrue(f.is_valid())
        pk = self.p.pk
        Mentee.objects.filter(pk=pk).delete()
        with self.assertRaises(Conflict): mutate(f, owner=self.a, aggregate=self.p)
        self.assertFalse(Session.objects.exists())

    def test_unknown_fields_and_whitespace_rejected(self):
        self.assertFalse(MenteeForm({'name': '   ', 'focus': '', 'create_nonce': uuid.uuid4()}).is_valid())
        self.assertFalse(MenteeForm({'name': 'Имя', 'focus': '', 'create_nonce': uuid.uuid4(), 'owner': self.b.pk}).is_valid())

    def test_early_boundary_errors_have_security_headers(self):
        for response in [self.client.get('/health/', HTTP_HOST='foreign.invalid'), self.client.post('/accounts/login/', data='{}', content_type='application/json'), self.client.post('/accounts/login/', data='x=' + 'a' * 33000, content_type='application/x-www-form-urlencoded')]:
            self.assertIn(response.status_code, [400, 413, 415])
            self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
            self.assertEqual(response['X-Frame-Options'], 'DENY')
            self.assertEqual(response['Cache-Control'], 'no-store')
            self.assertIn("frame-ancestors 'none'", response['Content-Security-Policy'])
