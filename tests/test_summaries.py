from spendee_mcp.summaries import (
    duplicate_key,
    filter_transactions,
    find_large_transactions,
    find_recurring_candidates,
    spending_summary,
)


TRANSACTIONS = [
    {
        "id": "1",
        "date": "2026-05-01",
        "amount": -12.50,
        "currency": "EUR",
        "category": "Food",
        "payee": "Cafe Nero",
        "wallet": "Personal",
    },
    {
        "id": "2",
        "date": "2026-05-02",
        "amount": -100.00,
        "currency": "EUR",
        "category": "Bills",
        "payee": "Electric Ireland",
        "wallet": "Personal",
    },
    {
        "id": "3",
        "date": "2026-05-03",
        "amount": 2500.00,
        "currency": "EUR",
        "category": "Income",
        "payee": "Client Payment",
        "wallet": "Business",
    },
    {
        "id": "4",
        "date": "2026-04-02",
        "amount": -100.00,
        "currency": "EUR",
        "category": "Bills",
        "payee": "Electric Ireland",
        "wallet": "Personal",
    },
    {
        "id": "5",
        "date": "2026-03-02",
        "amount": -100.00,
        "currency": "EUR",
        "category": "Bills",
        "payee": "Electric Ireland",
        "wallet": "Personal",
    },
]


def test_filter_transactions_by_wallet_and_date_range():
    result = filter_transactions(
        TRANSACTIONS,
        wallet="Personal",
        date_from="2026-05-01",
        date_to="2026-05-31",
    )

    assert [txn["id"] for txn in result] == ["1", "2"]


def test_spending_summary_groups_expenses_by_category_and_ignores_income():
    result = spending_summary(TRANSACTIONS, date_from="2026-05-01", date_to="2026-05-31")

    assert result["currency_totals"]["EUR"]["expenses"] == 112.5
    assert result["currency_totals"]["EUR"]["income"] == 2500.0
    assert result["categories"]["Food"]["spent"] == 12.5
    assert result["categories"]["Bills"]["spent"] == 100.0


def test_find_large_transactions_uses_absolute_spend_threshold():
    result = find_large_transactions(TRANSACTIONS, threshold=90)

    assert [txn["id"] for txn in result] == ["2", "4", "5"]


def test_find_recurring_candidates_finds_same_payee_and_amount_across_months():
    result = find_recurring_candidates(TRANSACTIONS, min_occurrences=3)

    assert len(result) == 1
    assert result[0]["payee"] == "Electric Ireland"
    assert result[0]["amount"] == -100.0
    assert result[0]["occurrences"] == 3


def test_duplicate_key_normalizes_date_amount_payee_wallet():
    txn = {"date": "2026-05-01", "amount": "-12.500", "payee": "  Cafe Nero ", "wallet": "Personal"}

    assert duplicate_key(txn) == "2026-05-01|-12.50|cafe nero|personal"
