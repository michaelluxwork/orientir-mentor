"""Bounded request protection for the isolated curator review deployment."""
from collections import deque
from threading import Lock
from time import monotonic
from django.http import HttpResponse


def context(request):
    return {'curator_review': True}


class ThrottleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.lock = Lock()
        self.login = deque(maxlen=30)
        self.writes = deque(maxlen=120)

    def __call__(self, request):
        bucket = None
        if request.method == 'POST' and request.path == '/accounts/login/':
            bucket = self.login
        elif request.method == 'POST' and request.path != '/accounts/logout/' and request.user.is_authenticated:
            bucket = self.writes
        if bucket is not None:
            with self.lock:
                now = monotonic()
                while bucket and now - bucket[0] >= 60:
                    bucket.popleft()
                if len(bucket) == bucket.maxlen:
                    response = HttpResponse('Слишком много запросов. Повторите через минуту.', status=429)
                    response['Retry-After'] = str(max(1, 61 - int(now - bucket[0])))
                    return response
                bucket.append(now)
        return self.get_response(request)
