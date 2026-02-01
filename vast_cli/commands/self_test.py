"""Self-test machine command."""

import json
import sys
import os
import time
import argparse

import requests

from vast_cli.parser import parser, argument
from vast_cli import state
from vast_cli.config import APIKEY_FILE, server_url_default, INFO, SUCCESS, FAIL, WARN
from vast_cli.api.client import http_get, http_post, http_put, http_del
from vast_cli.api.helpers import apiurl, apiheaders
from vast_cli.display.formatting import deindent, progress_print, debug_print
from vast_cli.helpers import (check_requirements, wait_for_instance, safe_float,
                              run_machinetester, instance_exist, destroy_instance_silent,
                              suppress_stdout)


@parser.command(
    argument("machine_id", help="Machine ID", type=str),
    argument("--debugging", action="store_true", help="Enable debugging output"),
    argument("--explain", action="store_true", help="Output verbose explanation of mapping of CLI calls to HTTPS API endpoints"),
    argument("--raw", action="store_true", help="Output machine-readable JSON"),
    argument("--url", help="Server REST API URL", default="https://console.vast.ai"),
    argument("--retry", help="Retry limit", type=int, default=3),
    argument("--ignore-requirements", action="store_true", help="Ignore the minimum system requirements and run the self test regardless"),
    usage="vastai self-test machine <machine_id> [--debugging] [--explain] [--api_key API_KEY] [--url URL] [--retry RETRY] [--raw] [--ignore-requirements]",
    help="[Host] Perform a self-test on the specified machine",
    epilog=deindent("""
        This command tests if a machine meets specific requirements and
        runs a series of tests to ensure it's functioning correctly.

        Examples:
         vast self-test machine 12345
         vast self-test machine 12345 --debugging
         vast self-test machine 12345 --explain
         vast self-test machine 12345 --api_key <YOUR_API_KEY>
    """),
)

