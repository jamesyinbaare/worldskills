from app.config import settings
from app.services.sms.base import SmsProvider
from app.services.sms.nalo import nalo_provider_from_settings
from app.services.sms.noop import NoopSmsProvider


def get_sms_provider() -> SmsProvider:
    if not settings.sms_enabled:
        return NoopSmsProvider()
    if not settings.nalo_sms_key.strip():
        return NoopSmsProvider()
    return nalo_provider_from_settings()
