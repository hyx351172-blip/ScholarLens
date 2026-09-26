import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from table_record_reconstruction import reconstruct_records
from table_grid_binding import bind_grid
from table_candidate_safety import guard_candidate
from audit_table_decoder import read, ROOT, parse_html_table
from table_structure import render_table_html


def sync_text(t):
    structure=parse_html_table(t['html'])[0]
    by={(c['row'],c['col']):c for c in t['cells']}
    t['assignments']=[]
    for native in structure['table_cells']:
        c=by[(native['start_row_offset_idx'],native['start_col_offset_idx'])]
        c['text']=' '.join(a['text'] for a in c['ocr'])
        native['text']=c['text'];t['assignments'].extend(copy.deepcopy(c['ocr']))
    t['assignments'].sort(key=lambda a:a['ocr_id'])
    t['html']=render_table_html(structure)
    return t


def fixture(records=4,wrap=True,extra_row=False):
    # Generic numbered labels + a short measurement anchor, not the real dates.
    cols=3; top=40; bottom=top+records*40
    html='<table><tr>'+('<th></th>'*cols)+'</tr><tr>'+('<td></td>'*cols)+'</tr>'
    if extra_row: html+='<tr>'+('<td></td>'*cols)+'</tr>'
    html+='</table>'
    ys=[0,top,bottom]+([bottom+30] if extra_row else [])
    boxes=[[c*120,ys[r],(c+1)*120,ys[r+1]] for r in range(len(ys)-1) for c in range(cols)]
    ob=[];text=[]
    def add(c,y,t,indent=5,width=100):
        ob.append([c*120+indent,y,c*120+min(indent+width,115),y+10]);text.append(t)
    for c,t in enumerate(['Input','Size','Output']):add(c,10,t)
    for i in range(records):
        y=top+8+i*40
        add(0,y,f'Sample {i+1} alpha'+('-' if wrap and i%2==0 else ''))
        add(1,y,f'{i+2} kg',width=40)
        add(2,y,f'Batch {i+10} beta'+('-' if wrap and i%2 else ''))
        if wrap:add(i%2*2,y+15,'continued',indent=15,width=70)
    if extra_row:
        for c in range(cols):add(c,bottom+8,'unchanged')
    captured={'geometry_reprocessing':{'detected_boxes':boxes},'match':{'ocr_boxes':ob},'render':{'texts':text}}
    return guard_candidate(bind_grid(html,captured,[360,ys[-1]]))


def two_rows():
    t=fixture(3,False,True)
    next_id=max(a['ocr_id'] for c in t['cells'] for a in c['ocr'])+1
    for c in t['cells']:
        if c['row']!=2:continue
        col=c['col'];c['bbox'][3]=340;c['ocr']=[]
        for i in range(4):
            text=[f'Trial {40+i}',f'{10+i} ms',f'Group {50+i}'][col]
            c['ocr'].append({'ocr_id':next_id,'text':text,'bbox':[col*120+5,168+i*40,col*120+100,178+i*40],
                             'cell_id':c['cell_id']});next_id+=1
        c['ocr_ids']=[a['ocr_id'] for a in c['ocr']]
    sync_text(t);t['ocr_count']=len(t['assignments']);return t


