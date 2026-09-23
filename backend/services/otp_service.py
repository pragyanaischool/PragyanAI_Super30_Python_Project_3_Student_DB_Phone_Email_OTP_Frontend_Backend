import secrets
import time
from typing import Dict, Optional, Tuple


class OTPService:
    """Generates, tracks, and verifies time-limited One-Time Passwords."""

    def __init__(self, expiry_seconds: int = 300):
        self.expiry_seconds = expiry_seconds
        # In-memory storage: {identifier: (otp_code, expires_at_timestamp)}
        self._store: Dict[str, Tuple[str, float]] = {}

    def generate_otp(self, identifier: str) -> str:
        """Generates a secure 6-digit OTP and associates it with the identifier."""
        # Cryptographically secure random 6-digit numeric string (000000 - 999999)
        otp = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = time.time() + self.expiry_seconds
        self._store[identifier] = (otp, expires_at)
        return otp

    def verify_otp(self, identifier: str, candidate_otp: str) -> bool:
        """Verifies candidate OTP using constant-time comparison.

        If valid or expired, removes the OTP to prevent replay attacks.
        """
        record: Optional[Tuple[str, float]] = self._store.get(identifier)
        if not record:
            return False

        stored_otp, expires_at = record

        # Check expiration
        if time.time() > expires_at:
            del self._store[identifier]
            return False

        # Constant-time comparison mitigates side-channel timing attacks
        if secrets.compare_digest(stored_otp, candidate_otp):
            del self._store[identifier]
            return True

        return False

    def clear_expired(self) -> int:
        """Housekeeping helper to remove expired records."""
        now = time.time()
        expired_keys = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired_keys:
            del self._store[k]
        return len(expired_keys)
