"""Commands for data transfer operations (copy, sync, clone, snapshot)."""

import json
import argparse
import subprocess

from vast_cli.parser import parser, argument
from vast_cli import state
from vast_cli.api.client import http_get, http_post, http_put, http_del
from vast_cli.api.helpers import apiurl
from vast_cli.display.formatting import deindent
from vast_cli.query.parser import parse_vast_url, VRLException
from vast_cli.validation.validators import (
    validate_frequency_values,
    default_start_date,
    default_end_date,
    parse_day_cron_style,
    parse_hour_cron_style,
    convert_timestamp_to_date,
    convert_dates_to_timestamps,
)

import requests


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


@parser.command(
    argument("dst", help="instance_id:/path to target of copy operation", type=str),
    usage="vastai cancel copy DST",
    help="Cancel a remote copy in progress, specified by DST id",
    epilog=deindent("""
        Use this command to cancel any/all current remote copy operations copying to a specific named instance, given by DST.

        Examples:
         vast cancel copy 12371

        The first example cancels all copy operations currently copying data into instance 12371

    """),
)
def cancel__copy(args: argparse.Namespace):
    """
    Cancel a remote copy in progress, specified by DST id"

    @param dst: ID of copy instance Target to cancel.
    """

    url = apiurl(args, f"/commands/copy_direct/")
    dst_id = args.dst
    if (dst_id is None):
        print("invalid arguments")
        return

    print(f"canceling remote copies to {dst_id} ")

    req_json = { "client_id": "me", "dst_id": dst_id, }
    r = http_del(args, url, headers=state.headers,json=req_json)
    r.raise_for_status()
    if (r.status_code == 200):
        rj = r.json();
        if (rj["success"]):
            print("Remote copy canceled - check instance status bar for progress updates (~30 seconds delayed).")
        else:
            print(rj["msg"]);
    else:
        print(r.text);
        print("failed with error {r.status_code}".format(**locals()));


@parser.command(
    argument("dst", help="instance_id:/path to target of sync operation", type=str),
    usage="vastai cancel sync DST",
    help="Cancel a remote copy in progress, specified by DST id",
    epilog=deindent("""
        Use this command to cancel any/all current remote cloud sync operations copying to a specific named instance, given by DST.

        Examples:
         vast cancel sync 12371

        The first example cancels all copy operations currently copying data into instance 12371

    """),
)
def cancel__sync(args: argparse.Namespace):
    """
    Cancel a remote cloud sync in progress, specified by DST id"

    @param dst: ID of cloud sync instance Target to cancel.
    """

    url = apiurl(args, f"/commands/rclone/")
    dst_id = args.dst
    if (dst_id is None):
        print("invalid arguments")
        return

    print(f"canceling remote copies to {dst_id} ")

    req_json = { "client_id": "me", "dst_id": dst_id, }
    r = http_del(args, url, headers=state.headers,json=req_json)
    r.raise_for_status()
    if (r.status_code == 200):
        rj = r.json();
        if (rj["success"]):
            print("Remote copy canceled - check instance status bar for progress updates (~30 seconds delayed).")
        else:
            print(rj["msg"]);
    else:
        print(r.text);
        print("failed with error {r.status_code}".format(**locals()));


@parser.command(
    argument("source", help="id of volume contract being cloned", type=int),
    argument("dest", help="id of volume offer volume is being copied to", type=int),
    argument("-s", "--size", help="Size of new volume contract, in GB. Must be greater than or equal to the source volume, and less than or equal to the destination offer.", type=float),
    argument("-d", "--disable_compression", action="store_true", help="Do not compress volume data before copying."),
    usage="vastai copy volume <source_id> <dest_id> [options]",
    help="Clone an existing volume",
    epilog=deindent("""
        Create a new volume with the given offer, by copying the existing volume.
        Size defaults to the size of the existing volume, but can be increased if there is available space.
    """)
)
def clone__volume(args: argparse.Namespace):
    json_blob={
        "src_id" : args.source,
        "dst_id": args.dest,
    }
    if args.size:
        json_blob["size"] = args.size
    if args.disable_compression:
        json_blob["disable_compression"] = True


    url = apiurl(args, "/volumes/copy/")

    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_post(args, url,  headers=state.headers,json=json_blob)
    r.raise_for_status()
    if args.raw:
        return r
    else:
        print("Created. {}".format(r.json()))


