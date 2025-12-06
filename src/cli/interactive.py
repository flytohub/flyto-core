"""
Interactive CLI Menu System

Provides an enhanced interactive menu for the workflow engine.
"""

import sys
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum


class MenuAction(Enum):
    """Menu action types"""
    RUN_WORKFLOW = "run_workflow"
    LIST_WORKFLOWS = "list_workflows"
    LIST_MODULES = "list_modules"
    SHOW_VERSION = "show_version"
    SHOW_HELP = "show_help"
    SETTINGS = "settings"
    EXIT = "exit"


@dataclass
class MenuItem:
    """Menu item configuration"""
    key: str
    action: MenuAction
    label_key: str
    description_key: str


class Colors:
    """Terminal color codes"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'


class InteractiveMenu:
    """
    Interactive menu system for CLI.

    Features:
    - Main menu with multiple options
    - Workflow browser with categories
    - Module catalog viewer
    - Settings management
    """

    LINE_WIDTH = 70

    MAIN_MENU_ITEMS = [
        MenuItem("1", MenuAction.RUN_WORKFLOW, "menu.run_workflow", "menu.run_workflow_desc"),
        MenuItem("2", MenuAction.LIST_WORKFLOWS, "menu.list_workflows", "menu.list_workflows_desc"),
        MenuItem("3", MenuAction.LIST_MODULES, "menu.list_modules", "menu.list_modules_desc"),
        MenuItem("4", MenuAction.SHOW_VERSION, "menu.version", "menu.version_desc"),
        MenuItem("5", MenuAction.SHOW_HELP, "menu.help", "menu.help_desc"),
        MenuItem("6", MenuAction.SETTINGS, "menu.settings", "menu.settings_desc"),
        MenuItem("0", MenuAction.EXIT, "menu.exit", "menu.exit_desc"),
    ]

    def __init__(self, i18n: Any, config: Dict[str, Any]):
        """
        Initialize interactive menu.

        Args:
            i18n: Internationalization handler
            config: Application configuration
        """
        self.i18n = i18n
        self.config = config
        self._handlers: Dict[MenuAction, Callable] = {}

    def register_handler(self, action: MenuAction, handler: Callable) -> None:
        """Register a handler for a menu action"""
        self._handlers[action] = handler

    def show_header(self, title: str) -> None:
        """Display section header"""
        print()
        print(Colors.CYAN + "=" * self.LINE_WIDTH + Colors.END)
        print(Colors.BOLD + title.center(self.LINE_WIDTH) + Colors.END)
        print(Colors.CYAN + "=" * self.LINE_WIDTH + Colors.END)

    def show_separator(self) -> None:
        """Display separator line"""
        print(Colors.DIM + "-" * self.LINE_WIDTH + Colors.END)

    def show_main_menu(self) -> Optional[MenuAction]:
        """
        Display main menu and get user selection.

        Returns:
            Selected MenuAction or None
        """
        self.show_header(self._t("menu.title"))
        print()

        for item in self.MAIN_MENU_ITEMS:
            label = self._t(item.label_key)
            desc = self._t(item.description_key)

            if item.action == MenuAction.EXIT:
                color = Colors.YELLOW
            elif item.action == MenuAction.RUN_WORKFLOW:
                color = Colors.GREEN
            else:
                color = Colors.BLUE

            print(f"  {color}[{item.key}]{Colors.END} {label}")
            if desc:
                print(f"      {Colors.DIM}{desc}{Colors.END}")

        print()
        self.show_separator()

        choice = self._get_input(self._t("menu.select_option"))

        for item in self.MAIN_MENU_ITEMS:
            if choice == item.key:
                return item.action

        print(f"{Colors.RED}{self._t('menu.invalid_choice')}{Colors.END}")
        return None

    def run(self) -> None:
        """Run the interactive menu loop"""
        while True:
            action = self.show_main_menu()

            if action is None:
                continue

            if action == MenuAction.EXIT:
                self._handle_exit()
                break

            handler = self._handlers.get(action)
            if handler:
                try:
                    handler()
                except KeyboardInterrupt:
                    print(f"\n{Colors.YELLOW}{self._t('menu.cancelled')}{Colors.END}")
                except Exception as e:
                    print(f"{Colors.RED}{self._t('menu.error')}: {e}{Colors.END}")
            else:
                print(f"{Colors.YELLOW}{self._t('menu.not_implemented')}{Colors.END}")

            self._wait_for_continue()

    def show_workflow_categories(self, workflows: List[Dict[str, Any]]) -> Optional[str]:
        """
        Display workflows grouped by category.

        Args:
            workflows: List of workflow definitions

        Returns:
            Selected workflow path or None
        """
        categories: Dict[str, List[Dict[str, Any]]] = {}

        for wf in workflows:
            cat = wf.get("category", "general")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(wf)

        self.show_header(self._t("workflows.select"))
        print()

        all_workflows = []
        idx = 1

        for cat_name, cat_workflows in sorted(categories.items()):
            print(f"{Colors.BOLD}{cat_name.upper()}{Colors.END}")

            for wf in cat_workflows:
                name = wf.get("name", wf.get("path", "Unknown"))
                desc = self._get_localized(wf.get("description", {}))

                print(f"  {Colors.GREEN}[{idx}]{Colors.END} {name}")
                if desc:
                    print(f"      {Colors.DIM}{desc}{Colors.END}")

                all_workflows.append(wf)
                idx += 1

            print()

        print(f"  {Colors.YELLOW}[0]{Colors.END} {self._t('menu.back')}")

        self.show_separator()
        choice = self._get_input(self._t("workflows.enter_number"))

        try:
            choice_num = int(choice)
            if choice_num == 0:
                return None
            if 1 <= choice_num <= len(all_workflows):
                return all_workflows[choice_num - 1].get("path")
        except ValueError:
            pass

        print(f"{Colors.RED}{self._t('menu.invalid_choice')}{Colors.END}")
        return None

    def show_modules_list(self, modules: List[Dict[str, Any]]) -> None:
        """
        Display available modules.

        Args:
            modules: List of module information
        """
        categories: Dict[str, List[Dict[str, Any]]] = {}

        for mod in modules:
            parts = mod.get("id", "").split(".")
            cat = parts[0] if parts else "other"
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(mod)

        self.show_header(self._t("modules.catalog"))
        print()
        print(f"{self._t('modules.total')}: {Colors.GREEN}{len(modules)}{Colors.END}")
        print()

        for cat_name, cat_modules in sorted(categories.items()):
            print(f"{Colors.BOLD}{cat_name.upper()}{Colors.END} ({len(cat_modules)})")

            for mod in sorted(cat_modules, key=lambda m: m.get("id", "")):
                mod_id = mod.get("id", "unknown")
                mod_name = mod.get("name", mod_id)

                print(f"  {Colors.CYAN}{mod_id}{Colors.END}")
                if mod_name != mod_id:
                    print(f"    {Colors.DIM}{mod_name}{Colors.END}")

            print()

    def show_version_info(self, version: str, build_info: Dict[str, Any]) -> None:
        """
        Display version information.

        Args:
            version: Version string
            build_info: Build information dictionary
        """
        self.show_header(self._t("version.title"))
        print()
        print(f"  {self._t('version.version')}: {Colors.GREEN}{version}{Colors.END}")

        if build_info.get("commit"):
            print(f"  {self._t('version.commit')}: {build_info['commit'][:8]}")
        if build_info.get("date"):
            print(f"  {self._t('version.date')}: {build_info['date']}")
        if build_info.get("python"):
            print(f"  Python: {build_info['python']}")

        print()

    def show_help(self) -> None:
        """Display help information"""
        self.show_header(self._t("help.title"))
        print()

        help_sections = [
            ("help.usage_title", "help.usage_content"),
            ("help.workflows_title", "help.workflows_content"),
            ("help.params_title", "help.params_content"),
        ]

        for title_key, content_key in help_sections:
            print(f"{Colors.BOLD}{self._t(title_key)}{Colors.END}")
            print(f"  {self._t(content_key)}")
            print()

    def show_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Display and modify settings.

        Args:
            settings: Current settings

        Returns:
            Updated settings
        """
        self.show_header(self._t("settings.title"))
        print()

        setting_items = [
            ("language", self._t("settings.language"), settings.get("language", "en")),
            ("output_dir", self._t("settings.output_dir"), settings.get("output_dir", "./output")),
            ("verbose", self._t("settings.verbose"), str(settings.get("verbose", False))),
        ]

        for idx, (key, label, value) in enumerate(setting_items, 1):
            print(f"  {Colors.BLUE}[{idx}]{Colors.END} {label}: {Colors.GREEN}{value}{Colors.END}")

        print(f"\n  {Colors.YELLOW}[0]{Colors.END} {self._t('menu.back')}")

        self.show_separator()
        choice = self._get_input(self._t("settings.select"))

        try:
            choice_num = int(choice)
            if choice_num == 0:
                return settings
            if 1 <= choice_num <= len(setting_items):
                key, label, _ = setting_items[choice_num - 1]
                new_value = self._get_input(f"{label}: ")

                if key == "verbose":
                    settings[key] = new_value.lower() in ["true", "yes", "1"]
                else:
                    settings[key] = new_value

                print(f"{Colors.GREEN}{self._t('settings.updated')}{Colors.END}")
        except ValueError:
            print(f"{Colors.RED}{self._t('menu.invalid_choice')}{Colors.END}")

        return settings

    def confirm(self, message: str) -> bool:
        """
        Show confirmation prompt.

        Args:
            message: Confirmation message

        Returns:
            True if confirmed, False otherwise
        """
        response = self._get_input(f"{message} (y/n): ")
        return response.lower() in ["y", "yes"]

    def show_progress(self, current: int, total: int, message: str = "") -> None:
        """
        Display progress indicator.

        Args:
            current: Current step
            total: Total steps
            message: Progress message
        """
        percent = (current / total) * 100 if total > 0 else 0
        bar_width = 40
        filled = int(bar_width * current / total) if total > 0 else 0

        bar = f"[{'#' * filled}{'-' * (bar_width - filled)}]"

        print(f"\r{Colors.CYAN}{bar}{Colors.END} {percent:.1f}% {message}", end="", flush=True)

        if current >= total:
            print()

    def _t(self, key: str) -> str:
        """Get translated text"""
        if hasattr(self.i18n, 't'):
            return self.i18n.t(key)
        return key

    def _get_localized(self, text: Any) -> str:
        """Get localized text from dict or string"""
        if isinstance(text, dict):
            lang = getattr(self.i18n, 'lang', 'en')
            return text.get(lang, text.get('en', ''))
        return str(text) if text else ''

    def _get_input(self, prompt: str) -> str:
        """Get user input with prompt"""
        try:
            return input(f"{prompt}> ").strip()
        except EOFError:
            return ""

    def _wait_for_continue(self) -> None:
        """Wait for user to press enter"""
        print()
        self._get_input(self._t("menu.press_enter"))

    def _handle_exit(self) -> None:
        """Handle exit action"""
        print()
        print(f"{Colors.CYAN}{self._t('menu.goodbye')}{Colors.END}")


def create_menu(i18n: Any, config: Dict[str, Any]) -> InteractiveMenu:
    """
    Factory function to create an interactive menu.

    Args:
        i18n: Internationalization handler
        config: Application configuration

    Returns:
        Configured InteractiveMenu instance
    """
    return InteractiveMenu(i18n, config)
