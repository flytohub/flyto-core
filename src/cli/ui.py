"""
CLI User Interface

Terminal UI utilities for the CLI.
"""

from .config import CLI_LINE_WIDTH, Colors, LOGO, SUPPORTED_LANGUAGES
from .i18n import I18n


def clear_screen() -> None:
    """Clear terminal screen using ANSI escape codes"""
    # Use ANSI escape sequence for cross-platform compatibility
    print('\033[2J\033[H', end='')


def print_logo(i18n: I18n) -> None:
    """Print ASCII logo"""
    print(Colors.OKCYAN + LOGO + Colors.ENDC)
    print(Colors.BOLD + i18n.t('cli.welcome') + Colors.ENDC)
    print(i18n.t('cli.version'))
    print(i18n.t('cli.description'))
    print()


def select_language() -> str:
    """Interactive language selection"""
    print("=" * CLI_LINE_WIDTH)
    print("Select language / Select Language / LanguageSelect:")
    for key, (code, name) in SUPPORTED_LANGUAGES.items():
        print(f"  {key}. {name}")
    print("=" * CLI_LINE_WIDTH)

    while True:
        choice = input("> ").strip()
        if choice in SUPPORTED_LANGUAGES:
            return SUPPORTED_LANGUAGES[choice][0]
        else:
            # Use English as fallback since i18n is not yet initialized
            print(f"Invalid choice. Please enter 1-{len(SUPPORTED_LANGUAGES)}. / "
                  f"Invalid choice. Please enter 1-{len(SUPPORTED_LANGUAGES)}.")
