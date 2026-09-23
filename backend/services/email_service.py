"""Email Dispatch Service using Brevo (Sendinblue) HTTPS API (Port 443).

Bypasses cloud provider (Render) socket blocks on SMTP ports 25, 465, and 587.
Allows sending to any recipient address without custom domain verification.
Falls back cleanly to mock logging if BREVO_API_KEY is not configured.
"""

import json
import os
import re
import urllib.error
import urllib.request
from typing import Optional

try:
    from backend.config import settings
except ImportError:
    try:
        from config import settings
    except ImportError:
        settings = None


class EmailService:
    def __init__(self):
        # Read API key from environment variable or fallback to provided key
        self.api_key: Optional[str] = os.getenv(
            "BREVO_API_KEY",
            ""
        )
        if not self.api_key and settings and hasattr(settings, "BREVO_API_KEY"):
            self.api_key = getattr(settings, "BREVO_API_KEY")

        # Sender email: Must match the account or verified sender in your Brevo console
        self.sender_email: str = os.getenv("SENDER_EMAIL", "pragyan.ai.school@gmail.com")
        self.sender_name: str = os.getenv("SENDER_NAME", "EduPortal Verification")

    def send_email(self, to_email: str, subject: str, content: str) -> bool:
        """Dispatches an email via Brevo v3 HTTPS REST API.

        Args:
            to_email: Target recipient address.
            subject: Subject line.
            content: Raw message text containing the OTP.

        Returns:
            bool: True if accepted by Brevo (HTTP 200, 201, 202), False otherwise.
        """
        clean_email = to_email.strip().lower()

        # Fallback to mock logging if no API key is set
        if not self.api_key or self.api_key.startswith("your_"):
            print("\n================================================")
            print(f"[EMAIL MOCK MODE] Outbound to: {clean_email}")
            print(f"Subject: {subject}")
            print(f"Body:\n{content}")
            print("================================================\n")
            return False

        # Extract 4-8 digit OTP passcode for styled HTML presentation
        otp_match = re.search(r"\b\d{4,8}\b", content)
        otp_display = otp_match.group(0) if otp_match else "------"

        html_body = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 500px; margin: 0 auto; background-color: #0b0f19; color: #f8fafc; padding: 28px; border-radius: 12px; border: 1px solid #222f49;">
            <div style="margin-bottom: 20px;">
                <h2 style="color: #3b82f6; margin: 0; font-size: 20px;">⚡ EduPortal Verification</h2>
                <p style="color: #94a3b8; font-size: 13px; margin: 6px 0 0 0;">Two-Step Student Account Activation</p>
            </div>
            
            <p style="color: #cbd5e1; font-size: 14px; line-height: 1.5;">Hello,</p>
            <p style="color: #cbd5e1; font-size: 14px; line-height: 1.5;">Please use the one-time verification passcode below to complete your registration:</p>
            
            <div style="font-size: 32px; font-weight: 700; letter-spacing: 6px; padding: 18px; background: #151d30; color: #10b981; text-align: center; border-radius: 8px; margin: 24px 0; border: 1px solid #222f49;">
                {otp_display}
            </div>
            
            <p style="color: #94a3b8; font-size: 12px; line-height: 1.5;">
                This code is valid for <strong>5 minutes</strong>. If you did not initiate this request, you can safely ignore this message.
            </p>
            
            <hr style="border: 0; border-top: 1px solid #222f49; margin: 24px 0 16px 0;" />
            <p style="color: #64748b; font-size: 11px; margin: 0;">Automated message from EduPortal Verification Engine.</p>
        </div>
        """

        payload = {
            "sender": {
                "name": self.sender_name,
                "email": self.sender_email
            },
            "to": [
                {"email": clean_email}
            ],
            "subject": subject,
            "htmlContent": html_body,
            "textContent": content
        }

        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "api-key": self.api_key.strip(),
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "EduPortal-Backend/2.0"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=12.0) as response:
                if response.status in (200, 201, 202):
                    res_body = response.read().decode("utf-8")
                    print(f"[✓] Brevo API Success: Dispatched to {clean_email} | Response: {res_body}")
                    return True

        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="ignore")
            print(f"[!] Brevo HTTP API Error ({e.code}) for {clean_email}: {err_msg}")
            return False
        except Exception as e:
            print(f"[!] Unexpected error during email dispatch to {clean_email}: {e}")
            return False

        return False
