"""Fix exc_info syntax errors introduced by auto-fix script."""
import re
from pathlib import Path


def fix_exc_info_syntax(content):
    """Fix ), exc_info=True) to , exc_info=True)."""
    # Pattern: anything), exc_info=True)
    pattern = r'(\)),\s*exc_info=True\)'
    replacement = r'\1, exc_info=True'
    
    return re.sub(pattern, replacement, content)


def main():
    """Fix syntax errors in all Python files."""
    files = Path('.').glob('*.py')
    
    fixed_count = 0
    for filepath in files:
        if filepath.name.startswith('test_') or filepath.name.startswith('fix_'):
            continue
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        fixed_content = fix_exc_info_syntax(content)
        
        if fixed_content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(fixed_content)
            print(f"✓ Fixed {filepath.name}")
            fixed_count += 1
    
    print(f"\nFixed {fixed_count} files")


if __name__ == "__main__":
    main()
