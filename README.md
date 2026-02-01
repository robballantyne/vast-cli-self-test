# Welcome to Vast.ai's Documentation!

## Overview
This repository contains the open source command line interface for Vast.ai. The CLI replicates much of the functionality available in the Vast.ai website GUI by using the same underlying REST API. The core logic lives in the `vast_cli/` Python package, with commands organized into individual modules under `vast_cli/commands/`. PDF invoice generation is provided by the supplementary script `vast_pdf.py`.

Our Python SDK is maintained through a separate repository [vast-ai/vast-sdk](https://github.com/vast-ai/vast-sdk).

[![PyPI version](https://badge.fury.io/py/vastai.svg)](https://badge.fury.io/py/vastai)

## Table of Contents
1. [Quickstart](#quickstart)
2. [Usage](#usage)
3. [Install](#install)
4. [Project Structure](#project-structure)
5. [Commands](#commands)
6. [List of Commands and Associated Help Message](#list-of-commands-and-associated-help-message)
7. [Self-Test a Machine (Single Machine)](#self-test-a-machine-single-machine)
8. [Host Machine Testing with `vast_machine_tester.py`](#host-machine-testing-with-vast_machine_testerpy)
9. [Usage Examples](#usage-examples)
10. [Tab-Completion](#tab-completion)

## Quickstart
Install the CLI from PyPI:
```bash
pip install vastai
```
Verify that it's working:
```bash
vastai --help
```
You should see a list of available commands. Next, log in to the Vast.ai website and obtain your API key from [https://vast.ai/console/cli/](https://vast.ai/console/cli/). Copy the provided command under "Login / Set API Key" and run it. The command will look similar to:
```bash
vastai api-key set xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```
This command saves your API key in `~/.config/vastai/vast_api_key`. **Keep your API key secure.**

You can test a search command with:
```bash
vastai offer search --limit 3
```
This should display a short list of machine offers.

## Usage
The Vast.ai CLI provides a variety of commands for interacting with the Vast.ai platform. For example, you can search for available machines by running:
```bash
vastai offer search
```
To refine your search, consult the extensive help by running:
```bash
vastai offer search --help
```
You can filter results based on numerous parameters, similar to the website GUI.

For example, to find Turing GPU instances (with compute capability 7.0 or higher):
```bash
vastai offer search 'compute_cap > 700'
```
Or to find instances with a reliability score >= 0.99 and at least 4 GPUs (ordered by GPU count descending):
```bash
vastai offer search 'reliability > 0.99 num_gpus>=4' -o 'num_gpus-'
```

## Install
The recommended way to install the CLI is via pip:
```bash
pip install vastai
```
This installs the `vastai` command globally. The legacy `vast.py` script still exists as a backward-compatibility shim and delegates to the same code.

### Development Setup
For development, clone the repository and use [uv](https://docs.astral.sh/uv/) to manage dependencies:
```bash
git clone https://github.com/vast-ai/vast-python.git
cd vast-python
uv sync
```
You can then run the CLI via:
```bash
uv run vastai --help
```

### PDF Invoices
For generating PDF invoices, you will need the `vast_pdf.py` script (found in this repository) and the third-party library [Borb](https://github.com/jorisschellekens/borb). Borb is included in the project dependencies and will be installed automatically.

## Project Structure
The CLI is organized as a Python package under `vast_cli/`:

```
vast_cli/
  main.py            # Entry point (arg parsing, API key loading, dispatch)
  parser.py          # @parser.command() decorator and argument infrastructure
  state.py           # Global mutable state (ARGS, headers, TABCOMPLETE)
  config.py          # Constants, XDG paths, environment variable defaults
  helpers.py         # Miscellaneous utility functions
  completions.py     # Tab-completion helpers
  api/               # HTTP client and URL construction
  auth/              # SSH key validation
  commands/          # One module per command group (~16 modules, ~130 commands)
  display/           # Table formatting and rich output
  query/             # Search query parser and field definitions
  validation/        # Input validators
  version/           # Version checking and update logic
```

For full architectural details, see [AGENTS.md](AGENTS.md).

## Commands
The Vast.ai CLI is organized across modules in `vast_cli/commands/`. Commands follow an "object verb" pattern. For example, to show your hosted machines:
```bash
vastai machine show
```

## List of Commands and Associated Help Message
For a full list of commands and help messages, run:
```bash
vastai --help
```
This will display available commands including, but not limited to:
- `help`
- `instance create`
- `instance destroy`
- `offer search`
- `machine self-test`
- `instance show`
... and many others.

## Self-Test a Machine (Single Machine)
Hosts can perform a **self-test** on a single machine to verify that it meets the necessary requirements and passes reliability and stress tests.

### Usage
```bash
vastai machine self-test <machine_id> [--ignore-requirements]
```
- **`machine_id`**: The numeric ID of the machine to test.
- **`--ignore-requirements`** (optional): Continues tests even if system requirements are not met. If omitted, the self-test stops at the first requirement failure.

**Examples:**
```bash
# Standard self-test, respecting requirements:
vastai machine self-test 12345

# Self-test ignoring system requirements:
vastai machine self-test 12345 --ignore-requirements
```

**Output:**
1. **Requirements Check:**
   The script verifies whether the machine meets all necessary requirements. If any requirements are not met, it will report the failures.
2. **Instance Creation:**
   A temporary test instance is launched.
3. **Test Execution:**
   A series of tests are performed (system checks, GPU tests, stress tests, etc.).
4. **Summary:**
   The results are displayed, indicating whether the machine passed or failed along with any error messages.

The temporary test instance is automatically destroyed after testing.

## Usage Examples

### Single Machine Self-Test
```bash
vastai machine self-test 54321
```
If the machine fails to meet requirements, the output will indicate the failure reasons and the test will stop.

### Self-Test with Ignored Requirements
```bash
vastai machine self-test 54321 --ignore-requirements
```
This command will display the failing requirements but continue with the self-test.

### Testing Multiple Machines Automatically
```bash
python3 vast_machine_tester.py --host_id 123456 --ignore-requirements
```
This command will run self-tests on multiple machines from the specified host and output the results to `passed_machines.txt` and `failed_machines.txt`.

### Testing a Sample of Machines
```bash
python3 vast_machine_tester.py --host_id 123456 --sample-pct 30
```
This command tests approximately 30% of the machines, randomly sampled from the total list.

## Tab-Completion
The CLI supports tab-completion in both Bash and Zsh shells via the [argcomplete](https://github.com/kislyuk/argcomplete) package (included in project dependencies). To enable tab-completion:

1. Enable global tab-completion by running:
   ```bash
   activate-global-python-argcomplete
   ```
   Alternatively, for a single session, run:
   ```bash
   eval "$(register-python-argcomplete vastai)"
   ```

*Note:* Rapid invocations via tab-completion might trigger API rate limits. If you experience issues, please report them in the project's GitHub issues.

---

This documentation should help you get started with the Vast.ai CLI tools and understand the available commands and usage patterns. For more detailed information, refer to the inline help provided by each command.
