"""SSH-related commands for vast_cli."""

import json

from vast_cli.parser import parser, argument
from vast_cli import state
from vast_cli.api.client import http_get, http_post, http_put, http_del
from vast_cli.api.helpers import apiurl
from vast_cli.display.formatting import deindent
from vast_cli.config import DIRS
from vast_cli.auth.keys import get_ssh_key, generate_ssh_key


@parser.command(
    argument("instance_id", help="id of instance to attach to", type=int),
    argument("ssh_key", help="ssh key to attach to instance", type=str),
    usage="vastai attach ssh instance_id ssh_key",
    help="Attach an ssh key to an instance. This will allow you to connect to the instance with the ssh key",
    epilog=deindent("""
        Attach an ssh key to an instance. This will allow you to connect to the instance with the ssh key.

        Examples:
         vastai attach "ssh 12371 ssh-rsa AAAAB3NzaC1yc2EAAA..."
         vastai attach "ssh 12371 ssh-rsa $(cat ~/.ssh/id_rsa)"
    """),
)
def attach__ssh(args):
    ssh_key = get_ssh_key(args.ssh_key)
    url = apiurl(args, "/instances/{id}/ssh/".format(id=args.instance_id))
    req_json = {"ssh_key": ssh_key}
    r = http_post(args, url, headers=state.headers, json=req_json)
    r.raise_for_status()
    print(r.json())


@parser.command(
    argument("instance_id", help="id of the instance", type=int),
    argument("ssh_key_id", help="id of the key to detach to the instance", type=str),
    usage="vastai detach instance_id ssh_key_id",
    help="Detach an ssh key from an instance",
    epilog=deindent("""
        Example: vastai detach 99999 12345
    """)
)
def detach__ssh(args):
    url = apiurl(args, "/instances/{id}/ssh/{ssh_key_id}/".format(id=args.instance_id, ssh_key_id=args.ssh_key_id))
    r = http_del(args, url, headers=state.headers)
    r.raise_for_status()
    print(r.json())


@parser.command(
    argument("ssh_key", help="add your existing ssh public key to your account (from the .pub file). If no public key is provided, a new key pair will be generated.", type=str, nargs='?'),
    argument("-y", "--yes", help="automatically answer yes to prompts", action="store_true"),
    usage="vastai create ssh-key [ssh_public_key] [-y]",
    help="Create a new ssh-key",
    epilog=deindent("""
        You may use this command to add an existing public key, or create a new ssh key pair and add that public key, to your Vast account.

        If you provide an ssh_public_key.pub argument, that public key will be added to your Vast account. All ssh public keys should be in OpenSSH format.

                Example: $vastai create ssh-key 'ssh_public_key.pub'

        If you don't provide an ssh_public_key.pub argument, a new Ed25519 key pair will be generated.

                Example: $vastai create ssh-key

        The generated keys are saved as ~/.ssh/id_ed25519 (private) and ~/.ssh/id_ed25519.pub (public). Any existing id_ed25519 keys are backed up as .backup_<timestamp>.
        The public key will be added to your Vast account.

        All ssh public keys are stored in your Vast account and can be used to connect to instances they've been added to.
    """)
)

def create__ssh_key(args):
    ssh_key_content = args.ssh_key

    # If no SSH key provided, generate one
    if not ssh_key_content:
        ssh_key_content = generate_ssh_key(args.yes)
    else:
        print("Adding provided SSH public key to account...")

    # Send the SSH key to the API
    url = apiurl(args, "/ssh/")
    r = http_post(args, url, headers=state.headers, json={"ssh_key": ssh_key_content})
    r.raise_for_status()

    # Print json response
    print("ssh-key created {}\nNote: You may need to add the new public key to any pre-existing instances".format(r.json()))


@parser.command(
    argument("id", help="id ssh key to delete", type=int),
    usage="vastai delete ssh-key ID",
    help="Remove an ssh-key",
)
def delete__ssh_key(args):
    url = apiurl(args, "/ssh/{id}/".format(id=args.id))
    r = http_del(args, url, headers=state.headers)
    r.raise_for_status()
    print(r.json())


@parser.command(
    usage="vastai show ssh-keys",
    help="List your ssh keys associated with your account",
)
def show__ssh_keys(args):
    url = apiurl(args, "/ssh/")
    r = http_get(args, url, headers=state.headers)
    r.raise_for_status()
    if args.raw:
        return r
    else:
        print(r.json())


@parser.command(
    argument("id", help="id of the ssh key to update", type=int),
    argument("ssh_key", help="new public key value", type=str),
    usage="vastai update ssh-key ID SSH_KEY",
    help="Update an existing SSH key",
)
def update__ssh_key(args):
    """Updates an existing SSH key for the authenticated user."""
    ssh_key = get_ssh_key(args.ssh_key)
    url = apiurl(args, f"/ssh/{args.id}/")

    payload = {
        "id": args.id,
        "ssh_key": ssh_key,
    }

    r = http_put(args, url, json=payload)
    r.raise_for_status()
    print(r.json())


@parser.command(
    argument("id", help="id of instance", type=int),
    usage="vastai ssh-url ID",
    help="ssh url helper",
)
def ssh_url(args):
    """

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    return _ssh_url(args, "ssh://")


@parser.command(
    argument("id",   help="id", type=int),
    usage="vastai scp-url ID",
    help="scp url helper",
)
def scp_url(args):
    """

    :param argparse.Namespace args: should supply all the command-line options
    :rtype:
    """
    return _ssh_url(args, "scp://")


def _ssh_url(args, protocol):

    json_object = None

    # Opening JSON file
    try:
        with open(f"{DIRS['temp']}/ssh_{args.id}.json", 'r') as openfile:
            json_object = json.load(openfile)
    except:
        pass

    port      = None
    ipaddr    = None

    if json_object is not None:
        ipaddr = json_object["ipaddr"]
        port   = json_object["port"]

    if ipaddr is None or ipaddr.endswith('.vast.ai'):
        req_url = apiurl(args, "/instances", {"owner": "me"})
        r = http_get(args, req_url)
        r.raise_for_status()
        rows = r.json()["instances"]

        if args.id:
            matches = [r for r in rows if r['id'] == args.id]
            if not matches:
                print(f"error: no instance found with id {args.id}")
                return 1
            instance = matches[0]
        elif len(rows) > 1:
            print("Found multiple running instances")
            return 1
        else:
            instance = rows[0]

        ports     = instance.get("ports",{})
        port_22d  = ports.get("22/tcp",None)
        port      = -1
        try:
            if (port_22d is not None):
                ipaddr = instance["public_ipaddr"]
                port   = int(port_22d[0]["HostPort"])
            else:
                ipaddr = instance["ssh_host"]
                port   = int(instance["ssh_port"])+1 if "jupyter" in instance["image_runtype"] else int(instance["ssh_port"])
        except:
            port = -1

    if (port > 0):
        print(f'{protocol}root@{ipaddr}:{port}')
    else:
        print(f'error: ssh port not found')


    # Writing to sample.json
    try:
        with open(f"{DIRS['temp']}/ssh_{args.id}.json", "w") as outfile:
            json.dump({"ipaddr":ipaddr, "port":port}, outfile)
    except:
        pass
