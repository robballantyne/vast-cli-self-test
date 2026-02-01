"""Commands for managing volumes (local and network)."""

import time
import argparse

from vast_cli.parser import parser, argument, hidden_aliases
from vast_cli import state
from vast_cli.api.client import http_get, http_post, http_put, http_del
from vast_cli.api.helpers import apiurl
from vast_cli.display.formatting import deindent
from vast_cli.display.table import display_table
from vast_cli.query.parser import parse_query
from vast_cli.query.fields import (
    vol_offers_fields,
    vol_displayable_fields,
    nw_vol_displayable_fields,
    volume_fields,
    offers_alias,
    offers_mult,
)
from vast_cli.validation.validators import strip_strings


@parser.command(
    argument("id", help="id of volume offer", type=int),
    argument("-s", "--size",
             help="size in GB of volume. Default %(default)s GB.", default=15, type=float),
    argument("-n", "--name", help="Optional name of volume.", type=str),
    aliases=hidden_aliases(["create volume"]),
    usage="vastai volume create ID [options]",
    help="Create a new volume",
    epilog=deindent("""
        Creates a volume from an offer ID (which is returned from "search volumes"). Each offer ID can be used to create multiple volumes,
        provided the size of all volumes does not exceed the size of the offer.
    """)
)
def volume__create(args: argparse.Namespace):

    json_blob ={
        "size": int(args.size),
        "id": int(args.id)
    }
    if args.name:
        json_blob["name"] = args.name

    url = apiurl(args, "/volumes/")

    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_put(args, url,  headers=state.headers,json=json_blob)
    r.raise_for_status()
    if args.raw:
        return r
    else:
        print("Created. {}".format(r.json()))


@parser.command(
    argument("id", help="id of network volume offer", type=int),
    argument("-s", "--size",
             help="size in GB of network volume. Default %(default)s GB.", default=15, type=float),
    argument("-n", "--name", help="Optional name of network volume.", type=str),
    aliases=hidden_aliases(["create network-volume"]),
    usage="vastai network-volume create ID [options]",
    help="Create a new network volume",
    epilog=deindent("""
        Creates a network volume from an offer ID (which is returned from "search network volumes"). Each offer ID can be used to create multiple volumes,
        provided the size of all volumes does not exceed the size of the offer.
    """)
)
def network_volume__create(args: argparse.Namespace):

    json_blob ={
        "size": int(args.size),
        "id": int(args.id)
    }
    if args.name:
        json_blob["name"] = args.name

    url = apiurl(args, "/network_volumes/")

    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_put(args, url,  headers=state.headers,json=json_blob)
    r.raise_for_status()
    if args.raw:
        return r
    else:
        print("Created. {}".format(r.json()))


@parser.command(
    argument("id", help="id of volume contract", type=int),
    aliases=hidden_aliases(["delete volume"]),
    usage="vastai volume delete ID",
    help="Delete a volume",
    epilog=deindent("""
        Deletes volume with the given ID. All instances using the volume must be destroyed before the volume can be deleted.
    """)
)
def volume__delete(args: argparse.Namespace):
    url = apiurl(args, "/volumes/", query_args={"id": args.id})
    r = http_del(args, url, headers=state.headers)
    r.raise_for_status()
    if args.raw:
        return r
    else:
        print("Deleted. {}".format(r.json()))


