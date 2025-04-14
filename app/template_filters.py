from datetime import datetime

def state_to_bootstrap_class(state):
    """Convert workflow state to Bootstrap background class"""
    state_map = {
        'COMPLETE': 'success',
        'QUEUED': 'secondary',
        'INITIALIZING': 'info',
        'RUNNING': 'primary',
        'PAUSED': 'warning',
        'EXECUTOR_ERROR': 'danger',
        'SYSTEM_ERROR': 'danger',
        'CANCELED': 'dark',
        'CANCELING': 'warning'
    }
    return state_map.get(state, 'secondary')

def format_datetime(value):
    """Format datetime to YYYY-MM-DD HH:MM:SS"""
    if not value:
        return 'N/A'
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return value
    return value.strftime('%Y-%m-%d %H:%M:%S')