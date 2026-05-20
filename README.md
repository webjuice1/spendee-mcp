# Spendee MCP

Read-only MCP server for Spendee, built for Claude Desktop / Claude Code / Hermes-compatible MCP clients.

This project connects to Spendee through the unofficial Python `spendee` package. Spendee does not provide a stable public MCP server or official public developer API, so this is intentionally defensive and read-only.

## Status

- Read-only by design
- No create/update/delete tools
- Uses local stdio MCP transport
- Credentials stay in `.env` or MCP client env

## Tools exposed

- `spendee_get_profile`
- `spendee_list_wallets`
- `spendee_list_budgets`
- `spendee_list_categories`
- `spendee_get_transactions`
- `spendee_spending_summary`
- `spendee_find_large_transactions`
- `spendee_find_recurring_candidates`

## Safety notes

The upstream Spendee API is undocumented and may break.

Do not add write tools unless you are ready to accept account-data risk. This repo is built for finance visibility, not mutation.

Never commit `.env`.

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
SPENDEE_PASSWORD=your-password
SPENDEE_READ_ONLY=true
```

Run tests:

```bash
pytest -q
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
        "SPENDEE_PASSWORD": "your-password",
        "SPENDEE_READ_ONLY": "true"
      }
    }
  }
}
```

Restart Claude Desktop after editing.

## Example prompts

```text
Show my Spendee wallets.
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

## Known limitations

- If your Spendee account uses only Google/Facebook/social login, email/password auth may fail.
- Transaction field names may vary because the Spendee API is undocumented.
- Some wallet/budget/category response structures may need adjustment after first live test.
- This project does not store, sync, or cache data. It reads live via the wrapper.