@parser.command(
    argument("-n", "--no-default", action="store_true", help="Disable default query"),
    argument("--limit", type=int, help=""),
    argument("--storage", type=float, default=1.0, help="Amount of storage to use for pricing, in GiB. default=1.0GiB"),
    argument("-o", "--order", type=str, help="Comma-separated list of fields to sort on. postfix field with - to sort desc. ex: -o 'disk_space,inet_up-'.  default='score-'", default='score-'),
    argument("query", help="Query to search for. default: 'external=false verified=true disk_space>=1', pass -n to ignore default", nargs="*", default=None),
    aliases=hidden_aliases(["search volumes"]),
    usage="vastai volume search [--help] [--api-key API_KEY] [--raw] <query>",
    help="Search for volume offers using custom query",
    epilog=deindent("""
        Query syntax:

            query = comparison comparison...
            comparison = field op value
            field = <name of a field>
            op = one of: <, <=, ==, !=, >=, >, in, notin
            value = <bool, int, float, string> | 'any' | [value0, value1, ...]
            bool: True, False

        note: to pass '>' and '<' on the command line, make sure to use quotes
        note: to encode a string query value (ie for gpu_name), replace any spaces ' ' with underscore '_'

        Examples:

            # search for volumes with greater than 50GB of available storage and greater than 500 Mb/s upload and download speed
            vastai volume search "disk_space>50 inet_up>500 inet_down>500"

        Available fields:

              Name                  Type       Description

            cpu_arch:               string    host machine cpu architecture (e.g. amd64, arm64)
            cuda_vers:              float     machine max supported cuda version (based on driver version)
            datacenter:             bool      show only datacenter offers
            disk_bw:                float     disk read bandwidth, in MB/s
            disk_space:             float     disk storage space, in GB
            driver_version:         string    machine's nvidia/amd driver version as 3 digit string ex. "535.86.05"
            duration:               float     max rental duration in days
            geolocation:            string    Two letter country code. Works with operators =, !=, in, notin (e.g. geolocation not in ['XV','XZ'])
            gpu_arch:               string    host machine gpu architecture (e.g. nvidia, amd)
            gpu_name:               string    GPU model name (no quotes, replace spaces with underscores, ie: RTX_3090 rather than 'RTX 3090')
            has_avx:                bool      CPU supports AVX instruction set.
            id:                     int       volume offer unique ID
            inet_down:              float     internet download speed in Mb/s
            inet_up:                float     internet upload speed in Mb/s
            machine_id:             int       machine id of volume offer
            pci_gen:                float     PCIE generation
            pcie_bw:                float     PCIE bandwidth (CPU to GPU)
            reliability:            float     machine reliability score (see FAQ for explanation)
            storage_cost:           float     storage cost in $/GB/month
            static_ip:              bool      is the IP addr static/stable
            total_flops:            float     total TFLOPs from all GPUs
            ubuntu_version:         string    host machine ubuntu OS version
            verified:               bool      is the machine verified
    """),
)
def volume__search(args: argparse.Namespace):
    try:

        if args.no_default:
            query = {}
        else:
            query = {"verified": {"eq": True}, "external": {"eq": False}, "disk_space": {"gte": 1}}

        if args.query is not None:
            query = parse_query(args.query, query, vol_offers_fields, {}, offers_mult)

        order = []
        for name in args.order.split(","):
            name = name.strip()
            if not name: continue
            direction = "asc"
            field = name
            if name.strip("-") != name:
                direction = "desc"
                field = name.strip("-")
            if name.strip("+") != name:
                direction = "asc"
                field = name.strip("+")
            if field in offers_alias:
                field = offers_alias[field];
            order.append([field, direction])

        query["order"] = order
        if (args.limit):
            query["limit"] = int(args.limit)
        query["allocated_storage"] = args.storage
    except ValueError as e:
        print("Error: ", e)
        return 1

    json_blob = query

    if (args.explain):
        print("request json: ")
        print(json_blob)
    url = apiurl(args, "/volumes/search/")
    r = http_post(args, url, headers=state.headers, json=json_blob)

    r.raise_for_status()

    if (r.headers.get('Content-Type') != 'application/json'):
        print(f"invalid return Content-Type: {r.headers.get('Content-Type')}")
        return

    rows = r.json()["offers"]

    if args.raw:
        return rows
    else:
        display_table(rows, vol_displayable_fields)



