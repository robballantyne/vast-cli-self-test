"""Scheduled job commands for vast_cli."""

from vast_cli.parser import parser, argument, hidden_aliases
from vast_cli import state
from vast_cli.api.client import http_get, http_del
from vast_cli.api.helpers import apiurl
from vast_cli.helpers import normalize_jobs
from vast_cli.query.fields import scheduled_jobs_fields
from vast_cli.display.table import display_table


@parser.command(
    argument("id", help="id of scheduled job to remove", type=int),
    aliases=hidden_aliases(["delete scheduled-job"]),
    usage="vastai scheduled-job delete ID",
    help="Delete a scheduled job",
)
def scheduled_job__delete(args):
    url = apiurl(args, "/commands/schedule_job/{id}/".format(id=args.id))
    r = http_del(args, url, headers=state.headers)
    r.raise_for_status()
    print(r.json())


@parser.command(
    aliases=hidden_aliases(["show scheduled-jobs"]),
    usage="vastai scheduled-job list [--api-key API_KEY] [--raw]",
    help="Display the list of scheduled jobs"
)
def scheduled_job__list(args):
    """
    Shows the list of scheduled jobs for the account.

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    req_url = apiurl(args, "/commands/schedule_job/")
    r = http_get(args, req_url)
    r.raise_for_status()
    rows = r.json()
    if args.raw:
        return rows
    else:
        rows = normalize_jobs(rows)
        display_table(rows, scheduled_jobs_fields)
