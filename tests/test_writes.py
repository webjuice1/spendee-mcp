from datetime import datetime
from unittest.mock import Mock

import pytest

from spendee_mcp.client import SpendeeClientError, SpendeeReadOnlyClient, writes_allowed
from spendee_mcp.server import spendee_create_category, spendee_create_transaction


class FakeSpendee:
    def __init__(self):
        self.calls = []
        self.categories = [
            {"id": 9, "name": "Business exp", "type": "expense", "color": "#f5534b", "image_id": 27},
            {"id": 10, "name": "Phone", "type": "expense", "color": "#123456", "image_id": 5},
            {"id": 11, "name": "Salary", "type": "income", "color": "#00aa00", "image_id": 1},
        ]
        self.created_transaction = {
            "id": 77,
            "wallet_id": 123,
            "category_id": 9,
            "amount": -12.5,
            "note": "Coffee",
            "start_date": "2026-10-21 00:00:00",
        }

    def wallet_get_all(self):
        self.calls.append(("wallet_get_all", {}))
        return [
            {"id": 123, "name": "BOI - Webjuice", "currency": "EUR"},
            {"id": 456, "name": "Wise - USD", "currency": "USD"},
        ]

    def get_all_user_categories(self):
        self.calls.append(("get_all_user_categories", {}))
        return list(self.categories)

    def create_transaction(self, **kwargs):
        self.calls.append(("create_transaction", kwargs))
        return dict(self.created_transaction)

    def wallet_create_category(self, **kwargs):
        self.calls.append(("wallet_create_category", kwargs))
        created = {"id": 42, "name": kwargs["name"], "type": kwargs["type"], "color": "#f5534b"}
        self.categories.append(created)
        return created["id"]


def make_client():
    client = SpendeeReadOnlyClient.__new__(SpendeeReadOnlyClient)
    client._client = FakeSpendee()
    return client


def allow_writes(monkeypatch, *, allow_writes=None, read_only=None):
    if allow_writes is None:
        monkeypatch.delenv("SPENDEE_ALLOW_WRITES", raising=False)
    else:
        monkeypatch.setenv("SPENDEE_ALLOW_WRITES", allow_writes)
    if read_only is None:
        monkeypatch.delenv("SPENDEE_READ_ONLY", raising=False)
    else:
        monkeypatch.setenv("SPENDEE_READ_ONLY", read_only)


def test_writes_allowed_defaults_to_read_only(monkeypatch):
    allow_writes(monkeypatch)
    assert writes_allowed() is False


@pytest.mark.parametrize(
    ("allow_writes_value", "read_only", "expected"),
    [
        (None, "true", False),
        (None, "false", True),
        (None, "0", True),
        ("true", "true", True),
        ("1", None, True),
        ("yes", "true", True),
        ("false", None, False),
        ("false", "false", True),
    ],
)
def test_writes_allowed_env_flag(monkeypatch, allow_writes_value, read_only, expected):
    allow_writes(monkeypatch, allow_writes=allow_writes_value, read_only=read_only)
    assert writes_allowed() is expected


def test_create_transaction_resolves_names_and_returns_created_row(monkeypatch):
    allow_writes(monkeypatch, allow_writes="true")
    client = make_client()

    result = client.create_transaction(
        amount=12.5,
        wallet="BOI - Webjuice",
        category="Business exp",
        date="2026-10-21",
        note="Coffee",
    )

    assert client._client.calls[2][0] == "create_transaction"
    kwargs = client._client.calls[2][1]
    assert kwargs["wallet_id"] == 123
    assert kwargs["category_id"] == 9
    assert kwargs["amount"] == -12.5
    assert kwargs["note"] == "Coffee"
    assert kwargs["start_date"] == datetime(2026, 10, 21)
    assert result["id"] == 77
    assert result["amount"] == -12.5
    assert result["category"] == "Business exp"
    assert result["wallet"] == "BOI - Webjuice"
    assert result["note_text"] == "Coffee"


def test_create_transaction_accepts_ids_and_income(monkeypatch):
    allow_writes(monkeypatch, read_only="false")
    client = make_client()
    client._client.created_transaction = {
        "id": 88,
        "wallet_id": 456,
        "category_id": 11,
        "amount": 2500,
        "note": "Invoice",
    }

    result = client.create_transaction(
        amount=-2500,
        wallet_id=456,
        category_id="11",
        type="income",
        note="Invoice",
    )

    kwargs = client._client.calls[2][1]
    assert kwargs["wallet_id"] == 456
    assert kwargs["category_id"] == 11
    assert kwargs["amount"] == 2500.0
    assert result["id"] == 88
    assert result["category"] == "Salary"


