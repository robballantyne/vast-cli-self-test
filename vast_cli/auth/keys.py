"""SSH key and permissions file helpers."""

import os
import sys
import time
import json
import subprocess
from pathlib import Path

from vast_cli.display.formatting import deindent


def load_permissions_from_file(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)


def get_ssh_key(argstr):
    ssh_key = argstr
    # Including a path to a public key is pretty reasonable.
    if os.path.exists(argstr):
      with open(argstr) as f:
        ssh_key = f.read()

    if "PRIVATE KEY" in ssh_key:
      raise ValueError(deindent("""
        \U0001f434 Woah, hold on there, partner!

        That's a *private* SSH key.  You need to give the *public*
        one. It usually starts with 'ssh-rsa', is on a single line,
        has around 200 or so "base64" characters and ends with
        some-user@some-where. "Generate public ssh key" would be
        a good search term if you don't know how to do this.
      """, add_separator=False))

    if not ssh_key.lower().startswith('ssh'):
      raise ValueError(deindent("""
        Are you sure that's an SSH public key?

        Usually it starts with the stanza 'ssh-(keytype)'
        where the keytype can be things such as rsa, ed25519-sk,
        or dsa. What you passed me was:

        {}

        And welp, that just don't look right.
      """.format(ssh_key), add_separator=False))

    return ssh_key


def generate_ssh_key(auto_yes=False):
    """
    Generate a new SSH key pair using ssh-keygen and return the public key content.

    Args:
        auto_yes (bool): If True, automatically answer yes to prompts

    Returns:
        str: The content of the generated public key

    Raises:
        SystemExit: If ssh-keygen is not available or key generation fails
    """

    print("No SSH key provided. Generating a new SSH key pair and adding public key to account...")

    # Define paths
    ssh_dir = Path.home() / '.ssh'
    private_key_path = ssh_dir / 'id_ed25519'
    public_key_path = ssh_dir / 'id_ed25519.pub'

    # Create .ssh directory if it doesn't exist
    try:
        ssh_dir.mkdir(mode=0o700, exist_ok=True)
    except OSError as e:
        print(f"Error creating .ssh directory: {e}", file=sys.stderr)
        sys.exit(1)

    # Check if any part of the key pair already exists and backup if needed
    if private_key_path.exists() or public_key_path.exists():
        print(f"An SSH key pair 'id_ed25519' already exists in {ssh_dir}")
        if auto_yes:
            print("Auto-answering yes to backup existing key pair.")
            response = 'y'
        else:
            response = input("Would you like to generate a new key pair and backup your existing id_ed25519 key pair. [y/N]: ").lower()
        if response not in ['y', 'yes']:
            print("Aborted. No new key generated.")
            sys.exit(0)

        # Generate timestamp for backup
        timestamp = int(time.time())
        backup_private_path = ssh_dir / f'id_ed25519.backup_{timestamp}'
        backup_public_path = ssh_dir / f'id_ed25519.pub.backup_{timestamp}'

        try:
            # Backup existing private key if it exists
            if private_key_path.exists():
                private_key_path.rename(backup_private_path)
                print(f"Backed up existing private key to: {backup_private_path}")

            # Backup existing public key if it exists
            if public_key_path.exists():
                public_key_path.rename(backup_public_path)
                print(f"Backed up existing public key to: {backup_public_path}")

        except OSError as e:
            print(f"Error backing up existing SSH keys: {e}", file=sys.stderr)
            sys.exit(1)

        print("Generating new SSH key pair and adding public key to account...")

    # Check if ssh-keygen is available
    try:
        subprocess.run(['ssh-keygen', '--help'], capture_output=True, check=False)
    except FileNotFoundError:
        print("Error: ssh-keygen not found. Please install OpenSSH client tools.", file=sys.stderr)
        sys.exit(1)

    # Generate the SSH key pair
    try:
        cmd = [
            'ssh-keygen',
            '-t', 'ed25519',       # Ed25519 key type
            '-f', str(private_key_path),  # Output file path
            '-N', '',              # Empty passphrase
            '-C', f'{os.getenv("USER") or os.getenv("USERNAME", "user")}-vast.ai'  # User
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            input='y\n',           # Automatically answer 'yes' to overwrite prompts
            check=True
        )

    except subprocess.CalledProcessError as e:
        print(f"Error generating SSH key: {e}", file=sys.stderr)
        if e.stderr:
            print(f"ssh-keygen error: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error during key generation: {e}", file=sys.stderr)
        sys.exit(1)

    # Set proper permissions for the private key
    try:
        private_key_path.chmod(0o600)  # Read/write for owner only
    except OSError as e:
        print(f"Warning: Could not set permissions for private key: {e}", file=sys.stderr)

    # Read and return the public key content
    try:
        with open(public_key_path, 'r') as f:
            public_key_content = f.read().strip()

        return public_key_content

    except IOError as e:
        print(f"Error reading generated public key: {e}", file=sys.stderr)
        sys.exit(1)
