"""Test table parsing with the example."""
import re

TABLE_PATTERN = re.compile(
    r"(\|.+\|[\r\n]+\|[\s\-:|]+\|[\r\n]+(?:\|.+\|[\r\n]*)+)", re.MULTILINE
)

# Test with the example table
test_content = """| Month    | Savings |
|----------|---------|
| January  | $250    |
| February | $80     |
| March    | $420    |"""

print("Testing table pattern...")
print(f"Content:\n{test_content}\n")

matches = TABLE_PATTERN.findall(test_content)
print(f"Found {len(matches)} table(s)")

if matches:
    for i, match in enumerate(matches):
        print(f"\nTable {i+1}:")
        print(repr(match))
else:
    print("❌ No tables found!")
    print("\nTrying to debug...")
    
    # Test parts of the pattern
    print("\n1. First line (header):")
    if re.match(r"\|.+\|", test_content.split('\n')[0]):
        print("   ✓ Header matches")
    else:
        print("   ✗ Header doesn't match")
    
    print("\n2. Second line (separator):")
    if re.match(r"\|[\s\-:|]+\|", test_content.split('\n')[1]):
        print("   ✓ Separator matches")
    else:
        print("   ✗ Separator doesn't match")
    
    print("\n3. Data lines:")
    for i, line in enumerate(test_content.split('\n')[2:], start=3):
        if re.match(r"\|.+\|", line):
            print(f"   ✓ Line {i} matches")
        else:
            print(f"   ✗ Line {i} doesn't match")
    
    # Try a simpler pattern
    simple_pattern = re.compile(r"\|.+\|\s+\|[\-\s]+\|\s+(?:\|.+\|\s*)+", re.MULTILINE)
    print("\n4. Trying simpler pattern:")
    simple_matches = simple_pattern.findall(test_content)
    print(f"   Found {len(simple_matches)} matches")
