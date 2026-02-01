"""Commands for managing host machines, volumes, and network disks."""

import argparse
import json
import requests
from datetime import datetime, timezone

from vast_cli.parser import parser, argument, hidden_aliases
from vast_cli import state
from vast_cli.api.client import http_get, http_post, http_put, http_del
from vast_cli.api.helpers import apiurl
from vast_cli.display.formatting import deindent
from vast_cli.display.table import display_table
from vast_cli.helpers import cleanup_machine, list_machine
from vast_cli.query.fields import (
    machine_fields,
    maintenance_fields,
    network_disk_fields,
    network_disk_machine_fields,
)
from vast_cli.validation.validators import string_to_unix_epoch


@parser.command(
    argument("machines", help="ids of machines to add disk to, that is networked to be on the same LAN as machine", type=int, nargs='+'),
    argument("mount_point", help="mount path of disk to add", type=str),
    argument("-d", "--disk_id", help="id of network disk to attach to machines in the cluster", type=int, nargs='?'),
    aliases=hidden_aliases(["add network-disk"]),
    usage="vastai machine add-network-disk MACHINES MOUNT_PATH [options]",
    help="[Host] Add Network Disk to Physical Cluster.",
    epilog=deindent("""
        This variant can be used to add a network disk to a physical cluster.
        When you add a network disk for the first time, you just need to specify the machine(s) and mount_path.
        When you add a network disk for the second time, you need to specify the disk_id.
        Example:
        vastai machine add-network-disk 1 /mnt/disk1
        vastai machine add-network-disk 1 /mnt/disk1 -d 12345
    """)
)
def machine__add_network_disk(args):
    json_blob = {
        "machines": [int(id) for id in args.machines],
        "mount_point": args.mount_point,
    }
    if args.disk_id is not None:
        json_blob["disk_id"] = args.disk_id
    url = apiurl(args, "/network_disk/")
    if args.explain:
        print("request json: ")
        print(json_blob)
    r = http_post(args, url, headers=state.headers, json=json_blob)
    r.raise_for_status()

    if args.raw:
        return r

    print("Attached network disk to machines. Disk id: " + str(r.json()["disk_id"]))


@parser.command(
    argument("id", help="id of machine to cancel maintenance(s) for", type=int),
    aliases=hidden_aliases(["cancel maint"]),
    usage="vastai machine cancel-maint id",
    help="[Host] Cancel maint window",
    epilog=deindent("""
        For deleting a machine's scheduled maintenance window(s), use this cancel maint command.
        Example: vastai machine cancel-maint 8207
    """),
    )
def machine__cancel_maint(args):
    """
    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    url = apiurl(args, "/machines/{id}/cancel_maint/".format(id=args.id))

    print(f"Cancelling scheduled maintenance window(s) for machine {args.id}.")
    ok = input("Continue? [y/n] ")
    if ok.strip().lower() != "y":
        return

    json_blob = {"client_id": "me", "machine_id": args.id}
    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_put(args, url,  headers=state.headers,json=json_blob)

    if r.status_code == 200:
        print(r.text)
        print(f"Cancel maintenance window(s) scheduled for machine {args.id} success")
    else:
        print(r.text)
        print(f"failed with error {r.status_code}")


@parser.command(
    argument("id", help="id of machine to cleanup", type=int),
    aliases=hidden_aliases(["cleanup machine"]),
    usage="vastai machine cleanup ID [options]",
    help="[Host] Remove all expired storage instances from the machine, freeing up space",
    epilog=deindent("""
        Instances expire on their end date. Expired instances still pay storage fees, but can not start.
        Since hosts are still paid storage fees for expired instances, we do not auto delete them.
        Instead you can use this CLI/API function to delete all expired storage instances for a machine.
        This is useful if you are running low on storage, want to do maintenance, or are subsidizing storage, etc.
    """)
)
def machine__cleanup(args):
    """
    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    cleanup_machine(args, args.id)


