# AGENTS.md - Developer and AI Agent Guide

## Overview

This repository is the Vast.ai CLI (`vastai`), a command-line tool for managing GPU instances, machines, billing, and other resources on the Vast.ai platform.

- **Entry point**: `vastai` command, defined in `pyproject.toml` as `vast_cli.main:main`
- **Backward compat**: `vast.py` in the repo root is a thin shim that imports and calls `vast_cli.main:main`
- **Package name on PyPI**: `vastai`

## Architecture

```
User -> vastai <command> [args]
     -> vast_cli/main.py          parse args, load API key, dispatch to command function
     -> vast_cli/commands/*.py     command logic (one module per domain)
     -> vast_cli/api/client.py     HTTP requests (GET/POST/PUT/DELETE with retry)
     -> vast_cli/api/helpers.py    URL construction (apiurl), header construction
     -> vast_cli/display/*.py      output formatting (tables, rich output)
```

**Startup sequence** (`main.py`):
1. `import vast_cli.commands` triggers all `@parser.command()` decorators to register commands
2. `main()` adds global arguments (`--url`, `--api-key`, `--raw`, `--explain`, `--curl`, etc.)
3. Parse args via `parser.parse_args()`
4. Load API key: CLI flag > `VAST_API_KEY` env var > TFA key file > API key file
5. Set `state.headers["Authorization"]`
6. Call `args.func(args)` to dispatch to the matched command function
7. If `--raw`, print the return value as JSON

## Directory Structure

```
vast_cli/
  __init__.py          Package marker
  main.py              Entry point: arg parsing, API key loading, command dispatch
  parser.py            apwrap class: @parser.command() decorator, argument(), hidden_aliases()
  state.py             Global mutable state: ARGS, headers, TABCOMPLETE, api_key_guard
  config.py            Constants: server URL, XDG paths, key file locations, emoji support
  helpers.py           Miscellaneous utility functions used across commands
  completions.py       Tab-completion functions for instance IDs, machine IDs, SSH keys

  api/
    __init__.py
    client.py          http_get(), http_post(), http_put(), http_del() with retry on 429
    helpers.py         apiurl() for URL construction, apiheaders() for auth headers

  auth/
    __init__.py
    keys.py            SSH key validation

  commands/
    __init__.py        Auto-imports all command modules to trigger registration
    accounts.py        Subaccounts, teams, team roles, member management
    api_keys.py        API key CRUD
    billing.py         Deposits, earnings, invoices, account balance
    clusters.py        Cluster and overlay network management
    env_vars.py        User environment variable CRUD
    instances.py       Instance lifecycle (create, start, stop, destroy, reboot, etc.)
    machines.py        Host machine management (publish, maintenance, cleanup, etc.)
    scheduled_jobs.py  Scheduled job listing and deletion
    search.py          Search for offers, benchmarks, invoices, templates
    self_test.py       Host machine self-testing
    ssh.py             SSH key management and instance SSH/SCP URLs
    templates.py       Template CRUD
    tfa.py             Two-factor authentication setup and login
    transfer.py        File copy, sync, snapshot, cloud-copy operations
    volumes.py         Volume and network volume management
    workers.py         Worker groups and endpoint management

  display/
    __init__.py
    table.py           display_table() for tabular output with ANSI colors
    formatting.py      deindent(), null-string handling, request pretty-printing
    rich_tables.py     Rich library tables for billing charges

  query/
    __init__.py
    parser.py          Search query string parser
    fields.py          Field definitions for searchable entities

  validation/
    __init__.py
    validators.py      Input validation functions

  version/
    __init__.py
    checker.py         PyPI version checking and update prompts
```

## Key Patterns

### Command Registration

Commands are registered using the `@parser.command()` decorator from `vast_cli/parser.py`:

```python
from vast_cli.parser import parser, argument, hidden_aliases
from vast_cli import state
from vast_cli.api.client import http_get
from vast_cli.api.helpers import apiurl

@parser.command(
    argument("name", help="Resource name", type=str),
    argument("--flag", action="store_true", help="Optional flag"),
    aliases=hidden_aliases(["alternative name"]),
    usage="vastai verb object <name> [--flag]",
    help="Short help text shown in command list",
)
def verb__object(args):
    """Docstring (not displayed to users)."""
    url = apiurl(args, "/some/endpoint/")
    r = http_get(args, url, headers=state.headers)
    r.raise_for_status()
    result = r.json()
    print(result)
```

**Function naming convention**: `verb__object` (double underscore) becomes the CLI command `verb object`. Single underscores become hyphens: `env_var__create` -> `env-var create`.

**Return values**: Commands can return:
- An exit code (int) for `sys.exit()`
- A response object or dict when `--raw` is used (main.py will JSON-serialize it)
- `None` for success (exits 0)

### Command Auto-Import

`vast_cli/commands/__init__.py` imports every command module:
```python
from vast_cli.commands import accounts      # noqa: F401
from vast_cli.commands import api_keys      # noqa: F401
# ... all 16 modules
```
When `main.py` does `import vast_cli.commands`, all `@parser.command()` decorators execute, registering every command with the argument parser.

### Global State

`vast_cli/state.py` holds mutable globals:
- `state.ARGS` - parsed argparse Namespace (set in `main()`)
- `state.headers` - dict with `Authorization` header (set in `main()`)
- `state.TABCOMPLETE` - bool, True if argcomplete is available
- `state.api_key_guard` - sentinel object for detecting missing API key

