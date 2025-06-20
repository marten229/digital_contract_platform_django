"""
Digital Contract Platform Oracle Service

Ein eigenständiger Oracle-Dienst für die automatische Bestätigung von DHL-Lieferungen
auf der Blockchain für die Digital Contract Platform.

Dieser Service läuft unabhängig von der Hauptanwendung und kommuniziert über:
- Datenbankabfragen für Contract-Informationen
- DHL API für Tracking-Status
- Ethereum Blockchain für Oracle-Bestätigungen
"""

__version__ = "1.0.0"
__author__ = "Digital Contract Platform Team"