@parser.command(
    argument("IDs", help="ids of machines", type=int, nargs='+'),
    aliases=hidden_aliases(["defrag machines"]),
    usage="vastai machine defrag IDs",
    help="[Host] Defragment machines",
    epilog=deindent("""
        Defragment some of your machines. This will rearrange GPU assignments to try and make more multi-gpu offers available.
    """),
)
def machine__defrag(args):
    url = apiurl(args, "/machines/defrag_offers/" )
    json_blob = {"machine_ids": args.IDs}
    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_put(args, url, headers=state.headers, json=json_blob)
    r.raise_for_status()
    if 'application/json' in r.headers.get('Content-Type', ''):
        try:
            print(f"defragment result: {r.json()}")
        except requests.exceptions.JSONDecodeError:
            print("The response is not valid JSON.")
            print(r)
            print(r.text)  # Print the raw response to help with debugging.
    else:
        print("The response is not JSON. Content-Type:", r.headers.get('Content-Type'))
        print(r.text)

@parser.command(
   argument("id", help="id of machine to delete", type=int),
    aliases=hidden_aliases(["delete machine"]),
    usage="vastai machine delete <id>",
    help="[Host] Delete machine if the machine is not being used by clients. host jobs on their own machines are disregarded and machine is force deleted.",
)
def machine__delete(args):
    """
    Deletes machine if the machine is not in use by clients. Disregards host jobs on their own machines and force deletes a machine.
    """
    req_url = apiurl(args, f"/machines/{args.id}/force_delete/")
    r = http_post(args, req_url, headers=state.headers)
    if (r.status_code == 200):
        rj = r.json()
        if (rj["success"]):
            print(f"deleted machine_id ({args.id}) and all related contracts.")
        else:
            print(rj["msg"])
    else:
        print(r.text)
        print(f"failed with error {r.status_code}")


