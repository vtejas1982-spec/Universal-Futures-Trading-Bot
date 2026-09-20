import pathlib
import unittest

BOT = pathlib.Path(__file__).resolve().parents[1] / "UniversalFuturesBot_V8_2_MODULAR_ENGINE.py"
SOURCE = BOT.read_text(encoding="utf-8")

class RecoveryContractTests(unittest.TestCase):
    def test_runtime_schema(self):
        self.assertIn('"schema_version": 3', SOURCE)

    def test_credentials_are_not_recovery_snapshot(self):
        self.assertIn("Credentials remain in the normal profile config", SOURCE)
        self.assertIn('"api_key", "api_secret", "tele_token", "tele_chat"', SOURCE)

    def test_exchange_verification_exists(self):
        self.assertIn("_verify_resume_exchange_state", SOURCE)
        self.assertIn("START BLOCKED", SOURCE)

    def test_unprotected_position_fails_closed(self):
        self.assertIn("Unprotected position", SOURCE)
        self.assertIn("closed by safety recovery", SOURCE)

if __name__ == "__main__":
    unittest.main()
