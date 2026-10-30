"""Local speech recognition into timed text; ASR output is a working transcript."""
import argparse,json,subprocess,wave
from prepare_review import sha
from pathlib import Path

def transcribe(media,output,model,language='auto',whisper='whisper-cli'):
 media=Path(media).resolve(strict=True);output=Path(output).resolve();model=Path(model).resolve(strict=True)
 identity={'media':str(media),'sha256':sha(media),'language':language,'model':str(model)}
 if output.exists():
  if not (output/'asr-config.json').exists() or json.loads((output/'asr-config.json').read_text())!=identity:raise ValueError('ASR cache belongs to another input; choose a new session path')
 else:output.mkdir(parents=True)
 (output/'asr-config.json').write_text(json.dumps(identity,indent=2)+'\n')
 audio=output/'source-mono16k.wav'
 if not audio.exists():subprocess.run(['ffmpeg','-v','error','-i',str(media),'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(audio)],check=True)
 with wave.open(str(audio)) as f:duration=f.getnframes()/f.getframerate()
 probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_type,duration:format=duration','-of','json',str(media)]))
 video=next(s for s in probe['streams'] if s['codec_type']=='video');duration=min(duration,float(video.get('duration') if video.get('duration') not in (None,'N/A') else probe['format']['duration']))
 prefix=output/'recognition'
 prompt='粵語口語逐字轉錄。保留原話、語氣詞、重複和未完成句，不翻譯、不改寫；加入適當標點。' if language=='yue' else 'Verbatim transcription. Preserve spoken words, repetitions and fillers. Do not summarize or translate. Add punctuation.'
 if not prefix.with_suffix('.json').exists():
  with (output/'recognition.log').open('w') as log:subprocess.run([whisper,'-m',str(model),'-l',language,'--prompt',prompt,'-ojf','-osrt','-of',str(prefix),'-f',str(audio)],stdout=log,stderr=subprocess.STDOUT,check=True)
 raw=json.loads(prefix.with_suffix('.json').read_text());cues=[]
 for segment in raw['transcription']:
  a=max(0,segment['offsets']['from']/1000);b=min(duration,segment['offsets']['to']/1000);text=segment['text'].strip()
  if a<b and text:cues.append({'start':a,'end':b,'text':text})
 if not cues:raise ValueError('No speech recognized. Review the recording/language or supply a same-clock transcript.')
 result={'cues':cues,'status':'verbatim-target local ASR; raw model wording preserved; not human proofread','language':raw.get('result',{}).get('language',language),'source_audio_duration':duration,'task':'transcribe','translation':False,'raw_recognition_file':str(prefix.with_suffix('.json'))}
 target=output/'transcript.json';target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');return target
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--media',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--model',type=Path,required=True);ap.add_argument('--language',default='auto');a=ap.parse_args();print(transcribe(a.media,a.output,a.model,a.language))
