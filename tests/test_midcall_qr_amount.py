import unittest

from app.tasks.scheduler import amount_confirmed_for_qr


class MidcallQrAmountTests(unittest.TestCase):
    def test_uses_confirmed_amount_when_present(self):
        gathered = {"confirmed_amount": 500, "proposed_amount": 500}

        self.assertEqual(amount_confirmed_for_qr(gathered), 500)

    def test_uses_proposed_amount_only_after_payment_node_was_visited(self):
        gathered = {
            "proposed_amount": 500,
            "nodes_visited": [
                "Greeting & Qualification",
                "Platform Intro & Offer",
                "Deposit Amount Confirmation",
                "Payment QR",
            ],
        }

        self.assertEqual(amount_confirmed_for_qr(gathered), 500)

    def test_does_not_use_unconfirmed_proposed_amount(self):
        gathered = {
            "proposed_amount": 500,
            "nodes_visited": ["Greeting & Qualification", "Platform Intro & Offer"],
        }

        self.assertIsNone(amount_confirmed_for_qr(gathered))


if __name__ == "__main__":
    unittest.main()
