from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

Transaction = dict[str, Any]


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return datetime.strptime(text[:26].rstrip("Z"), fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _money(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0.00")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    return str(value).strip()


def _txn_date(txn: Transaction) -> date | None:
    return _parse_date(txn.get("date") or txn.get("start_date") or txn.get("transaction_date") or txn.get("created"))


def _txn_amount(txn: Transaction) -> Decimal:
    return _money(txn.get("amount") or txn.get("value") or txn.get("transaction_amount"))


def txn_payee(txn: Transaction) -> str:
    return _text(txn.get("payee") or txn.get("merchant") or txn.get("name") or txn.get("note"), "Unknown")


def txn_category(txn: Transaction) -> str:
    category = txn.get("category") or txn.get("category_name") or txn.get("categoryName")
    if isinstance(category, dict):
        category = category.get("name") or category.get("title") or category.get("id")
    if not category and _text(txn.get("type")).upper() == "TRANSFER":
        category = "Transfer"
    return _text(category, "Uncategorized")


def txn_wallet(txn: Transaction) -> str:
    wallet = txn.get("wallet") or txn.get("wallet_name") or txn.get("walletName")
    if isinstance(wallet, dict):
        wallet = wallet.get("name") or wallet.get("id")
    return _text(wallet, "Unknown")


def txn_currency(txn: Transaction) -> str:
    currency = txn.get("currency") or txn.get("currency_code") or txn.get("currencyCode") or "EUR"
    if isinstance(currency, dict):
        currency = currency.get("code") or currency.get("name")
    return _text(currency, "EUR").upper()


def txn_note(txn: Transaction) -> str:
    return _text(txn.get("note_text") or txn.get("note") or txn.get("description") or txn.get("name"))


def txn_labels(txn: Transaction) -> list[str]:
    labels = txn.get("labels") or txn.get("hashtags") or txn.get("label")
    if labels in (None, "", {}, []):
        return []
    if isinstance(labels, str):
        return [labels.strip()] if labels.strip() else []
    if isinstance(labels, dict):
        labels = labels.values()
    elif not isinstance(labels, list):
        labels = [labels]

    result: list[str] = []
    for item in labels:
        if isinstance(item, dict):
            value = item.get("name") or item.get("label") or item.get("title") or item.get("value")
        else:
            value = item
        if value is not None and str(value).strip():
            result.append(str(value).strip())
    return result


def filter_transactions(
    transactions: Iterable[Transaction],
    *,
    wallet: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int | None = None,
) -> list[Transaction]:
    start = _parse_date(date_from)
    end = _parse_date(date_to)
    wallet_norm = wallet.lower().strip() if wallet else None
    filtered: list[Transaction] = []

    for txn in transactions:
        txn_date = _txn_date(txn)
        if start and (txn_date is None or txn_date < start):
            continue
        if end and (txn_date is None or txn_date > end):
            continue
        if wallet_norm and txn_wallet(txn).lower() != wallet_norm and str(txn.get("wallet_id", "")).lower() != wallet_norm:
            continue
        filtered.append(txn)
        if limit and len(filtered) >= limit:
            break

    return filtered


def spending_summary(
    transactions: Iterable[Transaction],
    *,
    wallet: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    selected = filter_transactions(transactions, wallet=wallet, date_from=date_from, date_to=date_to)
    categories: dict[str, dict[str, Any]] = defaultdict(lambda: {"spent": 0.0, "income": 0.0, "count": 0})
    currency_totals: dict[str, dict[str, float]] = defaultdict(lambda: {"expenses": 0.0, "income": 0.0, "net": 0.0})

    for txn in selected:
        amount = _txn_amount(txn)
        currency = txn_currency(txn)
        category = txn_category(txn)
        categories[category]["count"] += 1

        if amount < 0:
            expense = float(abs(amount))
            categories[category]["spent"] += expense
            currency_totals[currency]["expenses"] += expense
        else:
            income = float(amount)
            categories[category]["income"] += income
            currency_totals[currency]["income"] += income

        currency_totals[currency]["net"] += float(amount)

    return {
        "filters": {"wallet": wallet, "date_from": date_from, "date_to": date_to},
        "transaction_count": len(selected),
        "currency_totals": dict(currency_totals),
        "categories": dict(sorted(categories.items(), key=lambda item: item[1]["spent"], reverse=True)),
    }


def review_transactions(
    transactions: Iterable[Transaction],
    *,
    wallet: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    selected = filter_transactions(transactions, wallet=wallet, date_from=date_from, date_to=date_to, limit=limit)
    rows: list[dict[str, Any]] = []
    for txn in selected:
        txn_date = _txn_date(txn)
        amount = _txn_amount(txn)
        labels = txn_labels(txn)
        rows.append(
            {
                "date": txn_date.isoformat() if txn_date else None,
                "wallet": txn_wallet(txn),
                "amount": float(amount),
                "currency": txn_currency(txn),
                "category": txn_category(txn),
                "note": txn_note(txn),
                "labels": labels,
                "label": ", ".join(labels) if labels else None,
                "type": txn.get("type"),
                "id": txn.get("id"),
            }
        )
    return rows


def find_large_transactions(
    transactions: Iterable[Transaction],
    *,
    threshold: float = 100.0,
    wallet: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
) -> list[Transaction]:
    selected = filter_transactions(transactions, wallet=wallet, date_from=date_from, date_to=date_to)
    minimum = Decimal(str(threshold))
    matches = [txn for txn in selected if _txn_amount(txn) < 0 and abs(_txn_amount(txn)) >= minimum]
    matches.sort(key=lambda txn: abs(_txn_amount(txn)), reverse=True)
    return matches[:limit]


def find_recurring_candidates(
    transactions: Iterable[Transaction],
    *,
    min_occurrences: int = 3,
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, Decimal, str], list[Transaction]] = defaultdict(list)

    for txn in transactions:
        amount = _txn_amount(txn)
        if amount >= 0:
            continue
        key = (txn_payee(txn).lower(), amount, txn_currency(txn))
        groups[key].append(txn)

    results: list[dict[str, Any]] = []
    for (payee, amount, currency), txns in groups.items():
        month_values = set()
        for txn in txns:
            parsed = _txn_date(txn)
            month_values.add(parsed.strftime("%Y-%m") if parsed else "unknown")
        months = sorted(month_values)
        if len(txns) >= min_occurrences and len(months) >= min_occurrences:
            sample = txns[0]
            results.append(
                {
                    "payee": txn_payee(sample),
                    "amount": float(amount),
                    "currency": currency,
                    "occurrences": len(txns),
                    "months": months,
                    "category": txn_category(sample),
                    "wallet": txn_wallet(sample),
                }
            )

    results.sort(key=lambda item: (item["occurrences"], abs(item["amount"])), reverse=True)
    return results


def duplicate_key(txn: Transaction) -> str:
    txn_date = _txn_date(txn)
    date_text = txn_date.isoformat() if txn_date else "unknown-date"
    amount = _txn_amount(txn)
    return "|".join(
        [
            date_text,
            f"{amount:.2f}",
            txn_payee(txn).lower(),
            txn_wallet(txn).lower(),
        ]
    )