@parser.command(
    argument("src", help="Source location for copy operation (supports multiple formats)", type=str),
    argument("dst", help="Target location for copy operation (supports multiple formats)", type=str),
    argument("-i", "--identity", help="Location of ssh private key", type=str),
    usage="vastai copy SRC DST",
    help="Copy directories between instances and/or local",
    epilog=deindent("""
        Copies a directory from a source location to a target location. Each of source and destination
        directories can be either local or remote, subject to appropriate read and write
        permissions required to carry out the action.

        Supported location formats:
        - [instance_id:]path               (legacy format, still supported)
        - C.instance_id:path              (container copy format)
        - cloud_service:path              (cloud service format)
        - cloud_service.cloud_service_id:path  (cloud service with ID)
        - local:path                      (explicit local path)
        - V.volume_id:path                (volume copy, see restrictions)

        You should not copy to /root or / as a destination directory, as this can mess up the permissions on your instance ssh folder, breaking future copy operations (as they use ssh authentication)
        You can see more information about constraints here: https://vast.ai/docs/gpu-instances/data-movement#constraints
        Volume copy is currently only supported for copying to other volumes or instances, not cloud services or local.

        Examples:
         vast copy 6003036:/workspace/ 6003038:/workspace/
         vast copy C.11824:/data/test local:data/test
         vast copy local:data/test C.11824:/data/test
         vast copy drive:/folder/file.txt C.6003036:/workspace/
         vast copy s3.101:/data/ C.6003036:/workspace/
         vast copy V.1234:/file C.5678:/workspace/

        The first example copy syncs all files from the absolute directory '/workspace' on instance 6003036 to the directory '/workspace' on instance 6003038.
        The second example copy syncs files from container 11824 to the local machine using structured syntax.
        The third example copy syncs files from local to container 11824 using structured syntax.
        The fourth example copy syncs files from Google Drive to an instance.
        The fifth example copy syncs files from S3 bucket with id 101 to an instance.
    """),
)
def copy(args: argparse.Namespace):
    """
    Transfer data from one instance to another.

    @param src: Location of data object to be copied.
    @param dst: Target to copy object to.
    """

    (src_id, src_path) = parse_vast_url(args.src)
    (dst_id, dst_path) = parse_vast_url(args.dst)
    if (src_id is None) and (dst_id is None):
        pass
        #print("invalid arguments")
        #return

    print(f"copying {str(src_id)+':' if src_id else ''}{src_path} {str(dst_id)+':' if dst_id else ''}{dst_path}")

    req_json = {
        "client_id": "me",
        "src_id": src_id,
        "dst_id": dst_id,
        "src_path": src_path,
        "dst_path": dst_path,
    }
    if (args.explain):
        print("request json: ")
        print(req_json)
    if (src_id is None) or (dst_id is None):
        url = apiurl(args, f"/commands/rsync/")
    else:
        url = apiurl(args, f"/commands/copy_direct/")
    r = http_put(args, url,  headers=state.headers,json=req_json)
    r.raise_for_status()
    if (r.status_code == 200):
        rj = r.json()
        #print(json.dumps(rj, indent=1, sort_keys=True))
        if (rj["success"]) and ((src_id is None or src_id == "local") or (dst_id is None or dst_id == "local")):
            homedir = subprocess.getoutput("echo $HOME")
            #print(f"homedir: {homedir}")
            remote_port = None
            identity = f"-i {args.identity}" if (args.identity is not None) else ""
            if (src_id is None or src_id == "local"):
                #result = subprocess.run(f"mkdir -p {src_path}", shell=True)
                remote_port = rj["dst_port"]
                remote_addr = rj["dst_addr"]
                cmd = f"rsync -arz -v --progress --rsh=ssh -e 'ssh {identity} -p {remote_port} -o StrictHostKeyChecking=no' {src_path} vastai_kaalia@{remote_addr}::{dst_id}/{dst_path}"
                print(cmd)
                result = subprocess.run(cmd, shell=True)
                #result = subprocess.run(["sudo", "rsync" "-arz", "-v", "--progress", "-rsh=ssh", "-e 'sudo ssh -i {homedir}/.ssh/id_rsa -p {remote_port} -o StrictHostKeyChecking=no'", src_path, "vastai_kaalia@{remote_addr}::{dst_id}"], shell=True)
            elif (dst_id is None or dst_id == "local"):
                result = subprocess.run(f"mkdir -p {dst_path}", shell=True)
                remote_port = rj["src_port"]
                remote_addr = rj["src_addr"]
                cmd = f"rsync -arz -v --progress --rsh=ssh -e 'ssh {identity} -p {remote_port} -o StrictHostKeyChecking=no' vastai_kaalia@{remote_addr}::{src_id}/{src_path} {dst_path}"
                print(cmd)
                result = subprocess.run(cmd, shell=True)
                #result = subprocess.run(["sudo", "rsync" "-arz", "-v", "--progress", "-rsh=ssh", "-e 'ssh -i {homedir}/.ssh/id_rsa -p {remote_port} -o StrictHostKeyChecking=no'", "vastai_kaalia@{remote_addr}::{src_id}", dst_path], shell=True)
        else:
            if (rj["success"]):
                print("Remote to Remote copy initiated - check instance status bar for progress updates (~30 seconds delayed).")
            else:
                if rj["msg"] == "src_path not supported VMs.":
                    print("copy between VM instances does not currently support subpaths (only full disk copy)")
                elif rj["msg"] == "dst_path not supported for VMs.":
                    print("copy between VM instances does not currently support subpaths (only full disk copy)")
                else:
                    print(rj["msg"])
    else:
        print(r.text)
        print("failed with error {r.status_code}".format(**locals()));


