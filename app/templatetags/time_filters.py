from django import template

register = template.Library()

@register.filter
def seconds_to_hms(value):
    try:
        value = int(value)
        hours = value // 3600
        minutes = (value % 3600) // 60
        seconds = value % 60
        return f"{hours}h {minutes}m {seconds}s"
    except (ValueError, TypeError):
        return "0h 0m 0s"
