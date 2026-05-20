from spendee_mcp.client import SpendeeReadOnlyClient


class FakeSpendee:
    def __init__(self):
        self.calls = []

    def wallet_get_transactions(self, **kwargs):
        self.calls.append(kwargs)
        return [
            {"id": "a", "wallet_id": 123, "amount": -10},
            {"id": "b", "wallet_id": 456, "amount": -20},
        ]


def test_get_wallet_transactions_uses_upstream_offset_limit_api_and_filters_wallet_id():
    client = SpendeeReadOnlyClient.__new__(SpendeeReadOnlyClient)
    fake = FakeSpendee()
    client._client = fake

    result = client.get_wallet_transactions(123, limit=50)

    assert fake.calls == [{"limit": 50}]
    assert result == [{"id": "a", "wallet_id": 123, "amount": -10}]
