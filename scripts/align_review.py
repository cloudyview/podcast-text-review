#!/usr/bin/env python3
"""Attention-DTW candidates, with bounded recovery for short-tail assertions."""
import argparse,json,subprocess,wave,sys,shutil,os
from pathlib import Path

def align(session,model,language='auto',whisper='whisper-cli'):
 root=Path(session).resolve();config=json.loads((root/'config.json').read_text());cache=root/'align';cache.mkdir(exist_ok=True)
 media=Path(config['media']);st=media.stat()
 if st.st_size!=config['media_bytes'] or st.st_mtime_ns!=config['media_mtime_ns']:raise ValueError('Source media changed')
 normalizer=cache/'simplify-chinese'
 if sys.platform=='darwin' and shutil.which('swiftc') and not normalizer.exists():subprocess.run(['swiftc',str(Path(__file__).resolve().parent.parent/'assets/simplify_chinese.swift'),'-o',str(normalizer)],check=True)
 model=Path(model).resolve(strict=True);preset=model.name.removeprefix('ggml-').removesuffix('.bin').split('-q')[0].replace('large-v','large.v').replace('large.v3-turbo','large.v3.turbo')
 if preset not in ['tiny','tiny.en','base','base.en','small','small.en','medium','medium.en','large.v1','large.v2','large.v3','large.v3.turbo']:raise ValueError('This model has no supported DTW preset; use --no-align/manual boundaries or a compatible base/small/medium model')
 mono=cache/'merged-mono16k.wav'
 if not mono.exists():subprocess.run(['ffmpeg','-v','error','-i',str(media),'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(mono)],check=True)
 jobs=[]
 with wave.open(str(mono)) as f:
  total=f.getnframes()
  for start in range(0,total,25*16000):
   out=cache/f'win-{start//16000:05}.wav'
   if not out.exists():
    with wave.open(str(out),'wb') as g:g.setparams(f.getparams());f.setpos(start);g.writeframes(f.readframes(min(total-start,30*16000)))
   jobs.append({'offset':start/16000,'end':min(total,start+30*16000)/16000,'file':str(out)})
 (cache/'windows.json').write_text(json.dumps(jobs,ensure_ascii=False,indent=2)+'\n');logfile=cache/'dtw.log';recoveries=[]
 def valid(job):
  try:return isinstance(json.loads(Path(job['file']+'.json').read_text())['transcription'],list)
  except (OSError,ValueError,KeyError):return False
 attempts={}
 for attempt in range(7):
  todo=[j for j in jobs if not valid(j)]
  if not todo:return {'windows':len(jobs),'status':'candidate timestamps ready; not human phoneme signoff'}
  print(f'Preparing word candidates: {len(jobs)-len(todo)}/{len(jobs)} windows ready',flush=True)
  with logfile.open('a') as log:result=subprocess.run([whisper,'-m',str(model),'-l',language,'-dtw',preset,'-nfa','-ojf',*[j['file'] for j in todo]],stdout=log,stderr=subprocess.STDOUT)
  if result.returncode==0:continue
  with logfile.open('rb') as log:log.seek(max(0,logfile.stat().st_size-2000));tail=log.read().decode(errors='replace')
  failed=next((j for j in jobs if not valid(j)),None)
  if 'filter_width < a->ne[2]' not in tail or failed is None:raise RuntimeError(f'Alignment failed; inspect {logfile}. Existing candidates and manual boundary editing remain available.')
  path=Path(failed['file']);attempts[str(path)]=attempts.get(str(path),0)+1
  if attempts[str(path)]>2:raise RuntimeError('DTW window failed after two analysis-tail repairs; use manual boundaries for this window')
  # Append silence only to an analysis window. Actual media and true coverage end never change.
  with wave.open(str(path)) as f:params=f.getparams();samples=f.readframes(f.getnframes())
  temp=path.with_suffix('.pad.wav')
  with wave.open(str(temp),'wb') as f:f.setparams(params);f.writeframes(samples+b'\0'*(params.framerate*params.nchannels*params.sampwidth))
  os.replace(temp,path);recoveries.append({'file':str(path),'analysis_tail_pad_seconds':1,'true_coverage_end_unchanged':True});(cache/'dtw-recoveries.json').write_text(json.dumps(recoveries,indent=2)+'\n')
 raise RuntimeError('Alignment recovery limit reached; manual editing remains available')
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--session',type=Path,required=True);ap.add_argument('--model',type=Path,required=True);ap.add_argument('--whisper',default='whisper-cli');ap.add_argument('--language',default='auto');a=ap.parse_args();print(json.dumps(align(a.session,a.model,a.language,a.whisper)))
