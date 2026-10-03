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

m = re.search(r'var bootstrapData\s*=\s*(\{.*?\});\s*var', html, re.DOTALL)
if m:
    data = json.loads(m.group(1))
    changes = data.get('changes', {})
    print("Keys in bootstrapData:", list(data.keys()))
    # dump any string containing sheet names
    raw = json.dumps(data)
    # search for 'facewash', 'sunscreen', 'moisturizer'
    for term in ['facewash', 'sunscreen', 'moisturizer']:
        for item in re.finditer(re.escape(term), raw, re.IGNORECASE):
            start = max(0, item.start() - 100)
            end = min(len(raw), item.end() + 100)
            print(f"Context for '{term}':", raw[start:end])
