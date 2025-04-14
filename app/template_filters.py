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