@parser.command(
    argument("id", help="id of machine to list", type=int),
    argument("-g", "--price_gpu", help="per gpu rental price in $/hour  (price for active instances)", type=float),
    argument("-s", "--price_disk",
             help="storage price in $/GB/month (price for inactive instances), default: $0.10/GB/month", type=float),
    argument("-u", "--price_inetu", help="price for internet upload bandwidth in $/GB", type=float),
    argument("-d", "--price_inetd", help="price for internet download bandwidth in $/GB", type=float),
    argument("-b", "--price_min_bid", help="per gpu minimum bid price floor in $/hour", type=float),
    argument("-r", "--discount_rate", help="Max long term prepay discount rate fraction, default: 0.4 ", type=float),
    argument("-m", "--min_chunk", help="minimum amount of gpus", type=int),
    argument("-e", "--end_date", help="contract offer expiration - the available until date (optional, in unix float timestamp or MM/DD/YYYY format)", type=str),
    argument("-l", "--duration", help="Updates end_date daily to be duration from current date. Cannot be combined with end_date. Format is: `n days`, `n weeks`, `n months`, `n years`, or total intended duration in seconds."),
    argument("-v", "--vol_size", help="Size for volume contract offer. Defaults to half of available disk. Set 0 to not create a volume contract offer.", type=int),
    argument("-z", "--vol_price", help="Price for disk on volume contract offer. Defaults to price_disk. Invalid if vol_size is 0.", type=float),
    aliases=hidden_aliases(["list machine"]),
    usage="vastai machine publish ID [options]",
    help="[Host] list a machine for rent",
    epilog=deindent("""
        Performs the same action as pressing the "LIST" button on the site https://cloud.vast.ai/host/machines.
        On the end date the listing will expire and your machine will unlist. However any existing client jobs will still remain until ended by their owners.
        Once you list your machine and it is rented, it is extremely important that you don't interfere with the machine in any way.
        If your machine has an active client job and then goes offline, crashes, or has performance problems, this could permanently lower your reliability rating.
        We strongly recommend you test the machine first and only list when ready.
    """)
)
def machine__publish(args):
    """
    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    return list_machine(args, args.id)


@parser.command(
    argument("ids", help="ids of instance to list", type=int, nargs='+'),
    argument("-g", "--price_gpu", help="per gpu on-demand rental price in $/hour (base price for active instances)", type=float),
    argument("-s", "--price_disk",
             help="storage price in $/GB/month (price for inactive instances), default: $0.10/GB/month", type=float),
    argument("-u", "--price_inetu", help="price for internet upload bandwidth in $/GB", type=float),
    argument("-d", "--price_inetd", help="price for internet download bandwidth in $/GB", type=float),
    argument("-b", "--price_min_bid", help="per gpu minimum bid price floor in $/hour", type=float),
    argument("-r", "--discount_rate", help="Max long term prepay discount rate fraction, default: 0.4 ", type=float),
    argument("-m", "--min_chunk", help="minimum amount of gpus", type=int),
    argument("-e", "--end_date", help="contract offer expiration - the available until date (optional, in unix float timestamp or MM/DD/YYYY format)", type=str),
    argument("-l", "--duration", help="Updates end_date daily to be duration from current date. Cannot be combined with end_date. Format is: `n days`, `n weeks`, `n months`, `n years`, or total intended duration in seconds."),
    argument("-v", "--vol_size", help="Size for volume contract offer. Defaults to half of available disk. Set 0 to not create a volume contract offer.", type=int),
    argument("-z", "--vol_price", help="Price for disk on volume contract offer. Defaults to price_disk. Invalid if vol_size is 0.", type=float),
    aliases=hidden_aliases(["list machines"]),
    usage="vastai machine publish-batch IDs [options]",
    help="[Host] list machines for rent",
    epilog=deindent("""
        This variant can be used to list or update the listings for multiple machines at once with the same args.
        You could extend the end dates of all your machines using a command combo like this:
        ./vast.py machine publish-batch $(./vast.py machine list -q) -e 12/31/2024 --retry 6
    """)
)
def machine__publish_batch(args):
    """
    """
    return [list_machine(args, id) for id in args.ids]


@parser.command(
    argument("disk_id", help="id of network disk to list", type=int),
    argument("-p", "--price_disk", help="storage price in $/GB/month, default: $%(default).2f/GB/month", default=.15, type=float),
    argument("-e", "--end_date", help="contract offer expiration - the available until date (optional, in unix float timestamp or MM/DD/YYYY format), default 1 month", type=str, default=None),
    argument("-s", "--size", help="size of disk space allocated to offer in GB, default %(default)s GB", default=15, type=int),
    aliases=hidden_aliases(["list network-volume"]),
    usage="vastai network-volume publish DISK_ID [options]",
    help="[Host] list disk space for rent as a network volume"
)
def network_volume__publish(args):
    json_blob = {
        "disk_id": args.disk_id,
        "price_disk": args.price_disk,
        "size": args.size
    }

    if args.end_date:
        json_blob["end_date"] = string_to_unix_epoch(args.end_date)

    url = apiurl(args, "/network_volumes/")

    if args.explain:
        print("request json: ")
        print(json_blob)

    r = http_post(args, url, headers=state.headers, json=json_blob)
    r.raise_for_status()
    if args.raw:
        return r

    print(r.json()["msg"])


@parser.command(
    argument("id", help="id of machine to list", type=int),
    argument("-p", "--price_disk",
             help="storage price in $/GB/month, default: $%(default).2f/GB/month", default=.10, type=float),
    argument("-e", "--end_date", help="contract offer expiration - the available until date (optional, in unix float timestamp or MM/DD/YYYY format), default 3 months", type=str),
    argument("-s", "--size", help="size of disk space allocated to offer in GB, default %(default)s GB", default=15),
    aliases=hidden_aliases(["list volume"]),
    usage="vastai volume publish ID [options]",
    help="[Host] list disk space for rent as a volume on a machine",
    epilog=deindent("""
        Allocates a section of disk on a machine to be used for volumes.
    """)
)
def volume__publish(args):
    json_blob ={
        "size": int(args.size),
        "machine": int(args.id),
        "price_disk": float(args.price_disk)
    }
    if args.end_date:
        json_blob["end_date"] = string_to_unix_epoch(args.end_date)


    url = apiurl(args, "/volumes/")

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
    argument("ids", help="id of machines list", type=int, nargs='+'),
    argument("-p", "--price_disk",
             help="storage price in $/GB/month, default: $%(default).2f/GB/month", default=.10, type=float),
    argument("-e", "--end_date", help="contract offer expiration - the available until date (optional, in unix float timestamp or MM/DD/YYYY format), default 3 months", type=str),
    argument("-s", "--size", help="size of disk space allocated to offer in GB, default %(default)s GB", default=15),
    aliases=hidden_aliases(["list volumes"]),
    usage="vastai volume publish-batch IDs [options]",
    help="[Host] list disk space for rent as a volume on machines",
    epilog=deindent("""
        Allocates a section of disk on machines to be used for volumes.
    """)
)
def volume__publish_batch(args):
    json_blob ={
        "size": int(args.size),
        "machine": [int(id) for id in args.ids],
        "price_disk": float(args.price_disk)
    }
    if args.end_date:
        json_blob["end_date"] = string_to_unix_epoch(args.end_date)


    url = apiurl(args, "/volumes/")

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
    argument("id", help="id of machine to remove default instance from", type=int),
    aliases=hidden_aliases(["remove defjob"]),
    usage="vastai machine remove-defjob id",
    help="[Host] Delete default jobs",
)
def machine__remove_defjob(args):
    """


    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    req_url = apiurl(args, f"/machines/{args.id}/defjob/")
    r = http_del(args, req_url, headers=state.headers)

    if (r.status_code == 200):
        rj = r.json()
        if (rj["success"]):
            print(f"default instance for machine {args.id} removed.")
        else:
            print(rj["msg"])
    else:
        print(r.text)
        print(f"failed with error {r.status_code}")


