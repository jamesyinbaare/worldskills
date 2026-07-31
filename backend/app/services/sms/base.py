from typing import Protocol

from app.services.sms.types import SmsDeliveryResult


class SmsProvider(Protocol):
    async def send_sms(self, msisdn: str, message: str) -> SmsDeliveryResult: ...
