"""API URL and header construction helpers."""

import re
import json
import argparse
from typing import Dict

from vast_cli.config import quote_plus


def apiurl(args: argparse.Namespace, subpath: str, query_args: Dict = None) -> str:
    """Creates the endpoint URL for a given combination of parameters.

    :param argparse.Namespace args: Namespace with many fields relevant to the endpoint.
    :param str subpath: added to end of URL to further specify endpoint.
    :param typing.Dict query_args: specifics such as API key and search parameters that complete the URL.
    :rtype str:
    """
    result = None

    if query_args is None:
        query_args = {}
    if args.api_key is not None:
        query_args["api_key"] = args.api_key
    if not re.match(r"^/api/v(\d)+/", subpath):
        subpath = "/api/v0" + subpath

    query_json = None

    if query_args:
        # a_list      = [<expression> for <l-expression> in <expression>]
        '''
        vector result;
        for (l_expression: expression) {
            result.push_back(expression);
        }
        '''
        # an_iterator = (<expression> for <l-expression> in <expression>)

        query_json = "&".join(
            "{x}={y}".format(x=x, y=quote_plus(y if isinstance(y, str) else json.dumps(y))) for x, y in
            query_args.items())

        result = args.url + subpath + "?" + query_json
    else:
        result = args.url + subpath

    if (args.explain):
        print("query args:")
        print(query_args)
        print("")
        print(f"base: {args.url + subpath + '?'} + query: ")
        print(result)
        print("")
    return result

def apiheaders(args: argparse.Namespace) -> Dict:
    """Creates the headers for a given combination of parameters.

    :param argparse.Namespace args: Namespace with many fields relevant to the endpoint.
    :rtype Dict:
    """
    result = {}
    if args.api_key is not None:
        result["Authorization"] = "Bearer " + args.api_key
    return result
