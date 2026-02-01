"""Instance management commands."""

import json
import os
import re
import sys
import time
import argparse
from typing import List
from datetime import datetime, timedelta

import requests

from vast_cli.parser import parser, argument
from vast_cli import state
from vast_cli.api.client import http_get, http_post, http_put, http_del
from vast_cli.api.helpers import apiurl, apiheaders
from vast_cli.config import server_url_default, CACHE_FILE, CACHE_DURATION
from vast_cli.display.formatting import deindent
from vast_cli.display.table import display_table
from vast_cli.query.fields import instance_fields, offers_fields, offers_alias, offers_mult
from vast_cli.query.parser import parse_query
from vast_cli.validation.validators import (
    parse_env, validate_frequency_values, default_start_date, default_end_date,
    parse_day_cron_style, parse_hour_cron_style, strip_strings,
    validate_volume_params, validate_portal_config,
    convert_dates_to_timestamps, convert_timestamp_to_date,
)


# ---------------------------------------------------------------------------
# Helper functions used by instance commands
# ---------------------------------------------------------------------------

def get_runtype(args):
    runtype = 'ssh'
    if args.args:
        runtype = 'args'
    if (args.args == '') or (args.args == ['']) or (args.args == []):
        runtype = 'args'
        args.args = None
    if not args.jupyter and (args.jupyter_dir or args.jupyter_lab):
        args.jupyter = True
    if args.jupyter and runtype == 'args':
        print("Error: Can't use --jupyter and --args together. Try --onstart or --onstart-cmd instead of --args.", file=sys.stderr)
        return 1

    if args.jupyter:
        runtype = 'jupyter_direc ssh_direc ssh_proxy' if args.direct else 'jupyter_proxy ssh_proxy'
    elif args.ssh:
        runtype = 'ssh_direc ssh_proxy' if args.direct else 'ssh_proxy'

    return runtype


def add_scheduled_job(args, req_json, cli_command, api_endpoint, request_method, instance_id, contract_end_date=None):
    start_timestamp, end_timestamp = convert_dates_to_timestamps(args)
    if args.end_date is None:
        end_timestamp=contract_end_date
        args.end_date = convert_timestamp_to_date(contract_end_date)

    if start_timestamp >= end_timestamp:
        raise ValueError("--start_date must be less than --end_date.")

    day, hour, frequency = args.day, args.hour, args.schedule

    schedule_job_url = apiurl(args, f"/commands/schedule_job/")

    request_body = {
                "start_time": start_timestamp,
                "end_time": end_timestamp,
                "api_endpoint": api_endpoint,
                "request_method": request_method,
                "request_body": req_json,
                "day_of_the_week": day,
                "hour_of_the_day": hour,
                "frequency": frequency,
                "instance_id": instance_id
            }
                # Send a POST request
    response = requests.post(schedule_job_url, headers=state.headers, json=request_body)

    if args.explain:
        print("request json: ")
        print(request_body)

        # Handle the response based on the status code
    if response.status_code == 200:
        print(f"add_scheduled_job insert: success - Scheduling {frequency} job to {cli_command} from {args.start_date} UTC to {args.end_date} UTC")
    elif response.status_code == 401:
        print(f"add_scheduled_job insert: failed status_code: {response.status_code}. It could be because you aren't using a valid api_key.")
    elif response.status_code == 422:
        user_input = input("Existing scheduled job found. Do you want to update it (y|n)? ")
        if user_input.strip().lower() == "y":
            scheduled_job_id = response.json()["scheduled_job_id"]
            schedule_job_url = apiurl(args, f"/commands/schedule_job/{scheduled_job_id}/")
            response = _update_scheduled_job(cli_command, schedule_job_url, frequency, args.start_date, args.end_date, request_body)
        else:
            print("Job update aborted by the user.")
    else:
            # print(r.text)
        print(f"add_scheduled_job insert: failed error: {response.status_code}. Response body: {response.text}")


def _update_scheduled_job(cli_command, schedule_job_url, frequency, start_date, end_date, request_body):
    response = requests.put(schedule_job_url, headers=state.headers, json=request_body)

        # Raise an exception for HTTP errors
    response.raise_for_status()
    if response.status_code == 200:
        print(f"add_scheduled_job update: success - Scheduling {frequency} job to {cli_command} from {start_date} UTC to {end_date} UTC")
        print(response.json())
    elif response.status_code == 401:
        print(f"add_scheduled_job update: failed status_code: {response.status_code}. It could be because you aren't using a valid api_key.")
    else:
        print(f"add_scheduled_job update: failed error: {response.status_code}. Response body: {response.text}")


def exec_with_threads(f, args, nt=16, max_retries=5):
    import math
    from concurrent.futures import ThreadPoolExecutor

    def worker(sub_args):
        for arg in sub_args:
            retries = 0
            while retries <= max_retries:
                try:
                    result = None
                    if isinstance(arg,tuple):
                        result = f(*arg)
                    else:
                        result = f(arg)
                    if result:  # Assuming a truthy return value means success
                        break
                except Exception as e:
                    print(str(e))
                    pass
                retries += 1
                stime = 0.25 * 1.3 ** retries
                print(f"retrying in {stime}s")
                time.sleep(stime)  # Exponential backoff

    # Split args into nt sublists
    args_per_thread = math.ceil(len(args) / nt)
    sublists = [args[i:i + args_per_thread] for i in range(0, len(args), args_per_thread)]

    with ThreadPoolExecutor(max_workers=nt) as executor:
        executor.map(worker, sublists)


