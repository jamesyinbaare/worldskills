from app.services.sms.types import SmsDeliveryResult


class NoopSmsProvider:
    """Used when SMS is disabled or not configured — pretends success for local/dev."""

    async def send_sms(self, msisdn: str, message: str) -> SmsDeliveryResult:
        _ = (msisdn, message)
        return SmsDeliveryResult(sent=True)
