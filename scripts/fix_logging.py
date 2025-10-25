"""Script to fix logging f-string interpolation issues."""
import re
import sys


def fix_logging_fstrings(content):
    """Convert f-string logging to lazy % formatting."""
    # Pattern to match logger.level(f"...{var}...")
    pattern = r'(logger\.(debug|info|warning|error|critical|exception))\(f"([^"]*?)"\)'
    
    def replace_fstring(match):
        logger_call = match.group(1)
        log_level = match.group(2)
        fstring_content = match.group(3)
        
        # Find all {var} patterns
        var_pattern = r'\{([^}]+)\}'
        variables = re.findall(var_pattern, fstring_content)
        
        if not variables:
            # No variables, just remove f prefix
            return f'{logger_call}("{fstring_content}")'
        
        # Replace {var} with %s
        new_string = re.sub(var_pattern, '%s', fstring_content)
        
        # Build the argument tuple
        args = ', '.join(variables)
        
        return f'{logger_call}("{new_string}", {args})'
    
    return re.sub(pattern, replace_fstring, content)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fix_logging.py <file>")
        sys.exit(1)
    
    filename = sys.argv[1]
    
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    fixed_content = fix_logging_fstrings(content)
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(fixed_content)
    
    print(f"Fixed logging in {filename}")