def split_into_sublists(lst, k):
    # Calculate the size of each sublist
    sublist_size = (len(lst) + k - 1) // k

    # Create the sublists using list comprehension
    sublists = [lst[i:i + sublist_size] for i in range(0, len(lst), sublist_size)]

    return sublists


def split_list(lst, k):
    """
    Splits a list into sublists of maximum size k.
    """
    return [lst[i:i + k] for i in range(0, len(lst), k)]


def start_instance(id, args):

    json_blob ={"state": "running"}
    if isinstance(id,list):
        url = apiurl(args, "/instances/")
        json_blob["ids"] = id
    else:
        url = apiurl(args, "/instances/{id}/".format(id=id))

    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_put(args, url,  headers=state.headers,json=json_blob)
    r.raise_for_status()

    if (r.status_code == 200):
        rj = r.json()
        if (rj["success"]):
            print("starting instance {id}.".format(**(locals())))
        else:
            print(rj["msg"])
        return True
    else:
        print(r.text)
        print("failed with error {r.status_code}".format(**locals()))
    return False


def stop_instance(id, args):

    json_blob ={"state": "stopped"}
    if isinstance(id,list):
        url = apiurl(args, "/instances/")
        json_blob["ids"] = id
    else:
        url = apiurl(args, "/instances/{id}/".format(id=id))

    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_put(args, url,  headers=state.headers,json=json_blob)
    r.raise_for_status()

    if (r.status_code == 200):
        rj = r.json()
        if (rj["success"]):
            print("stopping instance {id}.".format(**(locals())))
        else:
            print(rj["msg"])
        return True
    else:
        print(r.text)
        print("failed with error {r.status_code}".format(**locals()))
    return False


def destroy_instance(id, args):
    url = apiurl(args, "/instances/{id}/".format(id=id))
    r = http_del(args, url, headers=state.headers,json={})
    r.raise_for_status()
    if args.raw:
        return r
    elif (r.status_code == 200):
        rj = r.json();
        if (rj["success"]):
            print("destroying instance {id}.".format(**(locals())));
        else:
            print(rj["msg"]);
    else:
        print(r.text);
        print("failed with error {r.status_code}".format(**locals()));


# ---------------------------------------------------------------------------
# Helper functions used by launch__instance
# ---------------------------------------------------------------------------

def _get_gpu_names() -> List[str]:
    """Returns a set of GPU names available on Vast.ai, with results cached for 24 hours."""

    def is_cache_valid() -> bool:
        """Checks if the cache file exists and is less than 24 hours old."""
        if not os.path.exists(CACHE_FILE):
            return False
        cache_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(CACHE_FILE))
        return cache_age < CACHE_DURATION

    if is_cache_valid():
        with open(CACHE_FILE, "r") as file:
            gpu_names = json.load(file)
    else:
        endpoint = "/api/v0/gpu_names/unique/"
        url = f"{server_url_default}{endpoint}"
        r = requests.get(url, headers={})
        r.raise_for_status()  # Will raise an exception for HTTP errors
        gpu_names = r.json()
        with open(CACHE_FILE, "w") as file:
            json.dump(gpu_names, file)

    formatted_gpu_names = [
        name.replace(" ", "_").replace("-", "_") for name in gpu_names['gpu_names']
    ]
    return formatted_gpu_names


REGIONS = {
"North_America": "[AG, BS, BB, BZ, CA, CR, CU, DM, DO, SV, GD, GT, HT, HN, JM, MX, NI, PA, KN, LC, VC, TT, US]",
"South_America": "[AR, BO, BR, CL, CO, EC, FK, GF, GY, PY, PE, SR, UY, VE]",
"Europe": "[AL, AD, AT, BY, BE, BA, BG, HR, CY, CZ, DK, EE, FI, FR, DE, GR, HU, IS, IE, IT, LV, LI, LT, LU, MT, MD, MC, ME, NL, MK, NO, PL, PT, RO, RU, SM, RS, SK, SI, ES, SE, CH, UA, GB, VA, XK]",
"Asia": "[AF, AM, AZ, BH, BD, BT, BN, KH, CN, GE, IN, ID, IR, IQ, IL, JP, JO, KZ, KW, KG, LA, LB, MY, MV, MN, MM, NP, KP, OM, PK, PH, QA, SA, SG, KR, LK, SY, TW, TJ, TH, TL, TR, TM, AE, UZ, VN, YE, HK, MO]",
"Oceania": "[AS, AU, CK, FJ, PF, GU, KI, MH, FM, NR, NC, NZ, NU, MP, PW, PG, PN, WS, SB, TK, TO, TV, VU, WF]",
"Africa": "[DZ, AO, BJ, BW, BF, BI, CV, CM, CF, TD, KM, CG, CD, CI, DJ, EG, GQ, ER, SZ, ET, GA, GM, GH, GN, GW, KE, LS, LR, LY, MG, MW, ML, MR, MU, MA, MZ, NA, NE, NG, RW, ST, SN, SC, SL, SO, ZA, SS, SD, TZ, TG, TN, UG, ZM, ZW]"
}

def _is_valid_region(region):
    """region is valid if it is a key in REGIONS or a string list of country codes."""
    if region in REGIONS:
        return True
    if region.startswith("[") and region.endswith("]"):
        country_codes = region[1:-1].split(',')
        return all(len(code.strip()) == 2 for code in country_codes)
    return False

def _parse_region(region):
    """Returns a string in a list format of two-char country codes."""
    if region in REGIONS:
        return REGIONS[region]
    return region


