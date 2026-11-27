from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.core.config import settings


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def get_business_date(dt: datetime | None = None) -> str:
    moment = dt if dt is not None else now_utc()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    tz = ZoneInfo(settings.business_timezone)
    return moment.astimezone(tz).strftime("%Y-%m-%d")