def self_test__machine(args):
    """
    Performs a self-test on the specified machine to verify its compliance with
    required specifications and functionality.
    """
    # Lazy import to avoid circular dependencies
    from vast_cli.commands.search import search__offers
    from vast_cli.commands.instances import create__instance

    instance_id = None  # Store instance ID for cleanup if needed
    result = {"success": False, "reason": ""}

    # Ensure debugging attribute exists in args
    if not hasattr(args, 'debugging'):
        args.debugging = False

    try:
        # Load API key
        if not args.api_key:
            api_key_file = os.path.expanduser("~/.vast_api_key")
            if os.path.exists(api_key_file):
                with open(api_key_file, "r") as reader:
                    args.api_key = reader.read().strip()
            else:
                progress_print(args, "No API key found. Please set it using 'vast set api-key YOUR_API_KEY_HERE'")
                result["reason"] = "API key not found."

        api_key = args.api_key
        if not api_key:
            raise Exception("API key is missing.")

        # Prepare destroy_args
        destroy_args = argparse.Namespace(
            api_key=api_key,
            url=args.url,
            retry=args.retry,
            explain=False,
            raw=args.raw,
            debugging=args.debugging,
        )

        # Check requirements
        meets_requirements, unmet_reasons = check_requirements(args.machine_id, api_key, args)
        if not meets_requirements and not args.ignore_requirements:
            # immediately fail
            progress_print(args, f"Machine ID {args.machine_id} does not meet the following requirements:")
            for reason in unmet_reasons:
                progress_print(args, f"- {reason}")
            result["reason"] = "; ".join(unmet_reasons)
            return result
        if not meets_requirements and args.ignore_requirements:
            progress_print(args, f"Machine ID {args.machine_id} does not meet the following requirements:")
            for reason in unmet_reasons:
                progress_print(args, f"- {reason}")
                # If user did pass --ignore-requirements, warn and continue
                progress_print(args, "Continuing despite unmet requirements because --ignore-requirements is set.")

        def cuda_map_to_image(cuda_version):
            """
            Maps a CUDA version to a Docker image tag, falling back to the next lower version until failure.
            """
            docker_repo = "vastai/test"
            # Convert float input to string
            if isinstance(cuda_version, float):
                cuda_version = str(cuda_version)

            # Predefined mapping. Tracks PyTorch releases
            docker_tag_map = {
                "11.8": "cu118",
                "12.1": "cu121",
                "12.4": "cu124",
                "12.6": "cu126",
                "12.8": "cu128"
            }

            if cuda_version in docker_tag_map:
                return f"{docker_repo}:self-test-{docker_tag_map[cuda_version]}"

            # Try to find the next version down
            cuda_float = float(cuda_version)

            # Try to decrement the version by 0.1 until we find a match or run out of options
            next_version = round(cuda_float - 0.1, 1)
            while next_version >= min(float(v) for v in docker_tag_map.keys()):
                next_version_str = str(next_version)
                if next_version_str in docker_tag_map:
                    return f"{docker_repo}:self-test-{docker_tag_map[next_version_str]}"
                next_version = round(next_version - 0.1, 1)

            raise KeyError(f"No CUDA version found for {cuda_version} or any lower version")


        def search_offers_and_get_top(machine_id):
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
                raw=True,
                explain=args.explain,
                api_key=api_key,
                url=args.url,
                curl=args.curl,
                retry=args.retry,
                debugging=args.debugging,
            )
            offers = search__offers(search_args)
            if not offers:
                progress_print(args, f"Machine ID {machine_id} not found or not rentable.")
                return None
            sorted_offers = sorted(offers, key=lambda x: x.get("dlperf", 0), reverse=True)
            return sorted_offers[0] if sorted_offers else None

        top_offer = search_offers_and_get_top(args.machine_id)
        if not top_offer:
            progress_print(args, f"No valid offers found for Machine ID {args.machine_id}")
            result["reason"] = "No valid offers found."
        else:
            ask_contract_id = top_offer["id"]
            cuda_version = top_offer["cuda_max_good"]
            docker_image = cuda_map_to_image(cuda_version)

            # Prepare arguments for instance creation
            create_args = argparse.Namespace(
                id=ask_contract_id,
                user=None,
                price=None,  # Set bid_price to None
                disk=40,  # Match the disk size from the working command
                image=docker_image,
                login=None,
                label=None,
                onstart=None,
                onstart_cmd="/verification/remote.sh",
                entrypoint=None,
                ssh=False,  # Set ssh to False
                jupyter=True,  # Set jupyter to True
                direct=True,
                jupyter_dir=None,
                jupyter_lab=False,
                lang_utf8=False,
                python_utf8=False,
                extra=None,
                env="-e TZ=PDT -e XNAME=XX4 -p 5000:5000 -p 1234:1234",
                args=None,
                force=False,
                cancel_unavail=False,
                template_hash=None,
                raw=True,
                explain=args.explain,
                api_key=api_key,
                url=args.url,
                retry=args.retry,
                debugging=args.debugging,
                bid_price=None,  # Ensure bid_price is None
                create_volume=None,
                link_volume=None,
            )

            # Create instance
            try:
                progress_print(args, f"Starting test with {docker_image}")
                response = create__instance(create_args)
                if isinstance(response, requests.Response):  # Check if it's an HTTP response
                    if response.status_code == 200:
                        try:
                            instance_info = response.json()  # Parse JSON
                            if args.debugging:
                                debug_print(args, "Captured instance_info from create__instance:", instance_info)
                        except json.JSONDecodeError as e:
                            progress_print(args, f"Error parsing JSON response: {e}")
                            debug_print(args, f"Raw response content: {response.text}")
                            raise Exception("Failed to parse JSON from instance creation response.")
                    else:
                        progress_print(args, f"HTTP error during instance creation: {response.status_code}")
                        debug_print(args, f"Response text: {response.text}")
                        raise Exception(f"Instance creation failed with status {response.status_code}")
                else:
                    raise Exception("Unexpected response type from create__instance.")
            except Exception as e:
                progress_print(args, f"Error creating instance: {e}")
                result["reason"] = "Failed to create instance. Check the docker configuration. Use the self-test machine function in vast cli "
                return result  # Cleanup handled in finally block

            # Extract instance ID and proceed
            instance_id = instance_info.get("new_contract")
            if not instance_id:
                progress_print(args, "Instance creation response did not contain 'new_contract'.")
                result["reason"] = "Instance creation failed."
            else:
                # Wait for the instance to start
                instance_info, wait_reason = wait_for_instance(instance_id, api_key, args, destroy_args)
                if not instance_info:
                    result["reason"] = wait_reason
                else:
                    # Proceed with the rest of your code
                    # Run machine tester
                    ip_address = instance_info.get("public_ipaddr")
                    if not ip_address:
                        result["reason"] = "Failed to retrieve public IP address."
                    else:
                        port_mappings = instance_info.get("ports", {}).get("5000/tcp", [])
                        port = port_mappings[0].get("HostPort") if port_mappings else None
                        if not port:
                            result["reason"] = "Failed to retrieve mapped port."
                        else:
                            delay = "15"
                            success, reason = run_machinetester(
                                ip_address, port, str(instance_id), args.machine_id, delay, args, api_key=api_key
                            )
                            result["success"] = success
                            result["reason"] = reason

    except Exception as e:
        result["success"] = False
        result["reason"] = str(e)

    finally:
        try:
            if instance_id and instance_exist(instance_id, api_key, destroy_args):
                destroy_instance_silent(instance_id, destroy_args)
        except Exception as e:
            if args.debugging:
                debug_print(args, f"Error during cleanup: {e}")

    # Output results
    if args.raw:
        print(json.dumps(result))
        sys.exit(0)
    else:
        if result["success"]:
            print("Test completed successfully.")
            sys.exit(0)
        else:
            print(f"Test failed: {result['reason']}")
            sys.exit(1)
