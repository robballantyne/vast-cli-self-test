"""Miscellaneous helper functions extracted from vast.py."""

import re
import os
import sys
import json
import time
import math
import argparse
import requests
import threading
import warnings
import urllib3
from typing import Dict, List
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from concurrent.futures import ThreadPoolExecutor

from vast_cli import state
from vast_cli.config import (CACHE_FILE, CACHE_DURATION, INFO, WARN, FAIL, SUCCESS,
                              server_url_default, APIKEY_FILE)
from vast_cli.api.client import http_get, http_put, http_post, http_del
from vast_cli.api.helpers import apiurl, apiheaders
from vast_cli.display.formatting import deindent, progress_print, debug_print
from vast_cli.display.table import display_table
from vast_cli.parser import argument
from vast_cli.validation.validators import (convert_dates_to_timestamps, convert_timestamp_to_date,
                                             validate_frequency_values, string_to_unix_epoch)


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


def validate_volume_params(args):
    if args.volume_size and not args.create_volume:
        raise argparse.ArgumentTypeError("Error: --volume-size can only be used with --create-volume. Please specify a volume ask ID to create a new volume of that size.")
    if (args.create_volume or args.link_volume) and not args.mount_path:
        raise argparse.ArgumentTypeError("Error: --mount-path is required when creating or linking a volume.")

    # This regex matches absolute or relative Linux file paths (no null bytes)
    valid_linux_path_regex = re.compile(r'^(/)?([^/\0]+(/)?)+$')
    if not valid_linux_path_regex.match(args.mount_path):
        raise argparse.ArgumentTypeError(f"Error: --mount-path '{args.mount_path}' is not a valid Linux file path.")

    volume_info = {
        "mount_path": args.mount_path,
        "create_new": True if args.create_volume else False,
        "volume_id": args.create_volume if args.create_volume else args.link_volume
    }
    if args.volume_label:
        volume_info["name"] = args.volume_label
    if args.volume_size:
        volume_info["size"] = args.volume_size
    elif args.create_volume:  # If creating a new volume and size is not passed in, default size is 15GB
        volume_info["size"] = 15

    return volume_info


def validate_portal_config(json_blob):
    # jupyter runtypes already self-correct
    if 'jupyter' in json_blob['runtype']:
        return

    # remove jupyter configs from portal_config if not a jupyter runtype
    portal_config = json_blob['env']['PORTAL_CONFIG'].split("|")
    filtered_config = [config_str for config_str in portal_config if 'jupyter' not in config_str.lower()]

    if not filtered_config:
        raise ValueError("Error: env variable PORTAL_CONFIG must contain at least one non-jupyter related config string if runtype is not jupyter")
    else:
        json_blob['env']['PORTAL_CONFIG'] = "|".join(filtered_config)


def get_template_arguments():
    return [
        argument("--name", help="name of the template", type=str),
        argument("--image", help="docker container image to launch", type=str),
        argument("--image_tag", help="docker image tag (can also be appended to end of image_path)", type=str),
        argument("--href", help="link you want to provide", type=str),
        argument("--repo", help="link to repository", type=str),
        argument("--login", help="docker login arguments for private repo authentication, surround with ''", type=str),
        argument("--env", help="Contents of the 'Docker options' field", type=str),
        argument("--ssh", help="Launch as an ssh instance type", action="store_true"),
        argument("--jupyter", help="Launch as a jupyter instance instead of an ssh instance", action="store_true"),
        argument("--direct", help="Use (faster) direct connections for jupyter & ssh", action="store_true"),
        argument("--jupyter-dir", help="For runtype 'jupyter', directory in instance to use to launch jupyter. Defaults to image's working directory", type=str),
        argument("--jupyter-lab", help="For runtype 'jupyter', Launch instance with jupyter lab", action="store_true"),
        argument("--onstart-cmd", help="contents of onstart script as single argument", type=str),
        argument("--search_params", help="search offers filters", type=str),
        argument("-n", "--no-default", action="store_true", help="Disable default search param query args"),
        argument("--disk_space", help="disk storage space, in GB", type=str),
        argument("--readme", help="readme string", type=str),
        argument("--hide-readme", help="hide the readme from users", action="store_true"),
        argument("--desc", help="description string", type=str),
        argument("--public", help="make template available to public", action="store_true"),
    ]


def fetch_url_content(url):
    response = requests.get(url)
    response.raise_for_status()  # Raises an HTTPError for bad responses
    return response.text


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


def exec_with_threads(f, args, nt=16, max_retries=5):
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
    r = http_put(args, url, headers=state.headers, json=json_blob)
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
    r = http_put(args, url, headers=state.headers, json=json_blob)
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


