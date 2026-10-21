# Spendee MCP

MCP server for Spendee, built for Claude Desktop, Claude Code, Hermes, and other MCP-compatible clients.

This project connects to Spendee through the unofficial Python `spendee` package. Spendee does not provide a stable public MCP server or official public developer API, so this server is intentionally defensive: read-only by default, with two optional write tools gated by an environment flag.

## Status

- Read-only by default
- Optional write tools (`spendee_create_transaction`, `spendee_create_category`) only run when an env flag allows writes
- No delete, update, transfer, bank-connect, or budget mutation tools
- Local stdio MCP transport
- No database, sync, or cache layer
- Credentials stay in `.env` or MCP client environment variables
- MIT licensed

## Tools exposed

- `spendee_get_profile`
- `spendee_list_wallets`
- `spendee_list_budgets`
- `spendee_list_categories`
- `spendee_get_transactions`
- `spendee_review_transactions`
- `spendee_spending_summary`
- `spendee_find_large_transactions`
- `spendee_find_recurring_candidates`
- `spendee_create_transaction` (write; gated)
- `spendee_create_category` (write; gated)

## Safety model

This project is built for finance visibility. Writes are opt-in so an assistant can log spending without exposing delete, update, transfer, bank-connect, or budget mutation.

Write tools stay disabled unless you set one of:

- `SPENDEE_ALLOW_WRITES=true`
- `SPENDEE_READ_ONLY=false`

The default is read-only (`SPENDEE_READ_ONLY=true` when unset). When writes are enabled, `spendee_create_transaction` and `spendee_create_category` call the live Spendee account through the unofficial wrapper. They return the created row as Spendee reports it.

Credential handling:

- Never commit `.env`.
- Use `.env.example` only for placeholders.
- Use MCP client environment variables when possible.
- Error messages are scrubbed for password, token, and bearer-token patterns before they are returned to the MCP client.

## Setup

```bash
git clone <repo-url>
cd spendee-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

Edit `.env`:

```env
SPENDEE_EMAIL=your@email.com
SPENDEE_PASSWORD=replace-with-your-spendee-password
SPENDEE_READ_ONLY=true
```

To let an assistant log spending, set `SPENDEE_READ_ONLY=false` or `SPENDEE_ALLOW_WRITES=true`. Leave the default if you only want to read wallets, categories, and transactions.

Run tests:

```bash
pytest -q
```

Run lint:

```bash
ruff check .
```

Run server manually:

```bash
python -m spendee_mcp.server
```

The server uses stdio, so it will wait for an MCP client.

## Claude Desktop config

macOS config path:

```bash
code ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

Example:

```json
{
  "mcpServers": {
    "spendee": {
      "command": "/absolute/path/to/spendee-mcp/.venv/bin/python",
      "args": ["-m", "spendee_mcp.server"],
      "cwd": "/absolute/path/to/spendee-mcp",
      "env": {
        "SPENDEE_EMAIL": "your@email.com",
        "SPENDEE_PASSWORD": "replace-with-your-spendee-password",
        "SPENDEE_READ_ONLY": "true"
      }
    }
  }
}
```

Restart Claude Desktop after editing. To enable the two write tools, set `SPENDEE_READ_ONLY` to `"false"` or add `"SPENDEE_ALLOW_WRITES": "true"`.

## Example prompts

```text
Show my Spendee wallets.
```

```text
List my Spendee categories so I can pick one.
```

```text
Review my last 50 Spendee transactions in a compact table.
```

```text
Summarise my Spendee spending this month by category.
```

```text
Find transactions over €100 in the last 30 days.
```

```text
Find recurring payment candidates.
```

```text
Log a €12.50 coffee expense today in my Personal wallet under Food.
```

```text
Create an expense category called Subscriptions.
```

## Known limitations

- If your Spendee account uses only Google, Facebook, or another social login, email/password auth may fail.
- Transaction field names may vary because the Spendee API is undocumented.
- Some wallet, budget, category, or transaction response structures may need adjustment after live testing.
- This project reads live data through the wrapper. It does not store, sync, or cache Spendee data.
- Write tools change the real Spendee account. There is no preview or undo tool.

## License

MIT. See [LICENSE](LICENSE).
