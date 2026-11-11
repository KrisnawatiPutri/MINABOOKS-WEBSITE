from decimal import Decimal, InvalidOperation
from django import template

register = template.Library()

@register.filter
def rupiah(value):
    try:
        amount = Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        return str(value)
    # Currency has two decimals internally. Display whole rupiah unless fractional.
    if amount == amount.to_integral_value():
        body = f'{abs(amount):,.0f}'.replace(',', '.')
    else:
        body = f'{abs(amount):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'{"−" if amount < 0 else ""}Rp {body}'

@register.filter
def number_id(value):
    try:
        amount = Decimal(str(value or 0))
        return f'{amount:,.3f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    except (InvalidOperation, ValueError):
        return str(value)
