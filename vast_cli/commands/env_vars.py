"""Commands for managing user environment variables."""

from vast_cli.parser import parser, argument, hidden_aliases
from vast_cli import state
from vast_cli.api.client import http_get, http_post, http_put, http_del
from vast_cli.api.helpers import apiurl


@parser.command(
    argument("name", help="Environment variable name", type=str),
    argument("value", help="Environment variable value", type=str),
    aliases=hidden_aliases(["create env-var"]),
    usage="vastai env-var create <name> <value>",
    help="Create a new user environment variable",
)
def env_var__create(args):
    """Create a new environment variable for the current user."""
    url = apiurl(args, "/secrets/")
    data = {"key": args.name, "value": args.value}
    r = http_post(args, url, headers=state.headers, json=data)
    r.raise_for_status()

    result = r.json()
    if result.get("success"):
        print(result.get("msg", "Environment variable created successfully."))
    else:
        print(f"Failed to create environment variable: {result.get('msg', 'Unknown error')}")


@parser.command(
    argument("name", help="Environment variable name to delete", type=str),
    aliases=hidden_aliases(["delete env-var"]),
    usage="vastai env-var delete <name>",
    help="Delete a user environment variable",
)
def env_var__delete(args):
    """Delete an environment variable for the current user."""
    url = apiurl(args, "/secrets/")
    data = {"key": args.name}
    r = http_del(args, url, headers=state.headers, json=data)
    r.raise_for_status()

    result = r.json()
    if result.get("success"):
        print(result.get("msg", "Environment variable deleted successfully."))
    else:
        print(f"Failed to delete environment variable: {result.get('msg', 'Unknown error')}")


@parser.command(
    argument("-s", "--show-values", action="store_true", help="Show the values of environment variables"),
    aliases=hidden_aliases(["show env-vars"]),
    usage="vastai env-var list [-s]",
    help="Show user environment variables",
)
def env_var__list(args):
    """Show the environment variables for the current user."""
    url = apiurl(args, "/secrets/")
    r = http_get(args, url, headers=state.headers)
    r.raise_for_status()

    env_vars = r.json().get("secrets", {})

    if args.raw:
        if not args.show_values:
            # Replace values with placeholder in raw output
            masked_env_vars = {k: "*****" for k, v in env_vars.items()}
            # indent was 2
            return masked_env_vars
        else:
            return env_vars
    else:
        if not env_vars:
            print("No environment variables found.")
        else:
            for key, value in env_vars.items():
                print(f"Name: {key}")
                if args.show_values:
                    print(f"Value: {value}")
                else:
                    print("Value: *****")
                print("---")

    if not args.show_values:
        print("\nNote: Values are hidden. Use --show-values or -s option to display them.")


@parser.command(
    argument("name", help="Environment variable name to update", type=str),
    argument("value", help="New environment variable value", type=str),
    aliases=hidden_aliases(["update env-var"]),
    usage="vastai env-var update <name> <value>",
    help="Update an existing user environment variable",
)
def env_var__update(args):
    """Update an existing environment variable for the current user."""
    url = apiurl(args, "/secrets/")
    data = {"key": args.name, "value": args.value}
    r = http_put(args, url, headers=state.headers, json=data)
    r.raise_for_status()

    result = r.json()
    if result.get("success"):
        print(result.get("msg", "Environment variable updated successfully."))
    else:
        print(f"Failed to update environment variable: {result.get('msg', 'Unknown error')}")