def set_ask(args):
    """

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    print("set asks!\n")


@parser.command(
    argument("id", help="id of machine to launch default instance on", type=int),
    argument("--price_gpu", help="per gpu rental price in $/hour", type=float),
    argument("--price_inetu", help="price for internet upload bandwidth in $/GB", type=float),
    argument("--price_inetd", help="price for internet download bandwidth in $/GB", type=float),
    argument("--image", help="docker container image to launch", type=str),
    argument("--args", nargs=argparse.REMAINDER, help="list of arguments passed to container launch"),
    aliases=hidden_aliases(["set defjob"]),
    usage="vastai machine set-defjob id [--api-key API_KEY] [--price_gpu PRICE_GPU] [--price_inetu PRICE_INETU] [--price_inetd PRICE_INETD] [--image IMAGE] [--args ...]",
    help="[Host] Create default jobs for a machine",
    epilog=deindent("""
        Performs the same action as creating a background job at https://cloud.vast.ai/host/create.

    """)

)
def machine__set_defjob(args):
    """

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    req_url   = apiurl(args, "/machines/create_bids/")
    json_blob = {'machine': args.id, 'price_gpu': args.price_gpu, 'price_inetu': args.price_inetu, 'price_inetd': args.price_inetd, 'image': args.image, 'args': args.args}
    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_put(args, req_url, headers=state.headers, json=json_blob)
    if (r.status_code == 200):
        rj = r.json()
        if (rj["success"]):
            print(f"bids created for machine {args.id},  @ ${args.price_gpu}/gpu/day, ${args.price_inetu}/GB up, ${args.price_inetd}/GB down")
        else:
            print(rj["msg"])
    else:
        print(r.text)
        print(f"failed with error {r.status_code}")


