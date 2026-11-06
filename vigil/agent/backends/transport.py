"""Identical bounded transport retries for all public provider formats."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from vigil.agent.backends.base import ModelBackendConfig, safe_error_detail


def request_json(request: urllib.request.Request, config: ModelBackendConfig) -> tuple[dict, int]:
    for attempt in range(config.request_max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=config.timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise RuntimeError("Model response must be a JSON object.")
            return payload, attempt + 1
        except urllib.error.HTTPError as exc:
            detail = safe_error_detail(exc.read().decode("utf-8", errors="replace"), config.api_key)
            retryable = exc.code in {429, 500, 502, 503, 504}
            error = f"Model request failed: HTTP {exc.code}: {detail}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            retryable = True
            error = f"Model request failed: {safe_error_detail(exc, config.api_key)}"
        except (ValueError, UnicodeError):
            raise RuntimeError("Model request failed: response is not valid JSON.") from None
        if not retryable or attempt == config.request_max_retries:
            raise RuntimeError(error) from None
        time.sleep(config.request_retry_delay_s)
    raise AssertionError("Unreachable request loop")
