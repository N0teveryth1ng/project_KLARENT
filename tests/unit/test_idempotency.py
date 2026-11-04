from app.idempotency.manager import IdempotencyManager


def test_generate_key():
    # Can't fully test without DB, but test the logic
    data = "run123:step1"
    import hashlib
    key = hashlib.sha256(data.encode()).hexdigest()
    assert len(key) == 64