@parser.command(
    argument("id", help="id of machine to set min bid price for", type=int),
    argument("--price", help="per gpu min bid price in $/hour", type=float),
    aliases=hidden_aliases(["set min-bid"]),
    usage="vastai machine set-min-bid id [--price PRICE]",
    help="[Host] Set the minimum bid/rental price for a machine",
    epilog=deindent("""
        Change the current min bid price of machine id to PRICE.
    """),
)
def machine__set_min_bid(args):
    """

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    url = apiurl(args, "/machines/{id}/minbid/".format(id=args.id))
    json_blob = {"client_id": "me", "price": args.price,}
    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_put(args, url,  headers=state.headers,json=json_blob)
    r.raise_for_status()
    print("Per gpu min bid price changed")


@parser.command(
    argument("id", help="id of machine to schedule maintenance for", type=int),
    argument("--sdate",      help="maintenance start date in unix epoch time (UTC seconds)", type=float),
    argument("--duration",   help="maintenance duration in hours", type=float),
    argument("--maintenance_category",   help="(optional) can be one of [power, internet, disk, gpu, software, other]", type=str, default="not provided"),
    aliases=hidden_aliases(["schedule maint"]),
    usage="vastai machine schedule-maint id [--sdate START_DATE --duration DURATION --maintenance_category MAINTENANCE_CATEGORY]",
    help="[Host] Schedule upcoming maint window",
    epilog=deindent("""
        The proper way to perform maintenance on your machine is to wait until all active contracts have expired or the machine is vacant.
        For unplanned or unscheduled maintenance, use this schedule maint command. That will notify the client that you have to take the machine down and that they should save their work.
        You can specify a date, duration, reason and category for the maintenance.

        Example: vastai machine schedule-maint 8207 --sdate 1677562671 --duration 0.5 --maintenance_category "power"
    """),
    )
def machine__schedule_maint(args):
    """
    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    url = apiurl(args, "/machines/{id}/dnotify/".format(id=args.id))

    dt = datetime.fromtimestamp(args.sdate, tz=timezone.utc)
    print(f"Scheduling maintenance window starting {dt} lasting {args.duration} hours")
    print(f"This will notify all clients of this machine.")
    ok = input("Continue? [y/n] ")
    if ok.strip().lower() != "y":
        return

    json_blob = {"client_id": "me", "sdate": string_to_unix_epoch(args.sdate), "duration": args.duration, "maintenance_category": args.maintenance_category}
    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_put(args, url,  headers=state.headers,json=json_blob)
    r.raise_for_status()
    print(f"Maintenance window scheduled for {dt} success")

@parser.command(
    argument("Machine", help="id of machine to display", type=int),
    argument("-q", "--quiet", action="store_true", help="only display numeric ids"),
    aliases=hidden_aliases(["show machine"]),
    usage="vastai machine show ID [OPTIONS]",
    help="[Host] Show hosted machines",
)
def machine__show(args):
    """
    Show a machine the host is offering for rent.

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    req_url = apiurl(args, f"/machines/{args.Machine}", {"owner": "me"})
    r = http_get(args, req_url)
    r.raise_for_status()
    rows = r.json()
    if args.raw:
        return r
    else:
        if args.quiet:
            ids = [f"{row['id']}" for row in rows]
            print(" ".join(id for id in ids))
        else:
            display_table(rows, machine_fields)


@parser.command(
    argument("-q", "--quiet", action="store_true", help="only display numeric ids"),
    aliases=hidden_aliases(["show machines"]),
    usage="vastai machine list [OPTIONS]",
    help="[Host] Show hosted machines",
)
def machine__list(args):
    """
    Show the machines user is offering for rent.

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    req_url = apiurl(args, "/machines", {"owner": "me"})
    r = http_get(args, req_url)
    r.raise_for_status()
    rows = r.json()["machines"]
    if args.raw:
        return r
    else:
        if args.quiet:
            ids = [f"{row['id']}" for row in rows]
            print(" ".join(id for id in ids))
        else:
            display_table(rows, machine_fields)


