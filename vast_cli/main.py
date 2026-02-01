"""Main entry point for vast_cli."""

from __future__ import unicode_literals, print_function

import os
import sys
import json
from typing import List, Optional

import requests

from vast_cli.config import (
    server_url_default, should_check_for_update,
    APIKEY_FILE, TFAKEY_FILE, JSONDecodeError,
)
from vast_cli import state
from vast_cli.parser import parser
from vast_cli.version.checker import is_pip_package, check_for_update, get_local_version

VERSION = get_local_version()

# Import all command modules to trigger @parser.command() registration
import vast_cli.commands  # noqa: F401

"""
try:
  class MyAutocomplete(argcomplete.CompletionFinder):
    def quote_completions(self, completions: List[str], cword_prequote: str, last_wordbreak_pos: Optional[int]) -> List[str]:
      pre = super().quote_completions(completions, cword_prequote, last_wordbreak_pos)
      # preference the non-hyphenated options first
      return sorted(pre, key=lambda x: x.startswith('-'))
except:
  pass


def main():
    global ARGS
    parser.add_argument("--url", help="Server REST API URL", default=server_url_default)
    parser.add_argument("--retry", help="Retry limit", default=3)
    parser.add_argument("--explain", action="store_true", help="Output verbose explanation of mapping of CLI calls to HTTPS API endpoints")
    parser.add_argument("--raw", action="store_true", help="Output machine-readable json")
    parser.add_argument("--full", action="store_true", help="Print full results instead of paging with `less` for commands that support it")
    parser.add_argument("--curl", action="store_true", help="Show a curl equivalency to the call")
    parser.add_argument("--api-key", help="API Key to use. defaults to using the one stored in {}".format(APIKEY_FILE), type=str, required=False, default=os.getenv("VAST_API_KEY", api_key_guard))
    parser.add_argument("--version", help="Show CLI version", action="version", version=VERSION)
    parser.add_argument("--no-color", action="store_true", help="Disable colored output for commands that support it (Note: the 'rich' python module is required for colored output)")

    ARGS = args = parser.parse_args()
"""


try:
    if state.TABCOMPLETE:
        import argcomplete

        class MyAutocomplete(argcomplete.CompletionFinder):
            def quote_completions(self, completions: List[str], cword_prequote: str, last_wordbreak_pos: Optional[int]) -> List[str]:
                pre = super().quote_completions(completions, cword_prequote, last_wordbreak_pos)
                # preference the non-hyphenated options first
                return sorted(pre, key=lambda x: x.startswith('-'))
except:
    pass


def main():
    parser.add_argument("--url", help="Server REST API URL", default=server_url_default)
    parser.add_argument("--retry", help="Retry limit", default=3)
    parser.add_argument("--explain", action="store_true", help="Output verbose explanation of mapping of CLI calls to HTTPS API endpoints")
    parser.add_argument("--raw", action="store_true", help="Output machine-readable json")
    parser.add_argument("--full", action="store_true", help="Print full results instead of paging with `less` for commands that support it")
    parser.add_argument("--curl", action="store_true", help="Show a curl equivalency to the call")
    parser.add_argument("--api-key", help="API Key to use. defaults to using the one stored in {}".format(APIKEY_FILE), type=str, required=False, default=os.getenv("VAST_API_KEY", state.api_key_guard))
    parser.add_argument("--version", help="Show CLI version", action="version", version=VERSION)
    parser.add_argument("--no-color", action="store_true", help="Disable colored output for commands that support it (Note: the 'rich' python module is required for colored output)")

    state.ARGS = args = parser.parse_args()
    #print(args.api_key)
    if args.api_key is state.api_key_guard:
        key_file = TFAKEY_FILE if os.path.exists(TFAKEY_FILE) else APIKEY_FILE
        if args.explain:
            print(f'checking {key_file}')
        if os.path.exists(key_file):
            if args.explain:
                print(f'reading key from {key_file}')
            with open(key_file, "r") as reader:
                args.api_key = reader.read().strip()
        else:
            args.api_key = None
    if args.api_key:
        state.headers["Authorization"] = "Bearer " + args.api_key

    if not args.raw and should_check_for_update:
        try:
            if is_pip_package():
                check_for_update()
        except Exception as e:
            print(f"Error checking for update: {e}")

    if state.TABCOMPLETE:
        myautocc = MyAutocomplete()
        myautocc(parser.parser)

    while True:
        try:
            res = args.func(args)
            if args.raw and res is not None:
                # There's two types of responses right now
                try:
                    print(json.dumps(res, indent=1, sort_keys=True))
                except:
                    print(json.dumps(res.json(), indent=1, sort_keys=True))
                sys.exit(0)
            sys.exit(res)

        except requests.exceptions.HTTPError as e:
            try:
                errmsg = e.response.json().get("msg");
            except JSONDecodeError:
                if e.response.status_code == 401:
                    errmsg = "Please log in or sign up"
                else:
                    errmsg = "(no detail message supplied)"

            # 2FA Session Key Expired
            if e.response.status_code == 401 and errmsg == "Invalid user key":
                if os.path.exists(TFAKEY_FILE):
                    print(f"Failed with error {e.response.status_code}: Your 2FA session has expired.")
                    os.remove(TFAKEY_FILE)
                    if os.path.exists(APIKEY_FILE):
                        with open(APIKEY_FILE, "r") as reader:
                            args.api_key = reader.read().strip()
                            state.headers["Authorization"] = "Bearer " + args.api_key
                            print(f"Trying again with your normal API Key from {APIKEY_FILE}...")
                            continue
                    else:
                        print("Please log in using the `tfa login` command and try again.")
                        break

            print(f"Failed with error {e.response.status_code}: {errmsg}")
            break

        except ValueError as e:
            print(e)
            break


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        pass
