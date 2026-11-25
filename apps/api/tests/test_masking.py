"""scrub_secrets must mask PAN-like digit runs however the user typed them: contiguous,
spaced, dotted or dashed — while leaving timestamps, UUIDs, phone numbers and amounts alone."""

from api.domain.masking import mask_pan, scrub_secrets


def test_contiguous_pan_masked() -> None:
    out = scrub_secrets("ma carte 4111111111111111 a été débitée")
    assert "4111111111111111" not in out
    assert "****" in out


def test_spaced_pan_masked() -> None:
    out = scrub_secrets("ma carte 4970 1010 2020 3030 ne passe pas")
    assert "4970 1010 2020 3030" not in out
    assert "****" in out


def test_dashed_pan_masked() -> None:
    out = scrub_secrets("PAN 4970-1010-2020-3030 svp")
    assert "4970-1010-2020-3030" not in out
    assert "****" in out


def test_dotted_pan_masked() -> None:
    out = scrub_secrets("PAN 4970.1010.2020.3030 svp")
    assert "4970.1010.2020.3030" not in out


def test_mixed_contiguous_and_grouped_masked() -> None:
    out = scrub_secrets("4970101020 203030 ici")
    assert "4970101020 203030" not in out


def test_13_digit_boundary_masked() -> None:
    out = scrub_secrets("run 1234567890123 end")
    assert "1234567890123" not in out


def test_short_numbers_untouched() -> None:
    text = "téléphone 01 23 45 67 89, montant 1 500 000 EUR, solde 3000.00 EUR"
    assert scrub_secrets(text) == text


def test_timestamp_and_uuid_untouched() -> None:
    text = '{"created_at":"2026-11-25T09:11:23.141000","id":"2bcd506a-36d7-4309-a66d-077d97252c31"}'
    assert scrub_secrets(text) == text


def test_long_digit_run_masked_too() -> None:
    # Anything at/above the PAN threshold is masked, including 20+ digit runs (IBAN-like).
    assert "12345678901234567890" not in scrub_secrets("ref 12345678901234567890 fin")


def test_twelve_digit_spaced_run_untouched() -> None:
    text = "code 12 345 678 901 ici"
    assert scrub_secrets(text) == text


def test_mask_pan_keeps_last4() -> None:
    assert mask_pan("4970 1010 2020 3030") == "**** **** **** 3030"
    assert mask_pan("4111111111111111") == "**** **** **** 1111"
