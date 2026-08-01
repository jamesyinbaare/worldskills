"""Nalo Solutions SMS API."""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.services.sms.types import SmsDeliveryResult

logger = logging.getLogger(__name__)

_NALO_TIMEOUT = httpx.Timeout(30.0)


class NaloSmsProvider:
    def __init__(
        self,
        *,
        api_key: str,
        sender_id: str,
        url: str,
    ) -> None:
        self._api_key = api_key
        self._sender_id = sender_id
        self._url = url

    async def send_sms(self, msisdn: str, message: str) -> SmsDeliveryResult:
        payload = {
            "key": self._api_key,
            "msisdn": msisdn,
            "message": message,
            "sender_id": self._sender_id,
        }
        try:
            async with httpx.AsyncClient(timeout=_NALO_TIMEOUT) as client:
                response = await client.post(self._url, json=payload)
        except httpx.HTTPError as exc:
            logger.warning("Nalo SMS request failed: %s", exc)
            return SmsDeliveryResult(sent=False, error=str(exc))

        body_text = (response.text or "").strip()
        if response.is_success:
            if body_text and _looks_like_error_body(body_text):
                logger.warning("Nalo SMS unexpected body on %s: %s", response.status_code, body_text[:200])
                return SmsDeliveryResult(sent=False, error=body_text)
            return SmsDeliveryResult(sent=True)

        logger.warning("Nalo SMS HTTP %s: %s", response.status_code, body_text[:200])
        return SmsDeliveryResult(
            sent=False,
            error=body_text or f"HTTP {response.status_code}",
        )


def _looks_like_error_body(text: str) -> bool:
    lowered = text.lower()
    if "invalid" in lowered or "error" in lowered or "fail" in lowered:
        return True
    if text.startswith("17") and ":" in text:
        return True
    return False


def nalo_provider_from_settings() -> NaloSmsProvider:
    return NaloSmsProvider(
        api_key=settings.nalo_sms_key,
        sender_id=settings.nalo_sms_sender_id,
        url=settings.nalo_sms_url,
    )
