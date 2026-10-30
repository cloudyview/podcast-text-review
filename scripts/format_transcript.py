"""Add reading punctuation and speaker-turn metadata without paraphrasing words."""
import json,re
from pathlib import Path
from prepare_review import timed_rows

def lexical(s):return ''.join(c for c in s if c.isalnum())
def format_rows(rows,turns=None):
 result=[];turns=turns or []
 for i,row in enumerate(rows):
  r=dict(row);raw=r.get('raw_text',r['text']);a,b=r['start_seconds'],r['end_seconds'];speaker=r.get('speaker','说话人待核');source=r.get('speaker_source','unassigned')
  if turns:
   totals={}
   for t in turns:
    overlap=max(0,min(b,float(t['end']))-max(a,float(t['start'])))
    if overlap:totals[t['speaker']]=totals.get(t['speaker'],0)+overlap
   if totals:
    best=max(totals,key=totals.get)
    if totals[best]/(b-a)>=.85:speaker=best;source='provided speaker turns; candidate identity'
    else:speaker='说话人交接待核';source='turn overlap; not forced to one speaker'
  text=raw.strip();nextrow=rows[i+1] if i+1<len(rows) else None;gap=(nextrow['start_seconds']-b) if nextrow else 1
  # Only append a reading mark; never rewrite, translate, deduplicate or finish a thought.
  if text and text[-1] not in '，。！？!?；;：:,.' and (gap>.6 or nextrow is None):
   chinese=bool(re.search(r'[\u3400-\u9fff]',text));text+='。' if chinese else '.'
  if lexical(raw)!=lexical(text):raise ValueError('Punctuation formatting changed a spoken word')
  result.append({**r,'text':text,'raw_text':raw,'speaker':speaker,'speaker_source':source,'punctuation_source':'raw ASR plus appended reading hints; reviewable','verbatim_lexical_invariant':True})
 return result
if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--transcript',type=Path,required=True);ap.add_argument('--speaker-turns',type=Path);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();turns=json.loads(a.speaker_turns.read_text()) if a.speaker_turns else []
 if isinstance(turns,dict):turns=turns['turns']
 with a.output.open('x') as f:json.dump({'rows':format_rows(timed_rows(a.transcript),turns)},f,ensure_ascii=False,indent=2);f.write('\n')
