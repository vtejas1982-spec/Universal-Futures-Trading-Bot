import os
import unittest

class ExchangeDemoSmokeTests(unittest.TestCase):
    @unittest.skipUnless(
        os.getenv("RUN_EXCHANGE_DEMO_TESTS") == "1",
        "Opt-in: exchange demo credentials are required; no live orders are placed by default."
    )
    def test_demo_suite_gate(self):
        self.assertEqual(os.getenv("RUN_EXCHANGE_DEMO_TESTS"), "1")

if __name__ == "__main__":
    unittest.main()
