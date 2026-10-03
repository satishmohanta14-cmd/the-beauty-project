import urllib.request
import ssl
import csv
import io
import re

ctx = ssl.create_default_context()
sheet_id = '1HhYXTClEcV_cAcLinGgaBW3QKh89iYjiGzF49Kbxtxc'

def inspect_full(gid, name):
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        content = resp.read().decode('utf-8', errors='ignore')
    print(f"\n==================== {name} (gid={gid}) ====================")
    reader = list(csv.reader(io.StringIO(content)))
    for idx, row in enumerate(reader):
        if any(row):
            print(f"[{idx}] {row}")

# Also fetch HTML to see any hyperlinks in the cells
def inspect_html(gid):
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/htmlview?gid={gid}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
        # Find all href links
        links = re.findall(r'href=[\'"]([^\'"]+)[\'"][^>]*>([^<]+)<', html)
        print(f"\nHyperlinks in gid {gid}:")
        for href, text in links:
            if 'google' in href or 'http' in href:
                print(f"  {text} -> {href}")
    except Exception as e:
        print(f"HTML fetch failed: {e}")

if __name__ == '__main__':
    inspect_full(892870375, "Sunscreen Tab (gid=892870375)")
    inspect_html(892870375)
    
    inspect_full(0, "Tab 0 (gid=0)")
    inspect_html(0)
