"""Commands for billing, invoices, earnings, and credit transfers."""

import json
import time
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, List

import requests

from vast_cli.parser import parser, argument
from vast_cli import state
from vast_cli.api.client import http_get, http_post, http_put, http_del
from vast_cli.api.helpers import apiurl
from vast_cli.display.formatting import deindent, translate_null_strings_to_blanks
from vast_cli.display.table import display_table, print_or_page
from vast_cli.display.rich_tables import (
    create_rich_table_for_charges,
    create_rich_table_for_invoices,
    create_rich_table_from_rows,
    rich_object_to_string,
    create_charges_tree,
)
from vast_cli.query.fields import invoice_fields, user_fields
from vast_cli.validation.validators import (
    string_to_unix_epoch,
    fix_date_fields,
    convert_dates_to_timestamps,
    convert_timestamp_to_date,
)
from vast_cli.helpers import filter_invoice_items, format_invoices_charges_results


def sum(X, k):
    y = 0
    for x in X:
        a = float(x.get(k,0))
        y += a
    return y

def select(X,k):
    Y = set()
    for x in X:
        v = x.get(k,None)
        if v is not None:
            Y.add(v)
    return Y


# Helper to convert date string or int to timestamp
def to_timestamp_(val):
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        if val.isdigit():
            return int(val)
        return int(datetime.strptime(val + "+0000", '%Y-%m-%d%z').timestamp())
    raise ValueError("Invalid date format")

charge_types = ['instance','volume','serverless', 'i', 'v', 's']
invoice_types = {
    "transfers": "transfer",
    "stripe": "stripe_payments",
    "bitpay": "bitpay",
    "coinbase": "coinbase",
    "crypto.com": "crypto.com",
    "reserved": "instance_prepay",
    "payout_paypal": "paypal_manual",
    "payout_wise": "wise_manual"
}


@parser.command(
    argument("id", help="id of instance to get info for", type=int),
    usage="vastai show deposit ID [options]",
    help="Display reserve deposit info for an instance"
)
def show__deposit(args):
    """
    Shows reserve deposit info for an instance.

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    req_url = apiurl(args, "/instances/balance/{id}/".format(id=args.id) , {"owner": "me"} )
    r = http_get(args, req_url)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=1, sort_keys=True))


@parser.command(
    argument("-q", "--quiet", action="store_true", help="only display numeric ids"),
    argument("-s", "--start_date", help="start date and time for report. Many formats accepted", type=str),
    argument("-e", "--end_date", help="end date and time for report. Many formats accepted ", type=str),
    argument("-m", "--machine_id", help="Machine id (optional)", type=int),
    usage="vastai show earnings [OPTIONS]",
    help="Get machine earning history reports",
)
def show__earnings(args):
    """
    Show earnings history for a time range, optionally per machine. Various options available to limit time range and type of items.

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """

    Minutes = 60.0
    Hours	= 60.0*Minutes
    Days	= 24.0*Hours
    Years	= 365.0*Days
    cday    = time.time() / Days
    sday = cday - 1.0
    eday = cday - 1.0

    try:
        import dateutil
        from dateutil import parser

    except ImportError:
        print("""\nWARNING: Missing dateutil, can't parse time format""")

    if args.end_date:
        try:
            end_date = dateutil.parser.parse(str(args.end_date))
            end_date_txt = end_date.isoformat()
            end_timestamp = end_date.timestamp()
            eday = end_timestamp / Days
        except ValueError as e:
            print(f"Warning: Invalid end date format! Ignoring end date! \n {str(e)}")

    if args.start_date:
        try:
            start_date = dateutil.parser.parse(str(args.start_date))
            start_date_txt = start_date.isoformat()
            start_timestamp = start_date.timestamp()
            sday = start_timestamp / Days
        except ValueError as e:
            print(f"Warning: Invalid start date format! Ignoring start date! \n {str(e)}")

    req_url = apiurl(args, "/users/me/machine-earnings", {"owner": "me", "sday": sday, "eday": eday, "machid" :args.machine_id});
    r = http_get(args, req_url)
    r.raise_for_status()
    rows = r.json()

    if args.raw:
        return rows
    print(json.dumps(rows, indent=1, sort_keys=True))