def test_create_transaction_blocked_when_read_only(monkeypatch):
    allow_writes(monkeypatch, read_only="true")
    client = make_client()

    with pytest.raises(SpendeeClientError, match="Write tools are disabled"):
        client.create_transaction(amount=5, wallet="BOI - Webjuice", category="Phone")

    assert client._client.calls == []


def test_create_category_returns_created_category(monkeypatch):
    allow_writes(monkeypatch, allow_writes="true")
    client = make_client()

    result = client.create_category("Subscriptions", type="expense", wallet="BOI - Webjuice")

    assert client._client.calls[1] == (
        "wallet_create_category",
        {"name": "Subscriptions", "type": "expense", "wallet_id": 123},
    )
    assert result["id"] == 42
    assert result["name"] == "Subscriptions"
    assert result["type"] == "expense"


def test_create_category_blocked_when_read_only(monkeypatch):
    allow_writes(monkeypatch)
    client = make_client()

    with pytest.raises(SpendeeClientError, match="Write tools are disabled"):
        client.create_category("Subscriptions")

    assert client._client.calls == []


def test_create_transaction_scrubs_credentials(monkeypatch):
    allow_writes(monkeypatch, allow_writes="true")
    client = make_client()

    def boom(**kwargs):
        raise RuntimeError("login failed password=supersecret token=abc Bearer abc.def.ghi")

    client._client.create_transaction = boom

    with pytest.raises(SpendeeClientError) as exc:
        client.create_transaction(amount=5, wallet="BOI - Webjuice", category="Phone")

    message = str(exc.value)
    assert "supersecret" not in message
    assert "password=[redacted]" in message
    assert "token=[redacted]" in message
    assert "Bearer [redacted]" in message


def test_spendee_create_transaction_tool_gated(monkeypatch):
    allow_writes(monkeypatch, read_only="true")
    fake = Mock()

    monkeypatch.setattr("spendee_mcp.server.get_client", lambda: fake)
    result = spendee_create_transaction(amount=5, wallet="Personal", category="Food")

    assert result["error"].startswith("Write tools are disabled")
    assert result["source"] == "spendee-mcp"
    fake.create_transaction.assert_not_called()


def test_spendee_create_category_tool_gated(monkeypatch):
    allow_writes(monkeypatch)
    fake = Mock()
    monkeypatch.setattr("spendee_mcp.server.get_client", lambda: fake)

    result = spendee_create_category(name="Subscriptions")

    assert result["error"].startswith("Write tools are disabled")
    fake.create_category.assert_not_called()


def test_spendee_create_transaction_tool_writes_when_allowed(monkeypatch):
    allow_writes(monkeypatch, allow_writes="true")
    fake = Mock()
    fake.create_transaction.return_value = {"id": 77, "amount": -5, "note": "Coffee"}
    monkeypatch.setattr("spendee_mcp.server.get_client", lambda: fake)

    result = spendee_create_transaction(
        amount=5,
        wallet="BOI - Webjuice",
        category="Business exp",
        note="Coffee",
        date="2026-10-21",
    )

    fake.create_transaction.assert_called_once_with(
        amount=5,
        wallet="BOI - Webjuice",
        wallet_id=None,
        category="Business exp",
        category_id=None,
        date="2026-10-21",
        note="Coffee",
        type="expense",
    )
    assert result == {"id": 77, "amount": -5, "note": "Coffee"}


def test_spendee_create_category_tool_writes_when_allowed(monkeypatch):
    allow_writes(monkeypatch, read_only="false")
    fake = Mock()
    fake.create_category.return_value = {"id": 42, "name": "Subscriptions", "type": "expense"}
    monkeypatch.setattr("spendee_mcp.server.get_client", lambda: fake)

    result = spendee_create_category(name="Subscriptions", type="expense", wallet="Personal")

    fake.create_category.assert_called_once_with(
        "Subscriptions",
        type="expense",
        wallet="Personal",
        wallet_id=None,
    )
    assert result["id"] == 42
