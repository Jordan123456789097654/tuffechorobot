import re

files = ['bot.py', 'hr_commands.py', 'hiring_commands.py']
total = 0

for filepath in files:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        matches = re.findall(r'@bot\.tree\.command\(name="([^"]+)"', content)
        print(f"{filepath}: {len(matches)} commands")
        for m in matches:
            print(f"  /{m}")
        total += len(matches)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")

print(f"\nTOTAL SLASH COMMANDS ACROSS ALL FILES: {total}")
