"""Commands for managing clusters, overlays, and connections."""

import argparse

from vast_cli.parser import parser, argument
from vast_cli import state
from vast_cli.api.client import http_get, http_post, http_put, http_del
from vast_cli.api.helpers import apiurl
from vast_cli.display.formatting import deindent
from vast_cli.display.table import display_table
from vast_cli.query.fields import cluster_fields, overlay_fields, connection_fields


@parser.command(
    argument("subnet", help="local subnet for cluster, ex: '0.0.0.0/24'", type=str),
    argument("manager_id", help="Machine ID of manager node in cluster. Must exist already.", type=int),
    usage="vastai create cluster SUBNET MANAGER_ID",
    help="Create Vast cluster",
    epilog=deindent("""
        Create Vast Cluster by defining a local subnet and manager id.""")
)
def create__cluster(args: argparse.Namespace):

    json_blob = {
        "subnet": args.subnet,
        "manager_id": args.manager_id
    }

    #TODO: this should happen at the decorator level for all CLI commands to reduce boilerplate
    if args.explain:
        print("request json: ")
        print(json_blob)

    req_url = apiurl(args, "/cluster/")
    r  = http_post(args, req_url, json=json_blob)
    r.raise_for_status()

    if args.raw:
        return r

    print(r.json()["msg"])

@parser.command(
    argument("cluster_id", help="ID of cluster to create overlay on top of", type=int),
    argument("name", help="overlay network name"),
    usage="vastai create overlay CLUSTER_ID OVERLAY_NAME",
    help="Creates overlay network on top of a physical cluster",
    epilog=deindent("""
    Creates an overlay network to allow local networking between instances on a physical cluster""")
)
def create__overlay(args: argparse.Namespace):
    json_blob = {
        "cluster_id": args.cluster_id,
        "name": args.name
    }

    if args.explain:
        print("request json:", json_blob)

    req_url = apiurl(args, "/overlay/")
    r = http_post(args, req_url, json=json_blob)
    r.raise_for_status()

    if args.raw:
        return r

    print(r.json()["msg"])

@parser.command(
    argument("cluster_id", help="ID of cluster to delete", type=int),
    usage="vastai delete cluster CLUSTER_ID",
    help="Delete Cluster",
    epilog=deindent("""
        Delete Vast Cluster""")
)
def delete__cluster(args: argparse.Namespace):
    json_blob = {
        "cluster_id": args.cluster_id
    }

    if args.explain:
        print("request json:", json_blob)

    req_url = apiurl(args, "/cluster/")
    r = http_del(args, req_url, json=json_blob)
    r.raise_for_status()

    if args.raw:
        return r

    print(r.json()["msg"])


@parser.command(
    argument("overlay_identifier", help="ID (int) or name (str) of overlay to delete", nargs="?"),
    usage="vastai delete overlay OVERLAY_IDENTIFIER",
    help="Deletes overlay and removes all of its associated instances"
)
def delete__overlay(args: argparse.Namespace):
    identifier = args.overlay_identifier
    try:
        overlay_id = int(identifier)
        json_blob = {
            "overlay_id": overlay_id
        }
    except (ValueError, TypeError):
        json_blob = {
            "overlay_name": identifier
        }

    if args.explain:
        print("request json:", json_blob)

    req_url = apiurl(args, "/overlay/")
    r = http_del(args, req_url, json=json_blob)
    r.raise_for_status()

    if args.raw:
        return r

    print(r.json()["msg"])

@parser.command(
    argument("cluster_id", help="ID of cluster to add machine to", type=int),
    argument("machine_ids", help="machine id(s) to join cluster", type=int, nargs="+"),
    usage="vastai join cluster CLUSTER_ID MACHINE_IDS",
    help="Join Machine to Cluster",
    epilog=deindent("""
        Join's Machine to Vast Cluster
    """)
)
def join__cluster(args: argparse.Namespace):
    json_blob = {
        "cluster_id": args.cluster_id,
        "machine_ids": args.machine_ids
    }

    if args.explain:
        print("request json:", json_blob)

    req_url = apiurl(args, "/cluster/")
    r = http_put(args, req_url, json=json_blob)
    r.raise_for_status()

    if args.raw:
        return r

    print(r.json()["msg"])


