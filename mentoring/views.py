from datetime import date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import DatabaseError, connection
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods
from django.core.paginator import Paginator
from .forms import MenteeForm, GoalForm, SessionForm, DeleteForm, ReportForm
from .models import Mentee, Goal, Session
from .services import Conflict, LimitReached, mutate, remove, statistics

def pk_ok(pk):
    if not 0 < pk <= 9223372036854775807: raise Http404
    return pk

def owned(request, pk):
    return get_object_or_404(Mentee, pk=pk_ok(pk), owner=request.user)

def child(mentee, model, pk):
    return get_object_or_404(model, pk=pk_ok(pk), mentee=mentee)

class MentorLoginView(LoginView):
    template_name = 'login.html'
    redirect_authenticated_user = True

@require_GET
def health(request):
    try:
        with connection.cursor() as cursor: cursor.execute('SELECT 1 FROM mentoring_mentee LIMIT 1')
        return JsonResponse({'status': 'ok'})
    except DatabaseError: return JsonResponse({'status': 'unavailable'}, status=503)

@login_required
@require_GET
def dashboard(request):
    all_people = Mentee.objects.filter(owner=request.user).annotate(goal_total=Count('goals', distinct=True), session_total=Count('sessions', distinct=True))
    people = list(all_people[:12])
    stats = statistics(people)
    for p in people: p.stats = stats[p.pk]
    recent = Session.objects.filter(mentee__owner=request.user).select_related('mentee')[:5]
    return render(request, 'dashboard.html', {'people': people, 'people_total': all_people.count(), 'goals_total': Goal.objects.filter(mentee__owner=request.user).count(), 'session_total': Session.objects.filter(mentee__owner=request.user).count(), 'recent_sessions': recent, 'next_steps_sessions': [s for s in recent if s.next_steps.strip()], 'active': 'dashboard'})

@login_required
@require_GET
def mentee_list(request):
    q = request.GET.get('q', '').strip()
    if len(q) > 100: return error(request, 400, 'Поисковый запрос слишком длинный.')
    query = Mentee.objects.filter(owner=request.user)
    if q: query = query.filter(Q(name__icontains=q) | Q(focus__icontains=q))
    page = Paginator(query, 20).get_page(request.GET.get('page'))
    stats = statistics(page.object_list)
    for p in page.object_list: p.stats = stats[p.pk]
    return render(request, 'mentees.html', {'page': page, 'q': q, 'active': 'mentees'})

@login_required
@require_GET
def mentee_detail(request, pk):
    p = owned(request, pk)
    stats = statistics([p])[p.pk]
    sessions = Paginator(p.sessions.select_related('checkin__goal'), 20).get_page(request.GET.get('page'))
    return render(request, 'detail.html', {'mentee': p, 'stats': stats, 'sessions': sessions, 'active': 'mentees'})

@login_required
@require_http_methods(['GET', 'POST'])
def edit_record(request, kind, pk=None, record_id=None):
    p = owned(request, pk) if pk is not None else None
    model, form_class = {'mentee': (Mentee, MenteeForm), 'goal': (Goal, GoalForm), 'session': (Session, SessionForm)}[kind]
    obj = p if kind == 'mentee' and p is not None else child(p, model, record_id) if record_id is not None else None
    aggregate = p
    kwargs = {'instance': obj}
    if aggregate is not None: kwargs['aggregate'] = aggregate
    form = form_class(request.POST if request.method == 'POST' else None, **kwargs)
    status = 200
    if request.method == 'POST':
        if form.is_valid():
            try:
                saved, created = mutate(form, owner=request.user, aggregate=aggregate)
                messages.success(request, 'Изменения сохранены.' if obj else 'Запись сохранена.' if created else 'Эта запись уже была сохранена; дубликат не создан.')
                return redirect('mentee-detail', pk=saved.pk if kind == 'mentee' else p.pk)
            except Conflict as exc:
                form.add_error(None, str(exc)); status = 409
            except LimitReached as exc:
                form.add_error(None, str(exc)); status = 400
            except DatabaseError:
                form.add_error(None, 'Не удалось сохранить. Текст формы остался на странице. Проверьте текущую запись перед повтором.'); status = 503
        else: status = 400
    title = {('mentee', False): 'Новый подопечный', ('mentee', True): 'Изменить подопечного', ('goal', False): 'Новая цель', ('goal', True): 'Изменить цель', ('session', False): 'Записать встречу', ('session', True): 'Изменить встречу'}[(kind, bool(obj))]
    return render(request, 'form.html', {'form': form, 'title': title, 'mentee': p, 'record': obj, 'kind': kind, 'unsaved': status != 200, 'active': 'mentees'}, status=status)

@login_required
@require_http_methods(['GET', 'POST'])
def delete_record(request, kind, pk, record_id=None):
    p = owned(request, pk)
    model = {'mentee': Mentee, 'goal': Goal, 'session': Session}[kind]
    obj = p if kind == 'mentee' else child(p, model, record_id)
    form = DeleteForm(request.POST if request.method == 'POST' else None, initial={'version': p.version})
    status = 200
    if request.method == 'POST':
        if form.is_valid():
            try:
                remove(obj, mentee=p, owner=request.user, version=form.cleaned_data['version'])
                messages.success(request, 'Запись удалена.')
                return redirect('mentee-list') if kind == 'mentee' else redirect('mentee-detail', pk=p.pk)
            except Conflict as exc: form.add_error(None, str(exc)); status = 409
            except DatabaseError: form.add_error(None, 'Удаление не подтверждено. Проверьте текущую запись перед повтором.'); status = 503
        else: status = 400
    counts = {'goals': p.goals.count(), 'sessions': p.sessions.count()} if kind == 'mentee' else None
    return render(request, 'delete.html', {'form': form, 'mentee': p, 'record': obj, 'kind': kind, 'counts': counts, 'active': 'mentees'}, status=status)

@login_required
@require_GET
def report(request, pk):
    p = owned(request, pk)
    data = {'start': request.GET.get('from', ''), 'end': request.GET.get('to', '')}
    form = ReportForm(data)
    if not form.is_valid(): return render(request, 'report.html', {'form': form, 'mentee': p, 'invalid': True, 'active': 'mentees'}, status=400)
    start, end = form.cleaned_data['start'], form.cleaned_data['end'] or timezone.localdate()
    stats = statistics([p], start=start, end=end)[p.pk]
    sessions = p.sessions.filter(held_on__lte=end).select_related('checkin__goal')
    if start: sessions = sessions.filter(held_on__gte=start)
    return render(request, 'report.html', {'form': form, 'mentee': p, 'stats': stats, 'report_sessions': sessions, 'start': start, 'end': end, 'generated': timezone.localdate(), 'active': 'mentees'})

def error(request, status, message): return render(request, 'error.html', {'code': status, 'error_message': message}, status=status)
def csrf_failure(request, reason=''): return error(request, 403, 'Форма устарела или источник запроса не подтверждён. Обновите страницу и повторите.')
def not_found(request, exception): return error(request, 404, 'Запись не найдена или недоступна этому наставнику.')
def server_error(request): return error(request, 500, 'Не удалось открыть страницу. Повторите позже; сохранённые записи не сбрасывались.')