def numeric_version(version_str):
    try:
        # Split the version string by the period
        major, minor, patch = version_str.split('.')

        # Pad each part with leading zeros to make it 3 digits
        major = major.zfill(3)
        minor = minor.zfill(3)
        patch = patch.zfill(3)

        # Concatenate the padded parts
        numeric_version_str = f"{major}{minor}{patch}"

        # Convert the concatenated string to an integer
        result = int(numeric_version_str)
        #print(result)
        return result

    except ValueError:
        print("Invalid version string format. Expected format: X.X.X")
        return None


def sum(X, k):
    y = 0
    for x in X:
        a = float(x.get(k,0))
        y += a
    return y

def select(X, k):
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


def format_invoices_charges_results(args, results):
    indices_to_remove = []
    for i,item in enumerate(results):
        item['start'] = convert_timestamp_to_date(item['start']) if item['start'] else None
        item['end'] = convert_timestamp_to_date(item['end']) if item['end'] else None
        if item['amount'] == 0:
            indices_to_remove.append(i)  # Removing items that don't contribute to the total
        elif args.invoices:
            if item['type'] not in {'transfer', 'payout'}:
                item['amount'] *= -1  # present amounts intuitively as related to balance
            item['amount_str'] = f"${item['amount']:.2f}" if item['amount'] > 0 else f"-${abs(item['amount']):.2f}"
        else:
            item['amount'] = f"${item['amount']:.3f}"

        if args.charges:
            if item['type'] in {'instance','volume'} and not args.verbose:
                item['items'] = []  # Remove instance charge details if verbose is not set
            if item['source'] and '-' in item['source']:
                item['type'], item['source'] = item['source'].capitalize().split('-')

        item['items'] = format_invoices_charges_results(args, item['items'])

    for i in reversed(indices_to_remove):  # Remove in reverse order to avoid index shifting
        del results[i]

    return results


def handle_failed_tfa_verification(args, e):
    error_data = e.response.json()
    error_msg = error_data.get("msg", str(e))
    error_code = error_data.get("error", "")

    if args.raw:
        print(json.dumps(error_data, indent=2))

    print(f"\n{FAIL} Error: {error_msg}")

    # Provide helpful context for common errors
    if error_code in {"tfa_locked", "2fa_verification_failed"}:
        fail_count = error_data.get("fail_count", 0)
        locked_until = error_data.get("locked_until")

        if fail_count > 0:
            print(f"   Failed attempts: {fail_count}")
        if locked_until:
            lock_time_sec = (datetime.fromtimestamp(locked_until) - datetime.now()).seconds
            minutes, seconds = divmod(lock_time_sec, 60)
            print(f"   Time Remaining for 2FA Lock: {minutes} minutes and {seconds} seconds...")

    elif error_code == "2fa_expired":
        # Note: Only SMS uses tfa challenges that expire when verifying
        print("\n   The SMS code and secret have expired. Please start over:")
        print("     vastai tfa send-sms")


def format_backup_codes(backup_codes):
    """Format backup codes for display or file output."""
    output_lines = [
        "=" * 60, "  VAST.AI 2FA BACKUP CODES", "=" * 60,
        f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"\n{WARN}  WARNING: All previous backup codes are now invalid!",
        "\nYour New Backup Codes (one-time use only):",
        "-" * 40,
    ]

    for i, code in enumerate(backup_codes, 1):
        output_lines.append(f"  {i:2d}. {code}")

    output_lines.extend([
        "-" * 40,
        "\nIMPORTANT:",
        " \u2022 Each code can only be used once",
        " \u2022 Store them in a secure location",
        " \u2022 Use these codes to log in if you lose access to your 2FA device",
        "\n" + "=" * 60,
    ])
    return "\n".join(output_lines)


def confirm_destructive_action(prompt="Are you sure? (y/n): "):
    """Prompt user for confirmation of destructive actions"""
    try:
        response = input(f" {prompt}").strip().lower()
        return 'y' in response
    except (EOFError, KeyboardInterrupt):
        print("\nOperation cancelled.")
        raise

def save_to_file(content, filepath):
    """Save content to file, creating parent directories if needed."""
    try:
        filepath = os.path.abspath(os.path.expanduser(filepath))

        # If directory provided, this should be handled by caller
        parent_dir = os.path.dirname(filepath)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        with open(filepath, "w") as f:
            f.write(content)
        return True
    except (IOError, OSError) as e:
        print(f"\n{FAIL} Error saving file: {e}")
        return False


