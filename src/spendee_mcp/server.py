from __future__ import annotations

import argparse
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from .client import SpendeeClientError, get_client
from .summaries import filter_transactions, find_large_transactions, find_recurring_candidates, spending_summary

mcp = FastMCP("spendee-readonly")


@mcp.tool()
def spendee_get_profile() -> dict[str, Any]:
    """Read the current Spendee user profile."""
    return _guard(lambda: get_client().get_profile())


@mcp.tool()
def spendee_list_wallets() -> list[dict[str, Any]] | dict[str, str]:
    """List Spendee wallets/accounts."""
    return _guard(lambda: get_client().list_wallets())


@mcp.tool()
def spendee_list_budgets() -> list[dict[str, Any]] | dict[str, str]:
    """List Spendee budgets."""
    return _guard(lambda: get_client().list_budgets())


@mcp.tool()
def spendee_list_categories() -> list[dict[str, Any]] | dict[str, str]:
    """List Spendee categories."""
    return _guard(lambda: get_client().list_categories())


@mcp.tool()
def spendee_get_transactions(
    wallet_id: str | None = None,
    wallet: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]] | dict[str, str]:
    """Read transactions with optional wallet/date/limit filters."""

    def run() -> list[dict[str, Any]]:
        client = get_client()
        upstream_limit = None if date_from or date_to else limit
        if wallet_id:
            rows = client.get_wallet_transactions(wallet_id, limit=upstream_limit)
        else:
            rows = client.get_all_transactions(limit_per_wallet=upstream_limit)
        return filter_transactions(rows, wallet=wallet, date_from=date_from, date_to=date_to, limit=limit)

    return _guard(run)


@mcp.tool()
def spendee_spending_summary(
    wallet: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Summarise Spendee spending/income by currency and category."""

    def run() -> dict[str, Any]:
        rows = get_client().get_all_transactions()
        return spending_summary(rows, wallet=wallet, date_from=date_from, date_to=date_to)

    return _guard(run)


@mcp.tool()
def spendee_find_large_transactions(
    threshold: float = 100.0,
    wallet: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]] | dict[str, str]:
    """Find large outgoing Spendee transactions over the threshold."""

    def run() -> list[dict[str, Any]]:
        rows = get_client().get_all_transactions()
        return find_large_transactions(rows, threshold=threshold, wallet=wallet, date_from=date_from, date_to=date_to, limit=limit)

    return _guard(run)


@mcp.tool()
def spendee_find_recurring_candidates(min_occurrences: int = 3) -> list[dict[str, Any]] | dict[str, str]:
    """Find possible recurring payments from repeated payee + amount patterns."""

    def run() -> list[dict[str, Any]]:
        rows = get_client().get_all_transactions()
        return find_recurring_candidates(rows, min_occurrences=min_occurrences)

    return _guard(run)


def _guard(fn):
    try:
        return fn()
    except SpendeeClientError as exc:
        return {"error": str(exc), "source": "spendee-mcp"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Spendee MCP server")
    parser.add_argument("--transport", choices=["stdio"], default="stdio")
    args = parser.parse_args()
    load_dotenv()
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
