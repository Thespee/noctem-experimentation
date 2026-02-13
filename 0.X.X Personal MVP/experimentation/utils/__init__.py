"""Noctem utility modules."""

# Core utilities
try:
    from .cache import cache_get, cache_set, cache_clear, get_cache_key
except ImportError:
    pass

try:
    from .rate_limit import wait_for_rate_limit, get_domain
except ImportError:
    pass

try:
    from .robots import is_allowed, fetch_robots_txt
except ImportError:
    pass

try:
    from .vault import get_vault, get_credential, set_credential, init_vault
except ImportError:
    pass

# Personal MVP utilities
from .birthday import get_upcoming_birthdays, format_birthday_reminder
from .calendar import get_events_for_date, format_todays_events, get_upcoming_events
from .morning_report import generate_morning_report
