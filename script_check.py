with open('templates/index.html', 'r', encoding='utf-8') as f:
    text = f.read()
lines = text.splitlines()
for l in lines:
    if 'switchView' in l or 'id="view-' in l:
        print(l[:100].encode('ascii', errors='ignore').decode('ascii'))
