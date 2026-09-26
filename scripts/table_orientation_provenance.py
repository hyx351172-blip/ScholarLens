"""Export native rotated Docling boxes into the original crop/page coordinate frame."""
import argparse
from pathlib import Path
from audit_table_decoder import read,write,sha
from table_orientation import original_bbox


def docling_bbox(box,original_size,angle,page_offset=(0,0)):
    # The experiment wraps pixels as equal-sized PDF points without resampling.
    width,height=original_size
    rh=width if angle in (90,270) else height
    if box['coord_origin']=='TOPLEFT':r=[box['l'],box['t'],box['r'],box['b']]
    elif box['coord_origin']=='BOTTOMLEFT':r=[box['l'],rh-box['t'],box['r'],rh-box['b']]
    else:raise ValueError('Unknown native coordinate origin')
    return original_bbox(r,original_size,angle,page_offset)


def run(root):
    summary=read(root/'summary.json');source=Path(summary['source'])
    manifest={c['id']:c for c in read(source/'prepared/manifest.json')['cases']}
    dest=root/'native-provenance';dest.mkdir()
    results=[]
    for row in summary['results']:
        if not row['angle_ccw'] or row['fresh_runs'].get('baseline',{}).get('status')!='completed':continue
        src=root/'fresh'/row['id']/'baseline'
        export=read(src/'baseline-export.json');raw=read(src/'docling-document.json')
        table=raw['tables'][export['selected_table']]
        size=row['orientation']['decision']['original_size'];angle=row['angle_ccw'];offset=manifest[row['id']]['crop_bbox'][:2]
        expected=size[::-1] if angle in (90,270) else size
        if len(raw['pages'])!=1:raise ValueError('Expected single cropped page')
        page=next(iter(raw['pages'].values()))
        if [page['size']['width'],page['size']['height']]!=expected:raise ValueError('Native PDF frame mismatch')
        cells=[];unavailable=[]
        for i,c in enumerate(table['data']['table_cells']):
            b=c.get('bbox')
            if b is None:unavailable.append(i);continue
            cells.append({'native_cell_id':i,'row':c['start_row_offset_idx'],'col':c['start_col_offset_idx'],
                'original_crop_bbox':docling_bbox(b,size,angle),'original_page_bbox':docling_bbox(b,size,angle,offset),
                'native_bbox':b})
        result={'id':row['id'],'angle_ccw':angle,'original_size':size,'page_offset':offset,'cells':cells,
                'unavailable_bbox_cell_ids':unavailable,'native_sha256':sha(src/'docling-document.json'),
                'coordinate_units':'crop pixels = crop PDF points; page boxes in source-image pixels'}
        write(dest/(row['id']+'.json'),result);results.append({'id':row['id'],'mapped_cells':len(cells),'missing_boxes':len(unavailable)})
    write(dest/'summary.json',{'results':results,'source_summary_sha256':sha(root/'summary.json'),'code_sha256':sha(Path(__file__).resolve())})
    print(results)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);run(p.parse_args().root.resolve())
