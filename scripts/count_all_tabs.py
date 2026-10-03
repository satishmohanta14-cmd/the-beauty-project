import urllib.request
import ssl
import re

ctx = ssl.create_default_context()
sheet_id = '1HhYXTClEcV_cAcLinGgaBW3QKh89iYjiGzF49Kbxtxc'

def get_links_for_tab(gid, name):
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/edit?gid={gid}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
        html = r.read().decode('utf-8', errors='ignore')
    
    links = set(re.findall(r'https://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_\-]+)/edit[^\s"\'<>]*', html))
    links.discard(sheet_id)
    print(f"=== {name} (gid={gid}) ===")
    print(f"Total linked spreadsheets: {len(links)}")
    return links

if __name__ == '__main__':
    sun_links = get_links_for_tab(892870375, "Sunscreen")
    face_links = get_links_for_tab(698282467, "Facewash")
    moist_links = get_links_for_tab(1277095192, "Moisturizer")
