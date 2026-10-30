#!/usr/bin/env python3
"""Export cuts, kept source ranges and new clock without altering media."""
import argparse,json,math
from pathlib import Path

def export(session):
 config=json.loads((session/'config.json').read_text());statefile=session/'data/删改状态.json'
 state=json.loads(statefile.read_text()) if statefile.exists() else {'baseline':config['baseline'],'revision':0,'cuts':[]}
 if state['baseline']!=config['baseline']:raise ValueError('State baseline mismatch')
 duration=config['duration'];cuts=[]
 for c in sorted(state['cuts'],key=lambda c:c['start']):
  a,b=float(c['start']),float(c['end'])
  if not math.isfinite(a) or not math.isfinite(b) or not 0<=a<b<=duration:raise ValueError('Invalid cut')
  if cuts and a<=cuts[-1]['end']+.001:cuts[-1]['end']=max(cuts[-1]['end'],b)
  else:cuts.append({'start':a,'end':b})
 cursor=0;output=0;kept=[]
 for cut in cuts+[{'start':duration,'end':duration}]:
  if cut['start']>cursor:
   length=cut['start']-cursor;kept.append({'source_in':cursor,'source_out':cut['start'],'output_in':output,'output_out':output+length});output+=length
  cursor=cut['end']
 return {'baseline':config['baseline'],'media':config['media'],'media_sha256':config['media_sha256'],'revision':state['revision'],'annotations':state.get('annotations',{}),'cuts':cuts,'kept':kept,'original_duration':duration,'kept_duration':output,'removed_duration':duration-output,'status':'human_marks_only_not_final_cut_or_semantic_signoff','operation_log':str(session/'data/删改过程.jsonl')}
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--session',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();result=export(a.session.resolve());a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(a.output)
