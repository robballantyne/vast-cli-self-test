"""Commands for managing accounts, teams, subaccounts, and related resources."""

import json
import argparse

from vast_cli.parser import parser, argument, hidden_aliases
from vast_cli import state
from vast_cli.api.client import http_get, http_post, http_put, http_del
from vast_cli.api.helpers import apiurl
from vast_cli.display.formatting import deindent
from vast_cli.display.table import display_table
from vast_cli.auth.keys import load_permissions_from_file
from vast_cli.query.fields import ipaddr_fields, audit_log_fields, user_fields


@parser.command(
    argument("--email", help="email address to use for login", type=str),
    argument("--username", help="username to use for login", type=str),
    argument("--password", help="password to use for login", type=str),
    argument("--type", help="host/client", type=str),
    aliases=hidden_aliases(["create subaccount"]),
    usage="vastai subaccount create --email EMAIL --username USERNAME --password PASSWORD --type TYPE",
    help="Create a subaccount",
    epilog=deindent("""
       Creates a new account that is considered a child of your current account as defined via the API key.

       vastai subaccount create --email bob@gmail.com --username bob --password password --type host

       vastai subaccount create --email vast@gmail.com --username vast --password password --type host
    """),
)
def subaccount__create(args):
    """Creates a new account that is considered a child of your current account as defined via the API key.
    """
    # Default value for host_only, can adjust based on expected default behavior
    host_only = False

    # Only process the --account_type argument if it's provided
    if args.type:
        host_only = args.type.lower() == "host"

    json_blob = {
        "email": args.email,
        "username": args.username,
        "password": args.password,
        "host_only": host_only,
        "parent_id": "me"
    }

    # Use --explain to print the request JSON and return early
    if getattr(args, 'explain', False):
        print("Request JSON would be: ")
        print(json_blob)
        return  # Prevents execution of the actual API call

    # API call execution continues here if --explain is not used
    url = apiurl(args, "/users/")
    r = http_post(args, url, headers=state.headers, json=json_blob)
    r.raise_for_status()

    if r.status_code == 200:
        rj = r.json()
        print(rj)
    else:
        print(r.text)
        print(f"Failed with error {r.status_code}")

@parser.command(
    argument("--team_name", help="name of the team", type=str),
    aliases=hidden_aliases(["create-team"]),
    usage="vastai team create --team_name TEAM_NAME",
    help="Create a new team",
    epilog=deindent("""
         Creates a new team under your account.

        Unlike legacy teams, this command does NOT convert your personal account into a team.
        Each team is created as a separate account, and you can be a member of multiple teams.

        When you create a team:
          - You become the team owner.
          - The team starts as an independent account with its own billing, credits, and resources.
          - Default roles (owner, manager, member) are automatically created.
          - You can invite others, assign roles, and manage resources within the team.

        Optional:
          You can transfer a portion of your existing personal credits to the team by using
          the `--transfer_credit` flag. Example:
              vastai create-team --team_name myteam --transfer_credit 25

        Notes:
          - You cannot create a team from within another team account.

        For more details, see:
        https://vast.ai/docs/teams-quickstart
    """)
)

def team__create(args):
    url = apiurl(args, "/team/")
    r = http_post(args, url, headers=state.headers, json={"team_name": args.team_name})
    r.raise_for_status()
    print(r.json())

@parser.command(
    argument("--name", help="name of the role", type=str),
    argument("--permissions", help="file path for json encoded permissions, look in the docs for more information", type=str),
    aliases=hidden_aliases(["create team-role"]),
    usage="vastai team-role create --name NAME --permissions PERMISSIONS",
    help="Add a new role to your team",
    epilog=deindent("""
        Creating a new team role involves understanding how permissions must be sent via json format.
        You can find more information about permissions here: https://vast.ai/docs/cli/roles-and-permissions
    """)
)
def team_role__create(args):
    url = apiurl(args, "/team/roles/")
    permissions = load_permissions_from_file(args.permissions)
    r = http_post(args, url, headers=state.headers, json={"name": args.name, "permissions": permissions})
    r.raise_for_status()
    print(r.json())

@parser.command(
    aliases=hidden_aliases(["destroy team"]),
    usage="vastai team destroy",
    help="Destroy your team",
)
def team__destroy(args):
    url = apiurl(args, "/team/")
    r = http_del(args, url, headers=state.headers)
    r.raise_for_status()
    print(r.json())

@parser.command(
    argument("--email", help="email of user to be invited", type=str),
    argument("--role", help="role of user to be invited", type=str),
    aliases=hidden_aliases(["invite member"]),
    usage="vastai member invite --email EMAIL --role ROLE",
    help="Invite a team member",
)
def member__invite(args):
    url = apiurl(args, "/team/invite/", query_args={"email": args.email, "role": args.role})
    r = http_post(args, url, headers=state.headers)
    r.raise_for_status()
    if (r.status_code == 200):
        print(f"successfully invited {args.email} to your current team")
    else:
        print(r.text);
        print(f"failed with error {r.status_code}")


