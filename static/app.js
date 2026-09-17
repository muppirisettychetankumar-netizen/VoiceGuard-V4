const $=id=>document.getElementById(id);
let ws=null,stream=null,ctx=null,processor=null,source=null,running=false,fileBlob=null,history=[];
const HISTORY_KEY="voiceguard_history_v1";
function setConn(ok,text){$('connDot').className=ok?'on':'off';$('connText').textContent=text;$('engineStatus').textContent=ok?'Online / Ready':'Engine unavailable';}
function pct(v){const n=Number(v);return Number.isFinite(n)?Math.max(0,Math.min(100,Math.round(n*100)/100)):0}
function saveLocalHistory(d, source){
 try{
  const arr=JSON.parse(localStorage.getItem(HISTORY_KEY)||"[]");
  arr.unshift({timestamp:new Date().toISOString(),source:source||"scan",name:d.filename||"",verdict:d.verdict||"Unknown",level:d.level||"warning",ai_probability:Number(d.synthetic_probability||0),aasist_probability:Number(d.aasist_probability||0),for_probability:Number(d.for_probability||0),confidence:Number(d.confidence||0)});
  localStorage.setItem(HISTORY_KEY,JSON.stringify(arr.slice(0,250)));
 }catch(e){}
}
function fmtTime(v){try{return new Date(v).toLocaleString()}catch(e){return "—"}}
function renderHistory(items){
 const body=$("historyBody"); if(!body)return;
 if(!items.length){body.innerHTML='<tr><td colspan="8">No scan history yet.</td></tr>';return;}
 body.innerHTML=items.map(x=>`<tr><td>${fmtTime(x.timestamp)}</td><td>${String(x.source||'').replaceAll('<','&lt;')}</td><td>${String(x.name||'').replaceAll('<','&lt;')}</td><td><span class="history-pill ${x.level||'warning'}">${String(x.verdict||'Unknown')}</span></td><td>${Number(x.ai_probability||0).toFixed(1)}%</td><td>${Number(x.aasist_probability||0).toFixed(1)}%</td><td>${Number(x.for_probability||0).toFixed(1)}%</td><td>${Number(x.confidence||0).toFixed(1)}%</td></tr>`).join('');
}
async function loadHistory(){
 try{const r=await fetch('/api/history?limit=50');const d=await r.json();let items=d.items||[];
  const local=JSON.parse(localStorage.getItem(HISTORY_KEY)||"[]");
  if(!items.length && local.length) items=local;
  renderHistory(items); $('historyStatus').textContent=items.length?`${items.length} recent scan(s) · metadata only`:"No scans recorded yet";
 }catch(e){try{renderHistory(JSON.parse(localStorage.getItem(HISTORY_KEY)||"[]"));$('historyStatus').textContent='Browser history';}catch(_){} }
}
function addHistoryFromResult(d, source){saveLocalHistory(d,source);loadHistory();}
function render(d){
 if(!d||d.type!=='result')return;
 const ai=pct(d.synthetic_probability), h=pct(d.human_probability), conf=pct(d.confidence);
 const aas=pct(d.aasist_probability), fo=pct(d.for_probability);
 const fusion=pct(d.fusion_probability ?? d.synthetic_probability);
 $('verdict').textContent=d.verdict||'Analysis complete';
 $('prob').textContent=ai+'%'; $('human').textContent=h+'%'; $('ai').textContent=ai+'%'; $('confidence').textContent=conf+'%';
 $('humanBar').style.width=h+'%';$('aiBar').style.width=ai+'%';$('confidenceBar').style.width=conf+'%';
 $('gauge').style.setProperty('--p',ai+'%');
 $('aasistScore').textContent=aas+'%';$('forScore').textContent=fo+'%';$('fusionScore').textContent=fusion+'%';
 $('aasistBar').style.width=aas+'%';$('forBar').style.width=fo+'%';
 const level=d.level||'safe'; const label=level==='danger'?'HIGH RISK':level==='warning'?'REVIEW':'LOW RISK';
 $('state').textContent=label;$('state').className='risk-pill '+level;$('captureOrb').className='capture-orb '+level;
 $('resultTag').textContent=label; const rb=$('resultBanner');rb.className='result-banner '+level;$('resultBannerText').textContent=level==='danger'?'Synthetic-voice risk detected':level==='warning'?'Mixed signals — review recommended':'No strong synthetic signal detected';
 $('verdictKicker').textContent=level==='danger'?'SYNTHETIC SIGNAL DETECTED':level==='warning'?'MIXED / UNCERTAIN SIGNAL':'BONA-FIDE SIGNAL';
 $('verdictDetail').textContent=level==='danger'?'Multiple signals indicate characteristics associated with synthetic or spoofed speech.':level==='warning'?'The model signals are not sufficiently aligned. Treat this sample as suspicious and review it.':'The current signals are consistent with genuine speech.';
 $('explainTitle').textContent=level==='danger'?'Why VoiceGuard raised the alert':level==='warning'?'Why VoiceGuard marked this for review':'Why VoiceGuard marked this likely human';
 $('explainText').textContent=level==='danger'?'The calibrated FoR classifier crossed 55.5% AI-risk probability. AASIST remains visible as corroborating evidence.':level==='warning'?'The sample did not produce a reliable primary-model decision. Verify independently.':'The calibrated FoR classifier remained below the 55.5% AI-risk boundary, so VoiceGuard favors genuine speech.';
 $('pathA').textContent='AASIST '+aas+'%';$('pathF').textContent='FoR '+fo+'%';$('pathResult').textContent=label;
 const rec=$('recommendation'); rec.className='recommendation '+level;
 if(level==='danger'){ $('recommendationTitle').textContent='Do not trust the voice alone'; $('recommendationText').textContent='Treat this sample as a high-risk synthetic-voice signal. Verify the speaker using a trusted second channel before acting on requests.'; }
 else if(level==='warning'){ $('recommendationTitle').textContent='Verify before taking action'; $('recommendationText').textContent='The model signals are mixed or uncertain. Ask for an independent verification before sharing sensitive information or approving a request.'; }
 else { $('recommendationTitle').textContent='No strong synthetic signal detected'; $('recommendationText').textContent='The current evidence favors genuine speech, but a low-risk score is not proof of speaker identity.'; }
 $('verdict').parentElement.parentElement.classList.remove('scan-loading');
 $('stream').textContent='Live';$('stream').className='online-tag on';$('signalText').textContent='Streaming analysis active';
 $('activity').classList.add('active');setTimeout(()=>$('activity').classList.remove('active'),900);
}
function connect(){
 return Promise.resolve();
}
let toastTimer=null;
function showError(msg){
 const t=$('toast');$('toastTitle').textContent='Live engine';$('toastText').textContent=msg||'Something went wrong.';$('toastIcon').textContent='!';t.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.remove('show'),4200);
}
function setCaptureStatus(mode,text){const el=$('captureStatus'), wrap=el.parentElement;wrap.className='capture-status '+(mode||'');el.textContent=text;wrap.querySelector('small').textContent=mode==='live'?'Audio stream is active':mode==='warning'?'Connection needs attention':'Waiting for an audio source';}

