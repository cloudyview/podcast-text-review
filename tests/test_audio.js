'use strict';
const assert=require('node:assert/strict');
const Audio=require('../assets/audio-engine.js');
(async()=>{
 const source=Float32Array.from([0,.1,.2,.3,.4,.5,.6,.7]),raw=Audio.makeWav(source,4),decoded=Audio.parseWav(raw);
 assert.equal(decoded.sampleRate,4);assert.equal(decoded.samples.length,8);
 const joined=Audio.sliceRanges(decoded.samples,4,0,[[0,.5],[1,2]]);assert.equal(joined.length,6);assert.ok(Math.abs(joined[2]-.4)<.0001);
 assert.throws(()=>Audio.sliceRanges(source,4,0,[[-1,1]]));
 let played=0;const element={pause(){},async play(){played++},hidden:true};
 const engine=new Audio({forceNative:true,element,fetch:async()=>({ok:true,arrayBuffer:async()=>raw.slice(0)})});
 await engine.load(0,2);assert.equal(await engine.play([[0,.5],[1,2]]),'html-audio');assert.equal(played,1);assert.equal(element.hidden,false);
 engine.stop();assert.equal(engine.objectUrl,null);
 element.play=async()=>{throw Error('autoplay blocked')};await engine.load(0,2);assert.equal(await engine.play([[0,1]]),'html-audio-needs-click');engine.stop();
 const stuck=new Audio({element,fetch:async()=>({ok:true,arrayBuffer:async()=>raw.slice(0)})});await stuck.load(0,2);
 stuck.buffer={};stuck.context={resume:()=>new Promise(()=>{}),state:'suspended'};
 assert.equal(await stuck.play([[0,1]]),'html-audio-needs-click');stuck.stop();
 assert.throws(()=>Audio.parseWav(new ArrayBuffer(44)));
 console.log('PASS PCM decoding, sample slicing, WAV encoding, no-WebAudio native fallback, autoplay recovery');
})().catch(e=>{console.error(e);process.exit(1)});
