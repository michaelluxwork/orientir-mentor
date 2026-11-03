import uuid
from django.conf import settings
from django.db import models

class CreatedRecord(models.Model):
    create_nonce = models.UUIDField(default=uuid.uuid4, editable=False)
    create_digest = models.CharField(max_length=64, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

class Mentee(CreatedRecord):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    focus = models.TextField(max_length=1000, blank=True)
    version = models.PositiveIntegerField(default=1)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['owner', 'create_nonce'], name='mentee_owner_nonce')]
        ordering = ['name', 'id']
    def __str__(self): return self.name

class Goal(CreatedRecord):
    mentee = models.ForeignKey(Mentee, related_name='goals', on_delete=models.CASCADE)
    title = models.CharField(max_length=160)
    description = models.TextField(max_length=2000, blank=True)
    target_date = models.DateField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['mentee', 'create_nonce'], name='goal_mentee_nonce')]
        ordering = ['id']
    def __str__(self): return self.title

class Session(CreatedRecord):
    mentee = models.ForeignKey(Mentee, related_name='sessions', on_delete=models.CASCADE)
    held_on = models.DateField()
    topic = models.CharField(max_length=160)
    notes = models.TextField(max_length=5000, blank=True)
    next_steps = models.TextField(max_length=2000, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['mentee', 'create_nonce'], name='session_mentee_nonce')]
        ordering = ['-held_on', '-id']
    def __str__(self): return self.topic

class Checkin(models.Model):
    session = models.OneToOneField(Session, related_name='checkin', on_delete=models.CASCADE)
    goal = models.ForeignKey(Goal, related_name='checkins', on_delete=models.CASCADE)
    progress = models.PositiveSmallIntegerField()
    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(progress__gte=0, progress__lte=100), name='progress_range')]
