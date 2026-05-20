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
        result = self._call("wallet_get_transactions", wallet_id=wallet_id)
        rows = _as_list(result)
        return rows[:limit] if limit else rows

    def get_all_transactions(self, limit_per_wallet: int | None = None) -> list[dict[str, Any]]:
        transactions: list[dict[str, Any]] = []
        for wallet in self.list_wallets():
            wallet_id = wallet.get("id") or wallet.get("wallet_id") or wallet.get("walletId")
            if not wallet_id:
                continue
            wallet_name = wallet.get("name") or wallet.get("title") or str(wallet_id)
            for txn in self.get_wallet_transactions(wallet_id, limit=limit_per_wallet):
                if isinstance(txn, dict):
                    txn.setdefault("wallet", wallet_name)
                    txn.setdefault("wallet_id", wallet_id)
                    transactions.append(txn)
        return transactions

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


@lru_cache(maxsize=1)
def get_client() -> SpendeeReadOnlyClient:
    return SpendeeReadOnlyClient()
