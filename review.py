#!/usr/bin/env python3
"""Local-first, human-in-the-loop video text review. No Node.js runtime required."""
import argparse,json,subprocess,sys,shutil,webbrowser
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
from dependencies import report,install,install_plan,download_model

def main(argv=None):
 ap=argparse.ArgumentParser(description=__doc__);subs=ap.add_subparsers(dest='command',required=True)
 doctor=subs.add_parser('doctor');doctor.add_argument('--install',choices=['ffmpeg','whisper','all']);doctor.add_argument('--dry-run',action='store_true')
 dl=subs.add_parser('download-model');dl.add_argument('name',nargs='?',default='base');dl.add_argument('--directory',type=Path)
 new=subs.add_parser('new');new.add_argument('--media',type=Path,required=True);new.add_argument('--session',type=Path,required=True);new.add_argument('--title',default='人工文字审校');new.add_argument('--transcript',type=Path);new.add_argument('--model',type=Path);new.add_argument('--model-name',default='base');new.add_argument('--language',default='auto');new.add_argument('--no-align',action='store_true',help='Skip model alignment; use manual waveform boundaries');new.add_argument('--proxy',action='store_true');new.add_argument('--speaker-turns',type=Path);new.add_argument('--asr-engine',choices=['whisper','mlx-qwen'],default='whisper');new.add_argument('--mlx-model',default='mlx-community/Qwen3-ASR-0.6B-4bit');new.add_argument('--mlx-aligner',default='mlx-community/Qwen3-ForcedAligner-0.6B-4bit')
 align=subs.add_parser('align');align.add_argument('--session',type=Path,required=True);align.add_argument('--model',type=Path,required=True);align.add_argument('--language',default='auto')
 serve=subs.add_parser('serve');serve.add_argument('--session',type=Path,required=True);serve.add_argument('--port',type=int,default=8794);serve.add_argument('--open',action='store_true')
 export=subs.add_parser('export-decisions');export.add_argument('--session',type=Path,required=True);export.add_argument('--output',type=Path,required=True)
 render=subs.add_parser('export-video');render.add_argument('--session',type=Path,required=True);render.add_argument('--output',type=Path,required=True)
 a=ap.parse_args(argv)
 if a.command=='doctor':
  print(json.dumps(report(),indent=2))
  if a.install:
   for tool in (['ffmpeg','whisper'] if a.install=='all' else [a.install]):
    if a.dry_run:print(json.dumps({'dependency':tool,'install_commands':install_plan(tool)}))
    else:install(tool)
 elif a.command=='download-model':print(download_model(a.name,a.directory))
 elif a.command=='new':
  from prepare_review import prepare
  if a.session.exists():raise FileExistsError('Session already exists; use serve to resume without overwriting marks')
  if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):raise RuntimeError('FFmpeg required: run python review.py doctor --install ffmpeg')
  transcript=a.transcript;model=a.model
  if transcript is None and a.asr_engine=='mlx-qwen':
   from transcribe_mlx import transcribe_mlx
   language={'yue':'Cantonese','zh':'Chinese','en':'English'}.get(a.language,a.language)
   transcript=transcribe_mlx(a.media,a.session.with_name(a.session.name+'-asr'),a.mlx_model,a.mlx_aligner,language,a.speaker_turns)
  elif transcript is None:
   if not shutil.which('whisper-cli'):raise RuntimeError('Local ASR required: run python review.py doctor --install whisper (or install official whisper.cpp)')
   if model is None:model=download_model(a.model_name)
   from transcribe_review import transcribe
   transcript=transcribe(a.media,a.session.with_name(a.session.name+'-asr'),model,a.language)
  prepare(a.media,transcript,a.session,a.title,proxy=a.proxy,speaker_turns=a.speaker_turns)
  if not a.no_align and a.asr_engine!='mlx-qwen':
   if not shutil.which('whisper-cli'):raise RuntimeError('Word candidates require whisper-cli; install it or use --no-align for manual boundaries')
   if model is None:model=download_model(a.model_name)
   subprocess.run([sys.executable,str(ROOT/'scripts/align_review.py'),'--session',str(a.session),'--model',str(model),'--language',a.language],check=True)
  print('Ready: '+str(a.session.resolve()));print('Start with: python review.py serve --session "'+str(a.session.resolve())+'" --open')
 elif a.command=='serve':
  subprocess.run([sys.executable,str(ROOT/'scripts/serve_review.py'),'--session',str(a.session),'--port',str(a.port)]+(['--open'] if a.open else []),check=True)
 elif a.command=='align':subprocess.run([sys.executable,str(ROOT/'scripts/align_review.py'),'--session',str(a.session),'--model',str(a.model),'--language',a.language],check=True)
 elif a.command=='export-decisions':
  from export_decisions import export
  with a.output.open('x') as f:json.dump(export(a.session.resolve()),f,ensure_ascii=False,indent=2);f.write('\n')
 elif a.command=='export-video':
  from render_review import render_video
  render_video(a.session.resolve(),a.output.resolve())
if __name__=='__main__':
 try:main()
 except (ValueError,RuntimeError,FileNotFoundError,FileExistsError,subprocess.CalledProcessError) as e:print('Error: '+str(e),file=sys.stderr);sys.exit(1)