class RecordReconstructionTests(unittest.TestCase):
    def test_wrapped_records_split_and_continuations_preserved(self):
        t=fixture();old=copy.deepcopy(t);out=reconstruct_records(t)
        self.assertTrue(out['gate']['passed'],out.get('record_reconstruction'))
        s=parse_html_table(out['html'])[0]
        self.assertEqual(s['num_rows'],5)
        self.assertEqual(s['num_cols'],3)
        self.assertEqual(t,old)
        cells={(c['row'],c['col']):c for c in out['cells']}
        self.assertEqual(cells[(1,0)]['text'],'Sample 1 alpha- continued')
        self.assertEqual(cells[(2,2)]['text'],'Batch 11 beta- continued')
        self.assertEqual(cells[(4,1)]['text'],'5 kg')
        before={a['ocr_id']:(a['text'],a['bbox']) for c in t['cells'] for a in c['ocr']}
        after=[a for c in out['cells'] for a in c['ocr']]
        self.assertEqual(len(after),len(before))
        self.assertEqual({a['ocr_id']:(a['text'],a['bbox']) for a in after},before)

    def test_variable_counts_no_wrap_and_following_row_shift(self):
        for n in (3,5,7):
            out=reconstruct_records(fixture(n,False,True))
            self.assertTrue(out['gate']['passed'],out.get('record_reconstruction'))
            self.assertEqual(parse_html_table(out['html'])[0]['num_rows'],n+2)
            last=[c for c in out['cells'] if c['row']==n+1]
            self.assertEqual([c['text'] for c in last],['unchanged']*3)

    def test_passed_and_other_rejected_inputs_are_unchanged(self):
        t=fixture();t['gate']={'passed':True,'reasons':[]}
        self.assertEqual(reconstruct_records(t),t)
        t['gate']={'passed':False,'reasons':['another_error']}
        self.assertEqual(reconstruct_records(t),t)

    def test_no_numeric_anchor_does_not_split_paragraphs(self):
        t=fixture()
        for a in t['cells'][4]['ocr']:a['text']='ordinary paragraph text'
        sync_text(t)
        out=reconstruct_records(t)
        self.assertFalse(out['gate']['passed'])
        self.assertIn('no_supported_record_partition',out['record_reconstruction']['reasons'][0])

    def test_numeric_list_without_two_independent_label_columns_rejected(self):
        t=fixture()
        for c in t['cells']:
            if c['row']==1 and c['col'] in (0,2):
                for a in c['ocr']:a['text']='normal wrapped sentence'
        sync_text(t)
        out=reconstruct_records(t)
        self.assertFalse(out['gate']['passed'])
        self.assertIn('insufficient_independent_record_labels',out['record_reconstruction']['reasons'][0])

    def test_unindented_unhyphenated_continuation_is_ambiguous(self):
        t=fixture();cell=t['cells'][3]
        cell['ocr'][0]['text']='Sample 1 alpha'
        cell['ocr'][1]['bbox'][0]=cell['ocr'][0]['bbox'][0]
        sync_text(t)
        out=reconstruct_records(t)
        self.assertFalse(out['gate']['passed'])
        self.assertIn('unsupported_continuation',out['record_reconstruction']['reasons'][0])

    def test_scale_translation_and_generic_label_changes(self):
        for scale in (.5,1.,2.5):
            t=fixture(3)
            for c in t['cells']:
                c['bbox']=[v*scale+(7 if i%2==0 else 11) for i,v in enumerate(c['bbox'])]
                for a in c['ocr']:
                    a['bbox']=[v*scale+(7 if i%2==0 else 11) for i,v in enumerate(a['bbox'])]
                    a['text']=a['text'].replace('Sample','Specimen').replace('Batch','Run').replace('kg','ms')
            sync_text(t);out=reconstruct_records(t)
            self.assertTrue(out['gate']['passed'],out.get('record_reconstruction'))
            self.assertEqual(parse_html_table(out['html'])[0]['num_rows'],4)

    def test_html_text_is_escaped_not_interpreted(self):
        t=fixture(3)
        a=t['cells'][3]['ocr'][0];a['text']='Sample 1 <b>safe & literal</b>-'
        sync_text(t);out=reconstruct_records(t)
        self.assertTrue(out['gate']['passed'],out.get('record_reconstruction'))
        self.assertIn('&lt;b&gt;safe &amp; literal&lt;/b&gt;',out['html'])

    def test_repair_idempotent(self):
        out=reconstruct_records(fixture())
        self.assertEqual(reconstruct_records(out),out)

    def test_whole_row_declared_header_is_not_split(self):
        t=fixture();s=parse_html_table(t['html'])[0]
        for c in s['table_cells']:
            if c['start_row_offset_idx']==1:c['column_header']=True
        t['html']=render_table_html(s)
        out=reconstruct_records(t)
        self.assertFalse(out['gate']['passed'])
        self.assertIn('target_row_contains_header',out['record_reconstruction']['reasons'])

    def test_conflicting_geometry_and_forged_binding_fail_closed(self):
        for bad in ('geometry','binding'):
            t=fixture()
            if bad=='geometry':t['cells'][4]['bbox'][1]+=1
            else:t['cells'][3]['ocr'][0]['cell_id']=500
            out=reconstruct_records(t)
            self.assertFalse(out['gate']['passed'])
            self.assertEqual(out['html'],t['html'])

    def test_record_limit_rejects_atomically(self):
        t=fixture(33,False);out=reconstruct_records(t)
        self.assertFalse(out['gate']['passed'])
        self.assertEqual(out['cells'],t['cells'])

    def test_missing_numeric_anchor_entry_is_not_absorbed_as_wrap(self):
        t=fixture();c=t['cells'][4]
        c['ocr'][1]['text']='two values'
        sync_text(t);out=reconstruct_records(t)
        self.assertFalse(out['gate']['passed'])

    def test_other_columns_without_numeric_starts_remain_unchanged(self):
        t=fixture(4,False)
        for c in t['cells']:
            if c['row']==1 and c['col'] in (0,2):
                for a in c['ocr']:a['text']='continuously wrapped prose.'
        sync_text(t);out=reconstruct_records(t)
        self.assertFalse(out['gate']['passed'])
        self.assertEqual(out['cells'],t['cells'])

    def test_valid_rowspan_crossing_target_is_preserved_not_expanded(self):
        html='<table><tr><th></th><th></th><th></th></tr>'
        html+='<tr><td rowspan="2"></td><td></td><td></td></tr><tr><td></td><td></td></tr></table>'
        boxes=[[c*120,0,(c+1)*120,40] for c in range(3)]+[[0,40,120,240]]
        boxes += [[c*120,a,(c+1)*120,b] for c in (1,2) for a,b in ((40,80),(80,240))]
        ob=[];texts=[]
        for i in range(4):
            for c,text in [(1,f'{i+1} kg'),(2,f'Sample {i+1}')]:
                ob.append([c*120+5,90+i*35,c*120+95,100+i*35]);texts.append(text)
        cap={'geometry_reprocessing':{'detected_boxes':boxes},'match':{'ocr_boxes':ob},'render':{'texts':texts}}
        t=guard_candidate(bind_grid(html,cap,[360,240]))
        self.assertEqual(t['gate']['reasons'],['aligned_multiline_row_ambiguity'])
        out=reconstruct_records(t)
        self.assertFalse(out['gate']['passed'])
        self.assertIn('target_row_contains_span_or_header',out['record_reconstruction']['reasons'])
        self.assertEqual(out['html'],t['html'])

    def test_entire_multiline_first_row_remains_unverified(self):
        t=fixture(4,False)
        # Valid table, all original body cells now the first and only row.
        s=parse_html_table(t['html'])[0];s['table_cells']=s['table_cells'][3:];s['num_rows']=1
        t['cells']=t['cells'][3:]
        for n,c in zip(s['table_cells'],t['cells']):
            n['start_row_offset_idx']=0;n['end_row_offset_idx']=1;c['row']=0
        t['html']=render_table_html(s);sync_text(t)
        out=reconstruct_records(t)
        self.assertFalse(out['gate']['passed'])
        self.assertIn('unverified_body_row',out['record_reconstruction']['reasons'])

    def test_multiple_merged_rows_shift_independently(self):
        out=reconstruct_records(two_rows())
        self.assertTrue(out['gate']['passed'],out.get('record_reconstruction'))
        self.assertEqual(parse_html_table(out['html'])[0]['num_rows'],8)
        self.assertEqual(len(out['record_reconstruction']['rows']),2)
        self.assertEqual(next(c['text'] for c in out['cells'] if (c['row'],c['col'])==(7,2)),'Group 53')

    def test_later_failure_never_returns_partial_reconstruction(self):
        t=two_rows();s=parse_html_table(t['html'])[0]
        for c in s['table_cells']:
            if c['start_row_offset_idx']==2:c['column_header']=True
        t['html']=render_table_html(s);out=reconstruct_records(t)
        self.assertFalse(out['gate']['passed'])
        self.assertEqual(out['html'],t['html']);self.assertEqual(out['cells'],t['cells'])
        self.assertEqual(out['assignments'],t['assignments'])

    def test_header_span_missing_start_and_cross_row_span_not_split(self):
        for mutate in ('header','span','missing'):
            t=fixture()
            if mutate=='header':t['cells'][3]['is_header']=True
            if mutate=='span':t['cells'][3]['row_span']=2
            if mutate=='missing':t['cells'][5]['ocr'][0]['text']='not a record start'
            if mutate=='missing':sync_text(t)
            self.assertFalse(reconstruct_records(t)['gate']['passed'])

    def test_nan_duplicate_id_and_inconsistent_html_fail_closed(self):
        for bad in ('nan','duplicate','html'):
            t=fixture()
            if bad=='nan':t['cells'][3]['ocr'][0]['bbox'][0]=float('nan')
            if bad=='duplicate':t['cells'][4]['ocr'][0]['ocr_id']=t['cells'][3]['ocr'][0]['ocr_id']
            if bad=='html':t['html']='<table><tr><td>unrelated</td></tr></table>'
            self.assertFalse(reconstruct_records(t)['gate']['passed'])

    def test_real_v13_collapsed_row_restored_without_gold(self):
        t=read(ROOT/'output/benchmarks/omnidocbench-table-safety-v13-bounded/final/case-13/grid-trace.json')
        out=reconstruct_records(t)
        self.assertTrue(out['gate']['passed'],out.get('record_reconstruction'))
        s=parse_html_table(out['html'])[0]
        self.assertEqual((s['num_rows'],s['num_cols']),(5,3))
        self.assertEqual(len(out['assignments']),20)
        values={(c['row'],c['col']):c['text'] for c in out['cells']}
        self.assertEqual(values[(3,2)],'June 12 Mon- day.')
        self.assertEqual(values[(4,0)],'June 7 Wednes- day.')

if __name__=='__main__':unittest.main()
