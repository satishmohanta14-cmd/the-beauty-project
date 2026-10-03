import urllib.request
import ssl
import csv
import io
import json

ctx = ssl.create_default_context()
sheet_id = '1HhYXTClEcV_cAcLinGgaBW3QKh89iYjiGzF49Kbxtxc'

def fetch_gid(gid):
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            content = resp.read().decode('utf-8', errors='ignore')
            rows = list(csv.reader(io.StringIO(content)))
            print(f"\n=== GID: {gid} === (Total rows: {len(rows)})")
            for idx, r in enumerate(rows[:5]):
                print(f"Row {idx}: {[c[:60].replace(chr(10), ' ') for c in r if c]}")
            return rows
    except Exception as e:
        print(f"GID {gid} failed: {e}")
        return []

def fetch_tab_name(name):
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={name}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            content = resp.read().decode('utf-8', errors='ignore')
            rows = list(csv.reader(io.StringIO(content)))
            print(f"\n=== TAB: {name} === (Total rows: {len(rows)})")
            for idx, r in enumerate(rows[:5]):
                print(f"Row {idx}: {[c[:60].replace(chr(10), ' ') for c in r if c]}")
            return rows
    except Exception as e:
        print(f"TAB {name} failed: {e}")
        return []

if __name__ == '__main__':
    # 1. Fetch gid 892870375 from user URL
    fetch_gid(892870375)
    # 2. Fetch gid 0
    fetch_gid(0)
    # 3. Try variations of names
    for name in ['sunscreen', 'Sunscreen', 'facewash', 'Facewash', 'Face wash', 'moisturizer', 'Moisturizer', 'Moisturizers', 'moisturizers']:
        fetch_tab_name(name)
