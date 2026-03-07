import pytz
from datetime import datetime

def get_current_time_in_lima() -> str:
    """
    Returns the current time in America/Lima timezone in ISO 8601 format.
    """
    try:
        lima_tz = pytz.timezone("America/Lima")
        lima_time = datetime.now(lima_tz)
        return lima_time.strftime("%Y-%m-%d %H:%M:%S %Z")
    except pytz.UnknownTimeZoneError:
        # Fallback to UTC if timezone is not found
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