# ===========================================================================
# Instance commands
# ===========================================================================

@parser.command(
    argument("id", help="id of instance type to launch (returned from search offers)", type=int),
    argument("--template_hash", help="Create instance from template info", type=str),
    argument("--user", help="User to use with docker create. This breaks some images, so only use this if you are certain you need it.", type=str),
    argument("--disk", help="size of local disk partition in GB", type=float, default=10),
    argument("--image", help="docker container image to launch", type=str),
    argument("--login", help="docker login arguments for private repo authentication, surround with '' ", type=str),
    argument("--label", help="label to set on the instance", type=str),
    argument("--onstart", help="filename to use as onstart script", type=str),
    argument("--onstart-cmd", help="contents of onstart script as single argument", type=str),
    argument("--entrypoint", help="override entrypoint for args launch instance", type=str),
    argument("--ssh",     help="Launch as an ssh instance type", action="store_true"),
    argument("--jupyter", help="Launch as a jupyter instance instead of an ssh instance", action="store_true"),
    argument("--direct",  help="Use (faster) direct connections for jupyter & ssh", action="store_true"),
    argument("--jupyter-dir", help="For runtype 'jupyter', directory in instance to use to launch jupyter. Defaults to image's working directory", type=str),
    argument("--jupyter-lab", help="For runtype 'jupyter', Launch instance with jupyter lab", action="store_true"),
    argument("--lang-utf8", help="Workaround for images with locale problems: install and generate locales before instance launch, and set locale to C.UTF-8", action="store_true"),
    argument("--python-utf8", help="Workaround for images with locale problems: set python's locale to C.UTF-8", action="store_true"),
    argument("--extra", help=argparse.SUPPRESS),
    argument("--env",   help="env variables and port mapping options, surround with '' ", type=str),
    argument("--args",  nargs=argparse.REMAINDER, help="list of arguments passed to container ENTRYPOINT. Onstart is recommended for this purpose. (must be last argument)"),
    #argument("--create-from", help="Existing instance id to use as basis for new instance. Instance configuration should usually be identical, as only the difference from the base image is copied.", type=str),
    argument("--force", help="Skip sanity checks when creating from an existing instance", action="store_true"),
    argument("--cancel-unavail", help="Return error if scheduling fails (rather than creating a stopped instance)", action="store_true"),
    argument("--bid_price", help="(OPTIONAL) create an INTERRUPTIBLE instance with per machine bid price in $/hour", type=float),
    argument("--create-volume", metavar="VOLUME_ASK_ID", help="Create a new local volume using an ID returned from the \"search volumes\" command and link it to the new instance", type=int),
    argument("--link-volume", metavar="EXISTING_VOLUME_ID", help="ID of an existing rented volume to link to the instance during creation. (returned from \"show volumes\" cmd)", type=int),
    argument("--volume-size", help="Size of the volume to create in GB. Only usable with --create-volume (default 15GB)", type=int),
    argument("--mount-path", help="The path to the volume from within the new instance container. e.g. /root/volume", type=str),
    argument("--volume-label", help="(optional) A name to give the new volume. Only usable with --create-volume", type=str),

    usage="vastai create instance ID [OPTIONS] [--args ...]",
    help="Create a new instance",
    epilog=deindent("""
        Performs the same action as pressing the "RENT" button on the website at https://console.vast.ai/create/
        Creates an instance from an offer ID (which is returned from "search offers"). Each offer ID can only be used to create one instance.
        Besides the offer ID, you must pass in an '--image' argument as a minimum.

        If you use args/entrypoint launch mode, we create a container from your image as is, without attempting to inject ssh and or jupyter.
        If you use the args launch mode, you can override the entrypoint with --entrypoint, and pass arguments to the entrypoint with --args.
        If you use --args, that must be the last argument, as any following tokens are consumed into the args string.
        For ssh/jupyter launch types, use --onstart-cmd to pass in startup script, instead of --entrypoint and --args.

        Examples:

        # create an on-demand instance with the PyTorch (cuDNN Devel) template and 64GB of disk
        vastai create instance 384826 --template_hash 661d064bbda1f2a133816b6d55da07c3 --disk 64

        # create an on-demand instance with the pytorch/pytorch image, 40GB of disk, open 8081 udp, direct ssh, set hostname to billybob, and a small onstart script
        vastai create instance 6995713 --image pytorch/pytorch --disk 40 --env '-p 8081:8081/udp -h billybob' --ssh --direct --onstart-cmd "env | grep _ >> /etc/environment; echo 'starting up'";

        # create an on-demand instance with the bobsrepo/pytorch:latest image, 20GB of disk, open 22, 8080, jupyter ssh, and set some env variables
        vastai create instance 384827  --image bobsrepo/pytorch:latest --login '-u bob -p 9d8df!fd89ufZ docker.io' --jupyter --direct --env '-e TZ=PDT -e XNAME=XX4 -p 22:22 -p 8080:8080' --disk 20

        # create an on-demand instance with the pytorch/pytorch image, 40GB of disk, override the entrypoint to bash and pass bash a simple command to keep the instance running. (args launch without ssh/jupyter)
        vastai create instance 5801802 --image pytorch/pytorch --disk 40 --onstart-cmd 'bash' --args -c 'echo hello; sleep infinity;'

        # create an interruptible (spot) instance with the PyTorch (cuDNN Devel) template, 64GB of disk, and a bid price of $0.10/hr
        vastai create instance 384826 --template_hash 661d064bbda1f2a133816b6d55da07c3 --disk 64 --bid_price 0.1

        Return value:
        Returns a json reporting the instance ID of the newly created instance:
        {'success': True, 'new_contract': 7835610}
    """),
)
def create__instance(args: argparse.Namespace):
    """Performs the same action as pressing the "RENT" button on the website at https://console.vast.ai/create/.

    :param argparse.Namespace args: Namespace with many fields relevant to the endpoint.
    """

    if args.onstart:
        with open(args.onstart, "r") as reader:
            args.onstart_cmd = reader.read()
    if args.onstart_cmd is None:
        args.onstart_cmd = args.entrypoint

    runtype = None
    json_blob ={
        "client_id": "me",
        "image": args.image,
        "env" : parse_env(args.env),
        "price": args.bid_price,
        "disk": args.disk,
        "label": args.label,
        "extra": args.extra,
        "onstart": args.onstart_cmd,
        "image_login": args.login,
        "python_utf8": args.python_utf8,
        "lang_utf8": args.lang_utf8,
        "use_jupyter_lab": args.jupyter_lab,
        "jupyter_dir": args.jupyter_dir,
        #"create_from": args.create_from,
        "force": args.force,
        "cancel_unavail": args.cancel_unavail,
        "template_hash_id" : args.template_hash,
        "user": args.user
    }

    if args.create_volume or args.link_volume:
        volume_info = validate_volume_params(args)
        json_blob["volume_info"] = volume_info

    if args.template_hash is None:
        runtype = get_runtype(args)
        if runtype == 1:
            return 1
        json_blob["runtype"] = runtype

    if (args.args != None):
        json_blob["args"] = args.args

    if "PORTAL_CONFIG" in json_blob["env"]:
        validate_portal_config(json_blob)

    #print(f"put asks/{args.id}/  runtype:{runtype}")
    url = apiurl(args, "/asks/{id}/".format(id=args.id))

    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_put(args, url,  headers=state.headers,json=json_blob)
    r.raise_for_status()
    if args.raw:
        return r
    else:
        print("Started. {}".format(r.json()))