'''
@parser.command(
    argument("src", help="instance_id of source VM.", type=int),
    argument("dst", help="instance_id of destination VM", type=int),
    usage="vastai vm copy SRC DST",
    help=" Copy VM image from one VM instance to another",
    epilog=deindent("""
        Copies the entire VM image of from one instance to another.

        Note: destination VM must be stopped during copy. The source VM
        does not need to be stopped, but it's highly recommended that you keep
        the source VM stopped for the duration of the copy.
    """),
)
def vm__copy(args: argparse.Namespace):
    """
    Transfer VM image from one instance to another.

    @param src: instance_id of source.
    @param dst: instance_id of destination.
    """
    src_id = args.src
    dst_id = args.dst

    print(f"copying from {src_id} to {dst_id}")

    req_json = {
        "client_id": "me",
        "src_id": src_id,
        "dst_id": dst_id,
    }
    url = apiurl(args, f"/commands/copy_direct/")
    if (args.explain):
        print("request json: ")
        print(req_json)

    r = http_put(args, url,  headers=state.headers,json=req_json)
    r.raise_for_status()
    if (r.status_code == 200):
        rj = r.json();
        if (rj["success"]):
            print("Remote to Remote copy initiated - check instance status bar for progress updates (~30 seconds delayed).")
        else:
            if rj["msg"] == "Invalid src_path.":
                print("src instance is not a VM")
            elif rj["msg"] == "Invalid dst_path.":
                print("dst instance is not a VM")
            else:
                print(rj["msg"]);
    else:
        print(r.text);
        print("failed with error {r.status_code}".format(**locals()));
'''

