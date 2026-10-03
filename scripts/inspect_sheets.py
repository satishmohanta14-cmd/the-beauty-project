import urllib.request
import urllib.parse
import ssl
import re
import csv
import io

ctx = ssl.create_default_context()
sheet_id = '1HhYXTClEcV_cAcLinGgaBW3QKh89iYjiGzF49Kbxtxc'

def get_sheet_names():
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/edit'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
    
    # Extract sheet names and gids
    # Looking for: "name":"...",...,"sheetId":12345
    pattern = r'\{[^{}]*?"name":\s*"([^"]+)"[^{}]*?"sheetId":\s*([0-9]+)[^{}]*?\}'
    matches = re.findall(pattern, html)
    return matches

def dump_tab(tab_name_or_gid):
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(tab_name_or_gid)}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            content = resp.read().decode('utf-8', errors='ignore')
            reader = list(csv.reader(io.StringIO(content)))
            print(f"\n==================== TAB: {tab_name_or_gid} ====================")
            print(f"Total rows: {len(reader)}")
            for idx, r in enumerate(reader[:10]):
                # print first few non-empty cells
                non_empty = [c[:80].replace('\n', ' ') for c in r if c]
                print(f"Row {idx}: {non_empty}")
            return reader
    except Exception as e:
        print(f"Failed to fetch {tab_name_or_gid}: {e}")
        return []

if __name__ == '__main__':
    sheets = get_sheet_names()
    print("Detected Sheets (Name, GID):")
    for name, gid in sheets:
        print(f" - {name} (gid={gid})")
    
    # Try dumping sheets
    for name, gid in sheets:
        dump_tab(name)
