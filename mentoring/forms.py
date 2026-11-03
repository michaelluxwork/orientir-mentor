import uuid
from django import forms
from django.utils import timezone
from .models import Mentee, Goal, Session

class MutationForm(forms.ModelForm):
    version = forms.IntegerField(min_value=1, max_value=2147483646, widget=forms.HiddenInput, required=False)
    create_nonce = forms.UUIDField(widget=forms.HiddenInput, required=False)
    def __init__(self, *args, aggregate=None, **kwargs):
        super().__init__(*args, **kwargs)
        if aggregate is not None:
            self.fields['version'].required = True
            self.initial['version'] = aggregate.version
        if not self.instance.pk:
            self.fields['create_nonce'].required = True
            self.initial['create_nonce'] = uuid.uuid4()
    def clean(self):
        data = super().clean()
        extra = set(self.data) - set(self.fields) - {'csrfmiddlewaretoken'}
        if extra: self.add_error(None, 'Форма содержит неизвестные поля. Обновите страницу и повторите.')
        return data

class MenteeForm(MutationForm):
    class Meta:
        model = Mentee
        fields = ['name', 'focus']
        labels = {'name': 'Имя подопечного', 'focus': 'Фокус работы'}
        widgets = {'focus': forms.Textarea(attrs={'rows': 4})}

class GoalForm(MutationForm):
    class Meta:
        model = Goal
        fields = ['title', 'description', 'target_date']
        labels = {'title': 'Согласованная цель', 'description': 'Критерий результата', 'target_date': 'Целевой срок'}
        widgets = {'description': forms.Textarea(attrs={'rows': 4}), 'target_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'min': '1900-01-01', 'max': '2199-12-31'})}
    def clean_target_date(self):
        value = self.cleaned_data.get('target_date')
        if value and not 1900 <= value.year <= 2199: raise forms.ValidationError('Укажите дату между1900 и2199 годом.')
        return value

class OwnedGoalChoice(forms.ModelChoiceField):
    def to_python(self, value):
        if value not in self.empty_values:
            text = str(value)
            if len(text) > 19 or not text.isascii() or not text.isdigit() or not 0 < int(text) <= 9223372036854775807:
                raise forms.ValidationError('Выберите доступную цель этого подопечного.')
        return super().to_python(value)

class SessionForm(MutationForm):
    goal = OwnedGoalChoice(queryset=Goal.objects.none(), required=False, label='Цель для оценки', empty_label='Без оценки цели')
    progress = forms.IntegerField(min_value=0, max_value=100, required=False, label='Оценка прогресса, 0–100%', help_text='Если на этой встрече цель не оценивали, оставьте оба поля пустыми. Ноль — оценка наставника, а не отсутствие данных.')
    class Meta:
        model = Session
        fields = ['held_on', 'topic', 'notes', 'next_steps']
        labels = {'held_on': 'Дата встречи', 'topic': 'Тема встречи', 'notes': 'Заметки', 'next_steps': 'Следующие шаги'}
        widgets = {'held_on': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'min': '1900-01-01'}), 'notes': forms.Textarea(attrs={'rows': 5}), 'next_steps': forms.Textarea(attrs={'rows': 3})}
    def __init__(self, *args, aggregate, **kwargs):
        super().__init__(*args, aggregate=aggregate, **kwargs)
        self.fields['goal'].queryset = aggregate.goals.all()
        self.fields['held_on'].widget.attrs['max'] = timezone.localdate().isoformat()
        if self.instance.pk:
            checkin = getattr(self.instance, 'checkin', None)
            if checkin: self.initial.update(goal=checkin.goal_id, progress=checkin.progress)
        else: self.initial['held_on'] = timezone.localdate()
    def clean_held_on(self):
        value = self.cleaned_data['held_on']
        if value.year < 1900 or value > timezone.localdate(): raise forms.ValidationError('Дата состоявшейся встречи должна быть между01.01.1900 и сегодняшним днём.')
        return value
    def clean(self):
        data = super().clean()
        goal, progress = data.get('goal'), data.get('progress')
        if bool(goal) != (progress is not None): self.add_error(None, 'Для оценки выберите цель и укажите число0–100. Или оставьте оба поля пустыми.')
        return data

class DeleteForm(forms.Form):
    version = forms.IntegerField(min_value=1, max_value=2147483646, widget=forms.HiddenInput)
    confirm = forms.BooleanField(label='Подтверждаю удаление этой записи и связанных данных')

class ReportForm(forms.Form):
    start = forms.DateField(required=False, label='С даты', widget=forms.DateInput(attrs={'type': 'date', 'min': '1900-01-01', 'max': '2199-12-31'}))
    end = forms.DateField(required=False, label='По дату', widget=forms.DateInput(attrs={'type': 'date', 'min': '1900-01-01', 'max': '2199-12-31'}))
    def clean(self):
        data = super().clean()
        a, b = data.get('start'), data.get('end')
        for d in (a, b):
            if d and not 1900 <= d.year <= 2199: self.add_error(None, 'Укажите дату между1900 и2199 годом.')
        if a and b and a > b: self.add_error(None, 'Начало периода должно быть не позже конца.')
        return data
