import json

st = json.load(open('.flip_state.json', encoding='utf-8'))
for r in st.get('pending_relists', []):
    r['game'] = 'EA SPORTS FC 26'
open('.flip_state.json', 'w', encoding='utf-8').write(
    json.dumps(st, ensure_ascii=False))
print('queue games fixed:', [r['game'] for r in st['pending_relists']])