@parser.command(
    argument("id", help="id of instance type to change bid", type=int),
    argument("--price", help="per machine bid price in $/hour", type=float),
    argument("--schedule", choices=["HOURLY", "DAILY", "WEEKLY"], help="try to schedule a command to run hourly, daily, or monthly. Valid values are HOURLY, DAILY, WEEKLY  For ex. --schedule DAILY"),
    argument("--start_date", type=str, default=default_start_date(), help="Start date/time in format 'YYYY-MM-DD HH:MM:SS PM' (UTC). Default is now. (optional)"),
    argument("--end_date", type=str, default=default_end_date(), help="End date/time in format 'YYYY-MM-DD HH:MM:SS PM' (UTC). Default is 7 days from now. (optional)"),
    argument("--day", type=parse_day_cron_style, help="Day of week you want scheduled job to run on (0-6, where 0=Sunday) or \"*\". Default will be 0. For ex. --day 0", default=0),
    argument("--hour", type=parse_hour_cron_style, help="Hour of day you want scheduled job to run on (0-23) or \"*\" (UTC). Default will be 0. For ex. --hour 16", default=0),
    usage="vastai change bid id [--price PRICE]",
    help="Change the bid price for a spot/interruptible instance",
    epilog=deindent("""
        Change the current bid price of instance id to PRICE.
        If PRICE is not specified, then a winning bid price is used as the default.
    """),
)
def change__bid(args: argparse.Namespace):
    """Alter the bid with id contained in args.

    :param argparse.Namespace args: should supply all the command-line options
    :rtype int:
    """
    url = apiurl(args, "/instances/bid_price/{id}/".format(id=args.id))

    json_blob = {"client_id": "me", "price": args.price,}
    if (args.explain):
        print("request json: ")
        print(json_blob)

    if (args.schedule):
        validate_frequency_values(args.day, args.hour, args.schedule)
        cli_command = "change bid"
        api_endpoint = "/api/v0/instances/bid_price/{id}/".format(id=args.id)
        json_blob["instance_id"] = args.id
        add_scheduled_job(args, json_blob, cli_command, api_endpoint, "PUT", instance_id=args.id)
        return

    r = http_put(args, url, headers=state.headers, json=json_blob)
    r.raise_for_status()
    print("Per gpu bid price changed".format(r.json()))


@parser.command(
    argument("id", help="id of instance to delete", type=int),
    usage="vastai destroy instance id [-h] [--api-key API_KEY] [--raw]",
    help="Destroy an instance (irreversible, deletes data)",
    epilog=deindent("""
        Perfoms the same action as pressing the "DESTROY" button on the website at https://console.vast.ai/instances/
        Example: vastai destroy instance 4242
    """),
)
def destroy__instance(args):
    """Perfoms the same action as pressing the "DESTROY" button on the website at https://console.vast.ai/instances/.

    :param argparse.Namespace args: should supply all the command-line options
    """
    destroy_instance(args.id,args)

@parser.command(
    argument("ids", help="ids of instance to destroy", type=int, nargs='+'),
    usage="vastai destroy instances [--raw] <id>",
    help="Destroy a list of instances (irreversible, deletes data)",
)
def destroy__instances(args):
    """
    """
    for id in args.ids:
        destroy_instance(id, args)

