from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv

from .security import safe_error


class SpendeeClientError(RuntimeError):
    """Raised when Spendee cannot be reached or returns unexpected data."""


class SpendeeReadOnlyClient:
    """Thin read-only adapter around the unofficial `spendee` Python package."""

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
        result = self._call("get_all_user_categories")
        return _as_list(result)

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
        for key in ("items", "wallets", "budgets", "categories", "transactions", "data"):
            child = value.get(key)
            if isinstance(child, list):
                return [item for item in child if isinstance(item, dict)]
        return [value]
    return []


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