@parser.command(
    argument("--src", help="path to source of object to copy", type=str),
    argument("--dst", help="path to target of copy operation", type=str, default="/workspace"),
    argument("--instance", help="id of the instance", type=str),
    argument("--connection", help="id of cloud connection on your account (get from calling 'vastai show connections')", type=str),
    argument("--transfer", help="type of transfer, possible options include Instance To Cloud and Cloud To Instance", type=str, default="Instance to Cloud"),
    argument("--dry-run", help="show what would have been transferred", action="store_true"),
    argument("--size-only", help="skip based on size only, not mod-time or checksum", action="store_true"),
    argument("--ignore-existing", help="skip all files that exist on destination", action="store_true"),
    argument("--update", help="skip files that are newer on the destination", action="store_true"),
    argument("--delete-excluded", help="delete files on dest excluded from transfer", action="store_true"),
    argument("--schedule", choices=["HOURLY", "DAILY", "WEEKLY"], help="try to schedule a command to run hourly, daily, or monthly. Valid values are HOURLY, DAILY, WEEKLY  For ex. --schedule DAILY"),
    argument("--start_date", type=str, default=default_start_date(), help="Start date/time in format 'YYYY-MM-DD HH:MM:SS PM' (UTC). Default is now. (optional)"),
    argument("--end_date", type=str, help="End date/time in format 'YYYY-MM-DD HH:MM:SS PM' (UTC). Default is contract's end. (optional)"),
    argument("--day", type=parse_day_cron_style, help="Day of week you want scheduled job to run on (0-6, where 0=Sunday) or \"*\". Default will be 0. For ex. --day 0", default=0),
    argument("--hour", type=parse_hour_cron_style, help="Hour of day you want scheduled job to run on (0-23) or \"*\" (UTC). Default will be 0. For ex. --hour 16", default=0),
    usage="vastai cloud copy --src SRC --dst DST --instance INSTANCE_ID -connection CONNECTION_ID --transfer TRANSFER_TYPE",
    help="Copy files/folders to and from cloud providers",
    epilog=deindent("""
        Copies a directory from a source location to a target location. Each of source and destination
        directories can be either local or remote, subject to appropriate read and write
        permissions required to carry out the action. The format for both src and dst is [instance_id:]path.
        You can find more information about the cloud copy operation here: https://vast.ai/docs/gpu-instances/cloud-sync

        Examples:
         vastai show connections
         ID    NAME      Cloud Type
         1001  test_dir  drive
         1003  data_dir  drive

         vastai cloud copy --src /folder --dst /workspace --instance 6003036 --connection 1001 --transfer "Instance To Cloud"

        The example copies all contents of /folder into /workspace on instance 6003036 from gdrive connection 'test_dir'.
    """),
)
def cloud__copy(args: argparse.Namespace):
    """
    Transfer data from one instance to another.

    @param src: Location of data object to be copied.
    @param dst: Target to copy object to.
    """

    url = apiurl(args, f"/commands/rclone/")
    #(src_id, src_path) = parse_vast_url(args.src)
    #(dst_id, dst_path) = parse_vast_url(args.dst)
    if (args.src is None) and (args.dst is None):
        print("invalid arguments")
        return

    # Initialize an empty list for flags
    flags = []

    # Append flags to the list based on the argparse.Namespace
    if args.dry_run:
        flags.append("--dry-run")
    if args.size_only:
        flags.append("--size-only")
    if args.ignore_existing:
        flags.append("--ignore-existing")
    if args.update:
        flags.append("--update")
    if args.delete_excluded:
        flags.append("--delete-excluded")

    print(f"copying {args.src} {args.dst} {args.instance} {args.connection} {args.transfer}")

    req_json = {
        "src": args.src,
        "dst": args.dst,
        "instance_id": args.instance,
        "selected": args.connection,
        "transfer": args.transfer,
        "flags": flags
    }

    if (args.explain):
        print("request json: ")
        print(req_json)

    if (args.schedule):
        validate_frequency_values(args.day, args.hour, args.schedule)
        req_url = apiurl(args, "/instances/{id}/".format(id=args.instance) , {"owner": "me"} )
        r = http_get(args, req_url)
        r.raise_for_status()
        row = r.json()["instances"]

        if args.transfer.lower() == "instance to cloud":
            if row:
                # Get the cost per TB of internet upload
                up_cost = row.get("internet_up_cost_per_tb", None)
                if up_cost is not None:
                    confirm = input(
                        f"Internet upload cost is ${up_cost} per TB. "
                        "Are you sure you want to schedule a cloud backup? (y/n): "
                    ).strip().lower()
                    if confirm != "y":
                        print("Cloud backup scheduling aborted.")
                        return
                else:
                    print("Warning: Could not retrieve internet upload cost. Proceeding without confirmation. You can use show scheduled-jobs and delete scheduled-job commands to delete scheduled cloud backup job.")

                cli_command = "cloud copy"
                api_endpoint = "/api/v0/commands/rclone/"
                contract_end_date = row.get("end_date", None)
                add_scheduled_job(args, req_json, cli_command, api_endpoint, "POST", instance_id=args.instance, contract_end_date=contract_end_date)
                return
            else:
                print("Instance not found. Please check the instance ID.")
                return

    r = http_post(args, url, headers=state.headers,json=req_json)
    r.raise_for_status()
    if (r.status_code == 200):
        print("Cloud Copy Started - check instance status bar for progress updates (~30 seconds delayed).")
        print("When the operation is finished you should see 'Cloud Copy Operation Finished' in the instance status bar.")
    else:
        print(r.text);
        print("failed with error {r.status_code}".format(**locals()));


