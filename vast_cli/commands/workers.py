"""Worker group and endpoint commands for vast_cli."""

import argparse
import json

import requests

from vast_cli.parser import parser, argument
from vast_cli import state
from vast_cli.api.client import http_get, http_post, http_put, http_del
from vast_cli.api.helpers import apiurl
from vast_cli.display.formatting import deindent
from vast_cli.config import server_url_default


@parser.command(
    argument("--template_hash", help="template hash (required, but **Note**: if you use this field, you can skip search_params, as they are automatically inferred from the template)", type=str),
    argument("--template_id",   help="template id (optional)", type=int),
    argument("-n", "--no-default", action="store_true", help="Disable default search param query args"),
    argument("--launch_args",   help="launch args  string for create instance  ex: \"--onstart onstart_wget.sh  --env '-e ONSTART_PATH=https://s3.amazonaws.com/vast.ai/onstart_OOBA.sh' --image atinoda/text-generation-webui:default-nightly --disk 64\"", type=str),
    argument("--endpoint_name", help="deployment endpoint name (allows multiple workergroups to share same deployment endpoint)", type=str),
    argument("--endpoint_id",   help="deployment endpoint id (allows multiple workergroups to share same deployment endpoint)", type=int),
    argument("--test_workers",help="number of workers to create to get an performance estimate for while initializing workergroup (default 3)", type=int, default=3),
    argument("--gpu_ram",     help="estimated GPU RAM req  (independent of search string)", type=float),
    argument("--search_params", help="search param string for search offers    ex: \"gpu_ram>=23 num_gpus=2 gpu_name=RTX_4090 inet_down>200 direct_port_count>2 disk_space>=64\"", type=str),
    argument("--min_load", help="[NOTE: this field isn't currently used at the workergroup level] minimum floor load in perf units/s  (token/s for LLms)", type=float),
    argument("--target_util", help="[NOTE: this field isn't currently used at the workergroup level] target capacity utilization (fraction, max 1.0, default 0.9)", type=float),
    argument("--cold_mult",   help="[NOTE: this field isn't currently used at the workergroup level]cold/stopped instance capacity target as multiple of hot capacity target (default 2.0)", type=float),
    argument("--cold_workers",   help="min number of workers to keep 'cold' for this workergroup", type=int),
    argument("--auto_instance", help=argparse.SUPPRESS, type=str, default="prod"),
    usage="vastai workergroup create [OPTIONS]",
    help="Create a new autoscale group",
    epilog=deindent("""
        Create a new autoscaling group to manage a pool of worker instances.

        Example: vastai create workergroup --template_hash HASH  --endpoint_name "LLama" --test_workers 5
        """),
)
def create__workergroup(args):
    url = apiurl(args, "/autojobs/" )

    # if args.launch_args_dict:
    #     launch_args_dict = json.loads(args.launch_args_dict)
    #     json_blob = {"client_id": "me", "min_load": args.min_load, "target_util": args.target_util, "cold_mult": args.cold_mult, "template_hash": args.template_hash, "template_id": args.template_id, "search_params": args.search_params, "launch_args_dict": launch_args_dict, "gpu_ram": args.gpu_ram, "endpoint_name": args.endpoint_name}
    if args.no_default:
        query = ""
    else:
        query = " verified=True rentable=True rented=False"
        #query = {"verified": {"eq": True}, "external": {"eq": False}, "rentable": {"eq": True}, "rented": {"eq": False}}
    search_params = (args.search_params if args.search_params is not None else "" + query).strip()

    json_blob = {"client_id": "me", "min_load": args.min_load, "target_util": args.target_util, "cold_mult": args.cold_mult, "cold_workers" : args.cold_workers, "test_workers" : args.test_workers, "template_hash": args.template_hash, "template_id": args.template_id, "search_params": search_params, "launch_args": args.launch_args, "gpu_ram": args.gpu_ram, "endpoint_name": args.endpoint_name, "endpoint_id": args.endpoint_id, "autoscaler_instance": args.auto_instance}

    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_post(args, url, headers=state.headers,json=json_blob)
    r.raise_for_status()
    if 'application/json' in r.headers.get('Content-Type', ''):
        try:
            print("workergroup create {}".format(r.json()))
        except requests.exceptions.JSONDecodeError:
            print("The response is not valid JSON.")
            print(r)
            print(r.text)  # Print the raw response to help with debugging.
    else:
        print("The response is not JSON. Content-Type:", r.headers.get('Content-Type'))
        print(r.text)


