from dataclasses import dataclass


@dataclass(frozen=True)
class SmsDeliveryResult:
    sent: bool
    error: str | None = None