function downsample(buf,inRate,outRate){if(inRate===outRate)return buf;const ratio=inRate/outRate,n=Math.round(buf.length/ratio),out=new Float32Array(n);for(let i=0;i<n;i++){const start=Math.floor(i*ratio),end=Math.min(Math.floor((i+1)*ratio),buf.length);let sum=0,c=0;for(let j=start;j<end;j++){sum+=buf[j];c++}out[i]=c?sum/c:0}return out}
function encodeWav(samples,sampleRate){
 const buffer=new ArrayBuffer(44+samples.length*2),view=new DataView(buffer);
 const write=(off,str)=>{for(let i=0;i<str.length;i++)view.setUint8(off+i,str.charCodeAt(i));};
 write(0,'RIFF');view.setUint32(4,36+samples.length*2,true);write(8,'WAVE');write(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,sampleRate,true);view.setUint32(28,sampleRate*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);write(36,'data');view.setUint32(40,samples.length*2,true);
 let o=44;for(let i=0;i<samples.length;i++){const v=Math.max(-1,Math.min(1,samples[i]));view.setInt16(o,v<0?v*32768:v*32767,true);o+=2;}return new Blob([buffer],{type:'audio/wav'});
}
let liveSending=false,liveLastSend=0,mediaRecorder=null,mediaChunks=[],captureTimer=null;
async function analyzeLiveWavBlob(blob,mode){
 if(liveSending)return;
 liveSending=true;
 try{
  const ab=await blob.arrayBuffer();
  const audioCtx=new (window.AudioContext||window.webkitAudioContext)();
  await audioCtx.resume();
  const decoded=await audioCtx.decodeAudioData(ab.slice(0));
  const channels=decoded.numberOfChannels;
  const n=decoded.length;
  const mono=new Float32Array(n);
  for(let c=0;c<channels;c++){
   const ch=decoded.getChannelData(c);
   for(let i=0;i<n;i++) mono[i]+=ch[i]/channels;
  }
  const wav=encodeWav(downsample(mono,decoded.sampleRate,16000),16000);
  await audioCtx.close();
  const fd=new FormData();fd.append('audio',wav,mode==='system'?'tab-live.wav':'mic-live.wav');
  const r=await fetch('/api/analyze',{method:'POST',body:fd});
  const d=await r.json();if(!r.ok)throw Error(d.error||'Live analysis failed');
  render({...d,type:'result'});addHistoryFromResult(d,mode==='system'?'tab-live':'mic-live');
 }catch(e){showError(e.message||'Could not analyze live audio.');}
 finally{liveSending=false;liveLastSend=Date.now();}
}
function chooseRecorderMime(){
 const types=['audio/webm;codecs=opus','audio/webm','audio/mp4'];
 for(const t of types)if(window.MediaRecorder&&MediaRecorder.isTypeSupported&&MediaRecorder.isTypeSupported(t))return t;
 return '';
}
async function startCapture(mode){
 if(running)return;
 try{
  if(mode==='system' && /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)){
   throw new Error('Tab/call audio capture is supported on desktop Chrome/Edge. On Android, use Microphone mode.');
  }

  let opts;
  if(mode==='system'){
   if(!navigator.mediaDevices?.getDisplayMedia)throw new Error('Tab audio capture is not supported. Use desktop Chrome or Edge.');
   opts=await navigator.mediaDevices.getDisplayMedia({video:true,audio:true});
  }else{
   if(!navigator.mediaDevices?.getUserMedia)throw new Error('Microphone access is not supported by this browser.');
   opts=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:false,noiseSuppression:false,autoGainControl:false}});
  }

  stream=opts;
  const track=stream.getAudioTracks()[0];
  if(!track)throw new Error(mode==='system'?'No tab audio track was captured. Select a tab and enable Share tab audio.':'No microphone audio track was captured. Check microphone permission.');
  if(!window.MediaRecorder)throw new Error('This browser does not support live audio recording. Try Chrome or Edge.');

  running=true;window.__vgMode=mode;
  startRecorderCycle(mode);

  $('micBtn').disabled=true;$('systemBtn').disabled=true;$('stopBtn').disabled=false;
  $('captureOrb').classList.add('live');
  $('modeText').textContent=mode==='system'?'Call/tab audio is being monitored':'Microphone is being monitored';
  setCaptureStatus('live',mode==='system'?'Monitoring call/tab':'Monitoring microphone');
  $('stream').textContent='Live';$('stream').className='online-tag on';
  setConn(true,'Capturing live audio');
  track.onended=stopCapture;
 }catch(e){stopCapture();showError(e.message||'Could not start audio capture.');}
}