@parser.command(
    argument("name", help="Overlay network name to join instance to.", type=str),
    argument("instance_id", help="Instance ID to add to overlay.", type=int),
    usage="vastai join overlay OVERLAY_NAME INSTANCE_ID",
    help="Adds instance to an overlay network",
    epilog=deindent("""
    Adds an instance to a compatible overlay network.""")
)
def join__overlay(args: argparse.Namespace):
    json_blob = {
        "name": args.name,
        "instance_id": args.instance_id
    }

    if args.explain:
        print("request json:", json_blob)

    req_url = apiurl(args, "/overlay/")
    r = http_put(args, req_url, json=json_blob)
    r.raise_for_status()

    if args.raw:
        return r

    print(r.json()["msg"])


@parser.command(
    usage="vastai show connections [--api-key API_KEY] [--raw]",
    help="Display user's cloud connections"
)
def show__connections(args):
    """
    Shows the stats on the machine the user is renting.

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    req_url = apiurl(args, "/users/cloud_integrations/");
    print(req_url)
    r = http_get(args, req_url, headers=state.headers);
    r.raise_for_status()
    rows = r.json()

    if args.raw:
        return rows
    else:
        display_table(rows, connection_fields)


@parser.command(
    usage="vastai show clusters",
    help="Show clusters associated with your account.",
    epilog=deindent("""
        Show clusters associated with your account.
    """)
)
def show__clusters(args: argparse.Namespace):
    req_url = apiurl(args, "/clusters/")
    r = http_get(args, req_url)
    r.raise_for_status()
    response_data = r.json()

    if args.raw:
        return response_data

    rows = []
    for cluster_id, cluster_data in response_data['clusters'].items():
        machine_ids = [ node["machine_id"] for node in cluster_data["nodes"]]

        manager_node = next(node for node in cluster_data['nodes'] if node['is_cluster_manager'])

        row_data = {
            'id': cluster_id,
            'subnet': cluster_data['subnet'],
            'node_count': len(cluster_data['nodes']),
            'machine_ids': str(machine_ids),
            'manager_id': str(manager_node['machine_id']),
            'manager_ip': manager_node['local_ip'],
        }

        rows.append(row_data)

    display_table(rows, cluster_fields, replace_spaces=False)


@parser.command(
    usage="vastai show overlays",
    help="Show overlays associated with your account.",
    epilog=deindent("""
        Show overlays associated with your account.
    """)
)
def show__overlays(args: argparse.Namespace):
    req_url = apiurl(args, "/overlay/")
    r = http_get(args, req_url)
    r.raise_for_status()
    response_data = r.json()
    if args.raw:
        return response_data
    rows = []
    for overlay in response_data:
        row_data = {
            'overlay_id': overlay['overlay_id'],
            'name': overlay['name'],
            'subnet': overlay['internal_subnet'] if overlay['internal_subnet'] else 'N/A',
            'cluster_id': overlay['cluster_id'],
            'instance_count': len(overlay['instances']),
            'instances': str(overlay['instances']),
        }
        rows.append(row_data)
    display_table(rows, overlay_fields, replace_spaces=False)


@parser.command(
    argument("cluster_id", help="ID of cluster you want to remove machine from.", type=int),
    argument("machine_id", help="ID of machine to remove from cluster.", type=int),
    argument("new_manager_id", help="ID of machine to promote to manager. Must already be in cluster", type=int, nargs="?"),
    usage="vastai remove-machine-from-cluster CLUSTER_ID MACHINE_ID NEW_MANAGER_ID",
    help="Removes machine from cluster",
    epilog=deindent("""Removes machine from cluster and also reassigns manager ID,
    if we're removing the manager node""")
)
def remove_machine_from_cluster(args: argparse.Namespace):
    json_blob = {
        "cluster_id": args.cluster_id,
        "machine_id": args.machine_id,
    }

    if args.new_manager_id:
        json_blob["new_manager_id"] = args.new_manager_id
    if args.explain:
        print("request json:", json_blob)

    req_url = apiurl(args, "/cluster/remove_machine/")
    r = http_del(args, req_url, json=json_blob)
    r.raise_for_status()

    if args.raw:
        return r

    print(r.json()["msg"])
