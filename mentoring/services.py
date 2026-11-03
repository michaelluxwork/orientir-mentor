import hashlib
import json
from collections import defaultdict
from django.db import transaction
from django.utils import timezone
from .models import Mentee, Goal, Session, Checkin

class Conflict(Exception): pass
class LimitReached(Exception): pass

def digest(data):
    payload = {k: str(v.pk) if hasattr(v, 'pk') else str(v) if v is not None else None for k, v in data.items() if k not in {'version', 'create_nonce'}}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def bump(mentee, version):
    if not Mentee.objects.filter(pk=mentee.pk, owner=mentee.owner, version=version).update(version=version + 1, updated_at=timezone.now()):
        raise Conflict('Запись изменилась в другой вкладке. Ваш текст не сохранён. Обновите данные и повторите правку.')

def current_aggregate(mentee, owner):
    fresh = Mentee.objects.filter(pk=mentee.pk, owner=owner).first()
    if fresh is None: raise Conflict('Подопечный больше недоступен. Изменения не сохранены; вернитесь к списку и проверьте запись.')
    return fresh

def mutate(form, *, owner, aggregate=None):
    model = form._meta.model
    is_new = not form.instance.pk
    nonce = form.cleaned_data.get('create_nonce')
    fingerprint = digest(form.cleaned_data)
    with transaction.atomic():
        if is_new:
            scope = {'owner': owner} if model is Mentee else {'mentee': aggregate}
            previous = model.objects.filter(**scope, create_nonce=nonce).first()
            if previous:
                if previous.create_digest != fingerprint: raise Conflict('Эта отправка уже использована с другим содержимым. Откройте новую форму.')
                return previous, False
            limit = 100 if model is Mentee else 20 if model is Goal else 500
            if model.objects.filter(**scope).count() >= limit: raise LimitReached('Достигнут лимит записей. Сохраните отчёт и удалите ненужное перед добавлением.')
        if aggregate is not None:
            # SQLite IMMEDIATE serializes writers; version guards stale browser forms.
            fresh = current_aggregate(aggregate, owner)
            bump(fresh, form.cleaned_data['version'])
        obj = form.save(commit=False)
        if is_new:
            obj.create_nonce, obj.create_digest = nonce, fingerprint
            if model is Mentee: obj.owner = owner
            else: obj.mentee = aggregate
        if model is Mentee and not is_new:
            obj.version = form.cleaned_data['version'] + 1
        obj.save()
        if model is Session:
            goal, progress = form.cleaned_data.get('goal'), form.cleaned_data.get('progress')
            if goal is not None and goal.mentee_id != aggregate.pk: raise Conflict('Цель не принадлежит этому подопечному.')
            if goal is not None and progress is not None:
                Checkin.objects.update_or_create(session=obj, defaults={'goal': goal, 'progress': progress})
            else:
                Checkin.objects.filter(session=obj).delete()
        return obj, True

def remove(obj, *, mentee, owner, version):
    with transaction.atomic():
        fresh = current_aggregate(mentee, owner)
        bump(fresh, version)
        if isinstance(obj, Mentee): fresh.delete()
        else: obj.delete()

def statistics(mentees, *, end=None, start=None):
    people = list(mentees)
    end = end or timezone.localdate()
    goals = list(Goal.objects.filter(mentee__in=people).order_by('id'))
    grouped = defaultdict(list)
    for g in goals:
        g.score, g.rated_on, g.baseline = None, None, None
        g.history = []
        grouped[g.mentee_id].append(g)
    lookup = {g.pk: g for g in goals}
    points = Checkin.objects.filter(goal__in=goals, session__held_on__lte=end).select_related('session').order_by('session__held_on', 'session_id')
    for point in points:
        g = lookup[point.goal_id]
        g.score, g.rated_on = point.progress, point.session.held_on
        if start and point.session.held_on < start:
            g.baseline = point
        else:
            # Scores are mentor assessments; each point is a recorded observation.
            g.history.append(point)
    result = {}
    for p in people:
        own = grouped[p.pk]
        rated = [g.score for g in own if g.score is not None]
        score = (2 * sum(rated) + len(rated)) // (2 * len(rated)) if rated else None
        result[p.pk] = {'score': score, 'rated_count': len(rated), 'goal_count': len(own), 'goals': own}
    return result