function startRecorderCycle(mode){
 if(!running||!stream)return;
 try{
  const audioOnly=new MediaStream(stream.getAudioTracks());
  const mime=chooseRecorderMime();
  const rec=mime?new MediaRecorder(audioOnly,{mimeType:mime}):new MediaRecorder(audioOnly);
  mediaRecorder=rec;
  mediaChunks=[];
  rec.ondataavailable=e=>{if(e.data&&e.data.size)mediaChunks.push(e.data);};
  rec.onerror=e=>{if(running)showError('Browser audio recorder error. Please allow microphone/audio capture and try again.');};
  rec.onstop=async()=>{
   const chunks=mediaChunks;
   mediaChunks=[];
   const blob=new Blob(chunks,{type:rec.mimeType||mime||'audio/webm'});
   if(mediaRecorder===rec)mediaRecorder=null;
   if(running && blob.size){
    await analyzeLiveWavBlob(blob,mode);
   }
   if(running)startRecorderCycle(mode);
  };
  rec.start();
  captureTimer=setTimeout(()=>{
   if(rec.state==='recording')rec.stop();
  },4500);
 }catch(e){
  if(running)showError(e.message||'Could not start live audio recorder.');
 }
}
function stopCapture(){
 running=false;if(captureTimer){clearTimeout(captureTimer);captureTimer=null;}
 if(mediaRecorder){try{if(mediaRecorder.state!=='inactive')mediaRecorder.stop()}catch(e){}mediaRecorder=null;}
 if(stream)stream.getTracks().forEach(t=>t.stop());
 ws=null;processor=source=ctx=stream=null;mediaChunks=[];$('micBtn').disabled=false;$('systemBtn').disabled=false;$('stopBtn').disabled=true;$('captureOrb').className='capture-orb';$('modeText').textContent='Ready to monitor';setCaptureStatus('', 'Ready');$('stream').textContent='Offline';$('stream').className='online-tag';$('signalText').textContent='Awaiting audio';setConn(false,'Engine idle');
}
$('micBtn').onclick=()=>startCapture('mic');$('systemBtn').onclick=()=>startCapture('system');$('stopBtn').onclick=stopCapture;
// Android browsers generally cannot expose another app's call/tab audio to a web page.
if(/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)){$('systemBtn').disabled=true;$('systemBtn').title='Tab/call audio capture requires desktop Chrome/Edge';}
$('micBtn').onclick=()=>startCapture('mic');$('systemBtn').onclick=()=>startCapture('system');$('stopBtn').onclick=stopCapture;
$('file').onchange=e=>selectFile(e.target.files[0]);
function selectFile(f){
 fileBlob=f||null;if(fileBlob && !((fileBlob.type||'').toLowerCase()==='audio/wav' || /\.wav$/i.test(fileBlob.name))){fileBlob=null;showError('Please choose a WAV audio file.');}$('uploadBtn').disabled=!fileBlob;
 if(fileBlob){$('fileName').textContent=fileBlob.name;$('fileMeta').textContent=`${(fileBlob.size/1024).toFixed(1)} KB · WAV sample`;$('fileState').textContent='READY';$('fileState').style.color='var(--mint)';}
 else{$('fileName').textContent='No file selected';$('fileMeta').textContent='Choose a sample to begin';$('fileState').textContent='—';}
}
['dragenter','dragover'].forEach(ev=>$('dropzone').addEventListener(ev,e=>{e.preventDefault();$('dropzone').classList.add('drag')}));
['dragleave','drop'].forEach(ev=>$('dropzone').addEventListener(ev,e=>{e.preventDefault();$('dropzone').classList.remove('drag')}));
$('dropzone').addEventListener('drop',e=>{if(e.dataTransfer.files[0])selectFile(e.dataTransfer.files[0])});
$('uploadBtn').onclick=async()=>{
 if(!fileBlob)return;
 $('uploadBtn').disabled=true;$('uploadBtn').textContent='Analyzing…';$('fileState').textContent='SCANNING';$('fileState').style.color='var(--amber)';
 $('resultTag').textContent='ANALYZING';$('verdict').textContent='Analyzing voice…';$('verdict').parentElement.parentElement.classList.add('scan-loading');$('verdictKicker').textContent='PROCESSING';$('verdictDetail').textContent='Preprocessing audio and running the detection pipeline.';
 try{const fd=new FormData();fd.append('audio',fileBlob,fileBlob.name);const r=await fetch('/api/analyze',{method:'POST',body:fd});const d=await r.json();if(!r.ok)throw Error(d.error||'Analysis failed');render({...d,type:'result'}); addHistoryFromResult(d,'upload'); $('fileState').textContent='COMPLETE';$('fileState').style.color='var(--mint)';}
 catch(e){$('fileState').textContent='ERROR';$('fileState').style.color='var(--red)';showError(e.message)}
 finally{$('uploadBtn').disabled=!fileBlob;$('uploadBtn').innerHTML='Analyze sample <span>→</span>'}
};
$('refreshHistory').onclick=loadHistory; $('clearHistory').onclick=async()=>{if(!confirm('Clear server scan history and browser history?'))return; try{await fetch('/api/history',{method:'DELETE'});}catch(e){} localStorage.removeItem(HISTORY_KEY); loadHistory();}; loadHistory();
fetch('/api/model-status').then(r=>r.json()).then(d=>{setConn(!!d.ready,d.ready?'AI model ready':'Model loading');if(!d.ready)showError('The AI model is still loading. Try again in a moment.');}).catch(()=>setConn(false,'Engine unavailable'));
const activity=$('activity');for(let i=0;i<52;i++){const s=document.createElement('span');activity.appendChild(s)}
