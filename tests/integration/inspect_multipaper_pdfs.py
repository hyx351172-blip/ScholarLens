"""Local PDF evidence inventory, no network/model calls."""
from pathlib import Path
import hashlib
import json
import fitz

ROOT=Path(__file__).resolve().parents[2]
DATA=Path('C:/Users/hp/Desktop/ScholarLens/backend/data/evaluation_papers')
OUT=ROOT/'output/e2e-multipaper-v1'
FILES=['1706.03762_attention-is-all-you-need.pdf','1810.04805_bert.pdf','2106.09685_lora.pdf']

if __name__=='__main__':
    papers=[]
    for name in FILES:
        pdf=DATA/name
        doc=fitz.open(pdf)
        pages=[p.get_text() for p in doc]
        (OUT/(pdf.stem+'.txt')).write_text('\n\n'.join(f'=== PDF PAGE {i} ===\n{t}' for i,t in enumerate(pages,1)),encoding='utf-8')
        papers.append(dict(filename=name,path=str(pdf),sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),pages=len(doc)))
        print(name,len(doc))
        for i,p in enumerate(doc):
            if (name.startswith('1706') and i==7) or (name.startswith('1810') and 'Model Size' in pages[i]) or (name.startswith('2106') and i==0):
                p.get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(OUT/f'{pdf.stem}-p{i+1}.png')
    (OUT/'pdf-inventory.json').write_text(json.dumps(papers,indent=2)+'\n',encoding='utf-8')
