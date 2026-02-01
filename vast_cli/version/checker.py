"""Version checking and update functionality."""

import sys
import subprocess
import importlib.metadata

import requests

from vast_cli.config import PYPI_BASE_PATH


def parse_version(version: str) -> tuple[int, ...]:
    parts = version.split(".")

    if len(parts) < 3:
        print(f"Invalid version format: {version}", file=sys.stderr)

    return tuple(int(part) for part in parts)


def get_git_version():
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            check=True,
        )
        tag = result.stdout.strip()

        return tag[1:] if tag.startswith("v") else tag
    except Exception:
        return "0.0.0"


def get_pip_version():
    try:
        return importlib.metadata.version("vastai")
    except Exception:
        return "0.0.0"


def is_pip_package():
    try:
        return importlib.metadata.metadata("vastai") is not None
    except Exception:
        return False

def get_update_command(stable_version: str) -> str:
    if is_pip_package():
        if "test.pypi.org" in PYPI_BASE_PATH:
            return f"{sys.executable} -m pip install --force-reinstall --no-cache-dir -i {PYPI_BASE_PATH} vastai=={stable_version}"
        else:
            return f"{sys.executable} -m pip install --force-reinstall --no-cache-dir vastai=={stable_version}"
    else:
        return f"git fetch --all --tags --prune && git checkout tags/v{stable_version}"


def get_local_version():
    if is_pip_package():
        return get_pip_version()
    return get_git_version()


def get_project_data(project_name: str) -> dict[str, dict[str, str]]:
    url = PYPI_BASE_PATH + f"/pypi/{project_name}/json"
    response = requests.get(url, headers={"Accept": "application/json"})

    # this will raise for HTTP status 4xx and 5xx
    response.raise_for_status()

    # this will raise for HTTP status >200,<=399
    if response.status_code != 200:
        raise Exception(
            f"Could not get PyPi Project: {project_name}. Response: {response.status_code}"
        )

    response_data: dict[str, dict[str, str]] = response.json()
    return response_data


def get_pypi_version(project_data: dict[str, dict[str, str]]) -> str:
    info_data = project_data.get("info")

    if not info_data:
        raise Exception("Could not get PyPi Project")

    version_data: str = str(info_data.get("version"))

    return str(version_data)

def check_for_update():
    pypi_data = get_project_data("vastai")
    pypi_version = get_pypi_version(pypi_data)

    local_version = get_local_version()

    local_tuple = parse_version(local_version)
    pypi_tuple = parse_version(pypi_version)

    if local_tuple >= pypi_tuple:
        return

    user_wants_update = input(
        f"Update available from {local_version} to {pypi_version}. Would you like to update [Y/n]: "
    ).lower()

    if user_wants_update not in ["y", ""]:
        print("You selected no. If you don't want to check for updates each time, update should_check_for_update in vast_cli/config.py")
        return

    update_command = get_update_command(pypi_version)

    print("Updating...")
    _ = subprocess.run(
        update_command,
        shell=True,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    print("Update completed successfully!\nAttempt to run your command again!")
    sys.exit(0)
