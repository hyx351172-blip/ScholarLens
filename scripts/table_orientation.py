"""Gold-free quarter-turn selection and edge-coordinate inverse transforms."""
import math

ANGLES = (0,90,180,270)
POLICY = {'min_score': .65, 'min_margin': .08, 'min_characters': 40,
          'min_lines': 4, 'min_horizontal_fraction': .7, 'max_probe_side': 1280}


def ocr_quality(raw):
    texts,scores,boxes = (raw[k] for k in ('rec_texts','rec_scores','rec_boxes'))
    if not len(texts) == len(scores) == len(boxes) or len(texts)>10000:
        raise ValueError('OCR array mismatch or excessive result')
    numerator = denominator = horizontal = chars = lines = 0
    for text,score,box in zip(texts,scores,boxes):
        if not isinstance(text,str) or not math.isfinite(score) or not 0<=score<=1:
            raise ValueError('Invalid OCR confidence/text')
        if len(box)!=4 or not all(math.isfinite(v) for v in box) or box[0]>=box[2] or box[1]>=box[3]:
            raise ValueError('Invalid OCR rectangle')
        n=sum(not c.isspace() for c in text); w=min(n,40)
        denominator += w
        if box[2]-box[0] >= 1.25*(box[3]-box[1]):
            horizontal += w; numerator += w*score
            if score>=.5: chars+=n; lines+=bool(n)
    return {'score': numerator/max(1,denominator), 'horizontal_fraction': horizontal/max(1,denominator),
            'readable_characters': chars,'readable_lines':lines,'text_lines':len(texts)}


def choose_orientation(quality):
    if set(quality)!=set(ANGLES): raise ValueError('All four probes required')
    for q in quality.values():
        if any(not math.isfinite(q[k]) or not 0<=q[k]<=1 for k in ('score','horizontal_fraction')):
            raise ValueError('Invalid quality')
    ranked=sorted(quality,key=lambda a:(-quality[a]['score'],a))
    best=ranked[0]; q=quality[best]
    margin=q['score']-quality[ranked[1]]['score']; gain=q['score']-quality[0]['score']
    enough=(q['score']>=POLICY['min_score'] and q['horizontal_fraction']>=POLICY['min_horizontal_fraction']
            and q['readable_characters']>=POLICY['min_characters'] and q['readable_lines']>=POLICY['min_lines'])
    rotate=best!=0 and enough and margin>=POLICY['min_margin'] and gain>=POLICY['min_margin']
    return {'angle_ccw':best if rotate else 0,'best_probe':best,'margin':margin,'gain_over_zero':gain,
            'reason':'confident_rotation' if rotate else 'upright_or_insufficient_evidence',
            'policy':dict(POLICY),'quality':quality}


def original_bbox(box, original_size, angle_ccw, page_offset=(0,0)):
    if (len(original_size)!=2 or any(type(v) is not int or not 0<v<=50000 for v in original_size)
            or angle_ccw not in ANGLES or len(page_offset)!=2 or
            any(not math.isfinite(v) or v<0 for v in page_offset)):
        raise ValueError('Invalid rotation frame')
    w,h=original_size; rw,rh=(h,w) if angle_ccw in (90,270) else (w,h)
    if (len(box)!=4 or not all(math.isfinite(v) for v in box) or
            not (0<=box[0]<box[2]<=rw and 0<=box[1]<box[3]<=rh)):
        raise ValueError('Box outside rotated frame')
    points=[]
    for x,y in ((box[0],box[1]),(box[0],box[3]),(box[2],box[1]),(box[2],box[3])):
        ox,oy={0:(x,y),90:(w-y,x),180:(w-x,h-y),270:(y,h-x)}[angle_ccw]
        points.append((ox+page_offset[0],oy+page_offset[1]))
    return [min(x for x,y in points),min(y for x,y in points),max(x for x,y in points),max(y for x,y in points)]