@parser.command(
    argument("-q", "--quiet", action="store_true", help="only display numeric ids"),
    argument("-s", "--start_date", help="start date and time for report. Many formats accepted (optional)", type=str),
    argument("-e", "--end_date", help="end date and time for report. Many formats accepted (optional)", type=str),
    argument("-c", "--only_charges", action="store_true", help="Show only charge items"),
    argument("-p", "--only_credits", action="store_true", help="Show only credit items"),
    argument("--instance_label", help="Filter charges on a particular instance label (useful for autoscaler groups)"),
    usage="(DEPRECATED) vastai show invoices [OPTIONS]",
    help="(DEPRECATED) Get billing history reports",
)
def show__invoices(args):
    """
    Show current payments and charges. Various options available to limit time range and type
    of items. Default is to show everything for user's entire billing history.

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """

    sdate,edate = convert_dates_to_timestamps(args)
    req_url = apiurl(args, "/users/me/invoices", {"owner": "me", "sdate":sdate, "edate":edate, "inc_charges" : not args.only_credits});

    r = http_get(args, req_url)
    r.raise_for_status()
    rows = r.json()["invoices"]
    # print("Timestamp for first row: ", rows[0]["timestamp"])
    invoice_filter_data = filter_invoice_items(args, rows)
    rows = invoice_filter_data["rows"]
    filter_header = invoice_filter_data["header_text"]

    contract_ids = None

    if (args.instance_label):
        #print(rows)
        contract_ids = select(rows, 'instance_id')
        #print(contract_ids)

        url = apiurl(args, f"/contracts/fetch/")

        req_json = {
            "label": args.instance_label,
            "contract_ids": list(contract_ids)
        }

        if (args.explain):
            print("request json: ")
            print(req_json)

        result = http_post(args, url, headers=state.headers,json=req_json)
        result.raise_for_status()
        filtered_rows = result.json()["contracts"]
        #print(rows)

        contract_ids = select(filtered_rows, 'id')
        #print(contract_ids)

        rows2 = []
        for row in rows:
            id = row.get("instance_id", None)
            if id in contract_ids:
                rows2.append(row)
        rows = rows2

    current_charges = r.json()["current"]
    if args.quiet:
        for row in rows:
            id = row.get("id", None)
            if id is not None:
                print(id)
    elif args.raw:
        # sort keys
        return rows
        # print("Current: ", current_charges)
    else:
        print(filter_header)
        display_table(rows, invoice_fields)
        print(f"Total: ${sum(rows, 'amount')}")
        print("Current: ", current_charges)


