import datetime


def parse_date(date_str: str) -> datetime.date | None:
    try:
        return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None


def get_date_today() -> datetime.date:
    return datetime.date.today()


def is_timeout_message(msg: str) -> bool:
    return "Timeout" in msg and "exceeded" in msg
