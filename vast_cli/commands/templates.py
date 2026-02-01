"""Commands for managing templates."""

import json

import requests

from vast_cli.parser import parser, argument
from vast_cli import state
from vast_cli.api.client import http_post, http_put, http_del
from vast_cli.api.helpers import apiurl
from vast_cli.display.formatting import deindent
from vast_cli.helpers import get_template_arguments
from vast_cli.query.parser import parse_query
from vast_cli.query.fields import offers_fields, offers_alias, offers_mult


@parser.command(
    *get_template_arguments(),
    usage="vastai create template",
    help="Create a new template",
    epilog=deindent("""
        Create a template that can be used to create instances with

        Example:
            vastai create template --name "tgi-llama2-7B-quantized" --image "ghcr.io/huggingface/text-generation-inference:1.0.3"
                                    --env "-p 3000:3000 -e MODEL_ARGS='--model-id TheBloke/Llama-2-7B-chat-GPTQ --quantize gptq'"
                                    --onstart-cmd 'wget -O - https://raw.githubusercontent.com/vast-ai/vast-pyworker/main/scripts/launch_tgi.sh | bash'
                                    --search_params "gpu_ram>=23 num_gpus=1 gpu_name=RTX_3090 inet_down>128 direct_port_count>3 disk_space>=192 driver_version>=535086005 rented=False"
                                    --disk_space 8.0 --ssh --direct
    """)
)
def create__template(args):
    # url = apiurl(args, f"/users/0/templates/")
    url = apiurl(args, f"/template/")
    jup_direct = args.jupyter and args.direct
    ssh_direct = args.ssh and args.direct
    use_ssh = args.ssh or args.jupyter
    runtype = "jupyter" if args.jupyter else ("ssh" if args.ssh else "args")
    if args.login:
        login = args.login.split(" ")
        docker_login_repo = login[0]
    else:
        docker_login_repo = None
    default_search_query = {}
    if not args.no_default:
        default_search_query = {"verified": {"eq": True}, "external": {"eq": False}, "rentable": {"eq": True}, "rented": {"eq": False}}

    extra_filters = parse_query(args.search_params, default_search_query, offers_fields, offers_alias, offers_mult)
    template = {
        "name" : args.name,
        "image" : args.image,
        "tag" : args.image_tag,
        "href": args.href,
        "repo" : args.repo,
        "env" : args.env, #str format
        "onstart" : args.onstart_cmd, #don't accept file name for now
        "jup_direct" : jup_direct,
        "ssh_direct" : ssh_direct,
        "use_jupyter_lab" : args.jupyter_lab,
        "runtype" : runtype,
        "use_ssh" : use_ssh,
        "jupyter_dir" : args.jupyter_dir,
        "docker_login_repo" : docker_login_repo, #can't store username/password with template for now
        "extra_filters" : extra_filters,
        "recommended_disk_space" : args.disk_space,
        "readme": args.readme,
        "readme_visible": not args.hide_readme,
        "desc": args.desc,
        "private": not args.public,
    }

    if (args.explain):
        print("request json: ")
        print(template)

    r = http_post(args, url, headers=state.headers, json=template)
    r.raise_for_status()
    try:
        rj = r.json()
        if rj["success"]:
            print(f"New Template: {rj['template']}")
        else:
            print(rj['msg'])
    except requests.exceptions.JSONDecodeError:
        print("The response is not valid JSON.")


