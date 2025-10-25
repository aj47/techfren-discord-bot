"""Script to fix all logging f-string interpolation issues across multiple files."""
import re
import sys
from pathlib import Path


def fix_logging_fstrings(content):
    """Convert f-string logging to lazy % formatting."""
    lines = content.split('\n')
    result = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Check if line contains logger with f-string
        if 'logger.' in line and 'f"' in line and ('debug' in line or 'info' in line or 
                                                      'warning' in line or 'error' in line or 
                                                      'critical' in line or 'exception' in line):
            # Handle multi-line logging statements
            full_statement = line
            paren_count = line.count('(') - line.count(')')
            j = i + 1
            
            while paren_count > 0 and j < len(lines):
                full_statement += '\n' + lines[j]
                paren_count += lines[j].count('(') - lines[j].count(')')
                j += 1
            
            # Try to fix the statement
            fixed = fix_single_logger_call(full_statement)
            if fixed != full_statement:
                result.append(fixed)
                i = j
                continue
        
        result.append(line)
        i += 1
    
    return '\n'.join(result)


def fix_single_logger_call(statement):
    """Fix a single logger call."""
    # Pattern to match logger.level(f"...{var}...")
    # Simple cases first - single line
    simple_pattern = r'(logger\.(debug|info|warning|error|critical|exception))\(f"([^"]*?)"\)'
    match = re.search(simple_pattern, statement)
    
    if match:
        logger_call = match.group(1)
        fstring_content = match.group(3)
        
        # Find all {var} patterns
        var_pattern = r'\{([^}]+)\}'
        variables = re.findall(var_pattern, fstring_content)
        
        if not variables:
            # No variables, just remove f prefix
            return statement.replace('f"', '"')
        
        # Replace {var} with %s
        new_string = re.sub(var_pattern, '%s', fstring_content)
        
        # Build the argument list
        args = ', '.join(variables)
        
        return f'{logger_call}("{new_string}", {args})'
    
    return statement


def main():
    files = [
        'bot.py',
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
        'logging_config.py',
        'db_utils.py',
        'db_migration.py',
        'summarization_tasks.py',
        'sorting_utils.py',
    ]
    
    for filename in files:
        filepath = Path(filename)
        if not filepath.exists():
            print(f"Skipping {filename} - not found")
            continue
            
        print(f"Processing {filename}...")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        fixed_content = fix_logging_fstrings(content)
        
        if fixed_content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(fixed_content)
            print(f"  ✓ Fixed logging in {filename}")
        else:
            print(f"  - No changes needed in {filename}")


if __name__ == "__main__":
    main()
