import re

with open('templates/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

print('Length of index.html:', len(text))