@parser.command(
    argument("--min_load", help="minimum floor load in perf units/s  (token/s for LLms)", type=float, default=0.0),
    argument("--min_cold_load", help="minimum floor load in perf units/s (token/s for LLms), but allow handling with cold workers", type=float, default=0.0),
    argument("--target_util", help="target capacity utilization (fraction, max 1.0, default 0.9)", type=float, default=0.9),
    argument("--cold_mult",   help="cold/stopped instance capacity target as multiple of hot capacity target (default 2.5)", type=float, default=2.5),
    argument("--cold_workers", help="min number of workers to keep 'cold' when you have no load (default 5)", type=int, default=5),
    argument("--max_workers", help="max number of workers your endpoint group can have (default 20)", type=int, default=20),
    argument("--endpoint_name", help="deployment endpoint name (allows multiple autoscale groups to share same deployment endpoint)", type=str),
    argument("--auto_instance", help=argparse.SUPPRESS, type=str, default="prod"),

    usage="vastai create endpoint [OPTIONS]",
    help="Create a new endpoint group",
    epilog=deindent("""
        Create a new endpoint group to manage many autoscaling groups

        Example: vastai create endpoint --target_util 0.9 --cold_mult 2.0 --endpoint_name "LLama"
    """),
)
def create__endpoint(args):
    url = apiurl(args, "/endptjobs/" )

    json_blob = {"client_id": "me", "min_load": args.min_load, "min_cold_load":args.min_cold_load, "target_util": args.target_util, "cold_mult": args.cold_mult, "cold_workers" : args.cold_workers, "max_workers" : args.max_workers, "endpoint_name": args.endpoint_name, "autoscaler_instance": args.auto_instance}

    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = requests.post(url, headers=state.headers,json=json_blob)
    r.raise_for_status()
    if 'application/json' in r.headers.get('Content-Type', ''):
        try:
            print("create endpoint {}".format(r.json()))
        except requests.exceptions.JSONDecodeError:
            print("The response is not valid JSON.")
            print(r)
            print(r.text)  # Print the raw response to help with debugging.
    else:
        print("The response is not JSON. Content-Type:", r.headers.get('Content-Type'))
        print(r.text)


@parser.command(
    argument("id", help="id of group to delete", type=int),
    usage="vastai delete workergroup ID ",
    help="Delete a workergroup group",
    epilog=deindent("""
        Note that deleting a workergroup doesn't automatically destroy all the instances that are associated with your workergroup.
        Example: vastai delete workergroup 4242
    """),
)
def delete__workergroup(args):
    id  = args.id
    url = apiurl(args, f"/autojobs/{id}/" )
    json_blob = {"client_id": "me", "autojob_id": args.id}
    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_del(args, url, headers=state.headers,json=json_blob)
    r.raise_for_status()
    if 'application/json' in r.headers.get('Content-Type', ''):
        try:
            print("workergroup delete {}".format(r.json()))
        except requests.exceptions.JSONDecodeError:
            print("The response is not valid JSON.")
            print(r)
            print(r.text)  # Print the raw response to help with debugging.
    else:
        print("The response is not JSON. Content-Type:", r.headers.get('Content-Type'))
        print(r.text)

@parser.command(
    argument("id", help="id of endpoint group to delete", type=int),
    usage="vastai delete endpoint ID ",
    help="Delete an endpoint group",
    epilog=deindent("""
        Example: vastai delete endpoint 4242
    """),
)
def delete__endpoint(args):
    id  = args.id
    url = apiurl(args, f"/endptjobs/{id}/" )
    json_blob = {"client_id": "me", "endptjob_id": args.id}
    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_del(args, url, headers=state.headers,json=json_blob)
    r.raise_for_status()
    if 'application/json' in r.headers.get('Content-Type', ''):
        try:
            print("delete endpoint {}".format(r.json()))
        except requests.exceptions.JSONDecodeError:
            print("The response is not valid JSON.")
            print(r)
            print(r.text)  # Print the raw response to help with debugging.
    else:
        print("The response is not JSON. Content-Type:", r.headers.get('Content-Type'))
        print(r.text)


@parser.command(
    argument("id", help="id of endpoint group to fetch logs from", type=int),
    argument("--level", help="log detail level (0 to 3)", type=int, default=1),
    argument("--tail", help="", type=int, default=None),
    usage="vastai get endpt-logs ID [--api-key API_KEY]",
    help="Fetch logs for a specific serverless endpoint group",
    epilog=deindent("""
        Example: vastai get endpt-logs 382
    """),
)
def get__endpt_logs(args):
    #url = apiurl(args, "/endptjobs/" )
    if args.url == server_url_default:
        args.url = None
    url = (args.url or "https://run.vast.ai") + "/get_endpoint_logs/"
    json_blob = {"id": args.id, "api_key": args.api_key}
    if args.tail: json_blob["tail"] = args.tail
    if (args.explain):
        print(f"{url} with request json: ")
        print(json_blob)

    r = http_post(args, url, headers=state.headers,json=json_blob)
    r.raise_for_status()
    levels = {0 : "info0", 1: "info1", 2: "trace", 3: "debug"}

    if (r.status_code == 200):
        rj = None
        try:
            rj = r.json()
        except Exception as e:
            print(str(e))
            print(r.text)
        if args.raw:
            # sort_keys
            return rj or r.text
        else:
            dbg_lvl = levels[args.level]
            if rj and dbg_lvl: print(rj[dbg_lvl])
            #print(json.dumps(rj, indent=1, sort_keys=True))
    else:
        print(r.text)

