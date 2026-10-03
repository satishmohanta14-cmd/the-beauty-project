import urllib.request
import ssl
import re
import csv
import io

ctx = ssl.create_default_context()
sheet_id = '1HhYXTClEcV_cAcLinGgaBW3QKh89iYjiGzF49Kbxtxc'

def extract_all_links():
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/edit?gid=892870375'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
        html = r.read().decode('utf-8', errors='ignore')
    
    # find all spreadsheets links
    links = re.findall(r'https://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_\-]+)/edit[^\s"\'<>]*', html)
    print("Found linked sheet IDs:", set(links))
    
    for sid in set(links):
        if sid == sheet_id:
            continue
        print(f"\n--- Testing Linked Sheet ID: {sid} ---")
        csv_url = f'https://docs.google.com/spreadsheets/d/{sid}/export?format=csv'
        try:
            req2 = urllib.request.Request(csv_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req2, timeout=10, context=ctx) as r2:
                content = r2.read().decode('utf-8', errors='ignore')
                rows = list(csv.reader(io.StringIO(content)))
                print(f"Total rows: {len(rows)}")
                for idx, row in enumerate(rows[:6]):
                    if any(row):
                        print(f"  Row {idx}: {[c[:50] for c in row if c]}")
        except Exception as e:
            print(f"Failed to fetch {sid}: {e}")

if __name__ == '__main__':
    extract_all_links()
