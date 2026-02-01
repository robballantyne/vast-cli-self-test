"""Constants and configuration for vast_cli."""

import json
import os
import sys
import shutil
import logging
from datetime import timedelta
from urllib.parse import quote_plus


PYPI_BASE_PATH = "https://pypi.org"
# INFO - Change to False if you don't want to check for update each run.
should_check_for_update = False

JSONDecodeError = json.JSONDecodeError

#server_url_default = "https://vast.ai"
server_url_default = os.getenv("VAST_URL") or "https://console.vast.ai"
#server_url_default = "http://localhost:5002"
#server_url_default = "host.docker.internal"
#server_url_default = "http://localhost:5002"
#server_url_default  = "https://vast.ai/api/v0"

logging.basicConfig(
    level=os.getenv("LOGLEVEL") or logging.WARN,
    format="%(levelname)s - %(message)s"
)

APP_NAME = "vastai"

# define emoji support and fallbacks
_HAS_EMOJI = sys.stdout.encoding and 'utf' in sys.stdout.encoding.lower()
SUCCESS = "✅" if _HAS_EMOJI else "[OK]"
WARN    = "⚠️" if _HAS_EMOJI else "[!]"
FAIL    = "❌" if _HAS_EMOJI else "[X]"
INFO    = "ℹ️" if _HAS_EMOJI else "[i]"

try:
  # Although xdg-base-dirs is the newer name, there's
  # python compatibility issues with dependencies that
  # can be unresolvable using things like python 3.9
  # So we actually use the older name, thus older
  # version for now. This is as of now (2024/11/15)
  # the safer option. -cjm
  import xdg

  DIRS = {
      'config': xdg.xdg_config_home(),
      'temp': xdg.xdg_cache_home()
  }

except ImportError:
  # Reasonable defaults.
  DIRS = {
      'config': os.path.join(os.getenv('HOME'), '.config'),
      'temp': os.path.join(os.getenv('HOME'), '.cache'),
  }

for key in DIRS.keys():
  DIRS[key] = path = os.path.join(DIRS[key], APP_NAME)
  if not os.path.exists(path):
    os.makedirs(path)

CACHE_FILE = os.path.join(DIRS['temp'], "gpu_names_cache.json")
CACHE_DURATION = timedelta(hours=24)

APIKEY_FILE = os.path.join(DIRS['config'], "vast_api_key")
APIKEY_FILE_HOME = os.path.expanduser("~/.vast_api_key") # Legacy
TFAKEY_FILE = os.path.join(DIRS['config'], "vast_tfa_key")

if not os.path.exists(APIKEY_FILE) and os.path.exists(APIKEY_FILE_HOME):
  #print(f'copying key from {APIKEY_FILE_HOME} -> {APIKEY_FILE}')
  shutil.copyfile(APIKEY_FILE_HOME, APIKEY_FILE)
