import logging
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client
from config import settings

logger = logging.getLogger(__name__)


class TwilioService:
    """Service to handle SMS notifications via Twilio REST API."""

    def __init__(self):
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.from_phone = settings.TWILIO_PHONE_NUMBER
        self.is_configured = bool(self.account_sid and self.auth_token and self.from_phone)

        if self.is_configured:
            self.client = Client(self.account_sid, self.auth_token)
        else:
            self.client = None

    def send_sms(self, to_phone: str, message: str) -> bool:
        """Sends an SMS message to the specified recipient phone number.

        Falls back to console logging when Twilio API credentials are absent.
        """
        if not self.is_configured:
            logger.warning(
                "[TWILIO MOCK MODE] SMS to %s | Body: %s",
                to_phone,
                message,
            )
            return True

        try:
            msg_instance = self.client.messages.create(
                body=message,
                from_=self.from_phone,
                to=to_phone,
            )
            logger.info("Twilio SMS queued successfully. SID: %s", msg_instance.sid)
            return True

        except TwilioRestException as exc:
            logger.error("Twilio API error sending SMS to %s: %s (Code: %s)", to_phone, exc.msg, exc.code)
            return False
        except Exception as exc:
            logger.error("Unexpected error during SMS dispatch to %s: %s", to_phone, str(exc))
            return False
