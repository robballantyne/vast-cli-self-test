"""HTTP request helpers for the vast.ai API."""

import re
import json
import sys
import time

import requests

from vast_cli import state
from vast_cli.config import INFO

try:
    import curlify
except ImportError:
    pass


def http_request(verb, args, req_url, headers: dict[str, str] | None = None, json_data = None):
    t = 0.15
    for i in range(0, args.retry):
        req = requests.Request(method=verb, url=req_url, headers=headers, json=json_data)
        session = requests.Session()
        prep = session.prepare_request(req)
        if args.explain:
            print(f"\n{INFO}  Prepared Request:")
            print(f"{prep.method} {prep.url}")
            print(f"Headers: {json.dumps(headers, indent=1)}")
            print(f"Body: {json.dumps(json_data, indent=1)}" + "\n" + "_"*100 + "\n")

        if state.ARGS.curl:
            as_curl = curlify.to_curl(prep)
            simple = re.sub(r" -H '[^']*'", '', as_curl)
            parts = re.split(r'(?=\s+-\S+)', simple)
            pp = parts[-1].split("'")
            pp[-3] += "\n "
            parts = [*parts[:-1], *[x.rstrip() for x in "'".join(pp).split("\n")]]
            print("\n" + ' \\\n  '.join(parts).strip() + "\n")
            sys.exit(0)
        else:
            r = session.send(prep)

        if (r.status_code == 429):
            time.sleep(t)
            t *= 1.5
        else:
            break
    return r

def http_get(args, req_url, headers = None, json = None):
    return http_request('GET', args, req_url, headers, json)

def http_put(args, req_url, headers = None, json = {}):
    return http_request('PUT', args, req_url, headers, json)

def http_post(args, req_url, headers = None, json={}):
    return http_request('POST', args, req_url, headers, json)

def http_del(args, req_url, headers = None, json={}):
    return http_request('DELETE', args, req_url, headers, json)