@parser.command(
    argument("instance_id",      help="instance_id of the container instance to snapshot",      type=str),
    argument("--container_registry", help="Container registry to push the snapshot to. Default will be docker.io", type=str, default="docker.io"),
    argument("--repo",    help="repo to push the snapshot to",     type=str),
    argument("--docker_login_user",help="Username for container registry with repo",     type=str),
    argument("--docker_login_pass",help="Password or token for container registry with repo",     type=str),
    argument("--pause",            help="Pause container's processes being executed by the CPU to take snapshot (true/false). Default will be true", type=str, default="true"),
    usage="vastai take snapshot INSTANCE_ID "
          "--repo REPO --docker_login_user USER --docker_login_pass PASS"
          "[--container_registry REGISTRY] [--pause true|false]",
    help="Schedule a snapshot of a running container and push it to your repo in a container registry",
    epilog=deindent("""
        Takes a snapshot of a running container instance and pushes snapshot to the specified repository in container registry.

        Use pause=true to pause the container during commit (safer but slower),
        or pause=false to leave it running (faster but may produce a filesystem-
// safer snapshot).
    """),
)
def take__snapshot(args: argparse.Namespace):
    """
    Take a container snapshot and push.

    @param instance_id: instance identifier.
    @param repo: Docker repository for the snapshot.
    @param container_registry: Container registry
    @param docker_login_user: Docker registry username.
    @param docker_login_pass: Docker registry password/token.
    @param pause: "true" or "false" to pause the container during commit.
    """
    instance_id       = args.instance_id
    repo              = args.repo
    container_registry = args.container_registry
    user              = args.docker_login_user
    password          = args.docker_login_pass
    pause_flag        = args.pause

    print(f"Taking snapshot for instance {instance_id} and pushing to repo {repo} in container registry {container_registry}")
    req_json = {
        "id":               instance_id,
        "container_registry": container_registry,
        "personal_repo":    repo,
        "docker_login_user":user,
        "docker_login_pass":password,
        "pause":            pause_flag
    }

    url = apiurl(args, f"/instances/take_snapshot/{instance_id}/")
    if args.explain:
        print("Request JSON:")
        print(json.dumps(req_json, indent=2))

    # POST to the snapshot endpoint
    r = http_post(args, url, headers=state.headers, json=req_json)
    r.raise_for_status()

    if r.status_code == 200:
        data = r.json()
        if data.get("success"):
            print(f"Snapshot request sent successfully. Please check your repo {repo} in container registry {container_registry} in 5-10 mins. It can take longer than 5-10 mins to push your snapshot image to your repo depending on the size of your image.")
        else:
            print(data.get("msg", "Unknown error with snapshot request"))
    else:
        print(r.text);
        print("failed with error {r.status_code}".format(**locals()));
