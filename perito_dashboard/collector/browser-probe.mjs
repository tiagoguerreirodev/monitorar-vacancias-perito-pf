// Ordinary anonymous frontend bootstrap, adapted from the two demonstrated runs.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import {spawn} from 'node:child_process';
import {randomBytes} from 'node:crypto';
const run=process.argv[2], chrome=process.argv[3];
if(!run || !path.isAbsolute(run) || !chrome || !path.isAbsolute(chrome)) throw new Error('Explicit absolute owned paths required');
fs.mkdirSync(run,{mode:0o700});
const profile=fs.mkdtempSync(path.join(run,'clean-profile-'));
const downloadDir=path.join(run,'downloads');fs.mkdirSync(downloadDir);
const entry='https://pep.paineis.gov.br/extensions/pep/index.html';
const token=randomBytes(32).toString('hex');
const out=fs.openSync(path.join(run,'chrome.log'),'w',0o600);
let browser,ws,server,ended=false,fatal=null,seq=0,session,version,logBytes=0;
const pending=new Map();
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const log=(kind,data={})=>{const line=JSON.stringify({utc:new Date().toISOString(),kind,...data}).replace(/(qlik-csrf-token=)[^&\"\s]+/g,'$1[REDACTED]')+'\n';logBytes+=Buffer.byteLength(line);if(logBytes<8_000_000)fs.appendFileSync(path.join(run,'trace.jsonl'),line);else void stop('bounded trace exceeded');};
const send=(method,params={},sid=session)=>new Promise((resolve,reject)=>{const id=++seq;const timer=setTimeout(()=>{pending.delete(id);reject(new Error('CDP timeout: '+method));},45000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params,...(sid?{sessionId:sid}:{})}));});
async function finish(reason){
 if(ended)return;ended=true;
 try{if(ws?.readyState===1)await Promise.race([send('Browser.close',{},null),pause(1500)]);}catch{}
 try{ws?.close();}catch{}
 if(browser && browser.exitCode===null){browser.kill('SIGTERM');await Promise.race([new Promise(r=>browser.once('exit',r)),pause(2000)]);if(browser.exitCode===null){browser.kill('SIGKILL');await Promise.race([new Promise(r=>browser.once('exit',r)),pause(2000)]);}}
 const stopped=!browser || browser.exitCode!==null || browser.signalCode!==null;
 if(stopped)fs.rmSync(profile,{recursive:true,force:true});
 fs.writeFileSync(path.join(run,'end.json'),JSON.stringify({reason,fatal,browser_stopped:stopped,clean_profile_removed:!fs.existsSync(profile)}));
 server?.close();process.exit(fatal || !stopped?2:0);
}
async function stop(reason){if(fatal)return;fatal=reason;fs.writeFileSync(path.join(run,'STOP.json'),JSON.stringify({reason}));await finish(reason);}
setTimeout(()=>stop('bounded collector deadline'),180_000).unref();
process.on('SIGTERM',()=>stop('owner termination'));process.on('SIGINT',()=>stop('owner interrupt'));
process.on('uncaughtException',()=>stop('uncaught collector failure'));
process.on('unhandledRejection',()=>stop('unhandled collector failure'));
function onEvent(m){const p=m.params||{};
 if(m.method==='Network.responseReceived' && p.response.url.startsWith('https://pep.paineis.gov.br/') && [401,403,429].includes(p.response.status))void stop('public HTTP denial');
 if(m.method==='Network.webSocketHandshakeResponseReceived'){log('ws_handshake',{status:p.response.status});if(p.response.status!==101)void stop('public WebSocket denied');}
 if(m.method==='Network.webSocketFrameReceived'){let x;try{x=JSON.parse(p.response.payloadData);}catch{}if(x?.error && /denied|not authorized|authentication|captcha|forbidden/i.test(JSON.stringify(x.error)))void stop('public Qlik access denied');}
 if(m.method==='Network.webSocketFrameError' && /403|401|429|forbidden|denied/i.test(p.errorMessage))void stop('public WebSocket error');
 if(m.method==='Browser.downloadWillBegin'||m.method==='Browser.downloadProgress')log(m.method,p);
}
browser=spawn(chrome,['--headless=new','--user-data-dir='+profile,'--remote-debugging-port=0','--remote-debugging-address=127.0.0.1','--no-first-run','--no-default-browser-check','about:blank'],{stdio:['ignore',out,out]});
browser.on('error',()=>stop('Chrome launch failed'));
let port;for(let i=0;i<150;i++){try{port=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];break;}catch{}await pause(100);}if(!port)throw new Error('Chrome did not expose owned DevTools port');
const v=await(await fetch('http://127.0.0.1:'+port+'/json/version',{signal:AbortSignal.timeout(5000)})).json();version=v.Browser;
ws=new WebSocket(v.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.addEventListener('open',r,{once:true});ws.addEventListener('error',j,{once:true});});
ws.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);if(p){clearTimeout(p.timer);pending.delete(m.id);m.error?p.reject(new Error('CDP command failed')):p.resolve(m.result);}}else onEvent(m);});
const targets=await send('Target.getTargets',{},null);const target=targets.targetInfos.find(x=>x.type==='page'&&x.url==='about:blank');if(!target)throw new Error('No owned blank target');
session=(await send('Target.attachToTarget',{targetId:target.targetId,flatten:true},null)).sessionId;
await send('Network.enable');await send('Page.enable');await send('Runtime.enable');
await send('Browser.setDownloadBehavior',{behavior:'allowAndName',downloadPath:downloadDir,eventsEnabled:true},null);
const cookies=await send('Storage.getCookies',{},null);log('isolation',{version,cookieCountBeforeNavigation:cookies.cookies.length});if(cookies.cookies.length)throw new Error('Unexpected preexisting cookies');
server=http.createServer(async(req,res)=>{res.setHeader('Content-Type','application/json');try{
 if(req.method!=='POST'||req.url!=='/'||req.headers.authorization!=='Bearer '+token)throw new Error('Invalid owned control request');
 let body='';for await(const c of req){body+=c;if(body.length>100_000)throw new Error('Control bound');}
 const c=JSON.parse(body);let result;
 if(c.op==='eval'&&typeof c.expression==='string'&&c.expression.length<=90_000){result=await send('Runtime.evaluate',{expression:c.expression,awaitPromise:true,returnByValue:true,userGesture:!!c.userGesture});}
 else if(c.op==='stop'){result={closing:true};setTimeout(()=>finish('owner complete'),20);}
 else throw new Error('Unknown owned operation');
 res.end(JSON.stringify(result));
 }catch{res.statusCode=500;res.end(JSON.stringify({error:'Owned collector command failed'}));}});
server.requestTimeout=60_000;server.headersTimeout=5000;
await new Promise(r=>server.listen(0,'127.0.0.1',r));fs.writeFileSync(path.join(run,'control.json'),JSON.stringify({port:server.address().port,token,version}),{mode:0o600});
await send('Page.navigate',{url:entry});
let busy=false;setInterval(async()=>{if(ended||busy)return;busy=true;try{const r=await send('Runtime.evaluate',{expression:`(()=>({url:location.href,title:document.title,text:document.body?.innerText?.slice(0,14000),challenge:!!document.querySelector('input[type="password"],iframe[src*="captcha"],.g-recaptcha')}))()`,returnByValue:true});const x=r.result?.value;if(x&&(x.challenge||!x.url.startsWith(entry)||/^(403 Forbidden|Access Denied|Forbidden|Just a moment|Verify you are human|Login|Sign in)/i.test(x.title)||/access denied|não autorizado|acesso negado|verifique que você é humano/i.test(x.text||'')))void stop('public UI authentication, CAPTCHA or denial');}catch{}finally{busy=false;}},1500).unref();
