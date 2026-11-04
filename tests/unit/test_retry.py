from app.recovery.retry_manager import RetryManager


def test_is_retryable_timeout():
    rm = RetryManager()
    assert rm.is_retryable(TimeoutError("timeout")) == True


def test_is_retryable_network():
    rm = RetryManager()
    assert rm.is_retryable(Exception("network error")) == True


def test_is_not_retryable_auth():
    rm = RetryManager()
    assert rm.is_retryable(Exception("invalid credentials")) == False


def test_is_not_retryable_bad_request():
    rm = RetryManager()
    assert rm.is_retryable(Exception("bad request")) == False
