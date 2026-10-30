"""Explicit, non-destructive video export from confirmed review marks."""
import json,subprocess,tempfile,os
from pathlib import Path
from export_decisions import export

def render_video(session,output):
 if output.exists():raise FileExistsError('Refusing to overwrite existing output')
 config=json.loads((session/'config.json').read_text());media=Path(config['media']);st=media.stat()
 if st.st_size!=config['media_bytes'] or st.st_mtime_ns!=config['media_mtime_ns']:raise ValueError('Source media changed; do not apply old marks to another version')
 decision=export(session);kept=decision['kept']
 if not kept:raise ValueError('All media is marked deleted; no video can be exported')
 if len(kept)>1000:raise ValueError('More than 1000 intervals; consolidate the review before rendering')
 probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','json',str(media)]));audio=any(s['codec_type']=='audio' for s in probe['streams'])
 lines=[]
 for i,k in enumerate(kept):
  a,b=k['source_in'],k['source_out'];lines.append(f'[0:v:0]trim=start={a:.9f}:end={b:.9f},setpts=PTS-STARTPTS[v{i}]')
  if audio:lines.append(f'[0:a:0]atrim=start={a:.9f}:end={b:.9f},asetpts=PTS-STARTPTS[a{i}]')
 inputs=''.join(f'[v{i}]'+(f'[a{i}]' if audio else '') for i in range(len(kept)))
 lines.append(inputs+f'concat=n={len(kept)}:v=1:a={int(audio)}[v]'+('[a]' if audio else ''))
 # A temporary directory works on Windows, where an open NamedTemporaryFile cannot be reopened by ffmpeg.
 with tempfile.TemporaryDirectory(prefix='review-render-') as temp:
  graph=Path(temp)/'graph.txt';graph.write_text(';\n'.join(lines))
  cmd=['ffmpeg','-v','error','-n','-i',str(media),'-filter_complex_script',str(graph),'-map','[v]']
  if audio:cmd+=['-map','[a]','-c:a','aac','-b:a','192k']
  cmd+=['-c:v','libx264','-crf','20','-preset','medium','-pix_fmt','yuv420p','-movflags','+faststart',str(output)]
  subprocess.run(cmd,check=True)
 print(output)
