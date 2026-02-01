"""Validation and date/time utility functions."""

import sys
import re
import argparse
import time
from typing import Dict, List
from datetime import date, datetime, timedelta, timezone


def validate_seconds(value):
    """Validate that the input value is a valid number for seconds between yesterday and Jan 1, 2100."""
    try:
        val = int(value)

        # Calculate min_seconds as the start of yesterday in seconds
        yesterday = datetime.now() - timedelta(days=1)
        min_seconds = int(yesterday.timestamp())

        # Calculate max_seconds for Jan 1st, 2100 in seconds
        max_date = datetime(2100, 1, 1, 0, 0, 0)
        max_seconds = int(max_date.timestamp())

        if not (min_seconds <= val <= max_seconds):
            raise argparse.ArgumentTypeError(f"{value} is not a valid second timestamp.")
        return val
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value} is not a valid integer.")

def strip_strings(value):
    if isinstance(value, str):
        return value.strip()
    elif isinstance(value, dict):
        return {k: strip_strings(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [strip_strings(item) for item in value]
    return value  # Return as is if not a string, list, or dict

def string_to_unix_epoch(date_string):
    if date_string is None:
        return None
    try:
        # Check if the input is a float or integer representing Unix time
        return float(date_string)
    except ValueError:
        # If not, parse it as a date string
        date_object = datetime.strptime(date_string, "%m/%d/%Y")
        return time.mktime(date_object.timetuple())

def unix_to_readable(ts):
    # ts: integer or float, Unix timestamp
    return datetime.fromtimestamp(ts).strftime('%H:%M:%S|%h-%d-%Y')

def fix_date_fields(query: Dict[str, Dict], date_fields: List[str]):
    """Takes in a query and date fields to correct and returns query with appropriate epoch dates"""
    new_query: Dict[str, Dict] = {}
    for field, sub_query in query.items():
        # fix date values for given date fields
        if field in date_fields:
            new_sub_query = {k: string_to_unix_epoch(v) for k, v in sub_query.items()}
            new_query[field] = new_sub_query
        # else, use the original
        else: new_query[field] = sub_query

    return new_query

def default_start_date():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def default_end_date():
    return (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")

def convert_timestamp_to_date(unix_timestamp):
    utc_datetime = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
    return utc_datetime.strftime("%Y-%m-%d")

def parse_day_cron_style(value):
    """
    Accepts an integer string 0-6 or '*' to indicate 'Every day'.
    Returns 0-6 as int, or None if '*'.
    """
    val = str(value).strip()
    if val == "*":
        return None
    try:
        day = int(val)
        if 0 <= day <= 6:
            return day
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Day must be 0-6 (0=Sunday) or '*' for every day.")

def parse_hour_cron_style(value):
    """
    Accepts an integer string 0-23 or '*' to indicate 'Every hour'.
    Returns 0-23 as int, or None if '*'.
    """
    val = str(value).strip()
    if val == "*":
        return None
    try:
        hour = int(val)
        if 0 <= hour <= 23:
            return hour
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Hour must be 0-23 or '*' for every hour.")

def validate_frequency_values(day_of_the_week, hour_of_the_day, frequency):

    # Helper to raise an error with a consistent message.
    def raise_frequency_error():
        msg = ""
        if frequency == "HOURLY":
            msg += "For HOURLY jobs, day and hour must both be \"*\"."
        elif frequency == "DAILY":
            msg += "For DAILY jobs, day must be \"*\" and hour must have a value between 0-23."
        elif frequency == "WEEKLY":
            msg += "For WEEKLY jobs, day must have a value between 0-6 and hour must have a value between 0-23."
        sys.exit(msg)

    if frequency == "HOURLY":
        if not (day_of_the_week is None and hour_of_the_day is None):
            raise_frequency_error()
    if frequency == "DAILY":
        if not (day_of_the_week is None and hour_of_the_day is not None):
            raise_frequency_error()
    if frequency == "WEEKLY":
        if not (day_of_the_week is not None and hour_of_the_day is not None):
            raise_frequency_error()

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

def convert_dates_to_timestamps(args):
    selector_flag = ""
    end_timestamp = time.time()
    start_timestamp = time.time() - (24*60*60)
    start_date_txt = ""
    end_date_txt = ""

    import dateutil
    from dateutil import parser

    if args.end_date:
        try:
            end_date = dateutil.parser.parse(str(args.end_date))
            end_date_txt = end_date.isoformat()
            end_timestamp = time.mktime(end_date.timetuple())
        except ValueError as e:
            print(f"Warning: Invalid end date format! Ignoring end date! \n {str(e)}")

    if args.start_date:
        try:
            start_date = dateutil.parser.parse(str(args.start_date))
            start_date_txt = start_date.isoformat()
            start_timestamp = time.mktime(start_date.timetuple())
        except ValueError as e:
            print(f"Warning: Invalid start date format! Ignoring start date! \n {str(e)}")

    return start_timestamp, end_timestamp

def smart_split(s, char):
    in_double_quotes = False
    in_single_quotes = False #note that isn't designed to work with nested quotes within the env
    parts = []
    current = []

    for c in s:
        if c == char and not (in_double_quotes or in_single_quotes):
            parts.append(''.join(current))
            current = []
        elif c == '\'':
            in_single_quotes = not in_single_quotes
            current.append(c)
        elif c == '\"':
            in_double_quotes = not in_double_quotes
            current.append(c)
        else:
            current.append(c)
    parts.append(''.join(current))  # add last part
    return parts

def parse_env(envs):
    result = {}
    if (envs is None):
        return result
    env = smart_split(envs,' ')
    prev = None
    for e in env:
        if (prev is None):
          if (e in {"-e", "-p", "-h", "-v", "-n"}):
              prev = e
          else:
            pass
        else:
          if (prev == "-p"):
            if set(e).issubset(set("0123456789:tcp/udp")):
                result["-p " + e] = "1"
            else:
                pass
          elif (prev == "-e"):
            kv = e.split('=')
            if len(kv) >= 2: #set(e).issubset(set("1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_=")):
                val = kv[1]
                if len(kv) > 2:
                    val = '='.join(kv[1:])
                result[kv[0]] = val.strip("'\"")
            else:
                pass
          elif (prev == "-v"):
            if (set(e).issubset(set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:./_"))):
                result["-v " + e] = "1"
          elif (prev == "-n"):
            if (set(e).issubset(set("abcdefghijklmnopqrstuvwxyz0123456789-"))):
                result["-n " + e] = "1"
          else:
              result[prev] = e
          prev = None
    #print(result)
    return result
