import urllib.request
import ssl
import re

ctx = ssl.create_default_context()
sheet_id = '1HhYXTClEcV_cAcLinGgaBW3QKh89iYjiGzF49Kbxtxc'

def inspect_cell_links(gid):
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/edit?gid={gid}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
        html = r.read().decode('utf-8', errors='ignore')
    
    # search for drive links or urls near .xlsx
    xlsx_matches = [m.start() for m in re.finditer(r'\.xlsx', html)]
    print(f"=== GID {gid}: Found {len(xlsx_matches)} .xlsx references ===")
    for idx, p in enumerate(xlsx_matches[:5]):
        snippet = html[max(0, p-120):min(len(html), p+120)]
        print(f"[{idx}] {snippet}\n")

if __name__ == '__main__':
    inspect_cell_links(892870375)
    inspect_cell_links(698282467)
