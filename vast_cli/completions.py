"""Tab completion functions for vast_cli."""

from pathlib import Path
from vast_cli import state


def complete_instance_machine(prefix=None, action=None, parser=None, parsed_args=None):
    # Late import to avoid circular dependency - instance__list is registered in commands
    from vast_cli.commands.instances import instance__list
    return instance__list(state.ARGS, {'internal': True, 'field': 'machine_id'})

def complete_instance(prefix=None, action=None, parser=None, parsed_args=None):
    from vast_cli.commands.instances import instance__list
    return instance__list(state.ARGS, {'internal': True, 'field': 'id'})

def complete_sshkeys(prefix=None, action=None, parser=None, parsed_args=None):
    return [str(m) for m in Path.home().joinpath('.ssh').glob('*.pub')]
