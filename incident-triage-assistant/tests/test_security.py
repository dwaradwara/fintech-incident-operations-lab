from app.redaction import redact_text


def test_secret_and_pii_redaction():
    text = (
        "api_key=super-secret-value "
        "password=hunter123 "
        "user=test@example.com "
        "token=abc123xyz"
    )

    cleaned, count = redact_text(text)

    assert "super-secret-value" not in cleaned
    assert "hunter123" not in cleaned
    assert "test@example.com" not in cleaned
    assert "abc123xyz" not in cleaned
    assert "[REDACTED]" in cleaned
    assert count >= 4
