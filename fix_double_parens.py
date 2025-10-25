"""Fix double parenthesis issues from logging fixes."""
import re
from pathlib import Path


def fix_double_parens(content):
    """Fix logger.method("...", args)) to logger.method("...", args)."""
    # Pattern: logger.method("...", ...))
    lines = content.split('\n')
    fixed_lines = []
    
    for line in lines:
        # If line contains logger. and ends with ))
        if 'logger.' in line and line.rstrip().endswith('))'):
            # Check if this is truly a double paren issue
            # Count opening and closing parens
            open_count = line.count('(')
            close_count = line.count(')')
            
            if close_count > open_count:
                # Remove one closing paren
                line = line.rstrip()[:-1]
        
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)


def main():
    """Fix syntax errors in all Python files."""
    files = [
        'command_handler.py',
        'command_abstraction.py',
        'llm_handler.py',
        'chart_renderer.py',
        'discord_formatter.py',
        'message_utils.py',
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
            content = f.read()
        
        original = content
        fixed_content = fix_double_parens(content)
        
        if fixed_content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(fixed_content)
            print(f"✓ Fixed {filepath.name}")
            fixed_count += 1
    
    print(f"\nFixed {fixed_count} files")


if __name__ == "__main__":
    main()
