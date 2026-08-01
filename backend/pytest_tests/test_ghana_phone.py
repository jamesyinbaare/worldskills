"""Ghana phone MSISDN normalization and validation."""

from __future__ import annotations

import pytest

from app.services.sms.phone import is_valid_ghana_phone, normalize_msisdn


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0241234567", "233241234567"),
        ("+233241234567", "233241234567"),
        ("233241234567", "233241234567"),
        ("241234567", "233241234567"),
        ("+233 24 123 4567", "233241234567"),
        ("0302123456", "233302123456"),
    ],
)
def test_normalize_msisdn_accepts_ghana_forms(raw: str, expected: str) -> None:
    assert normalize_msisdn(raw) == expected
    assert is_valid_ghana_phone(raw) is True


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "123",
        "+15551234567",
        "15551234567",
        "023",
        "+23324",
        "abcdefghij",
    ],
)
def test_normalize_msisdn_rejects_non_ghana(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_msisdn(raw)
    assert is_valid_ghana_phone(raw) is False