Access from commands:
```python
from vast_cli import state
# Use state.headers for auth, state.ARGS for global flags
```

### API Calls

Use the functions in `vast_cli/api/`:

```python
from vast_cli.api.client import http_get, http_post, http_put, http_del
from vast_cli.api.helpers import apiurl

# Build URL (automatically prepends /api/v0 and appends api_key)
url = apiurl(args, "/instances/{}/".format(args.id))

# Make request (retries on 429, supports --explain and --curl flags)
r = http_get(args, url, headers=state.headers)
r.raise_for_status()
data = r.json()
```

`apiurl()` handles:
- Prepending `/api/v0` if the subpath doesn't already include a version
- Adding `api_key` as a query parameter
- URL-encoding query arguments

### Output

**Tables**: Use `display_table()` from `vast_cli/display/table.py`:
```python
from vast_cli.display.table import display_table

# Fields are 5-tuples: (key, header, format, transform, left_justify)
fields = [
    ("id",   "ID",   "{}",     None,              True),
    ("ram",  "RAM",  "{:0.1f}", lambda x: x/1000, False),
]
display_table(rows, fields)
```

**Raw JSON**: When the user passes `--raw`, return a dict or response object from the command function instead of printing. `main.py` handles the JSON serialization.

**Rich tables**: For billing/charges output, use `vast_cli/display/rich_tables.py`.

### Mutually Exclusive Arguments

Use the `mutex_group` parameter on `argument()`:
```python
@parser.command(
    argument("--by-id", mutex_group="selector", help="Select by ID"),
    argument("--by-name", mutex_group="selector", help="Select by name"),
)
def my__command(args):
    ...
```
Arguments in the same `mutex_group` are mutually exclusive. Set `required=True` on any one of them to make the group required.

## How to Add a New Command

1. **Create or edit a file** in `vast_cli/commands/`. Group related commands in the same file (e.g., all volume commands go in `volumes.py`).

2. **Add the imports and decorator**:
   ```python
   from vast_cli.parser import parser, argument, hidden_aliases
   from vast_cli import state
   from vast_cli.api.client import http_get
   from vast_cli.api.helpers import apiurl

   @parser.command(
       argument("id", help="Resource ID", type=int),
       usage="vastai show widget <id>",
       help="Show details of a widget",
   )
   def show__widget(args):
       url = apiurl(args, "/widgets/{}/".format(args.id))
       r = http_get(args, url, headers=state.headers)
       r.raise_for_status()
       if args.raw:
           return r.json()
       # format and print output
   ```

3. **If you created a new file**, add an import to `vast_cli/commands/__init__.py`:
   ```python
   from vast_cli.commands import widgets     # noqa: F401
   ```

4. **Follow conventions**:
   - Function name: `verb__object` (double underscore separates verb from object)
   - Provide `usage=` and `help=` in the decorator
   - Use `hidden_aliases()` for backward-compatible alternative names
   - Return a dict/response for `--raw` support, or an int exit code
   - Use `state.headers` for authenticated requests

## How to Add a New Submodule

For non-command modules (display helpers, validation, etc.):

1. Create a new directory under `vast_cli/` with an `__init__.py`
2. Add your module files
3. Import from commands as needed: `from vast_cli.mymodule.thing import func`
4. Avoid circular imports - command modules should import from utility modules, not the other way around

## Configuration

### Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `VAST_API_KEY` | API authentication key | Read from key file |
| `VAST_URL` | API server base URL | `https://console.vast.ai` |
| `LOGLEVEL` | Python logging level | `WARN` |

### API Key Precedence

1. `--api-key` CLI flag
2. `VAST_API_KEY` environment variable
3. `~/.config/vastai/vast_tfa_key` (temporary 2FA session key)
4. `~/.config/vastai/vast_api_key` (standard persistent key)
5. `~/.vast_api_key` (legacy location, auto-migrated on first run)

### File Paths (XDG)

All paths use XDG base directories via the `xdg` package:
- Config: `~/.config/vastai/` (API keys)
- Cache: `~/.cache/vastai/` (GPU name cache, 24h TTL)

## Testing

Integration tests live in `openapi/tests/`. Each test file defines a `CommandTestSuite` subclass:

```python
from openapi.tests.base import CommandTestSuite, TestCase

class MyTestSuite(CommandTestSuite):
    def __init__(self):
        super().__init__(command="show widget", description="...")
        self.add_test(TestCase(
            name="basic test",
            input_data={"id": 123},
            expected_output={"status_code": 200, "response": {...}},
        ))
```

Test discovery is automatic: `openapi/tests/__init__.py` imports all test modules and collects `CommandTestSuite` subclasses.

## Common Imports

Quick reference to avoid circular imports:

| Need | Import from |
|---|---|
| `@parser.command`, `argument`, `hidden_aliases` | `vast_cli.parser` |
| `state.ARGS`, `state.headers` | `vast_cli.state` (via `from vast_cli import state`) |
| `http_get`, `http_post`, `http_put`, `http_del` | `vast_cli.api.client` |
| `apiurl`, `apiheaders` | `vast_cli.api.helpers` |
| `display_table` | `vast_cli.display.table` |
| `deindent` | `vast_cli.display.formatting` |
| `server_url_default`, `APIKEY_FILE`, etc. | `vast_cli.config` |

**Import direction**: `commands/` -> `api/`, `display/`, `query/`, `validation/`, `config`, `state`, `helpers`. Never import from `commands/` into utility modules.
