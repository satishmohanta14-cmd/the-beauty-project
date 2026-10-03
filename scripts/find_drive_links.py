import urllib.request
import ssl
import re

ctx = ssl.create_default_context()
sheet_id = '1HhYXTClEcV_cAcLinGgaBW3QKh89iYjiGzF49Kbxtxc'
url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/edit?gid=892870375'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
    html = r.read().decode('utf-8', errors='ignore')

drive_links = re.findall(r'https?://(?:drive|docs)\.google\.com/[^\s"\'<>]+', html)
print('Drive/Docs links found:', len(drive_links))
for l in list(set(drive_links))[:10]:
    print(' ', l)