@parser.command(
    argument("id", help="id of instance to execute on", type=int),
    argument("COMMAND", help="bash command surrounded by single quotes",  type=str),
    argument("--schedule", choices=["HOURLY", "DAILY", "WEEKLY"], help="try to schedule a command to run hourly, daily, or monthly. Valid values are HOURLY, DAILY, WEEKLY  For ex. --schedule DAILY"),
    argument("--start_date", type=str, default=default_start_date(), help="Start date/time in format 'YYYY-MM-DD HH:MM:SS PM' (UTC). Default is now. (optional)"),
    argument("--end_date", type=str, default=default_end_date(), help="End date/time in format 'YYYY-MM-DD HH:MM:SS PM' (UTC). Default is 7 days from now. (optional)"),
    argument("--day", type=parse_day_cron_style, help="Day of week you want scheduled job to run on (0-6, where 0=Sunday) or \"*\". Default will be 0. For ex. --day 0", default=0),
    argument("--hour", type=parse_hour_cron_style, help="Hour of day you want scheduled job to run on (0-23) or \"*\" (UTC). Default will be 0. For ex. --hour 16", default=0),
    usage="vastai execute id COMMAND",
    help="Execute a (constrained) remote command on a machine",
    epilog=deindent("""
        Examples:
          vastai execute 99999 'ls -l -o -r'
          vastai execute 99999 'rm -r home/delete_this.txt'
          vastai execute 99999 'du -d2 -h'

        available commands:
          ls                 List directory contents
          rm                 Remote files or directories
          du                 Summarize device usage for a set of files

        Return value:
        Returns the output of the command which was executed on the instance, if successful. May take a few seconds to retrieve the results.

    """),
)
def execute(args):
    """Execute a (constrained) remote command on a machine.
    :param argparse.Namespace args: should supply all the command-line options
    """
    url = apiurl(args, "/instances/command/{id}/".format(id=args.id))
    json_blob={"command": args.COMMAND}
    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_put(args, url,  headers=state.headers,json=json_blob )
    r.raise_for_status()

    if (args.schedule):
        validate_frequency_values(args.day, args.hour, args.schedule)
        cli_command = "execute"
        api_endpoint = "/api/v0/instances/command/{id}/".format(id=args.id)
        json_blob["instance_id"] = args.id
        add_scheduled_job(args, json_blob, cli_command, api_endpoint, "PUT", instance_id=args.id)
        return

    if (r.status_code == 200):
        rj = r.json()
        if (rj["success"]):
            for i in range(0,30):
                time.sleep(0.3)
                url = rj["result_url"]
                r = requests.get(url)
                if (r.status_code == 200):
                    filtered_text = r.text.replace(rj["writeable_path"], '');
                    print(filtered_text)
                    break
        else:
            print(rj);
    else:
        print(r.text);
        print("failed with error {r.status_code}".format(**locals()));