def get_backup_codes_filename():
    """Generate a timestamped filename for backup codes."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"vastai_backup_codes_{timestamp}.txt"

def save_backup_codes(backup_codes):
    """Save or display 2FA backup codes based on user choice."""
    print(f"\nBackup codes regenerated successfully! {SUCCESS}")
    print(f"\n{WARN}  WARNING: All previous backup codes are now invalid!")

    formatted_content = format_backup_codes(backup_codes)
    filename = get_backup_codes_filename()

    while True:
        print("\nHow would you like to save your new backup codes?")
        print(f"  1. Save to default location (~/Downloads/{filename})")
        print(f"  2. Save to a custom path")
        print(f"  3. Print to screen ({WARN}  potentially unsafe - visible to onlookers)")

        try:
            choice = input("\nEnter choice (1-3): ").strip()

            if choice in {'1', '2'}:
                # Determine filepath
                if choice == '1':
                    downloads_dir = os.path.expanduser("~/Downloads")
                    filepath = os.path.join(downloads_dir, filename)
                else:  # choice == '2'
                    custom_path = input("\nEnter full path for backup codes file: ").strip()
                    if not custom_path:
                        print("Error: Path cannot be empty")
                        continue

                    filepath = os.path.abspath(os.path.expanduser(custom_path))

                    # If directory provided, add filename
                    if os.path.isdir(filepath):
                        filepath = os.path.join(filepath, filename)

                # Try to save
                if save_to_file(formatted_content, filepath):
                    print(f"\n{SUCCESS} Backup codes saved to: {filepath}")
                    print(f"\nIMPORTANT:")
                    print(f" \u2022 The file contains {len(backup_codes)} one-time use backup codes")
                    if choice == '1':
                        print(f" \u2022 Move this file to a secure location")
                    return
                else:
                    print("Please try again with a different path.")
                    continue

            elif choice == '3':
                print(f"\n{WARN}  WARNING: Printing sensitive codes to screen!")
                confirm = input("\nAre you sure? Anyone nearby can see these codes. (yes/no): ").strip().lower()

                if confirm in {'yes', 'y'}:
                    print("\n" + formatted_content + "\n")
                    return
                else:
                    print("Cancelled. Please choose another option.")
                    continue

            else:
                print("Invalid choice. Please enter 1, 2, or 3.")

        except (EOFError, KeyboardInterrupt):
            print("\n\nOperation cancelled. Your backup codes were generated but not saved.")
            print("You will need to regenerate them to get new codes.")
            raise


def build_tfa_verification_payload(args, **kwargs):
    """Build common payload for TFA verification requests."""
    payload = {
        "tfa_method_id": getattr(args, 'method_id', None),
        "tfa_method": "sms" if getattr(args, 'sms', False) else "totp",
        "code": getattr(args, 'code', None),
        "backup_code": getattr(args, 'backup_code', None),
        "secret": getattr(args, 'secret', None),
    }
    for key, value in kwargs.items():
        payload[key] = value

    return {k:v for k,v in payload.items() if v}


def filter_invoice_items(args: argparse.Namespace, rows: List) -> Dict:
    """This applies various filters to the invoice items. Currently it filters on start and end date and applies the
    'only_charge' and 'only_credits' options.invoice_number

    :param argparse.Namespace args: should supply all the command-line options
    :param List rows: The rows of items in the invoice

    :rtype List: Returns the filtered list of rows.

    """

    try:
        #import vast_pdf
        import dateutil
        from dateutil import parser
    except ImportError:
        print("""\nWARNING: The 'vast_pdf' library is not present. This library is used to print invoices in PDF format. If
        you do not need this feature you can ignore this message. To get the library you should download the vast-python
        github repository. Just do 'git@github.com:vast-ai/vast-python.git' and then 'cd vast-python'. Once in that
        directory you can run 'vast.py' and it will have access to 'vast_pdf.py'. The library depends on a Python
        package called Borb to make the PDF files. To install this package do 'pip3 install borb'.\n""")

    """
    try:
        vast_pdf
    except NameError:
        vast_pdf = Object()
        vast_pdf.invoice_number = -1
    """

    selector_flag = ""
    end_timestamp: float = 9999999999
    start_timestamp: float = 0
    start_date_txt = ""
    end_date_txt = ""

    if args.end_date:
        try:
            end_date = dateutil.parser.parse(str(args.end_date))
            end_date_txt = end_date.isoformat()
            end_timestamp = time.mktime(end_date.timetuple())
        except ValueError:
            print("Warning: Invalid end date format! Ignoring end date!")
    if args.start_date:
        try:
            start_date = dateutil.parser.parse(str(args.start_date))
            start_date_txt = start_date.isoformat()
            start_timestamp = time.mktime(start_date.timetuple())
        except ValueError:
            print("Warning: Invalid start date format! Ignoring start date!")

    if args.only_charges:
        type_txt = "Only showing charges."
        selector_flag = "only_charges"

        def type_filter_fn(row):
            return True if row["type"] == "charge" else False
    elif args.only_credits:
        type_txt = "Only showing credits."
        selector_flag = "only_credits"

        def type_filter_fn(row):
            return True if row["type"] == "payment" else False
    else:
        type_txt = ""

        def type_filter_fn(row):
            return True

    if args.end_date:
        if args.start_date:
            header_text = f'Invoice items after {start_date_txt} and before {end_date_txt}.'
        else:
            header_text = f'Invoice items before {end_date_txt}.'
    elif args.start_date:
        header_text = f'Invoice items after {start_date_txt}.'
    else:
        header_text = " "

    header_text = header_text + " " + type_txt

    rows = list(filter(lambda row: end_timestamp >= (row["timestamp"] or 0.0) >= start_timestamp and type_filter_fn(row) and float(row["amount"]) != 0, rows))

    if start_date_txt:
        start_date_txt = "S:" + start_date_txt

    if end_date_txt:
        end_date_txt = "E:" + end_date_txt

    now = date.today()
    invoice_number: int = now.year * 12 + now.month - 1


    pdf_filename_fields = list(filter(lambda fld: False if fld == "" else True,
                                      [str(invoice_number),
                                       start_date_txt,
                                       end_date_txt,
                                       selector_flag]))

    filename = "invoice_" + "-".join(pdf_filename_fields) + ".pdf"
    return {"rows": rows, "header_text": header_text, "pdf_filename": filename}


def cleanup_machine(args, machine_id):
    req_url = apiurl(args, f"/machines/{machine_id}/cleanup/")

    if (args.explain):
        print("request json: ")
    r = http_put(args, req_url, headers=state.headers, json={})

    if (r.status_code == 200):
        rj = r.json()
        if (rj["success"]):
            print(json.dumps(r.json(), indent=1))
        else:
            if args.raw:
                return r
            else:
                print(rj["msg"])
    else:
        print(r.text)
        print("failed with error {r.status_code}".format(**locals()))


def list_machine(args, id):
    req_url = apiurl(args, "/machines/create_asks/")

    json_blob = {
        'machine': id,
        'price_gpu': args.price_gpu,
        'price_disk': args.price_disk,
        'price_inetu': args.price_inetu,
        'price_inetd': args.price_inetd,
        'price_min_bid': args.price_min_bid,
        'min_chunk': args.min_chunk,
        'end_date': string_to_unix_epoch(args.end_date),
        'credit_discount_max': args.discount_rate,
        'duration': args.duration,
        'vol_size': args.vol_size,
        'vol_price': args.vol_price
    }
    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_put(args, req_url, headers=state.headers, json=json_blob)

    if (r.status_code == 200):
        rj = r.json()
        if (rj["success"]):
            price_gpu_ = str(args.price_gpu) if args.price_gpu is not None else "def"
            price_inetu_ = str(args.price_inetu)
            price_inetd_ = str(args.price_inetd)
            min_chunk_ = str(args.min_chunk)
            end_date_ = string_to_unix_epoch(args.end_date)
            discount_rate_ = str(args.discount_rate)
            duration_ = str(args.duration)
            if args.raw:
                return r
            else:
                print("offers created/updated for machine {id},  @ ${price_gpu_}/gpu/hr, ${price_inetu_}/GB up, ${price_inetd_}/GB down, {min_chunk_}/min gpus, max discount_rate {discount_rate_}, till {end_date_}, duration {duration_}".format(**locals()))
                num_extended = rj.get("extended", 0)

                if num_extended > 0:
                    print(f"extended {num_extended} client contracts to {args.end_date}")

        else:
            if args.raw:
                return r
            else:
                print(rj["msg"])
    else:
        print(r.text)
        print("failed with error {r.status_code}".format(**locals()))


def pretty_print_POST(req):
    print('{}\n{}\r\n{}\r\n\r\n{}'.format(
        '-----------START-----------',
        req.method + ' ' + req.url,
        '\r\n'.join('{}: {}'.format(k, v) for k, v in req.headers.items()),
        req.body,
    ))


def suppress_stdout():
    """
    A context manager to suppress standard output (stdout) within its block.

    This is useful for silencing output from functions or blocks of code that
    print to stdout, especially when such output is not needed or should be
    hidden from the user.

    Usage:
        with suppress_stdout():
            # Code block with suppressed stdout
            some_function_that_prints()

    Yields:
        None
    """
    with open(os.devnull, "w") as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try:
            yield
        finally:
            sys.stdout = old_stdout


def destroy_instance(id, args):
    url = apiurl(args, "/instances/{id}/".format(id=id))
    r = http_del(args, url, headers=state.headers, json={})
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


def destroy_instance_silent(id, args):
    """
    Silently destroys a specified instance, retrying up to three times if it fails.

    This function calls the `destroy_instance` function to terminate an instance.
    If the `args.raw` flag is set to True, the output of the destruction process
    is suppressed to keep the console output clean.

    Args:
        id (str): The ID of the instance to destroy.
        args (argparse.Namespace): Command-line arguments containing necessary flags.

    Returns:
        dict: A dictionary with a success status and error message, if any.
    """
    max_retries = 10
    for attempt in range(1, max_retries + 1):
        try:
            # Suppress output if args.raw is True
            if args.raw:
                with open(os.devnull, 'w') as devnull, redirect_stdout(devnull), redirect_stderr(devnull):
                    destroy_instance(id, args)
            else:
                destroy_instance(id, args)

            # If successful, exit the loop and return success
            if not args.raw:
                print(f"Instance {id} destroyed successfully on attempt {attempt}.")
            return {"success": True}

        except Exception as e:
            if not args.raw:
                print(f"Error destroying instance {id}: {e}")

        # Wait before retrying if the attempt failed
        if attempt < max_retries:
            if not args.raw:
                print(f"Retrying in 10 seconds... (Attempt {attempt}/{max_retries})")
            time.sleep(10)
        else:
            if not args.raw:
                print(f"Failed to destroy instance {id} after {max_retries} attempts.")
            return {"success": False, "error": "Max retries exceeded"}


def instance_exist(instance_id, api_key, args):
    # Import here to avoid circular imports - show__instance is a command function
    from vast_cli.commands import show__instance

    if not hasattr(args, 'debugging'):
        args.debugging = False

    if not instance_id:
        return False

    show_args = argparse.Namespace(
        id=instance_id,
        api_key=api_key,
        url=args.url,
        retry=args.retry,
        explain=False,
        raw=True,
        debugging=args.debugging
    )
    try:
        instance_info = show__instance(show_args)

        # Empty list or None means instance doesn't exist - return False without error
        if not instance_info:
            return False

        # If we have instance info, check its status
        status = instance_info.get('intended_status') or instance_info.get('actual_status')
        if status in ['destroyed', 'terminated', 'offline']:
            return False

        return True

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            # Instance does not exist
            return False
        else:
            if args.debugging:
                debug_print(args, f"HTTPError when checking instance existence: {e}")
            return False
    except Exception as e:
        if args.debugging:
            debug_print(args, f"No instance found or Unexpected error checking instance existence: {e}")
        return False

def run_machinetester(ip_address, port, instance_id, machine_id, delay, args, api_key=None):
    """
    Executes machine testing by connecting to the specified IP and port, monitoring
    the instance's status, and handling test completion or failures.

    This function performs the following steps:
        1. Disables SSL warnings.
        2. Optionally delays the start of testing.
        3. Continuously checks the instance status and attempts to connect to the
           `/progress` endpoint to monitor test progress.
        4. Handles different response messages, such as completion or errors.
        5. Implements timeout logic to prevent indefinite waiting.
        6. Ensures instance cleanup in case of failures or completion.

    Args:
        ip_address (str): The public IP address of the instance to test.
        port (int): The port number to connect to for testing.
        instance_id (str): The ID of the instance being tested.
        machine_id (str): The machine ID associated with the instance.
        delay (int): The number of seconds to delay before starting the test.
        args (argparse.Namespace): Parsed command-line arguments containing flags
                                  and options such as `debugging` and `raw`.
        api_key (str, optional): API key for authentication. Defaults to None.

    Returns:
        tuple:
            - bool: `True` if the test was successful, `False` otherwise.
            - str: Reason for failure if the test was not successful, empty string otherwise.
    """
    # Import here to avoid circular imports - show__instance is a command function
    from vast_cli.commands import show__instance

    # Temporarily disable SSL warnings
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    delay = int(delay)

    # Ensure debugging is set in args
    if not hasattr(args, 'debugging'):
        args.debugging = False

    def is_instance(instance_id):
        """Check instance status via show__instance."""
        show_args = argparse.Namespace(
            id=instance_id,
            explain=False,
            api_key=api_key,
            url="https://console.vast.ai",
            retry=3,
            raw=True,
            debugging=args.debugging,
        )
        try:
            instance_info = show__instance(show_args)
            if args.debugging:
                debug_print(args, f"is_instance(): Output from vast show instance: {instance_info}")

            if not instance_info or not isinstance(instance_info, dict):
                if args.debugging:
                    debug_print(args, "is_instance(): No valid instance information received.")
                return 'unknown'

            actual_status = instance_info.get('actual_status', 'unknown')
            return actual_status if actual_status in ['running', 'offline', 'exited', 'created'] else 'unknown'
        except Exception as e:
            if args.debugging:
                debug_print(args, f"is_instance(): Error: {e}")
            return 'unknown'

    # Prepare destroy_args with required attributes set to False as needed
    destroy_args = argparse.Namespace(api_key=api_key, url="https://console.vast.ai", retry=3, explain=False, raw=args.raw, debbuging=args.debugging,)

    # Delay start if specified
    if delay > 0:
        if args.debugging:
            debug_print(args, f"Sleeping for {delay} seconds before starting tests.")
        time.sleep(delay)

    start_time = time.time()
    no_response_seconds = 0
    printed_lines = set()
    first_connection_established = False  # Flag to track first successful connection
    instance_destroyed = False  # Track whether the instance has been destroyed
    try:
        while time.time() - start_time < 600:
            # Check instance status with high priority for offline status
            status = is_instance(instance_id)
            if args.debugging:
                debug_print(args, f"Instance {instance_id} status: {status}")

            if status == 'offline':
                reason = "Instance offline during testing"
                progress_print(args, f"Instance {instance_id} went offline. {reason}")
                destroy_instance_silent(instance_id, destroy_args)
                instance_destroyed = True
                with open("Error_testresults.log", "a") as f:
                    f.write(f"{machine_id}:{instance_id} {reason}\n")
                return False, reason

            # Attempt to connect to the progress endpoint
            try:
                if args.debugging:
                    debug_print(args, f"Sending GET request to https://{ip_address}:{port}/progress")
                response = requests.get(f'https://{ip_address}:{port}/progress', verify=False, timeout=10)

                if response.status_code == 200 and not first_connection_established:
                    progress_print(args, "Successfully established HTTPS connection to the server.")
                    first_connection_established = True

                message = response.text.strip()
                if args.debugging:
                    debug_print(args, f"Received message: '{message}'")
            except requests.exceptions.RequestException as e:
                if args.debugging:
                    progress_print(args, f"Error making HTTPS request: {e}")
                message = ''

            # Process response messages
            if message:
                lines = message.split('\n')
                new_lines = [line for line in lines if line not in printed_lines]
                for line in new_lines:
                    if line == 'DONE':
                        progress_print(args, "Test completed successfully.")
                        with open("Pass_testresults.log", "a") as f:
                            f.write(f"{machine_id}\n")
                        progress_print(args, f"Test passed.")
                        destroy_instance_silent(instance_id, destroy_args)
                        instance_destroyed = True
                        return True, ""
                    elif line.startswith('ERROR'):
                        progress_print(args, line)
                        with open("Error_testresults.log", "a") as f:
                            f.write(f"{machine_id}:{instance_id} {line}\n")
                        progress_print(args, f"Test failed with error: {line}.")
                        destroy_instance_silent(instance_id, destroy_args)
                        instance_destroyed = True
                        return False, line
                    else:
                        progress_print(args, line)
                    printed_lines.add(line)
                no_response_seconds = 0
            else:
                no_response_seconds += 20
                if args.debugging:
                    debug_print(args, f"No message received. Incremented no_response_seconds to {no_response_seconds}.")

            if status == 'running' and no_response_seconds >= 120:
                with open("Error_testresults.log", "a") as f:
                    f.write(f"{machine_id}:{instance_id} No response from port {port} for 120s with running instance\n")
                progress_print(args, f"No response for 120s with running instance. This may indicate a misconfiguration of ports on the machine. Network error or system stall or crashed. ")
                destroy_instance_silent(instance_id, destroy_args)
                instance_destroyed = True
                return False, "No response for 120 seconds with running instance. The system might have crashed or stalled during stress test. Use the self-test machine function in vast cli"

            if args.debugging:
                debug_print(args, "Waiting for 20 seconds before the next check.")
            time.sleep(20)

        if args.debugging:
            debug_print(args, f"Time limit reached. Destroying instance {instance_id}.")
        return False, "Test did not complete within the time limit"
    finally:
        # Ensure instance cleanup
        if not instance_destroyed and instance_id and instance_exist(instance_id, api_key, destroy_args):
           destroy_instance_silent(instance_id, destroy_args)
        progress_print(args, f"Machine: {machine_id} Done with testing remote.py results {message}")
        warnings.simplefilter('default')

def safe_float(value):
    """
    Convert value to float, returning 0 if value is None.

    Args:
        value: The value to convert to float

    Returns:
        float: The converted value, or 0 if value is None
    """
    if value is None:
        return 0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0

def check_requirements(machine_id, api_key, args):
    """
    Validates whether a machine meets the specified hardware and performance requirements.

    This function queries the machine's offers and checks various criteria such as CUDA
    version, reliability, port count, PCIe bandwidth, internet speeds, GPU RAM, system
    RAM, and CPU cores relative to the number of GPUs. If any of these requirements are
    not met, it records the reasons for the failure.

    Args:
        machine_id (str): The ID of the machine to check.
        api_key (str): API key for authentication with the VAST API.
        args (argparse.Namespace): Parsed command-line arguments containing flags
                                  and options such as `debugging` and `raw`.

    Returns:
        tuple:
            - bool: `True` if the machine meets all requirements, `False` otherwise.
            - list: A list of reasons why the machine does not meet the requirements.
    """
    # Import here to avoid circular imports - search__offers is a command function
    from vast_cli.commands import search__offers

    unmet_reasons = []

    # Prepare search arguments to get machine offers
    search_args = argparse.Namespace(
        query=[f"machine_id={machine_id}", "verified=any", "rentable=true", "rented=any"],
        type="on-demand",
        quiet=False,
        no_default=False,
        new=False,
        limit=None,
        disable_bundling=False,
        storage=5.0,
        order="score-",
        raw=True,  # Ensure raw output to get data directly
        explain=args.explain,
        api_key=api_key,
        url=args.url,
        retry=args.retry
    )

    try:
        # Call search__offers and capture the return value directly
        offers = search__offers(search_args)
        if args.debugging:
            debug_print(args, "Captured offers from search__offers:", offers)

        if not offers:
            unmet_reasons.append(f"Machine ID {machine_id} not found or not rentable.")
            progress_print(args, f"Machine ID {machine_id} not found or not rentable.")
            return False, unmet_reasons

        # Sort offers based on 'dlperf' in descending order
        sorted_offers = sorted(offers, key=lambda x: x.get('dlperf', 0), reverse=True)
        top_offer = sorted_offers[0]

        if args.debugging:
            debug_print(args, "Top offer found:", top_offer)

        # Requirement checks
        # 1. CUDA version
        if safe_float(top_offer.get('cuda_max_good')) < 11.8:
            unmet_reasons.append("CUDA version < 11.8")

        # 2. Reliability
        if safe_float(top_offer.get('reliability')) <= 0.90:
            unmet_reasons.append("Reliability <= 0.90")

        # 3. Direct port count
        if safe_float(top_offer.get('direct_port_count')) <= 3:
            unmet_reasons.append("Direct port count <= 3")

        # 4. PCIe bandwidth
        if safe_float(top_offer.get('pcie_bw')) <= 2.85:
            unmet_reasons.append("PCIe bandwidth <= 2.85")

        # 5. Download speed
        if safe_float(top_offer.get('inet_down')) < 500:
            unmet_reasons.append("Download speed < 500 Mb/s")

        # 6. Upload speed
        if safe_float(top_offer.get('inet_up')) < 500:
            unmet_reasons.append("Upload speed < 500 Mb/s")

        # 7. GPU RAM
        if safe_float(top_offer.get('gpu_ram')) <= 7:
            unmet_reasons.append("GPU RAM <= 7 GB")

        # Additional Requirement Checks

        # 8. System RAM vs. Total GPU RAM
        gpu_total_ram = safe_float(top_offer.get('gpu_total_ram'))  # in MB
        cpu_ram = safe_float(top_offer.get('cpu_ram'))  # in MB
        if cpu_ram < gpu_total_ram:
            unmet_reasons.append("System RAM is less than total VRAM.")

        # Debugging Information for RAM
        if args.debugging:
            debug_print(args, f"CPU RAM: {cpu_ram} MB")
            debug_print(args, f"Total GPU RAM: {gpu_total_ram} MB")

        # 9. CPU Cores vs. Number of GPUs
        cpu_cores = int(safe_float(top_offer.get('cpu_cores')))
        num_gpus = int(safe_float(top_offer.get('num_gpus')))
        if cpu_cores < 2 * num_gpus:
            unmet_reasons.append("Number of CPU cores is less than twice the number of GPUs.")

        # Debugging Information for CPU Cores
        if args.debugging:
            debug_print(args, f"CPU Cores: {cpu_cores}")
            debug_print(args, f"Number of GPUs: {num_gpus}")

        # Return True if all requirements are met, False otherwise
        if unmet_reasons:
            progress_print(args, f"Machine ID {machine_id} does not meet the requirements:")
            for reason in unmet_reasons:
                progress_print(args, f"- {reason}")
            return False, unmet_reasons
        else:
            progress_print(args, f"Machine ID {machine_id} meets all the requirements.")
            return True, []

    except Exception as e:
        progress_print(args, f"An unexpected error occurred: {str(e)}")
        if args.debugging:
            debug_print(args, f"Exception details: {e}")
        return False, [f"Unexpected error: {str(e)}"]


def wait_for_instance(instance_id, api_key, args, destroy_args, timeout=900, interval=10):
    """
    Waits for an instance to reach a running state and monitors its status for errors.

    """
    # Import here to avoid circular imports - show__instance is a command function
    from vast_cli.commands import show__instance

    if not hasattr(args, 'debugging'):
        args.debugging = False

    start_time = time.time()
    show_args = argparse.Namespace(
        id=instance_id,
        quiet=False,
        raw=True,  # Ensure raw output to get data directly
        explain=args.explain,
        api_key=api_key,
        url=args.url,
        retry=args.retry,
        debugging=args.debugging,
    )

    if args.debugging:
        debug_print(args, "Starting wait_for_instance with ID:", instance_id)

    while time.time() - start_time < timeout:
        try:
            # Directly call show__instance and capture the return value
            instance_info = show__instance(show_args)

            if not instance_info:
                progress_print(args, f"No information returned for instance {instance_id}. Retrying...")
                time.sleep(interval)
                continue  # Retry

            # Check for error in status_msg
            status_msg = instance_info.get('status_msg', '')
            if status_msg and 'Error' in status_msg:
                reason = f"Instance {instance_id} encountered an error: {status_msg.strip()}"
                progress_print(args, reason)

                # Destroy the instance
                if instance_exist(instance_id, api_key, destroy_args):
                    destroy_instance_silent(instance_id, destroy_args)
                    progress_print(args, f"Instance {instance_id} has been destroyed due to error.")
                else:
                    progress_print(args, f"Instance {instance_id} could not be destroyed or does not exist.")

                return False, reason

            # Check if instance went offline
            actual_status = instance_info.get('actual_status', 'unknown')
            if actual_status == 'offline':
                reason = "Instance offline during testing"
                progress_print(args, reason)

                # Destroy the instance
                if instance_exist(instance_id, api_key, destroy_args):
                    destroy_instance_silent(instance_id, destroy_args)
                    progress_print(args, f"Instance {instance_id} has been destroyed due to being offline.")
                else:
                    progress_print(args, f"Instance {instance_id} could not be destroyed or does not exist.")

                return False, reason

            # Check if instance is running
            if instance_info.get('intended_status') == 'running' and actual_status == 'running':
                if args.debugging:
                    debug_print(args, f"Instance {instance_id} is now running.")
                return instance_info, None  # Return instance_info with None for reason

            # Print feedback about the current status
            progress_print(args, f"Instance {instance_id} status: {actual_status}... waiting for 'running' status.")
            time.sleep(interval)

        except Exception as e:
            progress_print(args, f"Error retrieving instance info for {instance_id}: {e}. Retrying...")
            if args.debugging:
                debug_print(args, f"Exception details: {str(e)}")
            time.sleep(interval)

    # Timeout reached without instance running
    reason = f"Instance did not become running within {timeout} seconds. Verify network configuration. Use the self-test machine function in vast cli"
    progress_print(args, reason)
    return False, reason


def add_scheduled_job(args, req_json, cli_command, api_endpoint, request_method, instance_id, contract_end_date):
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
            response = update_scheduled_job(cli_command, schedule_job_url, frequency, args.start_date, args.end_date, request_body)
        else:
            print("Job update aborted by the user.")
    else:
            # print(r.text)
        print(f"add_scheduled_job insert: failed error: {response.status_code}. Response body: {response.text}")

def update_scheduled_job(cli_command, schedule_job_url, frequency, start_date, end_date, request_body):
    response = requests.put(schedule_job_url, headers=state.headers, json=request_body)

        # Raise an exception for HTTP errors
    response.raise_for_status()
    if response.status_code == 200:
        print(f"add_scheduled_job update: success - Scheduling {frequency} job to {cli_command} from {start_date} UTC to {end_date} UTC")
        print(response.json())
    elif response.status_code == 401:
        print(f"add_scheduled_job update: failed status_code: {response.status_code}. It could be because you aren't using a valid api_key.")
    else:
            # print(r.text)
        print(f"add_scheduled_job update: failed status_code: {response.status_code}.")
        print(response.json())

    return response


def normalize_schedule_fields(job):
    """
    Mutates the job dict to replace None values with readable scheduling labels.
    """
    if job.get("day_of_the_week") is None:
        job["day_of_the_week"] = "Everyday"
    else:
        days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        job["day_of_the_week"] = days[int(job["day_of_the_week"])]

    if job.get("hour_of_the_day") is None:
        job["hour_of_the_day"] = "Every hour"
    else:
        hour = int(job["hour_of_the_day"])
        suffix = "AM" if hour < 12 else "PM"
        hour_12 = hour % 12
        hour_12 = 12 if hour_12 == 0 else hour_12
        job["hour_of_the_day"] = f"{hour_12}_{suffix}"

    if job.get("min_of_the_hour") is None:
        job["min_of_the_hour"] = "Every minute"
    else:
        job["min_of_the_hour"] = f"{int(job['min_of_the_hour']):02d}"

    return job

def normalize_jobs(jobs):
    """
    Applies normalization to a list of job dicts.
    """
    return [normalize_schedule_fields(job) for job in jobs]
