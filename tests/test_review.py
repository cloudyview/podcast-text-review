import sys,json,unittest,tempfile,subprocess,shutil,threading,urllib.request,urllib.error,os,io,hashlib
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from prepare_review import prepare,timed_rows
from serve_review import create_handler,validate_cuts,lock_session
from export_decisions import export
from word_support import Words
from dependencies import install_plan,download_model
from render_review import render_video
from format_transcript import format_rows,lexical
from transcribe_mlx import rows_from_alignment

class PureTests(unittest.TestCase):
 def test_install_plans(self):
  which=lambda name:'/bin/'+name
  self.assertEqual(install_plan('ffmpeg','Darwin',which),[['brew','install','ffmpeg']])
  self.assertIn('Gyan.FFmpeg',install_plan('ffmpeg','Windows',which)[0])
  self.assertEqual(install_plan('ffmpeg','Linux',which)[0][0],'apt-get')
  self.assertEqual(install_plan('whisper','Windows',which),[])
 def test_verbatim_format_and_speakers(self):
  original=[{'cue_id':'a','start_seconds':0,'end_seconds':2,'text':'我哋唔係咁講喎'},{'cue_id':'b','start_seconds':2,'end_seconds':4,'text':'係呀係呀'}]
  formatted=format_rows(original,[{'start':0,'end':2,'speaker':'A'},{'start':2,'end':4,'speaker':'B'}])
  self.assertEqual([r['speaker'] for r in formatted],['A','B'])
  self.assertEqual([r['raw_text'] for r in formatted],[r['text'] for r in original])
  self.assertEqual([lexical(r['text']) for r in formatted],[lexical(r['text']) for r in original])
  self.assertEqual(formatted[0]['text'],original[0]['text']) # no punctuation inside continuous ASR chunk boundaries
 def test_aligned_verbatim_characters(self):
  rows=rows_from_alignment('我哋唔係咁講喎。',[{'text':c,'start':i*.2,'end':(i+1)*.2} for i,c in enumerate('我哋唔係咁講喎')],0,0,3,[{'start':0,'end':3,'speaker':'A'}])
  self.assertEqual(''.join(r['text'] for r in rows),'我哋唔係咁講喎。')
  self.assertEqual(rows[0]['speaker'],'A')
  self.assertEqual(len(rows[0]['word_spans']),7)
 def test_validation(self):
  for value in [float('nan'),float('inf'),True,-1,'1']:
   with self.assertRaises(ValueError):validate_cuts([{'start':value,'end':3}],8)
  validate_cuts([{'start':1,'end':2}],8)
 def test_zero_duration_alignment_keeps_words(self):
  text='我又又講。';items=[{'text':'我','start':0,'end':.3},{'text':'又','start':.3,'end':.3},{'text':'又','start':.3,'end':.3},{'text':'講','start':.4,'end':.7}]
  rows=rows_from_alignment(text,items,0,0,1,[{'start':0,'end':1,'speaker':'A'}]);self.assertEqual(''.join(r['text'] for r in rows),text)
  self.assertEqual(rows[0]['speaker'],'A')
 def test_verified_model_download(self):
  content=b'synthetic-model';metadata={'sha':'vendor-commit','siblings':[{'rfilename':'ggml-base.bin','lfs':{'sha256':hashlib.sha256(content).hexdigest()}}]}
  with tempfile.TemporaryDirectory() as tmp,patch('dependencies.urllib.request.urlopen',side_effect=[io.BytesIO(json.dumps(metadata).encode()),io.BytesIO(content)]):
   model=download_model('base',Path(tmp));self.assertEqual(model.read_bytes(),content)
 def test_srt(self):
  with tempfile.TemporaryDirectory() as tmp:
   f=Path(tmp)/'s.srt';f.write_text('1\n00:00:00,000 --> 00:00:02,000\nHello.\n\n2\n00:00:02,000 --> 00:00:03,000\nWorld.\n')
   self.assertEqual(len(timed_rows(f)),2)

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg integration tools required')
class MediaTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.media=self.root/'fixture.mp4'
  subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=320x180:r=30:d=8','-f','lavfi','-i','sine=frequency=440:sample_rate=24000','-t','8','-c:v','libx264','-c:a','aac',str(self.media)],check=True)
  self.sub=self.root/'s.json';self.sub.write_text(json.dumps({'cues':[{'start':0,'end':3,'text':'今天好'},{'start':3,'end':8,'text':'第二句'}]}));self.session=self.root/'review';prepare(self.media,self.sub,self.session,'Synthetic demo')
 def tearDown(self):self.tmp.cleanup()
 def server(self):
  server=ThreadingHTTPServer(('127.0.0.1',0),create_handler(self.session));threading.Thread(target=server.serve_forever,daemon=True).start();return server,f'http://127.0.0.1:{server.server_port}'
 def post(self,url,body,**headers):
  body={'baseline':json.loads((self.session/'config.json').read_text())['baseline'],**body}
  req=urllib.request.Request(url+'/api/state',data=json.dumps(body).encode(),headers={'Content-Type':'application/json',**headers})
  try:
   with urllib.request.urlopen(req) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:return e.code,None
 def test_http_save_restore_range_and_security(self):
  server,url=self.server()
  try:
   with urllib.request.urlopen(urllib.request.Request(url+'/media',headers={'Range':'bytes=0-99'})) as r:self.assertEqual((r.status,len(r.read())),(206,100))
   with urllib.request.urlopen(urllib.request.Request(url+'/media',headers={'Range':'bytes=-10'})) as r:self.assertEqual(len(r.read()),10)
   with urllib.request.urlopen(urllib.request.Request(url+'/media',method='HEAD')) as r:self.assertEqual(r.read(),b'')
   self.assertEqual(self.post(url,{'revision':0,'cuts':[{'start':1,'end':2,'selected_text':'Example','char_in':0,'char_out':1}]})[0],200)
   self.assertEqual(self.post(url,{'revision':0,'cuts':[]})[0],409)
   self.assertEqual(self.post(url,{'baseline':'previous-text','revision':1,'cuts':[]})[0],400)
   self.assertEqual(self.post(url,{'revision':1,'cuts':[]},Origin='https://example.invalid')[0],403)
   self.assertEqual(self.post(url,{'revision':1,'cuts':[{'start':0,'end':9}]})[0],400)
  finally:server.shutdown();server.server_close()
  server,url=self.server()
  try:self.assertEqual(json.load(urllib.request.urlopen(url+'/api/state'))['cuts'][0]['selected_text'],'Example')
  finally:server.shutdown();server.server_close()
 def test_committed_event_recovery(self):
  data=self.session/'data';data.mkdir();c=json.loads((self.session/'config.json').read_text());event={'baseline':c['baseline'],'revision':1,'before':[],'after':[{'start':1,'end':2}],'at':'test','action':'test'}
  (data/'删改过程.jsonl').write_text(json.dumps(event)+'\n');create_handler(self.session);self.assertEqual(json.loads((data/'删改状态.json').read_text())['revision'],1)
 def test_interrupted_log_and_speaker_annotation(self):
  data=self.session/'data';data.mkdir();(data/'删改过程.jsonl').write_bytes(b'{"interrupted')
  server,url=self.server()
  try:
   self.assertEqual(self.post(url,{'revision':0,'cuts':[],'annotations':{'speaker_overrides':{'cue-00001':'Speaker B'}}})[0],200)
  finally:server.shutdown();server.server_close()
  (data/'删改状态.json').unlink();create_handler(self.session)
  self.assertEqual(json.loads((data/'删改状态.json').read_text())['annotations']['speaker_overrides']['cue-00001'],'Speaker B')
  self.assertTrue(list(data.glob('interrupted-log-*.bin')))
 def test_lock(self):
  lock=lock_session(self.session)
  try:
   with self.assertRaises(RuntimeError):lock_session(self.session)
  finally:lock.close()
 def test_words_no_fabricated_character_times(self):
  cache=self.session/'align';cache.mkdir();f=cache/'win-00000.wav';(cache/'windows.json').write_text(json.dumps([{'file':str(f),'offset':0,'end':8}]))
  Path(str(f)+'.json').write_text(json.dumps({'transcription':[{'tokens':[{'text':'今天','t_dtw':100},{'text':'好','t_dtw':220},{'text':'第二句','t_dtw':450}]}]}))
  rows=json.loads((self.session/'transcript.json').read_text())['rows'];w=Words(self.media,rows,cache,8);one=w.locate(0,0);word=w.locate(0,1)
  self.assertEqual(one['alignment'],'partial_token_context');self.assertEqual((one['start'],one['end']),(word['start'],word['end']));self.assertTrue(w.audio(.5,1.5).startswith(b'RIFF'))
 def test_export_and_render(self):
  data=self.session/'data';data.mkdir();config=json.loads((self.session/'config.json').read_text());(data/'删改状态.json').write_text(json.dumps({'baseline':config['baseline'],'revision':1,'cuts':[{'start':1,'end':2},{'start':1.5,'end':4}]}));decision=export(self.session);self.assertEqual(decision['kept_duration'],5)
  output=self.root/'rendered.mp4';render_video(self.session,output);duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(output)]));self.assertLess(abs(duration-5),.1)
  with self.assertRaises(FileExistsError):render_video(self.session,output)
 def test_overwrite_and_changed_baseline(self):
  with self.assertRaises(FileExistsError):prepare(self.media,self.sub,self.session,'overwrite')
  (self.session/'transcript.json').write_text('{}')
  with self.assertRaises(ValueError):create_handler(self.session)
 def test_changed_media(self):
  with self.media.open('ab') as f:f.write(b'changed')
  with self.assertRaises(ValueError):create_handler(self.session)
 def test_proxy(self):
  config=prepare(self.media,self.sub,self.root/'proxy','Proxy',proxy=True);self.assertTrue(Path(config['playback_media']).exists())

if __name__=='__main__':unittest.main()
