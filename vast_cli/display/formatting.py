import re
import shutil
import sys
from typing import Dict


def translate_null_strings_to_blanks(d: Dict) -> Dict:
    """Map over a dict and translate any null string values into ' '.
    Leave everything else as is. This is needed because you cannot add TableCell
    objects with only a null string or the client crashes.

    :param Dict d: dict of item values.
    :rtype Dict:
    """

    # Beware: locally defined function.
    def translate_nulls(s):
        if s == "":
            return " "
        return s

    new_d = {k: translate_nulls(v) for k, v in d.items()}
    return new_d


def deindent(message: str, add_separator: bool = True) -> str:
    """
    Deindent a quoted string. Scans message and finds the smallest number of whitespace characters in any line and
    removes that many from the start of every line.

    :param str message: Message to deindent.
    :rtype str:
    """
    message = re.sub(r" *$", "", message, flags=re.MULTILINE)
    indents = [len(x) for x in re.findall("^ *(?=[^ ])", message, re.MULTILINE) if len(x)]
    a = min(indents)
    message = re.sub(r"^ {," + str(a) + "}", "", message, flags=re.MULTILINE)
    if add_separator:
        # For help epilogs - cleanly separating extra help from options
        line_width = min(150, shutil.get_terminal_size((80, 20)).columns)
        message = "_"*line_width + "\n"*2 + message.strip() + "\n" + "_"*line_width
    return message.strip()


def pretty_print_POST(req):
    print('{}\n{}\r\n{}\r\n\r\n{}'.format(
        '-----------START-----------',
        req.method + ' ' + req.url,
        '\r\n'.join('{}: {}'.format(k, v) for k, v in req.headers.items()),
        req.body,
    ))


def progress_print(args, *args_to_print):
    """
    Prints progress messages to the console based on the `raw` flag.

    This function ensures that progress messages are only printed when the `raw`
    output mode is not enabled. This is useful for controlling the verbosity of
    the script's output, especially in machine-readable formats.

    Args:
        args (argparse.Namespace): Parsed command-line arguments containing flags
                                  and options such as `raw`.
        *args_to_print: Variable length argument list of messages to print.

    Returns:
        None
    """
    if not args.raw:
        print(*args_to_print)

def debug_print(args, *args_to_print):
    """
    Prints debug messages to the console based on the `debugging` and `raw` flags.

    This function ensures that debug messages are only printed when debugging is
    enabled and the `raw` output mode is not active. It helps in providing detailed
    logs for troubleshooting without cluttering the standard output during normal
    operation.

    Args:
        args (argparse.Namespace): Parsed command-line arguments containing flags
                                  and options such as `debugging` and `raw`.
        *args_to_print: Variable length argument list of debug messages to print.

    Returns:
        None
    """
    if args.debugging and not args.raw:
        print(*args_to_print)
