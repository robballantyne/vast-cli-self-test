"""Scheduled job commands for vast_cli."""

from vast_cli.parser import parser, argument
from vast_cli import state
from vast_cli.api.client import http_get, http_del
from vast_cli.api.helpers import apiurl
from vast_cli.helpers import normalize_jobs
from vast_cli.query.fields import scheduled_jobs_fields
from vast_cli.display.table import display_table


@parser.command(
    argument("id", help="id of scheduled job to remove", type=int),
    usage="vastai delete scheduled-job ID",
    help="Delete a scheduled job",
)
def delete__scheduled_job(args):
    url = apiurl(args, "/commands/schedule_job/{id}/".format(id=args.id))
    r = http_del(args, url, headers=state.headers)
    r.raise_for_status()
    print(r.json())


@parser.command(
    usage="vastai show scheduled-jobs [--api-key API_KEY] [--raw]",
    help="Display the list of scheduled jobs"
)
def show__scheduled_jobs(args):
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
