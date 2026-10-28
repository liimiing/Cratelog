"""Validate locale syntax, formatting placeholders and English UI coverage."""
import ast
import json
from pathlib import Path
from string import Formatter
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cratelog_i18n import CATALOGS,EN,REVERSE
from translations import TRANSLATIONS
errors=[]
def fields(text):return {name for _,name,_,_ in Formatter().parse(text) if name is not None}
base=CATALOGS['en_US']
for code in TRANSLATIONS:
    catalog=CATALOGS.get(code,{})
    for source,target in catalog.items():
        if not target or fields(source)!=fields(target):errors.append(code+': '+source)
    print(f'{code}: {len(set(catalog)&set(base))}/{len(base)} translated player phrases; missing phrases use English')
for path in ROOT.glob('*.py'):
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='tr' and node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str):
            value=node.args[0].value
            if any('\u4e00'<=c<='\u9fff' for c in value) and value not in EN and value not in REVERSE:errors.append(path.name+': '+value)
if errors:
    print('\n'.join(errors));sys.exit(1)