@parser.command(
    argument("id", help="id of instance to label", type=int),
    argument("label", help="label to set", type=str),
    usage="vastai label instance <id> <label>",
    help="Assign a string label to an instance",
)
def label__instance(args):
    """

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    url       = apiurl(args, "/instances/{id}/".format(id=args.id))
    json_blob = { "label": args.label }
    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_put(args, url,  headers=state.headers,json=json_blob)
    r.raise_for_status()

    rj = r.json();
    if rj["success"]:
        print("label for {args.id} set to {args.label}.".format(**(locals())));
    else:
        print(rj["msg"]);


@parser.command(
    argument("-g", "--gpu-name", type=str, required=True, choices=_get_gpu_names(), help="Name of the GPU model, replace spaces with underscores"),
    argument("-n", "--num-gpus", type=str, required=True, choices=["1", "2", "4", "8", "12", "14"], help="Number of GPUs required"),
    argument("-r", "--region", type=str, help="Geographical location of the instance"),
    argument("-i", "--image", required=True, help="Name of the image to use for instance"),
    argument("-d", "--disk", type=float, default=16.0, help="Disk space required in GB"),
    argument("--limit", default=3, type=int, help=""),
    argument("-o", "--order", type=str, help="Comma-separated list of fields to sort on. postfix field with - to sort desc. ex: -o 'num_gpus,total_flops-'.  default='score-'", default='score-'),
    argument("--login", help="docker login arguments for private repo authentication, surround with '' ", type=str),
    argument("--label", help="label to set on the instance", type=str),
    argument("--onstart", help="filename to use as onstart script", type=str),
    argument("--onstart-cmd", help="contents of onstart script as single argument", type=str),
    argument("--entrypoint", help="override entrypoint for args launch instance", type=str),
    argument("--ssh",     help="Launch as an ssh instance type", action="store_true"),
    argument("--jupyter", help="Launch as a jupyter instance instead of an ssh instance", action="store_true"),
    argument("--direct",  help="Use (faster) direct connections for jupyter & ssh", action="store_true"),
    argument("--jupyter-dir", help="For runtype 'jupyter', directory in instance to use to launch jupyter. Defaults to image's working directory", type=str),
    argument("--jupyter-lab", help="For runtype 'jupyter', Launch instance with jupyter lab", action="store_true"),
    argument("--lang-utf8", help="Workaround for images with locale problems: install and generate locales before instance launch, and set locale to C.UTF-8", action="store_true"),
    argument("--python-utf8", help="Workaround for images with locale problems: set python's locale to C.UTF-8", action="store_true"),
    argument("--extra", help=argparse.SUPPRESS),
    argument("--env",   help="env variables and port mapping options, surround with '' ", type=str),
    argument("--args",  nargs=argparse.REMAINDER, help="list of arguments passed to container ENTRYPOINT. Onstart is recommended for this purpose. (must be last argument)"),
    argument("--force", help="Skip sanity checks when creating from an existing instance", action="store_true"),
    argument("--cancel-unavail", help="Return error if scheduling fails (rather than creating a stopped instance)", action="store_true"),
    argument("--template_hash",   help="template hash which contains all relevant information about an instance. This can be used as a replacement for other parameters describing the instance configuration", type=str),
    usage="vastai launch instance [--help] [--api-key API_KEY] <gpu_name> <num_gpus> <image> [geolocation] [disk_space]",
    help="Launch the top instance from the search offers based on the given parameters",
    epilog=deindent("""
        Launches an instance based on the given parameters. The instance will be created with the top offer from the search results.
        Besides the gpu_name and num_gpus, you must pass in an '--image' argument as a minimum.

        If you use args/entrypoint launch mode, we create a container from your image as is, without attempting to inject ssh and or jupyter.
        If you use the args launch mode, you can override the entrypoint with --entrypoint, and pass arguments to the entrypoint with --args.
        If you use --args, that must be the last argument, as any following tokens are consumed into the args string.
        For ssh/jupyter launch types, use --onstart-cmd to pass in startup script, instead of --entrypoint and --args.

        Examples:

            # launch a single RTX 3090 instance with the pytorch image and 16 GB of disk space located anywhere
            python vast.py launch instance -g RTX_3090 -n 1 -i pytorch/pytorch

            # launch a 4x RTX 3090 instance with the pytorch image and 32 GB of disk space located in North America
            python vast.py launch instance -g RTX_3090 -n 4 -i pytorch/pytorch -d 32.0 -r North_America

        Available fields:

            Name                    Type      Description

            num_gpus:               int       # of GPUs
            gpu_name:               string    GPU model name
            region:                 string    Region of the instance
            image:                  string    Docker image name
            disk_space:             float     Disk space in GB
            ssh, jupyter, direct:   bool      Flags to specify the instance type and connection method.
            env:                    str       Environment variables and port mappings, encapsulated in single quotes.
            args:                   list      Arguments passed to the container's ENTRYPOINT, used only if '--args' is specified.
    """),
)
def launch__instance(args):
    """Allows for a more streamlined and simplified way to create an instance.

    :param argparse.Namespace args: Namespace with many fields relevant to the endpoint.
    """
    args_query = f"num_gpus={args.num_gpus} gpu_name={args.gpu_name}"

    if args.region:
        if not _is_valid_region(args.region):
            print("Invalid region or country codes provided.")
            return
        region_query = _parse_region(args.region)
        args_query += f" geolocation in {region_query}"

    if args.disk:
        args_query += f" disk_space>={args.disk}"

    base_query = {"verified": {"eq": True}, "external": {"eq": False}, "rentable": {"eq": True}, "rented": {"eq": False}}
    query = parse_query(args_query, base_query, offers_fields, offers_alias, offers_mult)

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
        #print(f"{field} {name} {direction}")
        if field in offers_alias:
            field = offers_alias[field];
        order.append([field, direction])
    query["order"] = order
    query["type"] = "on-demand"
    # For backwards compatibility, support --type=interruptible option
    if query["type"] == 'interruptible':
        query["type"] = 'bid'
    if (args.limit):
        query["limit"] = int(args.limit)
    query["allocated_storage"] = args.disk

    if args.onstart:
        with open(args.onstart, "r") as reader:
            args.onstart_cmd = reader.read()

    if args.onstart_cmd is None:
        args.onstart_cmd = args.entrypoint

    json_blob = {
        "client_id": "me",
        "gpu_name": args.gpu_name,
        "num_gpus": args.num_gpus,
        "region": args.region,
        "image": args.image,
        "disk": args.disk,
        "q" : query,
        "env" : parse_env(args.env),
        "disk": args.disk,
        "label": args.label,
        "extra": args.extra,
        "onstart": args.onstart_cmd,
        "image_login": args.login,
        "python_utf8": args.python_utf8,
        "lang_utf8": args.lang_utf8,
        "use_jupyter_lab": args.jupyter_lab,
        "jupyter_dir": args.jupyter_dir,
        "force": args.force,
        "cancel_unavail": args.cancel_unavail,
        "template_hash_id" : args.template_hash
    }
    # don't send runtype with template_hash
    if args.template_hash is None:
        runtype = get_runtype(args)
        if runtype == 1:
            return 1
        json_blob["runtype"] = runtype

    if (args.args != None):
        json_blob["args"] = args.args

    url = apiurl(args, "/launch_instance/".format())

    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_put(args, url, headers=state.headers, json=json_blob)
    try:
        r.raise_for_status()  # This will raise an exception for HTTP error codes
        response_data = r.json()
        if args.raw:
            return r
        else:
            print("Started. {}".format(r.json()))
        if response_data.get('success'):
            print(f"Instance launched successfully: {response_data.get('new_contract')}")
        else:
            print(f"Failed to launch instance: {response_data.get('error')}, {response_data.get('message')}")
    except requests.exceptions.HTTPError as err:
        print(f"HTTP error occurred: {err}")
    except Exception as err:
        print(f"An error occurred: {err}")


@parser.command(
    argument("INSTANCE_ID", help="id of instance", type=int),
    argument("--tail", help="Number of lines to show from the end of the logs (default '1000')", type=str),
    argument("--filter", help="Grep filter for log entries", type=str),
    argument("--daemon-logs", help="Fetch daemon system logs instead of container logs", action="store_true"),
    usage="vastai logs INSTANCE_ID [OPTIONS] ",
    help="Get the logs for an instance",
)
def logs(args):
    """Get the logs for an instance
    :param argparse.Namespace args: should supply all the command-line options
    """
    url = apiurl(args, "/instances/request_logs/{id}/".format(id=args.INSTANCE_ID))
    json_blob = {'filter': args.filter} if args.filter else {}
    if args.tail:
        json_blob.update({'tail': args.tail})
    if args.daemon_logs:
        json_blob.update({'daemon_logs': 'true'})
    if args.explain:
        print("request json: ")
        print(json_blob)

    r = http_put(args, url, headers=state.headers, json=json_blob)
    r.raise_for_status()

    if r.status_code == 200:
        rj = r.json()
        for i in range(0, 30):
            time.sleep(0.3)
            url = rj["result_url"]
            print(f"waiting on logs for instance {args.INSTANCE_ID} fetching from {url}")
            r = requests.get(url)
            if r.status_code == 200:
                result = r.text
                cleaned_text = re.sub(r'\n\s*\n', '\n', result)
                print(cleaned_text)
                break
        else:
            print(rj["msg"])
    else:
        print(r.text)
        print(f"failed with error {r.status_code}")


@parser.command(
    argument("id", help="id of instance to prepay for", type=int),
    argument("amount", help="amount of instance credit prepayment (default discount func of 0.2 for 1 month, 0.3 for 3 months)", type=float),
    usage="vastai prepay instance ID AMOUNT",
    help="Deposit credits into reserved instance",
)
def prepay__instance(args):
    """
    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    url       = apiurl(args, "/instances/prepay/{id}/".format(id=args.id))
    json_blob = { "amount": args.amount }
    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_put(args, url,  headers=state.headers,json=json_blob)
    r.raise_for_status()

    rj = r.json();
    if rj["success"]:
        timescale = round( rj["timescale"], 3)
        discount_rate = 100.0*round( rj["discount_rate"], 3)
        print("prepaid for {timescale} months of instance {args.id} applying ${args.amount} credits for a discount of {discount_rate}%".format(**(locals())));
    else:
        print(rj["msg"]);


