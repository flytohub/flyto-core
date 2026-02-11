#!/usr/bin/env python3
"""
Add placeholder= to preset functions that produce string fields without options.

Strategy: For each preset function, find the return field() call and add placeholder= kwarg.
Uses AST validation to ensure no corruption.
"""
import ast
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CORE_ROOT = SCRIPT_DIR.parent

# Mapping: preset function name -> placeholder value
PRESETS_PLACEHOLDER = {
    # analysis.py
    'HTML_CONTENT': '<html><body>content</body></html>',
    # browser.py
    'DIALOG_PROMPT_TEXT': 'Enter text here',
    # communication.py
    'WEBHOOK_AUTH_TOKEN': 'Bearer your-token',
    'EMAIL_SUBJECT': 'Email Subject',
    'EMAIL_BODY': 'Email body content...',
    'EMAIL_FROM': 'sender@example.com',
    'EMAIL_CC': 'cc@example.com',
    'EMAIL_BCC': 'bcc@example.com',
    'SMTP_USER': 'user@example.com',
    'SMTP_PASSWORD': '********',
    'IMAP_USER': 'user@example.com',
    'IMAP_PASSWORD': '********',
    'EMAIL_FOLDER': 'INBOX',
    'EMAIL_SINCE_DATE': '2024-01-01',
    'EMAIL_FROM_FILTER': 'sender@example.com',
    'EMAIL_SUBJECT_FILTER': 'keyword',
    'SLACK_MESSAGE': 'Your message here',
    'SLACK_CHANNEL': '#general',
    'SLACK_USERNAME': 'Bot',
    # document.py
    'DOC_PAGES': '1-5',
    'DOC_IMAGES_OUTPUT_DIR': '/path/to/images',
    'EXCEL_SHEET': 'Sheet1',
    'EXCEL_RANGE': 'A1:Z100',
    'EXCEL_SHEET_NAME': 'Sheet1',
    'PDF_CONTENT': 'Document content...',
    'PDF_TITLE': 'Document Title',
    'PDF_AUTHOR': 'Author Name',
    'PDF_HEADER': 'Header text',
    'PDF_FOOTER': 'Footer text',
    'PDF_TEMPLATE': '/path/to/template.pdf',
    'WORD_FILE_PATH': '/path/to/document.docx',
    # format_ops.py
    'THOUSAND_SEPARATOR': ',',
    # hash.py
    'HASH_ENCODING': 'hex',
    # huggingface.py
    'HF_PROMPT': 'Enter your prompt...',
    'HF_TEXT_INPUT': 'Enter text...',
    'HF_SOURCE_LANG': 'en',
    'HF_TARGET_LANG': 'zh',
    'HF_AUDIO_PATH': '/path/to/audio.wav',
    'HF_IMAGE_PATH': '/path/to/image.png',
    'HF_LANGUAGE': 'en',
    # image.py
    'OUTPUT_DIRECTORY': '/path/to/output',
    'QRCODE_COLOR': '#000000',
    'QRCODE_BACKGROUND': '#FFFFFF',
    'QRCODE_LOGO_PATH': '/path/to/logo.png',
    # llm.py
    'LLM_MODEL': 'gpt-4o',
    'LLM_API_KEY': 'sk-...',
    # string_ext.py
    'STRING_PAD_CHAR': ' ',
    'STRING_SUFFIX': '-suffix',
    'STRING_SEPARATOR': ',',
}


def add_placeholder_to_preset(content: str, func_name: str, placeholder: str) -> str:
    """Add placeholder= to a preset function's field() call."""
    # Find the function definition
    pattern = rf'^def\s+{re.escape(func_name)}\s*\('
    func_match = re.search(pattern, content, re.MULTILINE)
    if not func_match:
        return content

    # Find the return field() call within this function
    func_start = func_match.start()
    # Find next function or end of file
    next_func = re.search(r'^def\s+\w+\s*\(', content[func_start + 10:], re.MULTILINE)
    if next_func:
        func_end = func_start + 10 + next_func.start()
    else:
        func_end = len(content)

    func_body = content[func_start:func_end]

    # Check if already has placeholder
    if 'placeholder=' in func_body or 'placeholder =' in func_body:
        return content

    # Find "return field(" in the function body
    field_match = re.search(r'return\s+field\(', func_body)
    if not field_match:
        return content

    # Find the closing paren of the field() call by counting nesting
    field_call_start = func_start + field_match.start()
    paren_start = content.index('(', field_call_start)

    depth = 0
    i = paren_start
    in_string = None
    escape_next = False
    paren_end = None

    while i < func_end:
        ch = content[i]
        if escape_next:
            escape_next = False
            i += 1
            continue
        if ch == '\\':
            escape_next = True
            i += 1
            continue
        if in_string:
            if ch == in_string:
                in_string = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_string = ch
            i += 1
            continue
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                paren_end = i
                break
        i += 1

    if paren_end is None:
        return content

    # Find indentation of existing kwargs
    field_section = content[paren_start:paren_end]
    indent = '        '
    for line in field_section.split('\n')[1:]:
        stripped = line.lstrip()
        if stripped and '=' in stripped:
            indent = line[:len(line) - len(stripped)]
            break

    # Insert placeholder= before closing paren
    before_close = content[paren_start + 1:paren_end].rstrip()
    comma = '' if before_close.endswith(',') else ','

    escaped_val = placeholder.replace("'", "\\'")
    insert = f"{comma}\n{indent}placeholder='{escaped_val}',"

    new_content = content[:paren_end] + insert + '\n' + content[paren_end:]
    return new_content


def main():
    dry_run = '--dry-run' in sys.argv
    verbose = '-v' in sys.argv or '--verbose' in sys.argv

    print("=" * 60)
    print("Preset Placeholder Fixer")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    preset_dir = CORE_ROOT / 'src' / 'core' / 'modules' / 'schema' / 'presets'
    fixed = 0
    skipped = 0

    # Group by file
    by_file = {}
    for func_name, placeholder in PRESETS_PLACEHOLDER.items():
        # Find which file contains this function
        for f in preset_dir.glob('*.py'):
            content = f.read_text()
            if re.search(rf'^def\s+{re.escape(func_name)}\s*\(', content, re.MULTILINE):
                by_file.setdefault(str(f), []).append((func_name, placeholder))
                break

    for fpath, items in sorted(by_file.items()):
        f = Path(fpath)
        content = f.read_text(encoding='utf-8')
        original = content

        for func_name, placeholder in items:
            new_content = add_placeholder_to_preset(content, func_name, placeholder)
            if new_content != content:
                # AST validate
                try:
                    ast.parse(new_content)
                    content = new_content
                    fixed += 1
                    if verbose:
                        print(f"  FIX  {f.name}:{func_name} -> placeholder='{placeholder}'")
                except SyntaxError as e:
                    skipped += 1
                    if verbose:
                        print(f"  FAIL {f.name}:{func_name} -> AST error: {e}")
            else:
                skipped += 1
                if verbose:
                    print(f"  SKIP {f.name}:{func_name} (already has or not found)")

        if content != original and not dry_run:
            f.write_text(content, encoding='utf-8')

    print()
    print("=" * 60)
    print(f"Fixed:   {fixed}")
    print(f"Skipped: {skipped}")
    print("=" * 60)
    if dry_run:
        print("DRY RUN - no files modified.")


if __name__ == '__main__':
    main()
