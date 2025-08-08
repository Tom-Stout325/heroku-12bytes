from django import template
from datetime import timedelta
import os

register = template.Library()

@register.filter
def duration_display(value):
    if not isinstance(value, timedelta):
        return "0 minutes"

    total_seconds = int(value.total_seconds())
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60

    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


@register.filter
def is_pdf(file_url):
    return str(file_url).lower().endswith('.pdf')



@register.filter
def file_icon(file_url):
    ext = os.path.splitext(file_url)[1].lower()
    return {
        '.pdf':  'fa-solid fa-file-pdf text-danger',
        '.doc':  'fa-solid fa-file-word text-primary',
        '.docx': 'fa-solid fa-file-word text-primary',
        '.xls':  'fa-solid fa-table text-success',
        '.xlsx': 'fa-solid fa-table text-success',
        '.jpg':  'fa-solid fa-image text-info',
        '.jpeg': 'fa-solid fa-file-image text-info',
        '.png':  'fa-regular fa-file-image text-info',
        '.zip':  'fa-solid fa-file-zipper text-warning',
        '.txt':  'fa-regular fa-file-lines text-muted',
    }.get(ext, 'fas fa-file')


@register.filter
def duration(value):
    if not value:
        return "00:00:00"
    try:
        total_seconds = int(value.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}"
    except (AttributeError, ValueError):
        return "00:00:00"


@register.filter(name='add_class')
def add_class(field, css_class):
    return field.as_widget(attrs={"class": css_class})


@register.filter
def file_icon(url):
    ext = os.path.splitext(url.lower())[1]
    if ext == '.pdf':
        return '<span class="badge bg-danger text-white"><i class="bi bi-file-earmark-pdf-fill"></i> PDF</span>'
    elif ext in ['.doc', '.docx']:
        return '<span class="badge bg-primary text-white"><i class="bi bi-file-earmark-word-fill"></i> DOC</span>'
    elif ext in ['.jpg', '.jpeg', '.png']:
        return '<span class="badge bg-info text-dark"><i class="bi bi-image-fill"></i> Image</span>'
    else:
        return '<span class="badge bg-secondary text-white"><i class="bi bi-file-earmark-fill"></i> File</span>'

@register.filter
def is_pdf(url):
    return url.lower().endswith('.pdf')
