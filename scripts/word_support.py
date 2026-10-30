"""Candidate text/audio matching from attention DTW, never character-count timing."""
from pathlib import Path
import json,re,subprocess,difflib,wave,io,math
class Words:
 def __init__(self,media,rows,cache,duration,simplifier=None):
  self.media=Path(media);self.rows=rows;self.cache=Path(cache);self.duration=duration;self.simplifier=Path(simplifier) if simplifier else (self.cache/'simplify-chinese')
  self.character_map={}
  if self.simplifier and self.simplifier.exists():
   original=list(dict.fromkeys(''.join(r['text'] for r in rows)))
   canonical=json.loads(subprocess.check_output([str(self.simplifier)],input=json.dumps(original,ensure_ascii=False).encode()))
   self.character_map=dict(zip(original,canonical))
  self.glyphs=[]
  for r in rows:
   row_base=len(self.glyphs)
   for k,ch in enumerate(r['text']):
    span=next((x for x in r.get('word_spans',[]) if x['char_in']<=k<x['char_out']),None)
    self.glyphs.append({'text':ch,'cue':r['cue_id'],'start':r['start_seconds'],'end':r['end_seconds'],'word_span':({**span,'char_in':row_base+span['char_in'],'char_out':row_base+span['char_out']} if span else None)})
 def norm(self,s):return ''.join(self.character_map.get(c,c) for c in s if c.isalnum()).lower()
 def locate(self,lo,hi):
  if not 0<=lo<=hi<len(self.glyphs) or hi-lo>2000:raise ValueError('Selection out of range')
  chosen=self.glyphs[lo:hi+1];a=min(x['start'] for x in chosen);b=max(x['end'] for x in chosen);mid=(a+b)/2
  direct=[g['word_span'] for g in chosen if g['text'].isalnum()]
  if direct and all(direct):
   start=min(s['start'] for s in direct);end=max(s['end'] for s in direct)
   partial=any(s['char_in']<lo or s['char_out']>hi+1 for s in direct)
   return {'selected_text':''.join(g['text'] for g in chosen),'char_in':lo,'char_out':hi+1,'cue_ids':list(dict.fromkeys(g['cue'] for g in chosen)),'start':start,'end':end,'alignment':'partial_token_context' if partial else 'forced_alignment_candidate','requires_boundary_review':True,'warning':'原话强制对齐的候选剪口；先听原声再确认。' if not partial else '所选字在多字词中；请手动定准字的边界并试听后确认。'}
  windows=[]
  if (self.cache/'windows.json').exists():windows=json.loads((self.cache/'windows.json').read_text())
  candidates=[(Path(j['file']+'.json'),j['offset'],j['end']) for j in windows if j['offset']<=max(0,a-.1) and j['end']>=min(self.duration,b+.1) and Path(j['file']+'.json').exists()]
  if not candidates and a<27 and b<28 and (self.cache/'start.json').exists():candidates=[(self.cache/'start.json',0,28)]
  result={'selected_text':''.join(g['text'] for g in chosen),'char_in':lo,'char_out':hi+1,'cue_ids':list(dict.fromkeys(g['cue'] for g in chosen)),'start':a,'end':b,'alignment':'cue_context_only','requires_boundary_review':True,'warning':'本处精细对齐尚未准备好，当前仅载入所在原声段；请听原声定起止，不能直接当成选中字词的范围。'}
  if candidates:
   f,offset,end=min(candidates,key=lambda x:abs((x[1]+x[2])/2-mid));sources=[(f,offset,end,None)]
  else:
   tiles=[j for j in windows if j['offset']<=b and j.get('core_out',j['offset']+25)>a]
   if not tiles or any(not Path(j['file']+'.json').exists() for j in tiles):return result
   sources=[(Path(j['file']+'.json'),j['offset'],j['end'],min(j.get('core_out',j['offset']+25),self.duration)) for j in tiles]
   offset=min(j[1] for j in sources);end=max(j[2] for j in sources);f=sources[0][0]
  tokens=[]
  for file,shift,limit,ownership in sources:
   raw=json.loads(file.read_text())
   for seg in raw['transcription']:
    for t in seg['tokens']:
     text=t['text'];point=t.get('t_dtw',-1);center=shift+point/100
     if text.startswith('[_') or not text.strip() or point<0 or ownership is not None and center>=ownership:continue
     tokens.append({'text':text,'center':center,'p':t.get('p',0)})
  tokens.sort(key=lambda t:t['center'])
  # Convert simplified/traditional for spelling matching only; timestamp comes from DTW centers.
  # Canonicalize both sides only for matching. Display/raw tokens are never rewritten.
  stream=[]
  for i,t in enumerate(tokens):
   for c in self.norm(t['text']):stream.append((c,i))
  contextlo=lo
  while contextlo>0 and self.glyphs[contextlo-1]['start']>=offset:contextlo-=1
  contexthi=hi
  while contexthi+1<len(self.glyphs) and self.glyphs[contexthi+1]['end']<=end:contexthi+=1
  chars=[]
  for n in range(contextlo,contexthi+1):
   for c in self.norm(self.glyphs[n]['text']):chars.append((c,n))
  mapping={}
  for match in difflib.SequenceMatcher(None,[c for c,n in chars],[c for c,n in stream],autojunk=False).get_matching_blocks():
   for k in range(match.size):mapping[chars[match.a+k][1]]=stream[match.b+k][1]
  meaningful=[i for i in range(lo,hi+1) if self.norm(self.glyphs[i]['text'])]
  mapped=[mapping[i] for i in meaningful if i in mapping]
  if not meaningful or len(mapped)!=len(meaningful):result['warning']='选中文字与本段识别未完全对应，已载入原声上下文；请先定准起止，不自动代删。';return result
  first,last=min(mapped),max(mapped);ta=tokens[first]['center'];tb=tokens[last]['center']
  # DTW gives token centers; neighboring-center midpoints are candidate boundaries, not certified phoneme edges.
  start=max(offset,(tokens[first-1]['center']+ta)/2 if first else ta-.12)
  finish=min(end,(tokens[last+1]['center']+tb)/2 if last+1<len(tokens) else tb+.15)
  if finish<=start or abs((start+finish)/2-mid)>6:return result
  if any(not self.glyphs[n]['start']-.75<=tokens[mapping[n]]['center']<=self.glyphs[n]['end']+.75 for n in meaningful):return result
  result.update({'start':start,'end':finish,'alignment':'attention_DTW_token_candidate','matched_token_text':''.join(t['text'] for t in tokens[first:last+1]),'source':str(f),'warning':'这是原声对齐给出的候选剪口；连读、多字词或识别错字可能使边界偏移。先只听所选，必要时拖动波形或±20毫秒微调，再确认删除。'})
  if self.norm(result['selected_text'])!=self.norm(result['matched_token_text']):result['alignment']='partial_token_context';result['warning']='所选字处于多字词或连读内，候选范围覆盖「'+result['matched_token_text']+'」。请结合波形只保留要删的字，试听后再确认。'
  return result
 def audio(self,a,b):
  if not math.isfinite(a) or not math.isfinite(b) or not 0<=a<b<=self.duration or b-a>180:raise ValueError('Audio context must be within 180s')
  return subprocess.check_output(['ffmpeg','-v','error','-ss',str(a),'-i',str(self.media),'-t',str(b-a),'-vn','-ac','1','-ar','24000','-c:a','pcm_s16le','-f','wav','pipe:1'],timeout=60)
