"""Automatically fix common pylint issues."""
import re
from pathlib import Path


def fix_logging_fstrings_in_line(line):
    """Fix f-string logging in a single line."""
    # Pattern: logger.level(f"text {var1} more {var2}")
    pattern = r'(logger\.(debug|info|warning|error|critical|exception)\()(f")([^"]*?)(")'
    
    match = re.search(pattern, line)
    if not match:
        return line
    
    logger_call = match.group(1)
    fstring_content = match.group(4)
    
    # Find all {var} patterns
    var_pattern = r'\{([^}]+)\}'
    variables = re.findall(var_pattern, fstring_content)
    
    if not variables:
        # No variables, just remove f prefix
        return line.replace('f"', '"')
    
    # Replace {var} with %s or %d based on context
    new_string = fstring_content
    replacements = []
    for var in variables:
        # Check if it's a length or count (use %d)
        if 'len(' in var or '.count' in var or var.isdigit():
            new_string = new_string.replace(f'{{{var}}}', '%d', 1)
        else:
            new_string = new_string.replace(f'{{{var}}}', '%s', 1)
        replacements.append(var)
    
    # Build the new line
    args_str = ', '.join(replacements)
    new_line = f'{logger_call}"{new_string}", {args_str})'
    
    return line.replace(match.group(0), new_line)


def fix_file(filepath):
    """Fix common pylint issues in a file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    fixed_lines = []
    changes_made = 0
    
    for line in lines:
        original = line
        
        # Fix trailing whitespace
        line = line.rstrip()
        
        # Fix logging f-strings (simple cases only)
        if 'logger.' in line and 'f"' in line and '(' in line:
            line = fix_logging_fstrings_in_line(line)
        
        if line != original:
            changes_made += 1
        
        fixed_lines.append(line)
    
    if changes_made > 0:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(fixed_lines))
        return changes_made
    
    return 0


def main():
    """Fix pylint issues in all Python files."""
    files = [
        'command_handler.py',
        'command_abstraction.py',
        'llm_handler.py',
        'chart_renderer.py',
        'discord_formatter.py',
        'message_utils.py',
        'database.py',
        'thread_memory.py',
        'rate_limiter.py',
        'apify_handler.py',
        'firecrawl_handler.py',
        'youtube_handler.py',
        'config_validator.py',
        'db_migration.py',
        'summarization_tasks.py',
        'sorting_utils.py',
    ]
    
    total_changes = 0
    for filename in files:
        filepath = Path(filename)
        if not filepath.exists():
            print(f"⏭ Skipping {filename} - not found")
            continue
        
        changes = fix_file(filepath)
        if changes > 0:
            print(f"✓ Fixed {changes} issues in {filename}")
            total_changes += changes
        else:
            print(f"- No changes in {filename}")
    
    print(f"\nTotal: Fixed {total_changes} issues across {len(files)} files")


if __name__ == "__main__":
    main()
