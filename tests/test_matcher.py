from sentinel.matcher import match_typescript_javascript


def test_matches_vendor_import_and_affected_endpoint() -> None:
    files = {
        "src/payments.ts": '''import Stripe from "stripe";\nconst payment = stripe.paymentIntents.create({});\n'''
    }
    sites = match_typescript_javascript(files, ["/v1/payment_intents"], "stripe")
    assert len(sites) == 1
    assert sites[0].file == "src/payments.ts"
    assert sites[0].line == 2


def test_ignores_unrelated_languages() -> None:
    files = {"src/payments.py": "stripe.PaymentIntent.create()"}
    assert match_typescript_javascript(files, ["/v1/payment_intents"], "stripe") == []
