"""Commands for managing API keys."""

import os

import requests

from vast_cli.parser import parser, argument
from vast_cli import state
from vast_cli.api.client import http_get, http_post, http_put, http_del
from vast_cli.api.helpers import apiurl
from vast_cli.display.formatting import deindent
from vast_cli.auth.keys import load_permissions_from_file
from vast_cli.config import APIKEY_FILE, APIKEY_FILE_HOME


@parser.command(
    argument("--name", help="name of the api-key", type=str),
    argument("--permission_file", help="file path for json encoded permissions, see https://vast.ai/docs/cli/roles-and-permissions for more information", type=str),
    argument("--key_params", help="optional wildcard key params for advanced keys", type=str),
    usage="vastai create api-key --name NAME --permission_file PERMISSIONS",
    help="Create a new api-key with restricted permissions. Can be sent to other users and teammates",
    epilog=deindent("""
        In order to create api keys you must understand how permissions must be sent via json format.
        You can find more information about permissions here: https://vast.ai/docs/cli/roles-and-permissions
    """)
)
def create__api_key(args):
    try:
        url = apiurl(args, "/auth/apikeys/")
        permissions = load_permissions_from_file(args.permission_file)
        r = http_post(args, url, headers=state.headers, json={"name": args.name, "permissions": permissions, "key_params": args.key_params})
        r.raise_for_status()
        print("api-key created {}".format(r.json()))
    except FileNotFoundError:
        print("Error: Permission file '{}' not found.".format(args.permission_file))
    except requests.exceptions.RequestException as e:
        print("Error: Failed to create api-key. Reason: {}".format(e))
    except Exception as e:
        print("An unexpected error occurred:", e)


@parser.command(
    argument("id", help="id of apikey to remove", type=int),
    usage="vastai delete api-key ID",
    help="Remove an api-key",
)
def delete__api_key(args):
    url = apiurl(args, "/auth/apikeys/{id}/".format(id=args.id))
    r = http_del(args, url, headers=state.headers)
    r.raise_for_status()
    print(r.json())


@parser.command(
    usage="vastai reset api-key",
    help="Reset your api-key (get new key from website)",
)
def reset__api_key(args):
    """Caution: a bad API key will make it impossible to connect to the servers.
    """
    #url = apiurl(args, "/users/current/reset-apikey/", {"owner": "me"})
    url = apiurl(args, "/commands/reset_apikey/" )
    json_blob = {"client_id": "me",}
    if (args.explain):
        print("request json: ")
        print(json_blob)
    r = http_put(args, url,  headers=state.headers,json=json_blob)
    r.raise_for_status()
    print(f"api-key reset {r.json()}")


@parser.command(
    argument("new_api_key", help="Api key to set as currently logged in user"),
    usage="vastai set api-key APIKEY",
    help="Set api-key (get your api-key from the console/CLI)",
)
def set__api_key(args):
    """Caution: a bad API key will make it impossible to connect to the servers.
    :param argparse.Namespace args: should supply all the command-line options
    """
    with open(APIKEY_FILE, "w") as writer:
        writer.write(args.new_api_key)
    print("Your api key has been saved in {}".format(APIKEY_FILE))

    if os.path.exists(APIKEY_FILE_HOME):
        os.remove(APIKEY_FILE_HOME)
        print("Your api key has been removed from {}".format(APIKEY_FILE_HOME))


@parser.command(
    argument("id", help="id of apikey to get", type=int),
    usage="vastai show api-key",
    help="Show an api-key",
)
def show__api_key(args):
    url = apiurl(args, "/auth/apikeys/{id}/".format(id=args.id))
    r = http_get(args, url, headers=state.headers)
    r.raise_for_status()
    print(r.json())

@parser.command(
    usage="vastai show api-keys",
    help="List your api-keys associated with your account",
)
def show__api_keys(args):
    url = apiurl(args, "/auth/apikeys/")
    r = http_get(args, url, headers=state.headers)
    r.raise_for_status()
    if args.raw:
        return r
    else:
        print(r.json())