@parser.command(
    argument("id", help="id of endpoint group to fetch logs from", type=int),
    argument("--level", help="log detail level (0 to 3)", type=int, default=1),
    argument("--tail", help="", type=int, default=None),
    usage="vastai get wrkgrp-logs ID [--api-key API_KEY]",
    help="Fetch logs for a specific serverless worker group group",
    epilog=deindent("""
        Example: vastai get endpt-logs 382
    """),
)
def get__wrkgrp_logs(args):
    #url = apiurl(args, "/endptjobs/" )
    if args.url == server_url_default:
        args.url = None
    url = (args.url or "https://run.vast.ai") + "/get_autogroup_logs/"
    json_blob = {"id": args.id, "api_key": args.api_key}
    if args.tail: json_blob["tail"] = args.tail
    if (args.explain):
        print(f"{url} with request json: ")
        print(json_blob)

    r = http_post(args, url, headers=state.headers,json=json_blob)
    r.raise_for_status()
    levels = {0 : "info0", 1: "info1", 2: "trace", 3: "debug"}

    if (r.status_code == 200):
        rj = None
        try:
            rj = r.json()
        except Exception as e:
            print(str(e))
            print(r.text)
        if args.raw:
            # sort_keys
            return rj or r.text
        else:
            dbg_lvl = levels[args.level]
            if rj and dbg_lvl: print(rj[dbg_lvl])
            #print(json.dumps(rj, indent=1, sort_keys=True))
    else:
        print(r.text)


@parser.command(
    usage="vastai show workergroups [--api-key API_KEY]",
    help="Display user's current workergroups",
    epilog=deindent("""
        Example: vastai show workergroups
    """),
)
def show__workergroups(args):
    url = apiurl(args, "/autojobs/" )
    json_blob = {"client_id": "me", "api_key": args.api_key}
    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_get(args, url, headers=state.headers,json=json_blob)
    r.raise_for_status()
    #print("workergroup list ".format(r.json()))

    if (r.status_code == 200):
        rj = r.json();
        if (rj["success"]):
            rows = rj["results"]
            if args.raw:
                return rows
            else:
                #print(rows)
                print(json.dumps(rows, indent=1, sort_keys=True))
        else:
            print(rj["msg"]);

@parser.command(
    usage="vastai show endpoints [--api-key API_KEY]",
    help="Display user's current endpoint groups",
    epilog=deindent("""
        Example: vastai show endpoints
    """),
)
def show__endpoints(args):
    url = apiurl(args, "/endptjobs/" )
    json_blob = {"client_id": "me", "api_key": args.api_key}
    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_get(args, url, headers=state.headers,json=json_blob)
    r.raise_for_status()
    #print("workergroup list ".format(r.json()))

    if (r.status_code == 200):
        rj = r.json();
        if (rj["success"]):
            rows = rj["results"]
            if args.raw:
                return rows
            else:
                #print(rows)
                print(json.dumps(rows, indent=1, sort_keys=True))
        else:
            print(rj["msg"]);