@parser.command(
    argument('-i', '--invoices', mutex_group='grp', action='store_true', required=True, help='Show invoices instead of charges'),
    argument('-it', '--invoice-type', choices=invoice_types.keys(), nargs='+', metavar='type', help=f'Filter which types of invoices to show: {{{", ".join(invoice_types.keys())}}}'),
    argument('-c', '--charges', mutex_group='grp', action='store_true', required=True, help='Show charges instead of invoices'),
    argument('-ct', '--charge-type', choices=charge_types, nargs='+', metavar='type', help='Filter which types of charges to show: {i|instance, v|volume, s|serverless}'),
    argument('-s', '--start-date', help='Start date (YYYY-MM-DD or timestamp)'),
    argument('-e', '--end-date', help='End date (YYYY-MM-DD or timestamp)'),
    argument('-l', '--limit', type=int, default=20, help='Number of results per page (default: 20, max: 100)'),
    argument('-t', '--next-token', help='Pagination token for next page'),
    argument('-f', '--format', choices=['table', 'tree'], default='table', help='Output format for charges (default: table)'),
    argument('-v', '--verbose', action='store_true', help='Include full Instance Charge details and Invoice Metadata (tree view only)'),
    argument('--latest-first', action='store_true', help='Sort by latest first'),
    usage="vastai show invoices-v1 [OPTIONS]",
    help="Get billing (invoices/charges) history reports with advanced filtering and pagination",
    epilog=deindent("""
        This command supports colored output and rich formatting if the 'rich' python module is installed!

        Examples:
            # Show the first 20 invoices in the last week  (note: default window is a 7 day period ending today)
            vastai show invoices-v1 --invoices

            # Show the first 50 charges over a 7 day period starting from 2025-11-30 in tree format
            vastai show invoices-v1 --charges -s 2025-11-30 -f tree -l 50

            # Show the first 20 invoices of specific types for the month of November 2025
            vastai show invoices-v1 -i -it stripe bitpay transfers --start-date 2025-11-01 --end-date 2025-11-30

            # Show the first 20 charges for only volumes and serverless instances between two dates, including all details and metadata
            vastai show invoices-v1 -c --charge-type v s -s 2025-11-01 -e 2025-11-05 --format tree --verbose

            # Get the next page of paginated invoices, limit to 50 per page  (note: type/date filters MUST match previous request for pagination to work)
            vastai show invoices-v1 --invoices --limit 50 --next-token eyJ2YWx1ZXMiOiB7ImlkIjogMjUwNzgyMzR9LCAib3NfcGFnZSI6IDB9

            # Show the last 10 instance (only) charges over a 7 day period ending in 2025-12-25, sorted by latest charges first
            vastai show invoices-v1 --charges -ct instance --end-date 2025-12-25 -l 10 --latest-first
    """)
)
def show__invoices_v1(args):
    output_lines = []
    try:
        from rich.prompt import Confirm
        has_rich = True
    except ImportError:
        output_lines.append("NOTE: To view results in color and table/tree format please install the 'rich' python module with 'pip install rich'\n")
        has_rich = False

    # Handle default start and end date values
    if not args.start_date and not args.end_date:
        args.end_date = int(time.time())  # Set end date to current time if both are missing
    if not args.start_date:
        args.start_date = args.end_date - 7 * 24*60*60  # Default to 7 days before given end date
    elif not args.end_date:
        args.end_date = args.start_date + 7 * 24*60*60  # Default to 7 days after given start date

    try:
        # Parse dates - handle both YYYY-MM-DD format and timestamps
        start_timestamp = to_timestamp_(args.start_date)
        end_timestamp = to_timestamp_(args.end_date)
    except Exception as e:
        print(f"Error parsing dates: {e}")
        print("Use format YYYY-MM-DD or UNIX timestamp")
        return

    if has_rich and not args.no_color:
        print("(use --no-color to disable colored output)\n")

    start_date = convert_timestamp_to_date(start_timestamp)
    end_date = convert_timestamp_to_date(end_timestamp)
    data_type = "Instance Charges" if args.charges else "Invoices"
    output_lines.append(f"Fetching {data_type} from {start_date} to {end_date}...")

    # Build request parameters
    date_col = 'day' if args.charges else 'when'
    params = {
        'select_filters': {date_col: {'gte': start_timestamp, 'lte': end_timestamp}},
        'latest_first': args.latest_first,
        'limit': min(args.limit, 100) if args.limit > 0 else 20,  # Enforce max limit of 100
    }
    if args.charges:
        params['format'] = args.format
        for ct in args.charge_type or []:
            filters = params['select_filters'].setdefault('type', {}).setdefault('in', [])
            if   ct in {'i','instance'}:   filters.append('instance')
            elif ct in {'v','volume'}:     filters.append('volume')
            elif ct in {'s','serverless'}: filters.append('serverless')

    if args.invoices:
        for it in args.invoice_type or []:
            filters = params['select_filters'].setdefault('service', {}).setdefault('in', [])
            filters.append(invoice_types[it])

    if args.next_token:
        params['after_token'] = args.next_token

    endpoint = '/api/v0/charges/' if args.charges else '/api/v1/invoices/'
    url = apiurl(args, endpoint, query_args=params)

    found_results, found_count = [], 0
    looping = True
    while looping:
        response = http_get(args, url)
        response.raise_for_status()
        response = response.json()

        found_results += response.get('results', [])
        found_count += response.get('count', 0)
        total = response.get('total', 0)
        next_token = response.get('next_token')

        if args.raw or has_rich is False:
            output_lines.append("Raw response:\n" + json.dumps(response, indent=2))
            if next_token:
                print(f"Next page token: {next_token}\n")
        elif not found_results:
            output_lines.append("No results found")
        else:  # Display results
            formatted_results = format_invoices_charges_results(args, deepcopy(found_results))
            if args.invoices:
                rich_obj = create_rich_table_for_invoices(formatted_results)
            elif args.format == 'tree':
                rich_obj = create_charges_tree(formatted_results)
            else:
                rich_obj = create_rich_table_for_charges(args, formatted_results)

            output_lines.append(rich_object_to_string(rich_obj, no_color=args.no_color))
            output_lines.append(f"Showing {found_count} of {total} results")
            if next_token:
                output_lines.append(f"Next page token: {next_token}\n")

        paging = print_or_page(args, '\n'.join(output_lines))

        if next_token and not paging:
            if has_rich:
                ans = Confirm.ask("Fetch next page?", show_default=False, default=False)
            else:
                ans = input("Fetch next page? (y/N): ").strip().lower() == 'y'
            if ans:
                params['after_token'] = next_token
                url = apiurl(args, endpoint, query_args=params)
                output_lines.clear()
                args.full = True
            else:
                looping = False
        else:
            looping = False


