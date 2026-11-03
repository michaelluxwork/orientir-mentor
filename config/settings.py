import os
import secrets
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
PROFILE = os.environ.get('MENTOR_PROFILE', 'local')
if PROFILE not in ('local', 'vps-demo'):
    raise ImproperlyConfigured('Unknown deployment profile')
PUBLIC_DEMO = PROFILE == 'vps-demo'
STATE_DIR = Path(os.environ.get('MENTOR_STATE_DIR', BASE_DIR / '.state')).resolve()
if any(p.name == 'эталон' for p in [STATE_DIR, *STATE_DIR.parents]):
    raise ImproperlyConfigured('Read-only reference directory cannot hold runtime state')
if PUBLIC_DEMO:
    SECRET_KEY = os.environ.get('MENTOR_SECRET_KEY', '')
    PUBLIC_HOST = os.environ.get('MENTOR_PUBLIC_HOST', '')
    if len(SECRET_KEY) < 50 or PUBLIC_HOST != 'orientir.178-255-126-110.sslip.io':
        raise ImproperlyConfigured('Invalid public deployment configuration')
    if not os.environ.get('MENTOR_STATE_DIR') or STATE_DIR == BASE_DIR / '.state' or STATE_DIR == BASE_DIR or BASE_DIR in STATE_DIR.parents or STATE_DIR in BASE_DIR.parents:
        raise ImproperlyConfigured('Public state must be outside the release')
STATE_DIR.mkdir(parents=True, exist_ok=True)
key_file = STATE_DIR / 'secret.key'
if not PUBLIC_DEMO:
    try:
        with key_file.open('x', encoding='ascii') as stream:
            stream.write(secrets.token_urlsafe(64))
    except FileExistsError:
        pass
    SECRET_KEY = key_file.read_text(encoding='ascii').strip()
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured('Invalid local secret; preserve it and recover manually')
DEBUG = False
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
if PUBLIC_DEMO:
    ALLOWED_HOSTS = [PUBLIC_HOST]
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'mentoring']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'mentoring.middleware.BoundaryMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': STATE_DIR / 'mentor.sqlite3', 'TEST': {'NAME': STATE_DIR / 'tests.sqlite3'}, 'OPTIONS': {'timeout': 5, 'transaction_mode': 'IMMEDIATE'}}}
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'}, {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}}, {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'}, {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE = 'ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
WHITENOISE_AUTOREFRESH = True
WHITENOISE_USE_FINDERS = True
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = LOGIN_URL
SESSION_COOKIE_NAME = 'orientir_session'
CSRF_COOKIE_NAME = 'orientir_csrf'
SESSION_COOKIE_AGE = 12 * 60 * 60
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
DATA_UPLOAD_MAX_MEMORY_SIZE = 32768
DATA_UPLOAD_MAX_NUMBER_FIELDS = 30
CSRF_FAILURE_VIEW = 'mentoring.views.csrf_failure'
LOGGING = {'version': 1, 'disable_existing_loggers': False, 'handlers': {'null': {'class': 'logging.NullHandler'}}, 'loggers': {'django.request': {'handlers': ['null'], 'propagate': False}, 'django.security': {'handlers': ['null'], 'propagate': False}}}
if PUBLIC_DEMO:
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT = True
    CSRF_TRUSTED_ORIGINS = ['https://' + PUBLIC_HOST]
    SECURE_PROXY_SSL_HEADER = None
    USE_X_FORWARDED_HOST = False
    WHITENOISE_AUTOREFRESH = WHITENOISE_USE_FINDERS = False
    MIDDLEWARE.insert(MIDDLEWARE.index('django.contrib.auth.middleware.AuthenticationMiddleware') + 1, 'mentoring.public_demo.ThrottleMiddleware')
    TEMPLATES[0]['OPTIONS']['context_processors'].append('mentoring.public_demo.context')
    LOGGING['loggers']['waitress'] = {'handlers': ['null'], 'propagate': False}
