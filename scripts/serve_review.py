#!/usr/bin/env python3
"""Loopback-only review server. Review marks are data, not destructive edits."""
import argparse,json,re,os,threading,hashlib,urllib.parse,mimetypes,math,webbrowser
from word_support import Words
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from datetime import datetime,timezone

def validate_cuts(cuts,duration):
 if not isinstance(cuts,list) or len(cuts)>5000:raise ValueError('Too many cuts')
 for c in cuts:
  if not isinstance(c,dict):raise ValueError('Invalid cut')
  a,b=c.get('start'),c.get('end')
  if isinstance(a,bool) or isinstance(b,bool) or not isinstance(a,(int,float)) or not isinstance(b,(int,float)) or not math.isfinite(a) or not math.isfinite(b) or not 0<=a<b<=duration:raise ValueError('Invalid range')
  if not isinstance(c.get('reason',''),str) or len(c.get('reason',''))>2000:raise ValueError('Invalid reason')

def validate_annotations(annotations):
 if not isinstance(annotations,dict):raise ValueError('Invalid annotations')
 labels=annotations.get('speaker_overrides',{})
 if not isinstance(labels,dict) or len(labels)>20000 or any(not isinstance(k,str) or not isinstance(v,str) or len(k)>150 or len(v)>100 for k,v in labels.items()):raise ValueError('Invalid speaker overrides')

