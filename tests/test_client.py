from spendee_mcp.client import SpendeeReadOnlyClient


class FakeSpendee:
    def __init__(self):
        self.calls = []

    def wallet_get_transactions(self, **kwargs):
        self.calls.append(("wallet_get_transactions", kwargs))
        return [
            {"id": "a", "wallet_id": 123, "category_id": 9, "amount": -10, "note": "OPENAI", "hashtags": []},
            {
                "id": "b",
                "wallet_id": 456,
                "category_id": 10,
                "amount": -20,
                "note": "XFERA",
                "hashtags": [{"name": "Phone"}],
            },
            {"id": "c", "wallet_id": 123, "category_id": None, "amount": -100, "note": "Transfer", "type": "TRANSFER"},
        ]

    def get_all_user_categories(self):
        self.calls.append(("get_all_user_categories", {}))
        return [
            {"id": 9, "name": "Business exp", "type": "expense", "color": "#f5534b", "image_id": 27},
            {"id": 10, "name": "Phone", "type": "expense", "color": "#123456", "image_id": 5},
        ]

    def wallet_get_all(self):
        self.calls.append(("wallet_get_all", {}))
        return [
            {"id": 123, "name": "BOI - Webjuice", "currency": "EUR"},
            {"id": 456, "name": "Wise - USD", "currency": "USD"},
        ]


def make_client():
    client = SpendeeReadOnlyClient.__new__(SpendeeReadOnlyClient)
    client._client = FakeSpendee()
    return client


def test_get_wallet_transactions_uses_upstream_offset_limit_api_and_filters_wallet_id():
    client = make_client()

    result = client.get_wallet_transactions(123, limit=50)

    assert client._client.calls[0] == ("wallet_get_transactions", {"limit": 50})
    assert len(result) == 2
    assert [txn["id"] for txn in result] == ["a", "c"]
    assert result[0]["wallet_id"] == 123


def test_enriches_transactions_with_spendee_ui_fields():
    client = make_client()

    result = client.get_all_transactions(limit_per_wallet=50)

    assert result[0]["category"] == "Business exp"
    assert result[0]["category_name"] == "Business exp"
    assert result[0]["category_type"] == "expense"
    assert result[0]["wallet"] == "BOI - Webjuice"
    assert result[0]["currency"] == "EUR"
    assert result[0]["note_text"] == "OPENAI"
    assert result[0]["labels"] == []
    assert result[0]["label"] is None
    assert result[1]["labels"] == ["Phone"]
    assert result[1]["label"] == "Phone"
    assert result[1]["currency"] == "USD"
    assert result[2]["category"] == "Transfer"
    assert result[2]["category_name"] == "Transfer"
    assert result[2]["category_type"] == "transfer"