@parser.command(
    argument("id", help="id of user to remove", type=int),
    aliases=hidden_aliases(["remove member"]),
    usage="vastai member remove ID",
    help="Remove a team member",
)
def member__remove(args):
    url = apiurl(args, "/team/members/{id}/".format(id=args.id))
    r = http_del(args, url, headers=state.headers)
    r.raise_for_status()
    print(r.json())

@parser.command(
    argument("NAME", help="name of the role", type=str),
    aliases=hidden_aliases(["remove team-role"]),
    usage="vastai team-role remove NAME",
    help="Remove a role from your team",
)
def team_role__remove(args):
    url = apiurl(args, "/team/roles/{id}/".format(id=args.NAME))
    r = http_del(args, url, headers=state.headers)
    r.raise_for_status()
    print(r.json())

@parser.command(
    argument("-q", "--quiet", action="store_true", help="display subaccounts from current user"),
    aliases=hidden_aliases(["show subaccounts"]),
    usage="vastai subaccount list [OPTIONS]",
    help="Get current subaccounts"
)
def subaccount__list(args):
    """
    Shows stats for logged-in user. Does not show API key.

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    req_url = apiurl(args, "/subaccounts", {"owner": "me"});
    r = http_get(args, req_url);
    r.raise_for_status()
    rows = r.json()["users"]
    if args.raw:
        return rows
    else:
        display_table(rows, user_fields)

@parser.command(
    aliases=hidden_aliases(["show members"]),
    usage="vastai member list",
    help="Show your team members",
)
def member__list(args):
    url = apiurl(args, "/team/members/")
    r = http_get(args, url, headers=state.headers)
    r.raise_for_status()

    if args.raw:
        return r
    else:
        print(r.json())

@parser.command(
    argument("NAME", help="name of the role", type=str),
    aliases=hidden_aliases(["show team-role"]),
    usage="vastai team-role show NAME",
    help="Show your team role",
)
def team_role__show(args):
    url = apiurl(args, "/team/roles/{id}/".format(id=args.NAME))
    r = http_get(args, url, headers=state.headers)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=1, sort_keys=True))

@parser.command(
    aliases=hidden_aliases(["show team-roles"]),
    usage="vastai team-role list",
    help="Show roles for a team"
)
def team_role__list(args):
    url = apiurl(args, "/team/roles-full/")
    r = http_get(args, url, headers=state.headers)
    r.raise_for_status()

    if args.raw:
        return r
    else:
        print(r.json())

@parser.command(
    argument("id", help="id of the role", type=int),
    argument("--name", help="name of the template", type=str),
    argument("--permissions", help="file path for json encoded permissions, look in the docs for more information", type=str),
    aliases=hidden_aliases(["update team-role"]),
    usage="vastai team-role update ID --name NAME --permissions PERMISSIONS",
    help="Update an existing team role",
)
def team_role__update(args):
    url = apiurl(args, "/team/roles/{id}/".format(id=args.id))
    permissions = load_permissions_from_file(args.permissions)
    r = http_put(args, url,  headers=state.headers, json={"name": args.name, "permissions": permissions})
    r.raise_for_status()
    if args.raw:
        return r
    else:
        print(json.dumps(r.json(), indent=1))


@parser.command(
    aliases=hidden_aliases(["show ipaddrs"]),
    usage="vastai account ipaddrs [--api-key API_KEY] [--raw]",
    help="Display user's history of ip addresses"
)
def account__ipaddrs(args):
    """
    Shows the history of ip address accesses to console.vast.ai endpoints

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """

    req_url = apiurl(args, "/users/me/ipaddrs", {"owner": "me"});
    r = http_get(args, req_url);
    r.raise_for_status()
    rows = r.json()["results"]
    if args.raw:
        return rows
    else:
        display_table(rows, ipaddr_fields)


@parser.command(
    argument("id", help="machine id", type=int),
    aliases=hidden_aliases(["reports"]),
    usage="vastai machine reports ID",
    help="Get the user reports for a given machine",
)
def machine__reports(args):
    """
    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    url = apiurl(args, "/machines/{id}/reports/".format(id=args.id))
    json_blob = {"machine_id" : args.id}

    if (args.explain):
        print("request json: ")
        print(json_blob)

    r = http_get(args, url, headers=state.headers, json=json_blob)
    r.raise_for_status()

    if (r.status_code == 200):
        print(f"reports: {json.dumps(r.json(), indent=2)}")


@parser.command(
    aliases=hidden_aliases(["show audit-logs"]),
    usage="vastai account audit-logs [--api-key API_KEY] [--raw]",
    help="Display account's history of important actions"
)
def account__audit_logs(args):
    """
    Shows the history of ip address accesses to console.vast.ai endpoints

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    req_url = apiurl(args, "/audit_logs/")
    r = http_get(args, req_url)
    r.raise_for_status()
    rows = r.json()
    if args.raw:
        return rows
    else:
        display_table(rows, audit_log_fields)