@parser.command(
    argument("id", help="id of autoscale group to update", type=int),
    argument("--min_load", help="minimum floor load in perf units/s  (token/s for LLms)", type=float),
    argument("--target_util",      help="target capacity utilization (fraction, max 1.0, default 0.9)", type=float),
    argument("--cold_mult",   help="cold/stopped instance capacity target as multiple of hot capacity target (default 2.5)", type=float),
    argument("--cold_workers",   help="min number of workers to keep 'cold' for this workergroup", type=int),
    argument("--test_workers",help="number of workers to create to get an performance estimate for while initializing workergroup (default 3)", type=int),
    argument("--gpu_ram",   help="estimated GPU RAM req  (independent of search string)", type=float),
    argument("--template_hash",   help="template hash (**Note**: if you use this field, you can skip search_params, as they are automatically inferred from the template)", type=str),
    argument("--template_id",   help="template id", type=int),
    argument("--search_params",   help="search param string for search offers    ex: \"gpu_ram>=23 num_gpus=2 gpu_name=RTX_4090 inet_down>200 direct_port_count>2 disk_space>=64\"", type=str),
    argument("-n", "--no-default", action="store_true", help="Disable default search param query args"),
    argument("--launch_args",   help="launch args  string for create instance  ex: \"--onstart onstart_wget.sh  --env '-e ONSTART_PATH=https://s3.amazonaws.com/public.vast.ai/onstart_OOBA.sh' --image atinoda/text-generation-webui:default-nightly --disk 64\"", type=str),
    argument("--endpoint_name",   help="deployment endpoint name (allows multiple workergroups to share same deployment endpoint)", type=str),
    argument("--endpoint_id",   help="deployment endpoint id (allows multiple workergroups to share same deployment endpoint)", type=int),
    usage="vastai update workergroup WORKERGROUP_ID --endpoint_id ENDPOINT_ID [options]",
    help="Update an existing autoscale group",
    epilog=deindent("""
        Example: vastai update workergroup 4242 --min_load 100 --target_util 0.9 --cold_mult 2.0 --search_params \"gpu_ram>=23 num_gpus=2 gpu_name=RTX_4090 inet_down>200 direct_port_count>2 disk_space>=64\" --launch_args \"--onstart onstart_wget.sh  --env '-e ONSTART_PATH=https://s3.amazonaws.com/public.vast.ai/onstart_OOBA.sh' --image atinoda/text-generation-webui:default-nightly --disk 64\" --gpu_ram 32.0 --endpoint_name "LLama" --endpoint_id 2
    """),
)
def update__workergroup(args):
    id  = args.id
    url = apiurl(args, f"/autojobs/{id}/" )
    if args.no_default:
        query = ""
    else:
        query = " verified=True rentable=True rented=False"
    if args.search_params is not None:
        query = args.search_params + query
    json_blob = {"client_id": "me", "autojob_id": args.id, "min_load": args.min_load, "target_util": args.target_util, "cold_mult": args.cold_mult, "cold_workers": args.cold_workers, "test_workers" : args.test_workers, "template_hash": args.template_hash, "template_id": args.template_id, "search_params": query, "launch_args": args.launch_args, "gpu_ram": args.gpu_ram, "endpoint_name": args.endpoint_name, "endpoint_id": args.endpoint_id}
    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_put(args, url,  headers=state.headers,json=json_blob)
    r.raise_for_status()
    if 'application/json' in r.headers.get('Content-Type', ''):
        try:
            print("workergroup update {}".format(r.json()))
        except requests.exceptions.JSONDecodeError:
            print("The response is not valid JSON.")
            print(r)
            print(r.text)  # Print the raw response to help with debugging.
    else:
        print("The response is not JSON. Content-Type:", r.headers.get('Content-Type'))
        print(r.text)

@parser.command(
    argument("id", help="id of endpoint group to update", type=int),
    argument("--min_load", help="minimum floor load in perf units/s  (token/s for LLms)", type=float),
    argument("--min_cold_load", help="minimum floor load in perf units/s  (token/s for LLms), but allow handling with cold workers", type=float),
    argument("--endpoint_state", help="active, suspended, or stopped", type=str),
    argument("--auto_instance", help=argparse.SUPPRESS, type=str, default="prod"),
    argument("--target_util",      help="target capacity utilization (fraction, max 1.0, default 0.9)", type=float),
    argument("--cold_mult",   help="cold/stopped instance capacity target as multiple of hot capacity target (default 2.5)", type=float),
    argument("--cold_workers", help="min number of workers to keep 'cold' when you have no load (default 5)", type=int),
    argument("--max_workers", help="max number of workers your endpoint group can have (default 20)", type=int),
    argument("--endpoint_name",   help="deployment endpoint name (allows multiple workergroups to share same deployment endpoint)", type=str),
    usage="vastai update endpoint ID [OPTIONS]",
    help="Update an existing endpoint group",
    epilog=deindent("""
        Example: vastai update endpoint 4242 --min_load 100 --target_util 0.9 --cold_mult 2.0 --endpoint_name "LLama"
    """),
)
def update__endpoint(args):
    id  = args.id
    url = apiurl(args, f"/endptjobs/{id}/" )
    json_blob = {"client_id": "me", "endptjob_id": args.id, "min_load": args.min_load, "min_cold_load":args.min_cold_load,"target_util": args.target_util, "cold_mult": args.cold_mult, "cold_workers": args.cold_workers, "max_workers" : args.max_workers, "endpoint_name": args.endpoint_name, "endpoint_state": args.endpoint_state, "autoscaler_instance":args.auto_instance}
    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_put(args, url,  headers=state.headers,json=json_blob)
    r.raise_for_status()
    if 'application/json' in r.headers.get('Content-Type', ''):
        try:
            print("update endpoint {}".format(r.json()))
        except requests.exceptions.JSONDecodeError:
            print("The response is not valid JSON.")
            print(r)
            print(r.text)  # Print the raw response to help with debugging.
    else:
        print("The response is not JSON. Content-Type:", r.headers.get('Content-Type'))
        print(r.text)
