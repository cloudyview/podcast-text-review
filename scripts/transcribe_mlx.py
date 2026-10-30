"""Optional Apple Silicon Qwen ASR + forced alignment, retaining raw wording."""
import json,subprocess,wave,difflib,re
from pathlib import Path
from prepare_review import sha

def rows_from_alignment(text,items,offset,core_in,core_out,turns=None):
 # Matching only: punctuation is retained in the source text, not fabricated as speech.
 raw=[(c,i) for i,c in enumerate(text) if c.isalnum()];stream=[]
 for j,item in enumerate(items):
  for c in item['text']:
   if c.isalnum():stream.append((c,j))
 mapping={}
 for m in difflib.SequenceMatcher(None,[x[0] for x in raw],[x[0] for x in stream],autojunk=False).get_matching_blocks():
  for k in range(m.size):mapping[raw[m.a+k][1]]=stream[m.b+k][1]
 indices=[]
 for i in range(len(text)):
  nearest=mapping.get(i)
  if nearest is None:
   previous=[p for p in mapping if p<i];after=[p for p in mapping if p>i]
   if previous:nearest=mapping[max(previous)]
   elif after:nearest=mapping[min(after)]
  if nearest is not None:
   item=items[nearest];center=offset+(item['start']+item['end'])/2
   if core_in<=center<core_out:indices.append(i)
 if not indices:
  if text.strip() and not mapping:return [{'text':text,'raw_text':text,'start':core_in,'end':core_out,'word_spans':[],'speaker':'说话人待核','needs_review':True,'word_timing':'alignment unavailable; manual boundaries required'}]
  return []
 first,last=min(indices),max(indices);result=[];bucket=[];speaker=None
 def who(i):
  if i not in mapping:return speaker or '说话人待核'
  it=items[mapping[i]];a,b=offset+it['start'],offset+it['end'];scores={}
  for t in turns or []:
   overlap=max(0,min(b,t['end'])-max(a,t['start']))
   if overlap:scores[t['speaker']]=scores.get(t['speaker'],0)+overlap
  return max(scores,key=scores.get) if scores else '说话人待核'
 def emit():
  if not bucket:return
  lo,hi=bucket[0],bucket[-1]+1;spans=[]
  for j,it in enumerate(items):
   positions=[i for i in range(lo,hi) if mapping.get(i)==j]
   if not positions:continue
   a=max(core_in,offset+it['start']);b=min(core_out,offset+it['end'])
   if a<b:spans.append({'char_in':min(positions)-lo,'char_out':max(positions)+1-lo,'start':a,'end':b,'text':it['text'],'source':'Qwen forced-alignment candidate'})
  if spans:
   rawtext=text[lo:hi];result.append({'text':rawtext,'raw_text':rawtext,'start':min(x['start'] for x in spans),'end':max(x['end'] for x in spans),'word_spans':spans,'speaker':speaker,'speaker_source':'provided source turns; review identity at interruptions','needs_review':any(text[i].isalnum() and i not in mapping for i in range(lo,hi)),'word_timing':'forced-alignment candidates, not human signoff'})
  bucket.clear()
 for i in range(first,last+1):
  label=who(i)
  if bucket and (label!=speaker or text[bucket[-1]] in '。！？!?\n'):emit()
  if not bucket:speaker=label
  bucket.append(i)
 emit();return result

def transcribe_mlx(media,output,model,aligner,language='Cantonese',speaker_turns=None):
 import numpy as np
 from mlx_audio.stt import load
 media=Path(media).resolve(strict=True);output=Path(output).resolve();identity={'media':str(media),'sha256':sha(media),'model':str(model),'aligner':str(aligner),'language':language,'speaker_turns_sha256':sha(Path(speaker_turns)) if speaker_turns else None}
 if output.exists():
  if not (output/'asr-config.json').exists() or json.loads((output/'asr-config.json').read_text())!=identity:raise ValueError('ASR cache belongs to another input; choose a new session path')
 else:output.mkdir(parents=True)
 (output/'asr-config.json').write_text(json.dumps(identity,indent=2)+'\n')
 if (output/'transcript.json').exists():return output/'transcript.json'
 audio=output/'source-mono16k.wav'
 if not audio.exists():subprocess.run(['ffmpeg','-v','error','-i',str(media),'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(audio)],check=True)
 asr=load(str(model));align=load(str(aligner));turns=json.loads(Path(speaker_turns).read_text()) if speaker_turns else []
 if isinstance(turns,dict):turns=turns['turns']
 probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_type,duration:format=duration','-of','json',str(media)]));video=next(s for s in probe['streams'] if s['codec_type']=='video');duration=float(video.get('duration') if video.get('duration') not in (None,'N/A') else probe['format']['duration'])
 rows=[]
 with wave.open(str(audio)) as src:
  total=min(src.getnframes(),round(duration*16000))
  for core in range(0,total,25*16000):
   start=max(0,core-2*16000);end=min(total,core+28*16000);rawfile=output/f'raw-{core//16000:05}.json'
   if rawfile.exists():raw=json.loads(rawfile.read_text())
   else:
    src.setpos(start);samples=np.frombuffer(src.readframes(end-start),dtype='<i2').astype(np.float32)/32768
    result=asr.generate(samples,language=None if language=='auto' else language,max_tokens=768)
    # Cantonese uses the aligner's CJK character tokenizer. This is not a translation.
    align_language='Chinese' if language.lower() in ('cantonese','chinese','yue','zh') or (language=='auto' and re.search(r'[\u3400-\u9fff]',result.text)) else ('English' if language=='auto' else language)
    units=align.generate(audio=samples,text=result.text,language=align_language)
    raw={'text':result.text,'offset':start/16000,'core_in':core/16000,'core_out':min(total,core+25*16000)/16000,'alignment_language':align_language,'items':[{'text':x.text,'start':x.start_time,'end':x.end_time} for x in units]}
    rawfile.write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n')
   rows+=rows_from_alignment(raw['text'],raw['items'],raw['offset'],raw['core_in'],raw['core_out'],turns)
   print(f'Verbatim-target ASR: {min(total,core+25*16000)/16000:.1f}/{total/16000:.1f}s',flush=True)
 for i,row in enumerate(rows,1):row['cue_id']=f'raw-{i:05}'
 target=output/'transcript.json';target.write_text(json.dumps({'cues':rows,'status':'Raw ASR words plus forced-alignment candidates. No paraphrase/translation postprocessing. Human review required.','engine':'mlx-qwen','language':language},ensure_ascii=False,indent=2)+'\n');return target