@parser.command(
    argument("id", help="id of instance to reboot", type=int),
    argument("--schedule", choices=["HOURLY", "DAILY", "WEEKLY"], help="try to schedule a command to run hourly, daily, or monthly. Valid values are HOURLY, DAILY, WEEKLY  For ex. --schedule DAILY"),
    argument("--start_date", type=str, default=default_start_date(), help="Start date/time in format 'YYYY-MM-DD HH:MM:SS PM' (UTC). Default is now. (optional)"),
    argument("--end_date", type=str, default=default_end_date(), help="End date/time in format 'YYYY-MM-DD HH:MM:SS PM' (UTC). Default is 7 days from now. (optional)"),
    argument("--day", type=parse_day_cron_style, help="Day of week you want scheduled job to run on (0-6, where 0=Sunday) or \"*\". Default will be 0. For ex. --day 0", default=0),
    argument("--hour", type=parse_hour_cron_style, help="Hour of day you want scheduled job to run on (0-23) or \"*\" (UTC). Default will be 0. For ex. --hour 16", default=0),
    usage="vastai reboot instance ID [OPTIONS]",
    help="Reboot (stop/start) an instance",
    epilog=deindent("""
        Stops and starts container without any risk of losing GPU priority.
    """),
)
def reboot__instance(args):
    """
    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    url = apiurl(args, "/instances/reboot/{id}/".format(id=args.id))
    r = http_put(args, url,  headers=state.headers,json={})
    r.raise_for_status()

    if (args.schedule):
        validate_frequency_values(args.day, args.hour, args.schedule)
        cli_command = "reboot instance"
        api_endpoint = "/api/v0/instances/reboot/{id}/".format(id=args.id)
        json_blob = {"instance_id": args.id}
        add_scheduled_job(args, json_blob, cli_command, api_endpoint, "PUT", instance_id=args.id)
        return

    if (r.status_code == 200):
        rj = r.json();
        if (rj["success"]):
            print("Rebooting instance {args.id}.".format(**(locals())));
        else:
            print(rj["msg"]);
    else:
        print(r.text);
        print("failed with error {r.status_code}".format(**locals()));


@parser.command(
    argument("id", help="id of instance to recycle", type=int),
    usage="vastai recycle instance ID [OPTIONS]",
    help="Recycle (destroy/create) an instance",
    epilog=deindent("""
        Destroys and recreates container in place (from newly pulled image) without any risk of losing GPU priority.
    """),
)
def recycle__instance(args):
    """
    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    url = apiurl(args, "/instances/recycle/{id}/".format(id=args.id))
    r = http_put(args, url,  headers=state.headers,json={})
    r.raise_for_status()

    if (r.status_code == 200):
        rj = r.json()
        if (rj["success"]):
            print("Recycling instance {args.id}.".format(**(locals())));
        else:
            print(rj["msg"]);
    else:
        print(r.text)
        print("failed with error {r.status_code}".format(**locals()));


