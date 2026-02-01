import shutil
import subprocess
from typing import Tuple


# ANSI escape codes for background/foreground colors
BG_DARK_GRAY = '\033[40m'  # Dark gray background
BG_LIGHT_GRAY = '\033[48;5;240m' # Light gray background
FG_WHITE = '\033[97m'            # Bright white text
BG_RESET = '\033[0m'             # Reset all formatting

def display_table(rows: list, fields: Tuple, replace_spaces: bool = True, auto_width: bool = True) -> None:
    """Basically takes a set of field names and rows containing the corresponding data and prints a nice tidy table
    of it.

    :param list rows: Each row is a dict with keys corresponding to the field names (first element) in the fields tuple.

    :param Tuple fields: 5-tuple describing a field. First element is field name, second is human readable version, third is format string, fourth is a lambda function run on the data in that field, fifth is a bool determining text justification. True = left justify, False = right justify. Here is an example showing the tuples in action.

    :rtype None:

    Example of 5-tuple: ("cpu_ram", "RAM", "{:0.1f}", lambda x: x / 1000, False)
    """
    header = [name for _, name, _, _, _ in fields]
    out_rows = [header]
    lengths = [len(x) for x in header]
    for instance in rows:
        row = []
        out_rows.append(row)
        for key, name, fmt, conv, _ in fields:
            conv = conv or (lambda x: x)
            val = instance.get(key, None)
            if val is None:
                s = "-"
            else:
                val = conv(val)
                s = fmt.format(val)
            if replace_spaces:
                s = s.replace(' ', '_')
            idx = len(row)
            lengths[idx] = max(len(s), lengths[idx])
            row.append(s)

    if auto_width:
        width = shutil.get_terminal_size((80, 20)).columns
        start_col_idxs = [0]
        total_len = 4  # +6ch for row label and -2ch for missing last sep in "  ".join()
        for i, l in enumerate(lengths):
            total_len += l + 2
            if total_len > width:
                start_col_idxs.append(i)  # index for the start of the next group
                total_len = l + 6         # l + 2 + the 4 from the initial length

        groups = {}
        for row in out_rows:
            grp_num = 0
            for i in range(len(start_col_idxs)):
                start = start_col_idxs[i]
                end = start_col_idxs[i+1]-1 if i+1 < len(start_col_idxs) else len(lengths)
                groups.setdefault(grp_num, []).append(row[start:end])
                grp_num += 1

        for i, group in groups.items():
            idx = start_col_idxs[i]
            group_lengths = lengths[idx:idx+len(group[0])]
            for row_num, row in enumerate(group):
                bg_color = BG_DARK_GRAY if (row_num - 1) % 2 else BG_LIGHT_GRAY
                row_label = "  #" if row_num == 0 else f"{row_num:3d}"
                out = [row_label]
                for l, s, f in zip(group_lengths, row, fields[idx:idx+len(row)]):
                    _, _, _, _, ljust = f
                    if ljust: s = s.ljust(l)
                    else:     s = s.rjust(l)
                    out.append(s)
                print(bg_color + FG_WHITE + "  ".join(out) + BG_RESET)
            print()
    else:
        for row in out_rows:
            out = []
            for l, s, f in zip(lengths, row, fields):
                _, _, _, _, ljust = f
                if ljust:
                    s = s.ljust(l)
                else:
                    s = s.rjust(l)
                out.append(s)
            print("  ".join(out))


def print_or_page(args, text):
    """ Print text to terminal, or pipe to pager_cmd if too long. """
    line_threshold = shutil.get_terminal_size(fallback=(80, 24)).lines
    lines = text.splitlines()
    if not args.full and len(lines) > line_threshold:
        pager_cmd = ['less', '-R'] if shutil.which('less') else None
        if pager_cmd:
            proc = subprocess.Popen(pager_cmd, stdin=subprocess.PIPE)
            proc.communicate(input=text.encode())
            return True
        else:
            print(text)
            return False
    else:
        print(text)
        return False
