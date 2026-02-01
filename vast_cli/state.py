"""Mutable global state for vast_cli.

Command modules should do:
    from vast_cli import state
and reference state.headers, state.ARGS, etc.
"""

ARGS = None
TABCOMPLETE = False
try:
    import argcomplete
    TABCOMPLETE = True
except:
    # No tab-completion for you
    pass

try:
    import curlify
except ImportError:
    pass

api_key_guard = object()

headers = {}