@parser.command(
    argument("-n", "--no-default", action="store_true", help="Disable default query"),
    argument("--limit", type=int, help=""),
    argument("--storage", type=float, default=1.0, help="Amount of storage to use for pricing, in GiB. default=1.0GiB"),
    argument("-o", "--order", type=str, help="Comma-separated list of fields to sort on. postfix field with - to sort desc. ex: -o 'disk_space,inet_up-'.  default='score-'", default='score-'),
    argument("query", help="Query to search for. default: 'external=false verified=true disk_space>=1', pass -n to ignore default", nargs="*", default=None),
    aliases=hidden_aliases(["search network-volumes"]),
    usage="vastai network-volume search [--help] [--api-key API_KEY] [--raw] <query>",
    help="Search for network volume offers using custom query",
    epilog=deindent("""
        Query syntax:

            query = comparison comparison...
            comparison = field op value
            field = <name of a field>
            op = one of: <, <=, ==, !=, >=, >, in, notin
            value = <bool, int, float, string> | 'any' | [value0, value1, ...]
            bool: True, False

        note: to pass '>' and '<' on the command line, make sure to use quotes
        note: to encode a string query value (ie for gpu_name), replace any spaces ' ' with underscore '_'

        Examples:

            # search for volumes with greater than 50GB of available storage and greater than 500 Mb/s upload and download speed
            vastai network-volume search "disk_space>50 inet_up>500 inet_down>500"

        Available fields:

              Name                  Type       Description
            duration:               float     max rental duration in days
            geolocation:            string    Two letter country code. Works with operators =, !=, in, notin (e.g. geolocation not in ['XV','XZ'])
            id:                     int       volume offer unique ID
            inet_down:              float     internet download speed in Mb/s
            inet_up:                float     internet upload speed in Mb/s
            reliability:            float     machine reliability score (see FAQ for explanation)
            storage_cost:           float     storage cost in $/GB/month
            verified:               bool      is the machine verified
    """),
)
def network_volume__search(args: argparse.Namespace):
    try:

        if args.no_default:
            query = {}
        else:
            query = {"verified": {"eq": True}, "external": {"eq": False}, "disk_space": {"gte": 1}}

        if args.query is not None:
            query = parse_query(args.query, query, vol_offers_fields, {}, offers_mult)

        order = []
        for name in args.order.split(","):
            name = name.strip()
            if not name: continue
            direction = "asc"
            field = name
            if name.strip("-") != name:
                direction = "desc"
                field = name.strip("-")
            if name.strip("+") != name:
                direction = "asc"
                field = name.strip("+")
            if field in offers_alias:
                field = offers_alias[field];
            order.append([field, direction])

        query["order"] = order
        if (args.limit):
            query["limit"] = int(args.limit)
        query["allocated_storage"] = args.storage
    except ValueError as e:
        print("Error: ", e)
        return 1

    json_blob = query

    if (args.explain):
        print("request json: ")
        print(json_blob)
    url = apiurl(args, "/network_volumes/search/")
    r = http_post(args, url, headers=state.headers, json=json_blob)

    r.raise_for_status()

    if (r.headers.get('Content-Type') != 'application/json'):
        print(f"invalid return Content-Type: {r.headers.get('Content-Type')}")
        return

    rows = r.json()["offers"]

    if args.raw:
        return rows
    else:
        display_table(rows, nw_vol_displayable_fields)


@parser.command(
    argument("-t", "--type", help="volume type to display. Default to all. Possible values are \"local\", \"all\", \"network\"", type=str, default="all"),
    aliases=hidden_aliases(["show volumes"]),
    usage="vastai volume list [OPTIONS]",
    help="Show stats on owned volumes.",
    epilog=deindent("""
        Show stats on owned volumes
    """)
)
def volume__list(args: argparse.Namespace):
    types = {
        "local": "local_volume",
        "network": "network_volume",
        "all": "all_volume"
    }
    type = types.get(args.type, "all")
    req_url = apiurl(args, "/volumes", {"owner": "me", "type" : type});
    r = http_get(args, req_url)
    r.raise_for_status()
    rows = r.json()["volumes"]
    processed = []
    for row in rows:
        row = {k: strip_strings(v) for k, v in row.items()}
        row['duration'] = time.time() - row['start_date']
        processed.append(row)
    if args.raw:
        return processed
    else:
        display_table(processed, volume_fields, replace_spaces=False)
