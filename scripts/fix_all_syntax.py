"""Fix all syntax errors from automated changes."""
import re
from pathlib import Path


def fix_line(line):
    """Fix common syntax errors in a line."""
    # Fix pattern: ...), exc_info=True (missing opening paren)
    if '), exc_info=True' in line and 'logger.' in line:
        # Count parens
        open_count = line.count('(')
        close_count = line.count(')')
        
        if close_count > open_count:
            # Replace ), exc_info=True with , exc_info=True)
            line = line.replace('), exc_info=True', ', exc_info=True)')
    
    # Fix f-string format issues like :.1f in non-f-strings
    if 'logger.' in line and ':.1f' in line and not line.strip().startswith('f"'):
        # This is a problem - we have f-string formatting but no f-string
        # We need to convert it back or fix it
        if '"%s"' in line or '"%d"' in line:
            # This was converted from f-string, need to use %s instead of :.1f
            line = re.sub(r', (\w+):.1f,', r', %s,', line)
            # Need to add str() around the variable or use %s
    
    return line


def main():
    """Fix syntax errors in all Python files."""
    files = [
        'command_handler.py',
        'command_abstraction.py',
        'llm_handler.py',
        'chart_renderer.py',
        'discord_formatter.py',
        'database.py',
        'youtube_handler.py',
        'apify_handler.py',
        'summarization_tasks.py',
        'db_migration.py',
        'firecrawl_handler.py',
    ]
    
    fixed_count = 0
    for filename in files:
        filepath = Path(filename)
        if not filepath.exists():
            continue
        
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        fixed_lines = [fix_line(line) for line in lines]
        
        if fixed_lines != lines:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(fixed_lines)
            print(f"✓ Fixed {filepath.name}")
            fixed_count += 1
    
    print(f"\nFixed {fixed_count} files")


if __name__ == "__main__":
    main()
