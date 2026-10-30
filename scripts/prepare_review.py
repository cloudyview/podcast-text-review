#!/usr/bin/env python3
"""Freeze a video + same-clock timed transcript into a reusable local review session."""
import argparse,hashlib,json,math,re,shutil,subprocess
from pathlib import Path

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def timed_rows(path):
 if path.suffix.lower()=='.srt':
  pattern=r'(?m)^(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})[^\n]*\n([\s\S]*?)(?=\n\s*\n|\Z)'
  cues=[]
  for m in re.finditer(pattern,path.read_text(encoding='utf-8-sig')):
   a=list(map(int,m.groups()[:8]));sec=lambda q:q[0]*3600+q[1]*60+q[2]+q[3]/1000
   cues.append({'start':sec(a[:4]),'end':sec(a[4:]),'text':m[9].strip()})
 else:
  d=json.loads(path.read_text(encoding='utf-8-sig'));cues=d if isinstance(d,list) else d.get('rows',d.get('cues',d.get('segments',[])))
 rows=[]
 for i,c in enumerate(cues,1):
  start=float(c['start_seconds'] if 'start_seconds' in c else c['start']);end=float(c['end_seconds'] if 'end_seconds' in c else c['end'])
  if not math.isfinite(start) or not math.isfinite(end) or not 0<=start<end:raise ValueError(f'invalid cue {i}')
  text=c['text'];assert isinstance(text,str)
  rows.append({**c,'cue_id':str(c.get('cue_id',f'cue-{i:05}')),'start_seconds':start,'end_seconds':end,'text':text})
 if not rows:raise ValueError('No timed cues; untimed TXT is not accepted for video synchronization')
 if len({r['cue_id'] for r in rows})!=len(rows):raise ValueError('cue IDs must be unique')
 if any(b['start_seconds']<a['start_seconds'] for a,b in zip(rows,rows[1:])):raise ValueError('cues must be ordered by start')
 return rows

def prepare(media,transcript,output,title,simplifier=None,proxy=False,speaker_turns=None):
 media=media.resolve(strict=True);transcript=transcript.resolve(strict=True);output=output.resolve()
 if output.exists():raise FileExistsError('Use an existing session with serve_review.py; refusing to overwrite review records')
 rows=timed_rows(transcript)
 from format_transcript import format_rows
 turns=json.loads(Path(speaker_turns).read_text()) if speaker_turns else []
 if isinstance(turns,dict):turns=turns['turns']
 rows=format_rows(rows,turns)
 probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,duration,avg_frame_rate','-of','json',str(media)]))
 videos=[s for s in probe['streams'] if s['codec_type']=='video']
 if not videos:raise ValueError('Video stream required')
 value=videos[0].get('duration');duration=float(probe['format']['duration'] if value in (None,'N/A') else value)
 if not math.isfinite(duration) or duration<=0:raise ValueError('Invalid media duration')
 if rows[-1]['end_seconds']>duration+.001 or any(r['end_seconds']>duration+.001 for r in rows):raise ValueError('Transcript exceeds video; confirm matching clock/version before use')
 digest=sha(media);st=media.stat();baseline='baseline-'+hashlib.sha256((digest+'|'+sha(transcript)).encode()).hexdigest()
 config={'schema_version':2,'simplifier':str(simplifier.resolve()) if simplifier else None,'title':title,'baseline':baseline,'media':str(media),'media_sha256':digest,'media_bytes':st.st_size,'media_mtime_ns':st.st_mtime_ns,'duration':duration,'frame_rate':videos[0].get('avg_frame_rate'),'transcript_source':str(transcript),'transcript_sha256':sha(transcript),'cue_count':len(rows),'review_limits':'selected text with candidate token timing and manual PCM boundary audition; not certified phoneme boundaries'}
 output.mkdir(parents=True)
 if proxy:
  preview=output/'playback-proxy.mp4'
  subprocess.run(['ffmpeg','-v','error','-i',str(media),'-map','0:v:0','-map','0:a:0?','-c:v','libx264','-preset','fast','-crf','22','-pix_fmt','yuv420p','-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-c:a','aac','-movflags','+faststart',str(preview)],check=True)
  config['playback_media']=str(preview);config['playback_bytes']=preview.stat().st_size;config['playback_mtime_ns']=preview.stat().st_mtime_ns;config['playback_sha256']=sha(preview)
 (output/'config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
 (output/'transcript.json').write_text(json.dumps({'rows':rows},ensure_ascii=False,indent=2)+'\n')
 shutil.copy2(transcript,output/('source-transcript'+transcript.suffix))
 def tc(t):
  ms=round(t*1000);sec,ms=divmod(ms,1000);mins,sec=divmod(sec,60);hours,mins=divmod(mins,60);return f'{hours:02}:{mins:02}:{sec:02}.{ms:03}'
 (output/'transcript.txt').write_text(title+'\n现有时间码工作稿；请按原声判断。\n\n'+'\n'.join(f"[{r['cue_id']}] {tc(r['start_seconds'])} --> {tc(r['end_seconds'])} 【{r['speaker']}】{r['text']}" for r in rows)+'\n')
 for name in ['index.html','audio-engine.js']:shutil.copy2(Path(__file__).resolve().parent.parent/'assets'/name,output/name)
 snapshot={n:sha(output/n) for n in ['config.json','transcript.json','transcript.txt','index.html','audio-engine.js','source-transcript'+transcript.suffix]}
 (output/'baseline-manifest.json').write_text(json.dumps({'baseline':baseline,'files':snapshot},ensure_ascii=False,indent=2)+'\n')
 return config
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--media',type=Path,required=True);ap.add_argument('--transcript',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--title',required=True);ap.add_argument('--simplifier',type=Path);a=ap.parse_args()
 print(json.dumps(prepare(a.media,a.transcript,a.output,a.title,a.simplifier),ensure_ascii=False,indent=2))