def create_handler(session):
 session=session.resolve();config=json.loads((session/'config.json').read_text());media=Path(config['media']);playback=Path(config.get('playback_media',media));duration=config['duration'];data=session/'data';lock=threading.Lock()
 def unchanged():
  st=media.stat()
  if st.st_size!=config['media_bytes'] or st.st_mtime_ns!=config['media_mtime_ns']:raise ValueError('Source media changed; create a new baseline')
  if playback!=media:
   st=playback.stat()
   if st.st_size!=config['playback_bytes'] or st.st_mtime_ns!=config['playback_mtime_ns']:raise ValueError('Playback proxy changed')
 unchanged()
 manifest=json.loads((session/'baseline-manifest.json').read_text())
 for name,digest in manifest['files'].items():
  if hashlib.sha256((session/name).read_bytes()).hexdigest()!=digest:raise ValueError('Baseline file changed: '+name)
 rows=json.loads((session/'transcript.json').read_text())['rows'];words=Words(media,rows,session/'align',duration,config.get('simplifier'));data.mkdir(parents=True,exist_ok=True)
 statefile=data/'删改状态.json';events=data/'删改过程.jsonl'
 initial={'revision':0,'baseline':config['baseline'],'duration':duration,'cuts':[]}
 # The append-only event is the durable commit. Recover a committed edit if an interrupted
 # atomic snapshot replacement left state.json behind. Never mix another baseline's log.
 restored=json.loads(statefile.read_text()) if statefile.exists() else initial
 if restored['baseline']!=config['baseline']:raise ValueError('State belongs to another baseline')
 if events.exists():
  valid_bytes=0;rawlog=events.read_bytes()
  for line in rawlog.splitlines(keepends=True):
    try:event=json.loads(line)
    except json.JSONDecodeError:break # interrupted trailing append is not a committed event
    valid_bytes+=len(line)
    if event.get('baseline')==config['baseline'] and event['revision']==restored['revision']+1 and event['before']==restored['cuts']:
     restored={**restored,'revision':event['revision'],'cuts':event['after'],'annotations':event.get('after_annotations',restored.get('annotations',{})),'updated_at':event['at']}
  if valid_bytes<len(rawlog):
   # Preserve the interrupted tail for diagnosis, then allow future commits to replay.
   (data/('interrupted-log-'+str(len(rawlog))+'.bin')).write_bytes(rawlog[valid_bytes:])
   with events.open('wb') as log:log.write(rawlog[:valid_bytes]);log.flush();os.fsync(log.fileno())
  elif rawlog and not rawlog.endswith(b'\n'):
   with events.open('ab') as log:log.write(b'\n');log.flush();os.fsync(log.fileno())
 if restored!=initial and (not statefile.exists() or json.loads(statefile.read_text())!=restored):
  tmp=statefile.with_suffix('.recover');tmp.write_text(json.dumps(restored,ensure_ascii=False,indent=2)+'\n');os.replace(tmp,statefile)
 def read():
  result=json.loads(statefile.read_text()) if statefile.exists() else initial
  if result['baseline']!=config['baseline']:raise ValueError('State baseline mismatch')
  return result
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def send(self,code,body,mime='application/json; charset=utf-8'):
   raw=body.encode() if isinstance(body,str) else body
   self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.end_headers()
   if self.command!='HEAD':self.wfile.write(raw)
  def trusted(self):
   host=self.headers.get('Host','');origin=self.headers.get('Origin')
   return host in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'} and (not origin or origin==f'http://{host}')
  def do_HEAD(self):self.do_GET()
  def do_GET(self):
   if not self.trusted():return self.send(403,'{}')
   uri=urllib.parse.urlsplit(self.path);path=uri.path;q=urllib.parse.parse_qs(uri.query)
   try:
    if path in ('/api/selection','/api/audio','/media'):unchanged()
    if path=='/api/selection':return self.send(200,json.dumps(words.locate(int(q['lo'][0]),int(q['hi'][0])),ensure_ascii=False))
    if path=='/api/audio':return self.send(200,words.audio(float(q['start'][0]),float(q['end'][0])),'audio/wav')
    if path=='/api/session':return self.send(200,json.dumps({'title':config['title'],'baseline':config['baseline'],'media_mime':mimetypes.guess_type(playback)[0],'text_baseline':config.get('text_baseline_sha256',config['transcript_sha256'])},ensure_ascii=False))
    if path in ('/','/audio-engine.js'):
     name='index.html' if path=='/' else 'audio-engine.js';return self.send(200,(session/name).read_bytes(),'text/html; charset=utf-8' if path=='/' else 'text/javascript; charset=utf-8')
    if path=='/api/transcript':return self.send(200,(session/'transcript.json').read_bytes())
    if path=='/api/state':
     with lock:return self.send(200,json.dumps(read(),ensure_ascii=False))
    if path=='/transcript.txt':return self.send(200,(session/'transcript.txt').read_bytes(),'text/plain; charset=utf-8')
    if path=='/media':
     size=playback.stat().st_size;start=0;end=size-1;partial=self.headers.get('Range')
     if partial:
      match=re.fullmatch(r'bytes=(\d*)-(\d*)',partial)
      if not match or not any(match.groups()):return self.send(416,'{}')
      if not match[1]:start=max(0,size-int(match[2]))
      else:start=int(match[1]);end=min(int(match[2]) if match[2] else end,end)
      if start>end or start>=size:
       self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return
     self.send_response(206 if partial else 200);self.send_header('Content-Type',mimetypes.guess_type(playback)[0] or 'application/octet-stream');self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1))
     if partial:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
     self.end_headers()
     if self.command=='HEAD':return
     try:
      with playback.open('rb') as f:
       f.seek(start);left=end-start+1
       while left:
        block=f.read(min(left,1024*1024))
        if not block:break
        self.wfile.write(block);left-=len(block)
     except (BrokenPipeError,ConnectionResetError):pass
     return
    self.send(404,'{}')
   except (ValueError,KeyError,FileNotFoundError) as e:self.send(400,json.dumps({'error':str(e)}))
  def do_POST(self):
   if not self.trusted():return self.send(403,'{}')
   if self.path!='/api/state':return self.send(404,'{}')
   try:
    unchanged();n=int(self.headers.get('Content-Length',0))
    if not 0<n<2000000:raise ValueError('Payload too large')
    payload=json.loads(self.rfile.read(n))
    if payload.get('baseline')!=config['baseline']:raise ValueError('Review baseline changed; refresh this page before editing')
    cuts=payload['cuts'];validate_cuts(cuts,duration)
    if not isinstance(payload['revision'],int) or isinstance(payload['revision'],bool):raise ValueError('Invalid revision')
    with lock:
     old=read()
     if payload['revision']!=old['revision']:return self.send(409,json.dumps(old,ensure_ascii=False))
     annotations=payload.get('annotations',old.get('annotations',{}));validate_annotations(annotations)
     new={**old,'annotations':annotations,'revision':old['revision']+1,'cuts':cuts,'updated_at':datetime.now(timezone.utc).isoformat()}
     event={'baseline':config['baseline'],'revision':new['revision'],'at':new['updated_at'],'action':str(payload.get('action','edit'))[:200],'before':old['cuts'],'after':cuts,'before_annotations':old.get('annotations',{}),'after_annotations':annotations}
     with events.open('a') as f:f.write(json.dumps(event,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
     tmp=statefile.with_suffix('.tmp')
     with tmp.open('w') as f:json.dump(new,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
     os.replace(tmp,statefile);self.send(200,json.dumps(new,ensure_ascii=False))
   except (ValueError,KeyError,TypeError) as e:self.send(400,json.dumps({'error':str(e)}))
 return Handler

def lock_session(session):
 data=session/'data';data.mkdir(parents=True,exist_ok=True);handle=(data/'.server.lock').open('a+b');handle.seek(0);handle.write(b'0');handle.flush();handle.seek(0)
 try:
  if os.name=='nt':
   import msvcrt;msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
  else:
   import fcntl;fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except OSError:handle.close();raise RuntimeError('This review session already has a running server. Reuse its URL instead of opening a second writer.')
 return handle
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8794);ap.add_argument('--session',type=Path,required=True);ap.add_argument('--open',action='store_true');a=ap.parse_args();session=a.session.resolve()
 held=lock_session(session)
 try:
  server=ThreadingHTTPServer(('127.0.0.1',a.port),create_handler(session));print(f'Local: http://127.0.0.1:{a.port}/',flush=True)
  if a.open:webbrowser.open(f'http://127.0.0.1:{a.port}/')
  try:server.serve_forever()
  except KeyboardInterrupt:pass
  finally:server.server_close()
 finally:held.close()