@parser.command(
    argument("-q", "--quiet", action="store_true", help="display information about user"),
    usage="vastai show user [OPTIONS]",
    help="Get current user data",
    epilog=deindent("""
        Shows stats for logged-in user. These include user balance, email, and ssh key. Does not show API key.
    """)
)
def show__user(args):
    """
    Shows stats for logged-in user. Does not show API key.

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    req_url = apiurl(args, "/users/current", {"owner": "me"});
    r = http_get(args, req_url);
    r.raise_for_status()
    user_blob = r.json()
    user_blob.pop("api_key")

    if args.raw:
        return user_blob
    else:
        display_table([user_blob], user_fields)


@parser.command(
    argument("--file", help="file path for params in json format", type=str),
    usage="vastai set user --file FILE",
    help="Update user data from json file",
    epilog=deindent("""

    Available fields:

    Name                            Type       Description

    ssh_key                         string
    paypal_email                    string
    wise_email                      string
    email                           string
    normalized_email                string
    username                        string
    fullname                        string
    billaddress_line1               string
    billaddress_line2               string
    billaddress_city                string
    billaddress_zip                 string
    billaddress_country             string
    billaddress_taxinfo             string
    balance_threshold_enabled       string
    balance_threshold               string
    autobill_threshold              string
    phone_number                    string
    """),
)
def set__user(args):
    params = None
    with open(args.file, 'r') as file:
        params = json.load(file)
    url = apiurl(args, "/users/")
    r = requests.put(url, headers=state.headers, json=params)
    r.raise_for_status()
    print(f"{r.json()}")


@parser.command(
    argument("recipient", help="email (or id) of recipient account", type=str),
    argument("amount",    help="$dollars of credit to transfer ", type=float),
    argument("--skip",    help="skip confirmation", action="store_true", default=False),
    usage="vastai transfer credit RECIPIENT AMOUNT",
    help="Transfer credits to another account",
    epilog=deindent("""
        Transfer (amount) credits to account with email (recipient).
    """),
)
def transfer__credit(args: argparse.Namespace):
    url = apiurl(args, "/commands/transfer_credit/")

    if not args.skip:
        print(f"Transfer ${args.amount} credit to account {args.recipient}?  This is irreversible.")
        ok = input("Continue? [y/n] ")
        if ok.strip().lower() != "y":
            return

    json_blob = {
        "sender":    "me",
        "recipient": args.recipient,
        "amount":    args.amount,
    }
    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_put(args, url,  headers=state.headers,json=json_blob)
    r.raise_for_status()

    if (r.status_code == 200):
        rj = r.json();
        if (rj["success"]):
            print(f"Sent {args.amount} to {args.recipient} ".format(r.json()))
        else:
            print(rj["msg"]);
    else:
        print(r.text);
        print("failed with error {r.status_code}".format(**locals()));
