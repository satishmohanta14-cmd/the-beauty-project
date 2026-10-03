import urllib.request
import ssl
import re
import json

ctx = ssl.create_default_context()
sheet_id = '1HhYXTClEcV_cAcLinGgaBW3QKh89iYjiGzF49Kbxtxc'
url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/edit'

req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

# Google sheets embeds sheets in `var bootstrapData = ...`
m = re.search(r'var bootstrapData\s*=\s*(\{.*?\});\s*var', html, re.DOTALL)
if not m:
    m = re.search(r'bootstrapData\s*=\s*(\{.*?\});', html, re.DOTALL)

if m:
    print("Found bootstrapData!")
    # Search for sheet names inside
    text = m.group(1)
    # look for sheet tab titles
    matches = re.findall(r'\[\s*([0-9]{1,10})\s*,\s*0\s*,\s*"([^"]+)"', text)
    print("Matches 1:", matches)
    matches2 = re.findall(r'"([0-9]{1,10})",\s*"([^"]+)"', text)
    print("Matches 2 (sample):", matches2[:10])
else:
    print("bootstrapData not found, searching raw html...")
    # Search for sheetId
    all_gids = re.findall(r'gid=([0-9]+)', html)
    print("Found gids:", set(all_gids))
    # Look for tab names
    tabs = re.findall(r'class="docs-sheet-tab-name"[^>]*>([^<]+)<', html)
    print("docs-sheet-tab-name:", tabs)