@parser.command(
    argument("id", help="ID of instance to start/restart", type=int),
    usage="vastai start instance ID [OPTIONS]",
    help="Start a stopped instance",
    epilog=deindent("""
        This command attempts to bring an instance from the "stopped" state into the "running" state. This is subject to resource availability on the machine that the instance is located on.
        If your instance is stuck in the "scheduling" state for more than 30 seconds after running this, it likely means that the required resources on the machine to run your instance are currently unavailable.
        Examples:
            vastai start instances $(vastai show instances -q)
            vastai start instance 329838
    """),
)
def start__instance(args):
    """

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    start_instance(args.id,args)


@parser.command(
    argument("ids", help="ids of instance to start", type=int, nargs='+'),
    usage="vastai start instances [OPTIONS] ID0 ID1 ID2...",
    help="Start a list of instances",
)
def start__instances(args):
    """
    for id in args.IDs:
        start_instance(id, args)
    """

    #start_instance(args.IDs, args)
    #exec_with_threads(lambda id : start_instance(id, args), args.IDs)

    idlist = split_list(args.ids, 64)
    exec_with_threads(lambda ids : start_instance(ids, args), idlist, nt=8)


@parser.command(
    argument("id", help="id of instance to stop", type=int),
    usage="vastai stop instance ID [OPTIONS]",
    help="Stop a running instance",
    epilog=deindent("""
        This command brings an instance from the "running" state into the "stopped" state. When an instance is "stopped" all of your data on the instance is preserved,
        and you can resume use of your instance by starting it again. Once stopped, starting an instance is subject to resource availability on the machine that the instance is located on.
        There are ways to move data off of a stopped instance, which are described here: https://vast.ai/docs/gpu-instances/data-movement
    """)
)
def stop__instance(args):
    """

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    stop_instance(args.id,args)

@parser.command(
    argument("ids", help="ids of instance to stop", type=int, nargs='+'),
    usage="vastai stop instances [OPTIONS] ID0 ID1 ID2...",
    help="Stop a list of instances",
    epilog=deindent("""
        Examples:
            vastai stop instances $(vastai show instances -q)
            vastai stop instances 329838 984849
    """),
)
def stop__instances(args):
    """
    for id in args.IDs:
        stop_instance(id, args)
    """

    idlist = split_list(args.ids, 64)
    #stop_instance(args.IDs, args)
    exec_with_threads(lambda ids : stop_instance(ids, args), idlist, nt=8)


@parser.command(
    argument("id", help="id of instance to get", type=int),
    usage="vastai show instance [--api-key API_KEY] [--raw]",
    help="Display user's current instances"
)
def show__instance(args):
    """
    Shows the stats on the machine the user is renting.

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """

    #req_url = apiurl(args, "/instance", {"owner": "me"});
    req_url = apiurl(args, "/instances/{id}/".format(id=args.id) , {"owner": "me"} )

    #r = http_get(req_url)
    r = http_get(args, req_url)
    r.raise_for_status()
    row = r.json()["instances"]
    row['duration'] = time.time() - row['start_date']
    row['extra_env'] = {env_var[0]: env_var[1] for env_var in row['extra_env']}
    if args.raw:
        return row
    else:
        #print(row)
        display_table([row], instance_fields)

@parser.command(
    argument("-q", "--quiet", action="store_true", help="only display numeric ids"),
    usage="vastai show instances [OPTIONS] [--api-key API_KEY] [--raw]",
    help="Display user's current instances"
)
def show__instances(args = {}, extra = {}):
    """
    Shows the stats on the machine the user is renting.

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    req_url = apiurl(args, "/instances", {"owner": "me"});
    #r = http_get(req_url)
    r = http_get(args, req_url)
    r.raise_for_status()
    rows = r.json()["instances"]
    for row in rows:
        row = {k: strip_strings(v) for k, v in row.items()}
        row['duration'] = time.time() - row['start_date']
        row['extra_env'] = {env_var[0]: env_var[1] for env_var in row['extra_env']}
    if 'internal' in extra:
        return [str(row[extra['field']]) for row in rows]
    elif args.quiet:
        for row in rows:
            id = row.get("id", None)
            if id is not None:
                print(id)
    elif args.raw:
        return rows
    else:
        display_table(rows, instance_fields)


@parser.command(
    argument("id", help="id of instance to update", type=int),
    argument("--template_id", help="new template ID to associate with the instance", type=int),
    argument("--template_hash_id", help="new template hash ID to associate with the instance", type=str),
    argument("--image", help="new image UUID for the instance", type=str),
    argument("--args", help="new arguments for the instance", type=str),
    argument("--env", help="new environment variables for the instance", type=json.loads),
    argument("--onstart", help="new onstart script for the instance", type=str),
    usage="vastai update instance ID [OPTIONS]",
    help="Update recreate an instance from a new/updated template",
    epilog=deindent("""
        Example: vastai update instance 1234 --template_hash_id 661d064bbda1f2a133816b6d55da07c3
    """),
)
def update__instance(args):
    """
    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    url = apiurl(args, f"/instances/update_template/{args.id}/")
    json_blob = {"id": args.id}

    if args.template_id:
        json_blob["template_id"] = args.template_id
    if args.template_hash_id:
        json_blob["template_hash_id"] = args.template_hash_id
    if args.image:
        json_blob["image"] = args.image
    if args.args:
        json_blob["args"] = args.args
    if args.env:
        json_blob["env"] = args.env
    if args.onstart:
        json_blob["onstart"] = args.onstart

    if args.explain:
        print("request json: ")
        print(json_blob)

    r = http_put(args, url, headers=state.headers, json=json_blob)

    if r.status_code == 200:
        response_data = r.json()
        if response_data.get("success"):
            print(f"Instance {args.id} updated successfully.")
            print("Updated instance details:")
            print(response_data.get("updated_instance"))
        else:
            print(f"Failed to update instance {args.id}: {response_data.get('msg')}")
    else:
        print(f"Failed to update instance {args.id} with error {r.status_code}: {r.text}")
