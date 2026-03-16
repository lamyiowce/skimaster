"""Shared HTTP retry configuration for rate-limited external service calls."""

import httpx
from tenacity import retry_if_exception, retry_if_exception_type, stop_after_attempt, wait_exponential


def is_retryable_http_error(exc: BaseException) -> bool:
    """Return True for HTTP 429 / 5xx errors that are worth retrying."""
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code in (429, 500, 502, 503, 504)
    )


def _log_retry(retry_state) -> None:
    exc = retry_state.outcome.exception()
    print(f"    [retry] attempt {retry_state.attempt_number} failed ({exc!r}) — retrying...")


RETRY_HTTP = dict(
    retry=retry_if_exception(is_retryable_http_error) | retry_if_exception_type(httpx.TransportError),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(3),
    reraise=True,
    before_sleep=_log_retry,
)
