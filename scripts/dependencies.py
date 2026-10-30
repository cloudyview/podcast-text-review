"""Explicit dependency inspection and package-manager installation plans."""
import json,os,platform,shlex,shutil,subprocess,urllib.request,hashlib
from pathlib import Path

def report():
 return {'python':platform.python_version(),'platform':platform.system(),'tools':{n:shutil.which(n) for n in ['ffmpeg','ffprobe','whisper-cli','cmake','git']}}
def install_plan(tool,system=None,which=shutil.which):
 system=system or platform.system()
 if tool not in ('ffmpeg','whisper'):raise ValueError('Unknown dependency')
 if system=='Darwin' and which('brew'):return [['brew','install','ffmpeg' if tool=='ffmpeg' else 'whisper-cpp']]
 if system=='Windows' and tool=='ffmpeg' and which('winget'):return [['winget','install','--id','Gyan.FFmpeg','--exact','--source','winget']]
 if system=='Linux' and tool=='ffmpeg':
  for manager,args in [('apt-get',['install','-y','ffmpeg']),('dnf',['install','-y','ffmpeg']),('pacman',['-S','--needed','--noconfirm','ffmpeg'])]:
   if which(manager):return [[manager,*args]]
 return []
def install(tool):
 if (tool=='ffmpeg' and shutil.which('ffmpeg') and shutil.which('ffprobe')) or (tool=='whisper' and shutil.which('whisper-cli')):return
 commands=install_plan(tool)
 if not commands:raise RuntimeError('No supported package-manager installation for this dependency. See README for official source-build instructions.')
 for cmd in commands:
  if platform.system()=='Linux' and hasattr(os,'geteuid') and os.geteuid()!=0:
   if not shutil.which('sudo'):raise RuntimeError('Installation requires administrator access; run the printed package-manager command in your terminal')
   cmd=['sudo',*cmd]
  print('Installing: '+shlex.join(cmd),flush=True);subprocess.run(cmd,check=True)
 # No fake success if PATH has not refreshed or a package is unavailable.
 if tool=='ffmpeg' and not (shutil.which('ffmpeg') and shutil.which('ffprobe')):raise RuntimeError('Installation finished but ffmpeg/ffprobe are not on PATH; reopen terminal and run doctor')
 if tool=='whisper' and not shutil.which('whisper-cli'):raise RuntimeError('whisper-cli is not on PATH after installation; run doctor in a new terminal')
def cache_dir():
 return Path(os.environ.get('PODCAST_REVIEW_CACHE',Path.home()/'.cache/podcast-text-review'))
def download_model(name='base',directory=None):
 allowed={'tiny','tiny.en','base','base.en','small','small.en','medium','medium.en','large-v3','large-v3-turbo','large-v3-turbo-q5_0','large-v3-turbo-q8_0'}
 if name not in allowed:raise ValueError('Unsupported model name')
 directory=Path(directory or cache_dir()/'models');directory.mkdir(parents=True,exist_ok=True);filename=f'ggml-{name}.bin';target=directory/filename
 # Vendor metadata supplies the content hash; weights are never bundled with the project.
 request=urllib.request.Request('https://huggingface.co/api/models/ggerganov/whisper.cpp?blobs=true',headers={'User-Agent':'podcast-text-review/0.1'})
 with urllib.request.urlopen(request,timeout=60) as response:metadata=json.load(response)
 entry=next(x for x in metadata['siblings'] if x['rfilename']==filename);expected=entry.get('lfs',{}).get('sha256')
 if not expected:raise RuntimeError('Vendor did not supply SHA256 for selected model; use an explicitly supplied local model')
 def digest(file):
  h=hashlib.sha256()
  with file.open('rb') as f:
   for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
  return h.hexdigest()
 if target.exists():
  if digest(target)==expected:return target
  raise RuntimeError('Cached model checksum mismatch; preserve it and choose a new cache directory')
 revision=metadata['sha'];url=f'https://huggingface.co/ggerganov/whisper.cpp/resolve/{revision}/{filename}'
 print(f'Downloading {name} model from the official whisper.cpp model repository to {target}',flush=True)
 partial=target.with_suffix('.bin.part')
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'podcast-text-review/0.1'}),timeout=120) as response,partial.open('wb') as out:shutil.copyfileobj(response,out)
 if digest(partial)!=expected:raise RuntimeError('Downloaded model SHA256 mismatch; not installing it')
 os.replace(partial,target);return target