@parser.command(
    argument("--template-id", help="Template ID of Template to Delete", type=int),
    argument("--hash-id", help="Hash ID of Template to Delete", type=str),
    usage="vastai delete template [--template-id <id> | --hash-id <hash_id>]",
    help="Delete a Template",
    epilog=deindent("""
        Note: Deleting a template only removes the user's replationship to a template. It does not get destroyed
        Example: vastai delete template --template-id 12345
        Example: vastai delete template --hash-id 49c538d097ad6437413b83711c9f61e8
    """),
)
def delete__template(args):
    url = apiurl(args, f"/template/" )

    if args.hash_id:
        json_blob = { "hash_id": args.hash_id }
    elif args.template_id:
        json_blob = { "template_id": args.template_id }
    else:
        print('ERROR: Must Specify either Template ID or Hash ID to delete a template')
        return

    if (args.explain):
        print("request json: ")
        print(json_blob)
        print(args)
        print(url)
    r = http_del(args, url, headers=state.headers,json=json_blob)
    print(r)
    # r.raise_for_status()
    if 'application/json' in r.headers.get('Content-Type', ''):
        try:
            print(r.json()['msg'])
        except requests.exceptions.JSONDecodeError:
            print("The response is not valid JSON.")
            print(r)
            print(r.text)  # Print the raw response to help with debugging.
    else:
        print("The response is not JSON. Content-Type:", r.headers.get('Content-Type'))
        print(r.text)


@parser.command(
    argument("HASH_ID", help="hash id of the template", type=str),
    *get_template_arguments(),
    usage="vastai update template HASH_ID",
    help="Update an existing template",
    epilog=deindent("""
        Update a template

        Example:
            vastai update template c81e7ab0e928a508510d1979346de10d --name "tgi-llama2-7B-quantized" --image "ghcr.io/huggingface/text-generation-inference:1.0.3"
                                    --env "-p 3000:3000 -e MODEL_ARGS='--model-id TheBloke/Llama-2-7B-chat-GPTQ --quantize gptq'"
                                    --onstart-cmd 'wget -O - https://raw.githubusercontent.com/vast-ai/vast-pyworker/main/scripts/launch_tgi.sh | bash'
                                    --search_params "gpu_ram>=23 num_gpus=1 gpu_name=RTX_3090 inet_down>128 direct_port_count>3 disk_space>=192 driver_version>=535086005 rented=False"
                                    --disk 8.0 --ssh --direct
    """)
)
def update__template(args):
    url = apiurl(args, f"/template/")
    jup_direct = args.jupyter and args.direct
    ssh_direct = args.ssh and args.direct
    use_ssh = args.ssh or args.jupyter
    runtype = "jupyter" if args.jupyter else ("ssh" if args.ssh else "args")
    if args.login:
        login = args.login.split(" ")
        docker_login_repo = login[0]
    else:
        docker_login_repo = None
    default_search_query = {}
    if not args.no_default:
        default_search_query = {"verified": {"eq": True}, "external": {"eq": False}, "rentable": {"eq": True}, "rented": {"eq": False}}

    extra_filters = parse_query(args.search_params, default_search_query, offers_fields, offers_alias, offers_mult)
    template = {
        "hash_id": args.HASH_ID,
        "name" : args.name,
        "image" : args.image,
        "tag" : args.image_tag,
        "href" : args.href,
        "repo" : args.repo,
        "env" : args.env, #str format
        "onstart" : args.onstart_cmd, #don't accept file name for now
        "jup_direct" : jup_direct,
        "ssh_direct" : ssh_direct,
        "use_jupyter_lab" : args.jupyter_lab,
        "runtype" : runtype,
        "use_ssh" : use_ssh,
        "jupyter_dir" : args.jupyter_dir,
        "docker_login_repo" : docker_login_repo, #can't store username/password with template for now
        "extra_filters" : extra_filters,
        "recommended_disk_space" : args.disk_space,
        "readme": args.readme,
        "readme_visible": not args.hide_readme,
        "desc": args.desc,
        "private": not args.public,
    }

    json_blob = template
    if (args.explain):
        print("request json: ")
        print(json_blob)

    r = http_put(args, url, headers=state.headers, json=json_blob)
    r.raise_for_status()
    try:
        rj = r.json()
        if rj["success"]:
            print(f"updated template: {json.dumps(rj['template'], indent=1)}")
        else:
            print("template update failed")
    except requests.exceptions.JSONDecodeError as e:
        print(str(e))
        #print(r.text)
        print(r.status_code)
