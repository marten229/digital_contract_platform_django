from django import template

register = template.Library()

@register.filter
def wei_to_eth(wei_value):
    """Konvertiert Wei zu ETH für die Anzeige"""
    if wei_value is None:
        return None
    try:
        return float(wei_value) / (10**18)
    except (ValueError, TypeError):
        return None

@register.filter
def format_eth(wei_value):
    """Formatiert Wei-Wert als ETH-String"""
    eth_value = wei_to_eth(wei_value)
    if eth_value is None:
        return ""
    return f"{eth_value:.6f}"
