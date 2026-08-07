from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    if not dictionary:
        return 0
    return dictionary.get(key, 0)
