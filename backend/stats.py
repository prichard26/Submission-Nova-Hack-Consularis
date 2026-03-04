"""In-memory usage stats: API calls and token counts (cumulative)."""
import threading

_lock = threading.Lock()
_api_calls: int = 0
_input_tokens: int = 0
_output_tokens: int = 0


def add_usage(api_calls: int = 0, input_tokens: int = 0, output_tokens: int = 0) -> None:
    with _lock:
        global _api_calls, _input_tokens, _output_tokens
        _api_calls += api_calls
        _input_tokens += input_tokens
        _output_tokens += output_tokens


def get_stats() -> dict:
    with _lock:
        return {
            "total_api_calls": _api_calls,
            "total_input_tokens": _input_tokens,
            "total_output_tokens": _output_tokens,
            "total_tokens": _input_tokens + _output_tokens,
        }
