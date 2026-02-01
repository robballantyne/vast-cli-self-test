"""Import all command modules to trigger @parser.command() registration."""

from vast_cli.commands import accounts      # noqa: F401
from vast_cli.commands import api_keys      # noqa: F401
from vast_cli.commands import billing       # noqa: F401
from vast_cli.commands import clusters      # noqa: F401
from vast_cli.commands import env_vars      # noqa: F401
from vast_cli.commands import instances     # noqa: F401
from vast_cli.commands import machines      # noqa: F401
from vast_cli.commands import scheduled_jobs  # noqa: F401
from vast_cli.commands import search        # noqa: F401
from vast_cli.commands import self_test     # noqa: F401
from vast_cli.commands import ssh           # noqa: F401
from vast_cli.commands import templates     # noqa: F401
from vast_cli.commands import tfa           # noqa: F401
from vast_cli.commands import transfer      # noqa: F401
from vast_cli.commands import volumes       # noqa: F401
from vast_cli.commands import workers       # noqa: F401
