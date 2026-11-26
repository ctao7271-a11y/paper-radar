// Offline tests for apps-script/Code.gs with mocked Apps Script services.  Run: node tests/test_apps_script.js [path/to/Code.gs]
const fs=require('fs'),vm=require('vm'),path=require('path');
const SRC=fs.readFileSync(process.argv[2]||path.join(__dirname,'..','apps-script','Code.gs'),'utf8')
  .replace(/const TO = '[^']*'/,"const TO = 'to@example.invalid'").replace(/const TEST_TO = '[^']*'/,"const TEST_TO = 'me@example.invalid'");
function run(nowIso, digest, lastSent){
  const sent=[], props={lastSentId:lastSent}; const triggers=[];
  const ctx={console:{log(){},warn(){}}, Date:class extends Date{constructor(...a){super(...(a.length?a:[nowIso]))} static now(){return 1}},
    Utilities:{formatDate(d,tz,f){const s=new Date(d.getTime()+8*3600e3).toISOString();const wd=((new Date(d.getTime()+8*3600e3).getUTCDay()+6)%7)+1;
      return f==='u'?String(wd):f==='HH:mm'?s.slice(11,16):s.slice(0,10);}},
    UrlFetchApp:{fetch:()=>({getResponseCode:()=>digest?200:404,getContentText:()=>JSON.stringify(digest)})},
    MailApp:{sendEmail:(to,s,t,o)=>sent.push({to,s,html:!!o.htmlBody,name:o.name})},
    PropertiesService:{getScriptProperties:()=>({getProperty:k=>props[k],setProperty:(k,v)=>props[k]=v})},
    ScriptApp:{getProjectTriggers:()=>[{getHandlerFunction:()=>'sendDigest'}],deleteTrigger:()=>triggers.push('del'),
      newTrigger:()=>({timeBased:()=>({everyHours:(n)=>({create:()=>triggers.push('every'+n)})})})}};
  vm.createContext(ctx); vm.runInContext(SRC+';this.f={sendDigest,testSend,setup};',ctx);
  return {ctx,sent,props,triggers};
}
const D={date:'2026-11-27',id:'2026-11-27',subject:'S',html:'<p>',text:'t',count:3};
const ok=(c,m)=>{if(!c)throw new Error(m);console.log('ok',m)};
let r=run('2026-11-27T02:00:00Z',D,'2026-11-26'); r.ctx.f.sendDigest(); ok(r.sent.length===1&&r.sent[0].to==='to@example.invalid'&&r.sent[0].html&&r.props.lastSentId==='2026-11-27','Fri 10:00 sends once');
r.ctx.f.sendDigest(); ok(r.sent.length===1,'second run same id: no resend');
r=run('2026-11-27T01:00:00Z',D,''); r.ctx.f.sendDigest(); ok(r.sent.length===0,'09:00 before window: no send');
r=run('2026-11-27T05:30:00Z',D,''); r.ctx.f.sendDigest(); ok(r.sent.length===0,'13:30 after window: no send');
r=run('2026-11-28T02:00:00Z',{...D,date:'2026-11-28',id:'2026-11-28'},''); r.ctx.f.sendDigest(); ok(r.sent.length===0,'Saturday: no send');
r=run('2026-11-30T02:00:00Z',D,''); r.ctx.f.sendDigest(); ok(r.sent.length===0,'stale date (Mon, file from Fri): no send');
r=run('2026-11-27T02:00:00Z',null,''); r.ctx.f.sendDigest(); ok(r.sent.length===0,'HTTP 404: no send');
r=run('2026-11-27T02:00:00Z',D,''); r.ctx.f.testSend(); ok(r.sent[0].to==='me@example.invalid'&&r.sent[0].s==='[测试] S'&&!r.props.lastSentId,'testSend to self only, no state');
r=run('2026-11-27T02:00:00Z',D,''); r.ctx.f.setup(); r.ctx.f.sendDigest(); ok(r.triggers.join()==='del,every1'&&r.sent.length===0,'setup: replaces trigger, baselines current id');
