"""
CLI Configuration

Constants and configuration for the CLI.
"""

from pathlib import Path


# CLI Constants
CLI_VERSION = "1.1.0"
CLI_LINE_WIDTH = 70
SUPPORTED_LANGUAGES = {
    '1': ('en', 'English'),
    '2': ('zh', 'Chinese'),
    '3': ('ja', 'Japanese'),
}
# Note: i18n files moved to flyto-i18n repository
CONFIG_FILE = Path(__file__).parent.parent / 'engine.yaml'
WORKFLOWS_DIR = Path(__file__).parent.parent / 'workflows'
DEFAULT_OUTPUT_DIR = Path('./output')

# ASCII Logo
LOGO = r"""






"""


class Colors:
    """Color codes for terminal output"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
