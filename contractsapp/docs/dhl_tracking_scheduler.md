# DHL Tracking Scheduler Configuration

This document provides instructions for setting up automatic DHL tracking updates for the Digital Contract Platform.

## Option 1: Using Cron (Linux/macOS)

Add the following line to your crontab (`crontab -e`):

```
# Run tracking updates every 30 minutes
*/30 * * * * cd /path/to/digital_contract_platform && python contractsapp/scripts/update_tracking.py
```

## Option 2: Using Windows Task Scheduler

1. Open Task Scheduler
2. Create a new Basic Task
   - Name: "DHL Tracking Update"
   - Description: "Updates DHL tracking status for contracts"
3. Trigger: Daily, recur every 1 day, repeat task every 30 minutes for 24 hours
4. Action: Start a program
   - Program/script: `python`
   - Arguments: `C:\path\to\digital_contract_platform\contractsapp\scripts\update_tracking.py`
   - Start in: `C:\path\to\digital_contract_platform\`

## Option 3: Using Celery (Recommended for production)

1. Install Celery: `pip install celery`

2. Create `contractsapp/tasks.py`:
```python
from celery import shared_task
from .scripts.update_tracking import update_all_tracking

@shared_task
def update_dhl_tracking():
    """Celery task to update DHL tracking information"""
    return update_all_tracking()
```

3. Configure Celery in `digital_contract_platform/celery.py`:
```python
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'digital_contract_platform.settings')

app = Celery('digital_contract_platform')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Configure periodic tasks
app.conf.beat_schedule = {
    'update-dhl-tracking-every-30-minutes': {
        'task': 'contractsapp.tasks.update_dhl_tracking',
        'schedule': 30 * 60,  # 30 minutes in seconds
    },
}
```

4. Update `digital_contract_platform/__init__.py`:
```python
from .celery import app as celery_app

__all__ = ('celery_app',)
```

5. Run Celery worker: `celery -A digital_contract_platform worker -l info`
6. Run Celery beat: `celery -A digital_contract_platform beat -l info`
