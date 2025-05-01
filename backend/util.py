import time
from typing import Any
import datetime

def print_err(message: Any):
    red = "\033[91m"
    reset = "\033[0m"
    print(f"{red}❌ {message}{reset}")

def print_warn(message: Any):
    yellow = "\033[93m"
    reset = "\033[0m"
    print(f"{yellow}⚠️  {message}{reset}")

def print_ok(message: Any):
    green = "\033[92m"
    reset = "\033[0m"
    print(f"{green}✅ {message}{reset}")

def timing_decorator(func):
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        result = await func(*args, **kwargs)
        end_time = time.time()
        print(f"Function {func.__name__} took {end_time - start_time:.4f} seconds")
        return result

    return wrapper


def parse_date(date_str: str) -> datetime.date | None:
    try:
        return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except:
        return None


def get_date_today() -> datetime.date:
    return datetime.date.today()

def get_date_a_month_ago() -> datetime.date:
    return datetime.date.today() - datetime.timedelta(days=30)

def is_timeout_message(msg: str) -> bool:
    return "Timeout" in msg and "exceeded" in msg