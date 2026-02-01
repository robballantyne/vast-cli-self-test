from io import StringIO
from datetime import datetime


def rich_object_to_string(rich_obj, no_color=True):
    """ Render a Rich object (Table or Tree) to a string. """
    from rich.console import Console
    buffer = StringIO()  # Use an in-memory stream to suppress visible output
    console = Console(record=True, file=buffer)
    console.print(rich_obj)
    return console.export_text(clear=True, styles=not no_color)

def create_charges_tree(results, parent=None, title="Charges Breakdown"):
    """ Build and return a Rich Tree from nested charge results. """
    from rich.text import Text
    from rich.tree import Tree
    from rich.panel import Panel
    if parent is None:  # Create root node if this is the first call
        root = Tree(Text(title, style="bold red"))
        create_charges_tree(results, root)
        return Panel(root, style="white on #000000", expand=False)

    top_level = (parent.label.plain == title)
    for item in results:
        end_date = f" → {item['end']}" if item['start'] != item['end'] else ""
        label = Text.assemble(
            (item["type"], "bold cyan"),
            (f" {item['source']}" if item.get('source') else "", "gold1"), " → ",
            (f"{item['amount']}", 'bold green1' if top_level else 'green1'),
            (f" — {item['description']}", "bright_white" if top_level else "dim white"),
            (f"  ({item['start']}{end_date})", "bold bright_white" if top_level else "white")
        )
        node = parent.add(label, guide_style="blue3")
        if item.get("items"):
            create_charges_tree(item["items"], node)
    return parent

def create_rich_table_for_charges(args, results):
    """ Build and return a Rich Table from charge results. """
    from rich.table import Table
    from rich.text import Text
    from rich import box
    from rich.padding import Padding
    table = Table(style="white", header_style="bold bright_yellow", box=box.DOUBLE_EDGE, row_styles=["on grey11", "none"])
    table.add_column(Text("Type", justify="center"), style="bold steel_blue1", justify="center")
    table.add_column(Text("ID", justify="center"), style="gold1", justify="center")
    table.add_column(Text("Amount", justify="center"), style="sea_green2", justify="right")
    table.add_column(Text("Start", justify="center"), style="bright_white", justify="center")
    table.add_column(Text("End", justify="center"), style="bright_white", justify="center")
    if not args.charge_type or 'serverless' in args.charge_type:
        table.add_column(Text("Endpoint", justify="center"), style="bright_red", justify="center")
        table.add_column(Text("Workergroup", justify="center"), style="orchid", justify="center")
    for item in results:
        row = [item['type'].capitalize(), item['source'], item['amount'], item['start'], item['end']]
        if not args.charge_type or 'serverless' in args.charge_type:
            row.append(str(item['metadata'].get('endpoint_id', '')))
            row.append(str(item['metadata'].get('workergroup_id', '')))
        table.add_row(*row)
    return Padding(table, (1, 2), style="on #000000", expand=False)  # Print with a black background

def create_rich_table_for_invoices(results):
    """ Build and return a Rich Table from invoice results. """
    from rich.table import Table
    from rich.text import Text
    from rich import box
    from rich.padding import Padding
    invoice_type_to_color = {
        "credit": "green1",
        "transfer": "gold1",
        "payout": "orchid",
        "reserved": "sky_blue1",
        "refund": "bright_red",
    }
    table = Table(style="white", header_style="bold bright_yellow", box=box.DOUBLE_EDGE, row_styles=["on grey11", "none"])
    table.add_column(Text("ID", justify="center"), style="bright_white", justify="center")
    table.add_column(Text("Created", justify="center"), style="yellow3", justify="center")
    table.add_column(Text("Paid", justify="center"), style="yellow3", justify="center")
    table.add_column(Text("Type", justify="center"), justify="center")
    table.add_column(Text("Result", justify="center"), justify="right")
    table.add_column(Text("Source", justify="center"), style="bright_cyan", justify="center")
    table.add_column(Text("Description", justify="center"), style="bright_white", justify="left")
    for item in results:
        table.add_row(
            str(item['metadata']['invoice_id']),
            item['start'],
            item['end'] if item['end'] else 'N/A',
            Text(item['type'].capitalize(), style=invoice_type_to_color.get(item['type'], "white")),
            Text(item['amount_str'], style="sea_green2" if item['amount'] > 0 else "bright_red"),
            item['source'].capitalize() if item['type'] != 'transfer' else item['source'],
            item['description'],
        )
    return Padding(table, (1, 2), style="on #000000", expand=False)  # Print with a black background

def create_rich_table_from_rows(rows, headers=None, title='', sort_key=None):
    """ (Generic) Creates a Rich table from a list of dict rows. """
    from rich import box
    from rich.table import Table
    if not isinstance(rows, list):
        raise ValueError("Invalid Data Type: rows must be a list")
    # Handle list of dictionaries
    if isinstance(rows[0], dict):
        headers = headers or list(rows[0].keys())
        rows = [[row_dict.get(h, "") for h in headers] for row_dict in rows]
    elif headers is None:
        raise ValueError("Headers must be provided if rows are not dictionaries")
    # Sort rows if requested
    if sort_key:
        rows = sorted(rows, key=sort_key)
    # Create the Rich table
    table = Table(title=title, style="white", header_style="bold bright_yellow", box=box.DOUBLE_EDGE)
    # Add columns
    for header in headers:
        # You can customize alignment and style here per column
        table.add_column(header, justify="left", style="bright_white", no_wrap=True)
    # Add rows
    for row in rows:
        # Convert everything to string to avoid type issues
        table.add_row(*[str(cell) for cell in row])
    return table


TFA_METHOD_FIELDS = (
    ("id", "ID", "{}", None, True),
    ("user_id", "User ID", "{}", None, True),
    ("is_primary", "Primary", "{}", None, True),
    ("method", "Method", "{}", None, True),
    ("label", "Label", "{}", None, True),
    ("phone_number", "Phone Number", "{}", None, False),
    ("created_at", "Created", "{}", lambda x: datetime.fromtimestamp(x).strftime('%Y-%m-%d %H:%M:%S') if x else "N/A", True),
    ("last_used", "Last Used", "{}", lambda x: datetime.fromtimestamp(x).strftime('%Y-%m-%d %H:%M:%S') if x else "Never", True),
    ("fail_count", "Failures", "{}", None, True),
    ("locked_until", "Locked Until", "{}", lambda x: datetime.fromtimestamp(x).strftime('%Y-%m-%d %H:%M:%S') if x else "N/A", True),
)

def display_tfa_methods(methods):
    """Helper function to display 2FA methods in a table."""
    from vast_cli.display.table import display_table
    method_fields = TFA_METHOD_FIELDS
    has_sms = any(m['method'] == 'sms' for m in methods)
    if not has_sms:  # Don't show Phone Number column if the user has no SMS methods
        method_fields = tuple(field for field in TFA_METHOD_FIELDS if field[0] != 'phone_number')

    display_table(methods, method_fields, replace_spaces=False)
