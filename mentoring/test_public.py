import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from django.conf import settings
from django.http import HttpResponse
from django.test import SimpleTestCase, RequestFactory
from mentoring.public_demo import ThrottleMiddleware


class PublicDeploymentTests(SimpleTestCase):
    def test_invalid_configuration_does_not_create_state(self):
        for changes in ({'MENTOR_SECRET_KEY': ''}, {'MENTOR_PUBLIC_HOST': '*'}, {'MENTOR_PROFILE': 'unknown'}, {'MENTOR_STATE_DIR': str(settings.BASE_DIR / 'static')}):
            with tempfile.TemporaryDirectory() as temp:
                state = Path(temp) / 'must-not-exist'
                env = {**os.environ, 'MENTOR_PROFILE': 'vps-demo', 'MENTOR_PUBLIC_HOST': 'orientir.178-255-126-110.sslip.io', 'MENTOR_SECRET_KEY': 'synthetic-test-key-' * 5, 'MENTOR_STATE_DIR': str(state), **changes}
                run = subprocess.run([sys.executable, '-c', 'import config.settings'], cwd=settings.BASE_DIR, env=env, capture_output=True)
                self.assertNotEqual(run.returncode, 0)
                self.assertFalse(state.exists())
                self.assertNotIn(env['MENTOR_SECRET_KEY'].encode(), run.stderr) if env['MENTOR_SECRET_KEY'] else None

    def test_public_settings_have_no_private_key_file(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / 'state'
            env = {**os.environ, 'MENTOR_PROFILE': 'vps-demo', 'MENTOR_PUBLIC_HOST': 'orientir.178-255-126-110.sslip.io', 'MENTOR_SECRET_KEY': 'synthetic-test-key-' * 5, 'MENTOR_STATE_DIR': str(state)}
            code = 'import config.settings as s; assert s.SESSION_COOKIE_SECURE and s.CSRF_COOKIE_SECURE and s.SECURE_SSL_REDIRECT; assert s.SECURE_PROXY_SSL_HEADER is None; assert not s.WHITENOISE_USE_FINDERS; assert not s.WHITENOISE_AUTOREFRESH'
            run = subprocess.run([sys.executable, '-c', code], cwd=settings.BASE_DIR, env=env, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertFalse((state / 'secret.key').exists())

    def test_login_limit_expiry_and_no_hash_work_after_limit(self):
        calls = []
        middleware = ThrottleMiddleware(lambda r: calls.append(1) or HttpResponse('ok'))
        request = RequestFactory().post('/accounts/login/')
        request.user = SimpleNamespace(is_authenticated=False)
        with patch('mentoring.public_demo.monotonic', return_value=100):
            for _ in range(30): self.assertEqual(middleware(request).status_code, 200)
            blocked = middleware(request)
            self.assertEqual(blocked.status_code, 429)
            self.assertIn('Retry-After', blocked)
            self.assertEqual(len(calls), 30)
        with patch('mentoring.public_demo.monotonic', return_value=161):
            self.assertEqual(middleware(request).status_code, 200)
        self.assertEqual(middleware.login.maxlen, 30)

    def test_write_limit_does_not_block_logout_or_health(self):
        middleware = ThrottleMiddleware(lambda r: HttpResponse('ok'))
        factory = RequestFactory()
        request = factory.post('/mentees/new/')
        request.user = SimpleNamespace(is_authenticated=True)
        for _ in range(120): self.assertEqual(middleware(request).status_code, 200)
        self.assertEqual(middleware(request).status_code, 429)
        for req in [factory.post('/accounts/logout/'), factory.get('/health/')]:
            req.user = request.user
            self.assertEqual(middleware(req).status_code, 200)
        self.assertEqual(len(middleware.login), 0)
