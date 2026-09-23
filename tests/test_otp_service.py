import time
from backend.services.otp_service import OTPService


def test_otp_generation_format():
    """Verify that generated OTPs are 6-digit numeric strings."""
    service = OTPService(expiry_seconds=300)
    otp = service.generate_otp("+919999988888")

    assert isinstance(otp, str)
    assert len(otp) == 6
    assert otp.isdigit()


def test_otp_successful_verification():
    """Verify that the correct OTP succeeds and is purged after use."""
    service = OTPService(expiry_seconds=300)
    identifier = "student@example.com"
    otp = service.generate_otp(identifier)

    # First attempt with valid OTP should pass
    assert service.verify_otp(identifier, otp) is True

    # Replay attempt with same OTP must fail (single-use protection)
    assert service.verify_otp(identifier, otp) is False


def test_otp_invalid_code_rejection():
    """Verify that an incorrect OTP is rejected without deleting the active OTP."""
    service = OTPService(expiry_seconds=300)
    identifier = "+919876543210"
    otp = service.generate_otp(identifier)

    # Wrong candidate code
    assert service.verify_otp(identifier, "000000" if otp != "000000" else "111111") is False

    # Stored OTP should still be redeemable with the correct value
    assert service.verify_otp(identifier, otp) is True


def test_otp_expiration():
    """Verify that OTP expires and fails after the configured TTL."""
    # Short TTL for testing: 1 second
    service = OTPService(expiry_seconds=1)
    identifier = "expires@example.com"
    otp = service.generate_otp(identifier)

    # Sleep past the expiration limit
    time.sleep(1.2)

    assert service.verify_otp(identifier, otp) is False


def test_otp_clear_expired_housekeeping():
    """Verify that clear_expired removes stale keys and retains active ones."""
    service = OTPService(expiry_seconds=1)
    service.generate_otp("stale1@example.com")
    service.generate_otp("stale2@example.com")

    # Wait for expiry
    time.sleep(1.1)

    # Add a fresh entry
    fresh_service = OTPService(expiry_seconds=300)
    service.expiry_seconds = 300
    service.generate_otp("fresh@example.com")

    # 2 stale records should be purged
    cleared_count = service.clear_expired()
    assert cleared_count == 2
    assert "fresh@example.com" in service._store
