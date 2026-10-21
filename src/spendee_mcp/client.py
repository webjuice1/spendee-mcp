from __future__ import annotations

import os
from datetime import datetime
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv

from .security import safe_error

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


def writes_allowed() -> bool:
    """Writes stay off unless an env flag explicitly opts in.

    Enable with ``SPENDEE_ALLOW_WRITES=true`` or ``SPENDEE_READ_ONLY=false``.
    Unset ``SPENDEE_READ_ONLY`` still means read-only.
    """

    allow = os.getenv("SPENDEE_ALLOW_WRITES", "").strip().lower()
    if allow in _TRUTHY:
        return True
    read_only = os.getenv("SPENDEE_READ_ONLY", "true").strip().lower()
    return read_only in _FALSY


class SpendeeClientError(RuntimeError):
    """Raised when Spendee cannot be reached or returns unexpected data."""


class SpendeeReadOnlyClient:
    """Thin adapter around the unofficial `spendee` Python package."""

    def __init__(self, email: str | None = None, password: str | None = None) -> None:
        load_dotenv()
        self.email = email or os.getenv("SPENDEE_EMAIL")
        self.password = password or os.getenv("SPENDEE_PASSWORD")
        if not self.email or not self.password:
            raise SpendeeClientError("Missing SPENDEE_EMAIL or SPENDEE_PASSWORD environment variables.")

        try:
            from spendee import Spendee  # type: ignore
        except Exception as exc:  # pragma: no cover - dependency/environment guard
            raise SpendeeClientError("The unofficial 'spendee' package is not installed or could not be imported.") from exc

        self._client = Spendee(self.email, self.password)

    def get_profile(self) -> dict[str, Any]:
        return self._call("user_get_profile")

    def list_wallets(self) -> list[dict[str, Any]]:
        result = self._call("wallet_get_all")
        return _as_list(result)

    def list_budgets(self) -> list[dict[str, Any]]:
        result = self._call("get_budgets")
        return _as_list(result)

    def list_categories(self) -> list[dict[str, Any]]:
        # Upstream method is get_all_user_categories, not wallet_get_categories.
        result = self._call("get_all_user_categories")
        return _as_list(result)

    def create_transaction(
        self,
        *,
        amount: float,
        wallet: str | None = None,
        wallet_id: str | int | None = None,
        category: str | None = None,
        category_id: str | int | None = None,
        date: str | None = None,
        note: str | None = None,
        type: str = "expense",
    ) -> dict[str, Any]:
        """Create an expense or income via ``Spendee.create_transaction``."""

        self._require_writes()
        resolved_wallet = self._resolve_row(
            self.list_wallets(),
            name=wallet,
            id_value=wallet_id,
            kind="wallet",
        )
        resolved_category = self._resolve_row(
            self.list_categories(),
            name=category,
            id_value=category_id,
            kind="category",
        )
        signed_amount = _signed_amount(amount, type)
        start_date = _parse_start_date(date)
        kwargs: dict[str, Any] = {
            "wallet_id": _as_int_id(resolved_wallet.get("id") or resolved_wallet.get("wallet_id"), kind="wallet"),
            "category_id": _as_int_id(
                resolved_category.get("id") or resolved_category.get("category_id"),
                kind="category",
            ),
            "amount": signed_amount,
        }
        if note is not None:
            kwargs["note"] = note
        if start_date is not None:
            kwargs["start_date"] = start_date
        result = self._call("create_transaction", **kwargs)
        return self._created_transaction(
            result,
            wallet=resolved_wallet,
            category=resolved_category,
            amount=signed_amount,
            note=note,
            start_date=start_date,
        )

    def create_category(
        self,
        name: str,
        *,
        type: str = "expense",
        wallet: str | None = None,
        wallet_id: str | int | None = None,
    ) -> dict[str, Any]:
        """Create an expense or income category via ``Spendee.wallet_create_category``."""

        self._require_writes()
        kind = _category_or_transaction_type(type)
        cleaned = (name or "").strip()
        if not cleaned:
            raise SpendeeClientError("Category name is required.")
        kwargs: dict[str, Any] = {"name": cleaned, "type": kind}
        if wallet is not None or wallet_id is not None:
            resolved_wallet = self._resolve_row(
                self.list_wallets(),
                name=wallet,
                id_value=wallet_id,
                kind="wallet",
            )
            kwargs["wallet_id"] = _as_int_id(resolved_wallet.get("id") or resolved_wallet.get("wallet_id"), kind="wallet")
        result = self._call("wallet_create_category", **kwargs)
        return self._created_category(result, name=cleaned, type=kind)

    def get_wallet_transactions(self, wallet_id: str | int, limit: int | None = None) -> list[dict[str, Any]]:
        # Upstream `spendee.wallet_get_transactions` does not accept wallet_id;
        # despite the name it returns transactions across wallets and only accepts
        # pagination args. Filter locally to keep this adapter wallet-scoped.
        kwargs: dict[str, Any] = {}
        if limit:
            kwargs["limit"] = limit
        result = self._call("wallet_get_transactions", **kwargs)
        rows = self.enrich_transactions(_as_list(result))
        wallet_id_str = str(wallet_id)
        filtered = [txn for txn in rows if str(txn.get("wallet_id") or txn.get("walletId") or "") == wallet_id_str]
        return filtered[:limit] if limit else filtered

    def get_all_transactions(self, limit_per_wallet: int | None = None) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {}
        if limit_per_wallet:
            kwargs["limit"] = limit_per_wallet
        result = self._call("wallet_get_transactions", **kwargs)
        return self.enrich_transactions(_as_list(result))

    def enrich_transactions(self, transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Add Spendee UI fields to raw transaction rows.

        The transaction endpoint returns IDs (`category_id`, `wallet_id`) plus note
        and hashtag data. Claude/Jimmy need the same concepts Mike sees in Spendee:
        category, note, label, wallet, and currency. Keep the original raw fields and
        add normalized read-only fields alongside them.
        """

        category_map = _lookup_by_id(self.list_categories())
        wallet_map = _lookup_by_id(self.list_wallets())
        return [_enrich_transaction(txn, category_map=category_map, wallet_map=wallet_map) for txn in transactions]

    def _require_writes(self) -> None:
        if not writes_allowed():
            raise SpendeeClientError(
                "Write tools are disabled. Set SPENDEE_ALLOW_WRITES=true or SPENDEE_READ_ONLY=false to enable them."
            )

    def _resolve_row(
        self,
        rows: list[dict[str, Any]],
        *,
        name: str | None,
        id_value: str | int | None,
        kind: str,
    ) -> dict[str, Any]:
        if id_value is not None and str(id_value).strip() != "":
            ident = str(id_value).strip()
            for row in rows:
                if _row_id(row, kind) == ident:
                    return row
            raise SpendeeClientError(f"{kind.capitalize()} id not found: {ident}")
        if name is None or str(name).strip() == "":
            raise SpendeeClientError(f"Provide {kind} or {kind}_id.")
        ident = str(name).strip()
        for row in rows:
            if _row_id(row, kind) == ident:
                return row
        matches = [row for row in rows if str(row.get("name") or "").lower() == ident.lower()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise SpendeeClientError(f"Multiple {kind}s named {ident!r}. Use {kind}_id.")
        raise SpendeeClientError(f"{kind.capitalize()} not found: {ident}")

    def _created_transaction(
        self,
        result: Any,
        *,
        wallet: dict[str, Any],
        category: dict[str, Any],
        amount: float,
        note: str | None,
        start_date: datetime | None,
    ) -> dict[str, Any]:
        payload = _unwrap_created(result, fallback_id_keys=("id", "transaction_id"))
        payload.setdefault("wallet_id", wallet.get("id") or wallet.get("wallet_id"))
        payload.setdefault("category_id", category.get("id") or category.get("category_id"))
        payload.setdefault("amount", amount)
        if note is not None:
            payload.setdefault("note", note)
        if start_date is not None:
            payload.setdefault("start_date", start_date.strftime("%Y-%m-%d %H:%M:%S"))
        return self.enrich_transactions([payload])[0]

    def _created_category(self, result: Any, *, name: str, type: str) -> dict[str, Any]:
        payload = _unwrap_created(result, fallback_id_keys=("id", "category_id"))
        created_id = payload.get("id") or payload.get("category_id")
        if created_id is not None:
            for category in self.list_categories():
                if _row_id(category, "category") == str(created_id):
                    return category
        payload.setdefault("name", name)
        payload.setdefault("type", type)
        return payload

    def _call(self, method_name: str, **kwargs: Any) -> Any:
        method = getattr(self._client, method_name, None)
        if method is None:
            raise SpendeeClientError(f"Spendee wrapper does not expose method: {method_name}")
        try:
            return method(**kwargs)
        except Exception as exc:  # pragma: no cover - depends on upstream API
            raise SpendeeClientError(safe_error(str(exc))) from exc


def _as_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("items", "wallets", "budgets", "categories", "transactions", "data", "result"):
            child = value.get(key)
            if isinstance(child, list):
                return [item for item in child if isinstance(item, dict)]
        return [value]
    return []


def _row_id(row: dict[str, Any], kind: str) -> str:
    return str(row.get("id") or row.get(f"{kind}_id") or row.get(f"{kind}Id") or "")


def _as_int_id(value: Any, *, kind: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise SpendeeClientError(f"Invalid {kind} id: {value}") from exc


def _category_or_transaction_type(value: str | None) -> str:
    kind = (value or "expense").strip().lower()
    if kind not in {"expense", "income"}:
        raise SpendeeClientError("type must be 'expense' or 'income'.")
    return kind


def _signed_amount(amount: float, txn_type: str) -> float:
    kind = _category_or_transaction_type(txn_type)
    value = float(amount)
    return -abs(value) if kind == "expense" else abs(value)


def _parse_start_date(value: str | None) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    for fmt, size in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(text[:size], fmt)
        except ValueError:
            continue
    raise SpendeeClientError(f"Unrecognized date: {value}. Use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS.")


def _unwrap_created(result: Any, *, fallback_id_keys: tuple[str, ...]) -> dict[str, Any]:
    if isinstance(result, list):
        rows = [item for item in result if isinstance(item, dict)]
        if rows:
            return dict(rows[0])
        return {"id": result}
    if isinstance(result, dict):
        payload = dict(result)
        for key in ("transaction", "category", "data", "result"):
            child = payload.get(key)
            if isinstance(child, dict):
                return dict(child)
            if isinstance(child, list):
                rows = [item for item in child if isinstance(item, dict)]
                if rows:
                    return dict(rows[0])
        return payload
    for key in fallback_id_keys:
        return {key: result}
    return {"id": result}


def _lookup_by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_id = row.get("id") or row.get("category_id") or row.get("wallet_id") or row.get("walletId")
        if row_id is not None:
            result[str(row_id)] = row
    return result


def _enrich_transaction(
    txn: dict[str, Any],
    *,
    category_map: dict[str, dict[str, Any]],
    wallet_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    enriched = dict(txn)

    category_id = enriched.get("category_id") or enriched.get("categoryId")
    category = category_map.get(str(category_id)) if category_id is not None else None
    if category:
        enriched.setdefault("category", category.get("name"))
        enriched.setdefault("category_name", category.get("name"))
        enriched.setdefault("category_type", category.get("type"))
        enriched.setdefault("category_color", category.get("color"))
        enriched.setdefault("category_image_id", category.get("image_id"))
    elif str(enriched.get("type") or "").upper() == "TRANSFER":
        enriched.setdefault("category", "Transfer")
        enriched.setdefault("category_name", "Transfer")
        enriched.setdefault("category_type", "transfer")

    wallet_id = enriched.get("wallet_id") or enriched.get("walletId")
    wallet = wallet_map.get(str(wallet_id)) if wallet_id is not None else None
    if wallet:
        enriched.setdefault("wallet", wallet.get("name"))
        enriched.setdefault("wallet_name", wallet.get("name"))
        enriched.setdefault("currency", wallet.get("currency"))
        enriched.setdefault("wallet_currency", wallet.get("currency"))

    labels = _normalize_labels(enriched.get("hashtags") or enriched.get("labels") or enriched.get("label"))
    enriched["labels"] = labels
    enriched["label"] = ", ".join(labels) if labels else None
    enriched["note_text"] = enriched.get("note") or enriched.get("description") or enriched.get("name")
    return enriched


def _normalize_labels(value: Any) -> list[str]:
    if value in (None, "", {}, []):
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        values = value.values()
    elif isinstance(value, list):
        values = value
    else:
        values = [value]

    labels: list[str] = []
    for item in values:
        if isinstance(item, dict):
            label = item.get("name") or item.get("label") or item.get("title") or item.get("value")
        else:
            label = item
        if label is not None and str(label).strip():
            labels.append(str(label).strip())
    return labels


@lru_cache(maxsize=1)
def get_client() -> SpendeeReadOnlyClient:
    return SpendeeReadOnlyClient()
