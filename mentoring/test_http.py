import uuid
from urllib.parse import urlencode
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from django.urls import reverse
from .models import Mentee, Goal, Session, Checkin

class FormClient(Client):
    def post(self, path, data=None, **kwargs):
        return super().post(path, data=urlencode(data or {}), content_type='application/x-www-form-urlencoded', **kwargs)

@override_settings(ALLOWED_HOSTS=['testserver', '127.0.0.1', 'localhost'])
class MentorHTTPTests(TestCase):
    client_class = FormClient
    @classmethod
    def setUpTestData(cls):
        U = get_user_model()
        cls.a = U.objects.create_user('alice-test', password='OnlyForTest-Strong!123')
        cls.b = U.objects.create_user('bob-test', password='OnlyForTest-Strong!456')
        cls.p = Mentee.objects.create(owner=cls.a, name='Участник А', create_digest='fixture')
        cls.other = Mentee.objects.create(owner=cls.b, name='Закрытая запись Б', create_digest='fixture')
        cls.g = Goal.objects.create(mentee=cls.p, title='Согласованная цель А', create_digest='fixture')
        cls.other_goal = Goal.objects.create(mentee=cls.other, title='Чужая цель Б', create_digest='fixture')
        cls.s = Session.objects.create(mentee=cls.p, held_on=timezone.localdate(), topic='Первая встреча', notes='Разбор первой задачи', next_steps='Следующий результат', create_digest='fixture')
        Checkin.objects.create(session=cls.s, goal=cls.g, progress=0)
    def setUp(self): self.client.force_login(self.a)

    def test_anonymous_redirects_and_logout_post_only(self):
        anonymous = Client()
        for url in ['/', '/mentees/', f'/mentees/{self.p.pk}/', f'/mentees/{self.p.pk}/report/']:
            self.assertEqual(anonymous.get(url).status_code, 302)
        self.assertEqual(self.client.get('/accounts/logout/').status_code, 405)
        self.assertEqual(self.client.get('/accounts/signup/').status_code, 404)
        self.assertEqual(self.client.post('/accounts/logout/', {'csrfmiddlewaretoken': 'test-client-token'}).status_code, 302)
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_foreign_parent_and_child_ids_are_invisible(self):
        for url in [f'/mentees/{self.other.pk}/', f'/mentees/{self.other.pk}/report/', f'/mentees/{self.other.pk}/edit/', f'/mentees/{self.other.pk}/delete/', f'/mentees/{self.p.pk}/goals/{self.other_goal.pk}/edit/', f'/mentees/{self.p.pk}/goals/{self.other_goal.pk}/delete/']:
            self.assertEqual(self.client.get(url).status_code, 404, url)
        page = self.client.get('/mentees/'); self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, self.other.name); self.assertContains(page, self.p.name)

    def test_csrf_and_forged_origin_block_mutations(self):
        c = FormClient(enforce_csrf_checks=True); c.force_login(self.a)
        path = f'/mentees/{self.p.pk}/edit/'
        self.assertEqual(c.post(path, {'name': 'Подмена', 'focus': '', 'version': self.p.version}).status_code, 403)
        page = c.get(path); self.assertEqual(page.status_code, 200)
        token = c.cookies['orientir_csrf'].value
        self.assertEqual(c.post(path, {'name': 'Подмена', 'focus': '', 'version': self.p.version, 'csrfmiddlewaretoken': token}, HTTP_ORIGIN='https://foreign.invalid').status_code, 403)
        self.p.refresh_from_db(); self.assertEqual(self.p.name, 'Участник А')

    def test_edit_and_stale_form_no_lost_update(self):
        path = f'/mentees/{self.p.pk}/edit/'
        data = {'name': 'Новое имя', 'focus': 'Фокус', 'version': self.p.version}
        self.assertEqual(self.client.post(path, data).status_code, 302)
        self.assertEqual(self.client.post(path, {**data, 'name': 'Старая вкладка'}).status_code, 409)
        self.p.refresh_from_db(); self.assertEqual(self.p.name, 'Новое имя')

    def test_server_form_create_retry_and_forged_goal(self):
        self.p.refresh_from_db()
        data = {'held_on': timezone.localdate().isoformat(), 'topic': 'Новая встреча', 'notes': 'Наблюдение', 'next_steps': '', 'version': self.p.version, 'create_nonce': str(uuid.uuid4()), 'goal': self.g.pk, 'progress': 60}
        path = f'/mentees/{self.p.pk}/sessions/new/'
        self.assertEqual(self.client.post(path, data).status_code, 302)
        self.assertEqual(self.client.post(path, data).status_code, 302)
        self.assertEqual(Session.objects.filter(mentee=self.p, topic='Новая встреча').count(), 1)
        self.p.refresh_from_db()
        forged = {**data, 'create_nonce': str(uuid.uuid4()), 'version': self.p.version, 'goal': self.other_goal.pk}
        self.assertEqual(self.client.post(path, forged).status_code, 400)
        self.assertEqual(Session.objects.filter(mentee=self.p).count(), 2)

    def test_xss_is_text_in_record_form_and_report(self):
        self.p.focus = '<img src=x onerror=alert(1)>'; self.p.save(update_fields=['focus'])
        self.s.notes = '<script>alert(2)</script>'; self.s.save(update_fields=['notes'])
        for url in [f'/mentees/{self.p.pk}/', f'/mentees/{self.p.pk}/edit/', f'/mentees/{self.p.pk}/report/']:
            r = self.client.get(url); self.assertEqual(r.status_code, 200)
            self.assertNotIn(b'<img src=x', r.content); self.assertNotIn(b'<script>alert(2)', r.content)
            self.assertIn("script-src 'self'", r['Content-Security-Policy'])

    def test_report_date_errors_and_zero_assessment(self):
        base = f'/mentees/{self.p.pk}/report/'
        self.assertEqual(self.client.get(base, {'from': '2026-12-02', 'to': '2026-01-01'}).status_code, 400)
        self.assertEqual(self.client.get(base, {'from': 'not-a-date'}).status_code, 400)
        report = self.client.get(base); self.assertEqual(report.status_code, 200)
        self.assertEqual(report.context['stats']['score'], 0)
        self.assertEqual(report.context['stats']['rated_count'], 1)
        self.assertEqual(report.context['stats']['goal_count'], 1)

    def test_invalid_ids_and_static_boundary(self):
        for path in ['/mentees/' + '9' * 200 + '/', '/mentees/١٢٣/', '/.state/secret.key', '/.git/config', '/manage.py', '/static/../.state/mentor.sqlite3', '/static/%2e%2e/.state/secret.key']:
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_get_delete_never_mutates_and_stale_cascade_rejected(self):
        path = f'/mentees/{self.p.pk}/delete/'
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertTrue(Mentee.objects.filter(pk=self.p.pk).exists())
        self.assertEqual(self.client.post(path, {'version': self.p.version}).status_code, 400)
        Mentee.objects.filter(pk=self.p.pk).update(version=self.p.version + 1)
        self.assertEqual(self.client.post(path, {'version': self.p.version, 'confirm': 'on'}).status_code, 409)
        self.assertEqual(Session.objects.filter(mentee=self.p).count(), 1)

    def test_health_is_minimal(self):
        r = Client().get('/health/')
        self.assertEqual(r.status_code, 200); self.assertEqual(r.json(), {'status': 'ok'})

    def test_invalid_field_errors_have_matching_describedby(self):
        r = self.client.post('/mentees/new/', {'name': '', 'focus': 'Черновик', 'create_nonce': uuid.uuid4()})
        self.assertContains(r, 'aria-describedby="id_name_error"', status_code=400)
        self.assertContains(r, 'id="id_name_error"', status_code=400)
        r = self.client.get(f'/mentees/{self.p.pk}/report/', {'from': 'invalid'})
        self.assertContains(r, 'aria-describedby="id_start_error"', status_code=400)
        self.assertContains(r, 'id="id_start_error"', status_code=400)
