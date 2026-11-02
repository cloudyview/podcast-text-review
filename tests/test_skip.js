'use strict';
const assert=require('node:assert/strict');
const Audio=require('../assets/audio-engine.js');
class Media {
 constructor(t){this.currentTime=t;this.paused=true;this.ended=false;this.seeking=false;this.muted=false;this.playbackRate=1;this.events={};}
 addEventListener(n,f){(this.events[n]||=[]).push(f)}
 removeEventListener(n,f){this.events[n]=this.events[n].filter(x=>x!==f)}
 emit(n){for(const f of this.events[n]||[])f()}
}
const cuts=[{start:2,end:4},{start:3,end:6},{start:6,end:8},{start:10,end:11}];
const m=new Media(3);let enabled=true;const c=Audio.attachSkip(m,{getCuts:()=>cuts,isEnabled:()=>enabled});
m.emit('timeupdate');assert.equal(m.currentTime,3,'paused word selection may inspect source frames');
m.paused=false;m.emit('play');assert.equal(m.currentTime,8,'native playback must skip the complete merged deletion');
m.currentTime=10.5;m.seeking=true;m.emit('seeking');assert.equal(m.currentTime,11);assert.equal(m.muted,true,'mute while seeking across a deleted range');
m.seeking=false;m.emit('seeked');assert.equal(m.muted,false,'restore the original mute setting');
enabled=false;m.currentTime=3;m.emit('play');assert.equal(m.currentTime,3,'explicit original-audio mode is allowed');
enabled=true;c.refresh();assert.equal(m.currentTime,8,'turning skip back on takes effect immediately');
m.muted=true;m.currentTime=10.2;m.seeking=true;m.emit('seeking');m.seeking=false;m.emit('seeked');assert.equal(m.muted,true,'preserve user mute preference');
c.destroy();assert.ok(Object.values(m.events).every(x=>x.length===0));
console.log('PASS main-video playback, seeking, merged deletions, skip toggle and mute restoration');