@parser.command(
    argument("-ids", help="comma seperated string of machine_ids for which to get maintenance information", type=str),
    argument("-q", "--quiet", action="store_true", help="only display numeric ids of the machines in maintenance"),
    aliases=hidden_aliases(["show maints"]),
    usage="\nvastai machine show-maints -ids 'machine_id_1' [OPTIONS]\nvastai machine show-maints -ids 'machine_id_1, machine_id_2' [OPTIONS]",
    help="[Host] Show maintenance information for host machines",
)
def machine__show_maints(args):
    """
    Show the maintenance information for the machines

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    machine_ids = args.ids.split(',')
    machine_ids = list(map(int, machine_ids))

    req_url = apiurl(args, "/machines/maintenances", {"owner": "me", "machine_ids" : machine_ids})
    r = http_get(args, req_url)
    r.raise_for_status()
    rows = r.json()
    if args.raw:
        return r
    else:
        if args.quiet:
            ids = [f"{row['machine_id']}" for row in rows]
            print(" ".join(id for id in ids))
        else:
            display_table(rows, maintenance_fields)


@parser.command(
    aliases=hidden_aliases(["show network-disks"]),
    usage="vastai machine show-network-disks",
    help="[Host] Show network disks associated with your account.",
    epilog=deindent("""
        Show network disks associated with your account.
    """)
)
def machine__show_network_disks(args: argparse.Namespace):
    req_url = apiurl(args, "/network_disk/")
    r = http_get(args, req_url)
    r.raise_for_status()
    response_data = r.json()

    if args.raw:
        return response_data

    for cluster_data in response_data['data']:
        print(f"Cluster ID: {cluster_data['cluster_id']}")
        display_table(cluster_data['network_disks'], network_disk_fields, replace_spaces=False)

        machine_rows = []
        for machine_id in cluster_data['machine_ids']:
            machine_rows.append(
                {
                    "machine_id": machine_id,
                    "mount_point": cluster_data['mounts'].get(str(machine_id), "N/A"),
                }
            )
        print()
        display_table(machine_rows, network_disk_machine_fields, replace_spaces=False)
        print("\n")


@parser.command(
    argument("id", help="id of machine to unlist", type=int),
    aliases=hidden_aliases(["unlist machine"]),
    usage="vastai machine unpublish <id>",
    help="[Host] Unlist a listed machine",
)

def machine__unpublish(args):
    """
    Removes machine from list of machines for rent.

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    req_url = apiurl(args, f"/machines/{args.id}/asks/")
    r = http_del(args, req_url, headers=state.headers)
    if (r.status_code == 200):
        rj = r.json()
        if (rj["success"]):
            print(f"all offers for machine {args.id} removed, machine delisted.")
        else:
            print(rj["msg"])
    else:
        print(r.text)
        print(f"failed with error {r.status_code}")

@parser.command(
    argument("id", help="id of network volume offer to unlist", type=int),
    aliases=hidden_aliases(["unlist network-volume"]),
    usage="vastai network-volume unpublish OFFER_ID",
    help="[Host] Unlists network volume offer",
)
def network_volume__unpublish(args):
    json_blob = {
        "id": args.id
    }

    url = apiurl(args, "/network_volumes/unlist/")

    if args.explain:
        print("request json: ")
        print(json_blob)

    r = http_post(args, url, headers=state.headers, json=json_blob)
    r.raise_for_status()
    if args.raw:
        return r

    print(r.json()["msg"])

@parser.command(
    argument("id", help="volume ID you want to unlist", type=int),
    aliases=hidden_aliases(["unlist volume"]),
    usage="vastai volume unpublish ID",
    help="[Host] unlist volume offer"
)
def volume__unpublish(args):
    id = args.id

    json_blob = {
        "id": id
    }

    url = apiurl(args, "/volumes/unlist")

    if args.explain:
        print("request json:", json_blob)

    r = http_post(args, url, headers=state.headers, json=json_blob)
    r.raise_for_status()
    if args.raw:
        return r
    else:
        print(r.json()["msg"])
