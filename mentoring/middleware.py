from django.core.exceptions import DisallowedHost, RequestDataTooBig, TooManyFieldsSent
from django.db import DatabaseError
from django.http import HttpResponse

class BoundaryMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        try:
            request.get_host()
            if request.method == 'POST':
                if request.content_type != 'application/x-www-form-urlencoded': return self.fail(415, 'Поддерживается только обычная форма без файлов.')
                size = int(request.META.get('CONTENT_LENGTH') or 0)
                if size > 32768: return self.fail(413, 'Форма слишком большая. Сократите текст.')
                if any(len(v) != 1 for _, v in request.POST.lists()): return self.fail(400, 'Поля формы не должны повторяться.')
        except DisallowedHost: return self.fail(400, 'Недопустимый адрес приложения.')
        except (ValueError, RequestDataTooBig, TooManyFieldsSent): return self.fail(400, 'Некорректная форма.')
        return self.headers(self.get_response(request))
    @classmethod
    def fail(cls, status, text): return cls.headers(HttpResponse(text, status=status, content_type='text/plain; charset=utf-8'))
    @staticmethod
    def headers(response):
        response['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
        response['Cache-Control'] = 'no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        return response
    def process_exception(self, request, exception):
        if isinstance(exception, DatabaseError):
            return self.fail(503, 'Хранилище временно недоступно. Изменения не подтверждены. Проверьте запись перед повторной отправкой.')
