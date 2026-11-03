import os
import signal
from waitress import serve
from config.wsgi import application
from django.conf import settings

if __name__ == '__main__':
    def stop(signum, frame): raise KeyboardInterrupt
    for name in ['SIGINT', 'SIGTERM', 'SIGBREAK']:
        if hasattr(signal, name): signal.signal(getattr(signal, name), stop)
    if settings.PUBLIC_DEMO and not (settings.STATE_DIR / 'mentor.sqlite3').is_file():
        raise RuntimeError('Established review database is missing; restore it before startup')
    options = {'url_scheme': 'https', 'trusted_proxy': None, 'connection_limit': 32, 'channel_timeout': 30} if settings.PUBLIC_DEMO else {}
    serve(application, host='127.0.0.1', port=4365 if settings.PUBLIC_DEMO else int(os.environ.get('MENTOR_PORT', '4365')), threads=2 if settings.PUBLIC_DEMO else 4, max_request_body_size=32768, max_request_header_size=16384, expose_tracebacks=False, clear_untrusted_proxy_headers=True, **options)
