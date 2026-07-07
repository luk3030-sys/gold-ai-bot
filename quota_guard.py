from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from config import env_bool, env_int
from db import (
    api_usage_counts,
    get_provider_state,
    record_api_usage,
    set_provider_state,
)

PROVIDER = "twelvedata"


class QuotaGuardBlocked(RuntimeError):
    """Raised when a live API request is blocked to protect the quota."""


class RateLimitError(RuntimeError):
    """Raised after a provider HTTP 429 response."""


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    reason: str
    minute_used: int
    daily_used: int
    minute_limit: int
    daily_limit: int
    blocked_until: Optional[str] = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _limits() -> tuple[int, int, int, int]:
    minute_limit = max(1, env_int("TD_MINUTE_CREDIT_LIMIT", 8))
    daily_limit = max(1, env_int("TD_DAILY_CREDIT_LIMIT", 800))
    minute_reserve = max(0, env_int("TD_MINUTE_CREDIT_RESERVE", 1))
    daily_reserve = max(0, env_int("TD_DAILY_CREDIT_RESERVE", 80))
    return minute_limit, daily_limit, minute_reserve, daily_reserve


def check_request(credits: int = 1) -> QuotaDecision:
    credits = max(1, int(credits))
    counts = api_usage_counts(PROVIDER)
    minute_limit, daily_limit, minute_reserve, daily_reserve = _limits()
    state = get_provider_state(PROVIDER) or {}
    blocked_until = state.get("blocked_until")

    if blocked_until:
        try:
            blocked_dt = datetime.fromisoformat(str(blocked_until))
            if blocked_dt.tzinfo is None:
                blocked_dt = blocked_dt.replace(tzinfo=timezone.utc)
            if blocked_dt > _now():
                return QuotaDecision(
                    False,
                    state.get("reason") or "circuit_breaker",
                    counts["minute_credits"],
                    counts["daily_credits"],
                    minute_limit,
                    daily_limit,
                    blocked_until,
                )
        except ValueError:
            pass

    minute_cap = max(0, minute_limit - minute_reserve)
    daily_cap = max(0, daily_limit - daily_reserve)
    if counts["minute_credits"] + credits > minute_cap:
        return QuotaDecision(
            False,
            "minute_quota_guard",
            counts["minute_credits"],
            counts["daily_credits"],
            minute_limit,
            daily_limit,
        )
    if counts["daily_credits"] + credits > daily_cap:
        return QuotaDecision(
            False,
            "daily_quota_guard",
            counts["minute_credits"],
            counts["daily_credits"],
            minute_limit,
            daily_limit,
        )
    return QuotaDecision(
        True,
        "allowed",
        counts["minute_credits"],
        counts["daily_credits"],
        minute_limit,
        daily_limit,
    )


def record_request(
    *,
    endpoint: str,
    symbol: str,
    interval: str,
    status: str,
    credits: int = 1,
    detail: str = "",
) -> None:
    record_api_usage(
        provider=PROVIDER,
        endpoint=endpoint,
        symbol=symbol,
        interval=interval,
        credits=max(0, int(credits)),
        status=status,
        detail=detail[:1000],
    )


def on_success() -> None:
    state = get_provider_state(PROVIDER) or {}
    if state.get("consecutive_429", 0) or state.get("blocked_until"):
        set_provider_state(
            PROVIDER,
            blocked_until=None,
            reason="healthy",
            consecutive_429=0,
        )


def on_429(detail: str = "") -> Dict[str, Any]:
    state = get_provider_state(PROVIDER) or {}
    consecutive = int(state.get("consecutive_429") or 0) + 1
    base = max(30, env_int("TD_429_BASE_COOLDOWN_SECONDS", 65))
    max_seconds = max(base, env_int("TD_429_MAX_COOLDOWN_SECONDS", 1800))
    cooldown = min(max_seconds, base * (2 ** min(consecutive - 1, 5)))
    blocked_until = (_now() + timedelta(seconds=cooldown)).isoformat()
    set_provider_state(
        PROVIDER,
        blocked_until=blocked_until,
        reason=f"http_429:{detail[:200]}",
        consecutive_429=consecutive,
    )
    return {
        "consecutive_429": consecutive,
        "cooldown_seconds": cooldown,
        "blocked_until": blocked_until,
    }


def quota_status() -> Dict[str, Any]:
    counts = api_usage_counts(PROVIDER)
    state = get_provider_state(PROVIDER) or {}
    minute_limit, daily_limit, minute_reserve, daily_reserve = _limits()
    return {
        "provider": PROVIDER,
        "enabled": env_bool("QUOTA_GUARD_ENABLED", True),
        "minute": {
            "used": counts["minute_credits"],
            "limit": minute_limit,
            "reserve": minute_reserve,
            "available_before_reserve": max(0, minute_limit - minute_reserve - counts["minute_credits"]),
        },
        "daily": {
            "used": counts["daily_credits"],
            "limit": daily_limit,
            "reserve": daily_reserve,
            "available_before_reserve": max(0, daily_limit - daily_reserve - counts["daily_credits"]),
        },
        "requests": {
            "last_minute": counts["minute_requests"],
            "today_utc": counts["daily_requests"],
            "http_429_today": counts["daily_429"],
        },
        "circuit_breaker": {
            "blocked_until": state.get("blocked_until"),
            "reason": state.get("reason"),
            "consecutive_429": int(state.get("consecutive_429") or 0),
        },
    }
