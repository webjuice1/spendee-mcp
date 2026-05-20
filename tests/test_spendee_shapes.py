from spendee_mcp.summaries import filter_transactions


def test_filter_transactions_uses_spendee_start_date_for_date_range():
    transactions = [
        {"id": "old-created", "created": "2025-10-18 12:14:07", "start_date": "2026-05-14 09:30:00"},
        {"id": "outside", "created": "2025-10-18 12:14:07", "start_date": "2026-05-01 09:30:00"},
    ]

    result = filter_transactions(transactions, date_from="2026-05-13", date_to="2026-05-20")

    assert [txn["id"] for txn in result] == ["old-created"]
