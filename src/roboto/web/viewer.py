"""Viewer HTML do console (D25) — página única, tema escuro, marca Potter ⚡.

Lê os endpoints JSON com o bearer token (via JS). Cobre TODOS os endpoints do console:
execuções (+detalhe com sessões/conversa), interações pendentes, custos, e as ações
cancelar/retentar/terminal por execução.
"""

VIEWER_HTML = """<!doctype html>
<html lang="pt"><head><meta charset="utf-8"><title>Potter · console</title>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="alternate icon" href="/favicon.ico">
<link rel="manifest" href="/manifest.webmanifest">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0f1115">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<style>
 :root{--bg:#0f1115;--card:#171a21;--fg:#e8e9ec;--muted:#8a909c;--accent:#ffd21e;--line:#272b35}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--fg);
   font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
 header{display:flex;align-items:center;gap:.7rem;padding:1rem 1.4rem;
   border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg)}
 .logo{font-size:1.7rem;filter:drop-shadow(0 0 6px rgba(255,210,30,.5))}
 .brand{font-weight:800;font-size:1.3rem;letter-spacing:.4px}
 .brand small{color:var(--muted);font-weight:400;font-size:.9rem}
 main{padding:1.2rem 1.4rem;max-width:1060px;margin:0 auto}
 .bar{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center;margin-bottom:1rem}
 input{background:var(--card);border:1px solid var(--line);color:var(--fg);
   padding:.5rem .6rem;border-radius:8px;width:240px}
 button{background:var(--card);border:1px solid var(--line);color:var(--fg);
   padding:.5rem .8rem;border-radius:8px;cursor:pointer;font-size:13px}
 button:hover{border-color:var(--accent)}
 button.accent{background:var(--accent);color:#111;border-color:var(--accent);font-weight:700}
 .card{background:var(--card);border:1px solid var(--line);border-radius:12px;
   padding:1rem 1.1rem;margin:.6rem 0}
 h2{font-size:1.05rem;margin:.2rem 0 .6rem}
 h3{font-size:.95rem;margin:1rem 0 .3rem;color:var(--muted)}
 table{border-collapse:collapse;width:100%} td,th{border-bottom:1px solid var(--line);
   padding:.45rem .6rem;text-align:left;font-size:13px;vertical-align:top}
 th{color:var(--muted);font-weight:600} tr:hover td{background:#1c2029}
 .muted{color:var(--muted)} .tot{font-weight:700;margin:.4rem 0;color:var(--accent)}
 .mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
 .pill{padding:.12rem .5rem;border-radius:999px;font-size:11px;font-weight:700;
   border:1px solid var(--line);white-space:nowrap}
 .s-running,.s-verifying{color:#7fd1ff;border-color:#2b4a5e}
 .s-waiting{color:var(--accent);border-color:#5e4e18}
 .s-done{color:#8ae27f;border-color:#2f5e2a}
 .s-failed,.s-abandoned{color:#ff8a8a;border-color:#5e2a2a}
 .s-queued{color:var(--muted)} a{color:var(--accent)}
 .term{width:100%;height:70vh;border:1px solid var(--line);border-radius:12px;background:#000}
 button.on{background:var(--accent);color:#111;border-color:var(--accent);font-weight:700}
</style></head><body>
<header><span class="logo">⚡</span>
 <div class="brand">Potter <small>· console</small></div></header>
<main>
 <div class="bar">
  <input id="tok" placeholder="CONSOLE_TOKEN"><button onclick="save()">salvar token</button>
  <span id="s" class="muted"></span>
 </div>
 <div class="bar">
  <button class="accent" onclick="execs()">Execuções</button>
  <button onclick="load('/interactions','interactions')">Interações pendentes</button>
  <button onclick="costs()">Custos</button>
  <button id="auto" onclick="toggleAuto()">Auto-refresh: off</button>
  <button id="install" style="display:none" onclick="install()">Instalar app</button>
 </div>
 <div id="out" class="muted">Salve o token e escolha uma visão.</div>
</main>
<script>
let T = localStorage.getItem('rtok') || '';
document.getElementById('tok').value = T;
function save(){ T=document.getElementById('tok').value; localStorage.setItem('rtok',T);
 document.getElementById('s').textContent='ok ✓'; }
// PWA: registra o service worker e habilita o botão instalar quando o browser oferecer.
if('serviceWorker' in navigator){ navigator.serviceWorker.register('/sw.js').catch(()=>{}); }
let deferredPrompt=null;
window.addEventListener('beforeinstallprompt',e=>{ e.preventDefault(); deferredPrompt=e;
 document.getElementById('install').style.display='inline-block'; });
async function install(){ if(!deferredPrompt) return; deferredPrompt.prompt(); deferredPrompt=null;
 document.getElementById('install').style.display='none'; }
// Auto-refresh (torre de controle): repõe a lista de execuções a cada 4s enquanto ligado.
let AUTO=null;
function stopAuto(){ if(AUTO){ clearInterval(AUTO); AUTO=null;
 document.getElementById('auto').textContent='Auto-refresh: off';
 document.getElementById('auto').classList.remove('on'); } }
function toggleAuto(){ if(AUTO){ stopAuto(); return; }
 AUTO=setInterval(execs,4000); document.getElementById('auto').textContent='Auto-refresh: on';
 document.getElementById('auto').classList.add('on'); execs(); }
function esc(v){ return String(v==null?'':v)
 .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function pill(s){ return '<span class="pill s-'+esc(s)+'">'+esc(s)+'</span>'; }
async function get(p){ const r=await fetch(p,{headers:{Authorization:'Bearer '+T}});
 if(!r.ok) throw new Error(r.status); return r.json(); }
async function post(p){ const r=await fetch(p,{method:'POST',headers:{Authorization:'Bearer '+T}});
 if(!r.ok) throw new Error(r.status); return r.json(); }
function table(rows){ if(!rows||!rows.length) return '<p class=muted>vazio</p>';
 const k=Object.keys(rows[0]);
 let h='<table><tr>'+k.map(x=>'<th>'+x+'</th>').join('')+'</tr>';
 for(const o of rows){ h+='<tr>'+k.map(x=>'<td class=mono>'+esc(o[x]).slice(0,160)+'</td>').join('')
  +'</tr>'; } return h+'</table>'; }
function kv(o){ return '<table>'+Object.keys(o).map(k=>'<tr><th>'+k+'</th><td>'
 +(k==='state'?pill(o[k]):'<span class=mono>'+esc(o[k])+'</span>')+'</td></tr>').join('')
 +'</table>'; }
function err(o,e){ o.innerHTML='<p class=muted>erro '+e.message+' (token correto?)</p>'; }
async function load(p,key){ stopAuto(); const o=document.getElementById('out');
 try{ const d=await get(p); o.innerHTML='<div class=card>'+table(d[key])+'</div>'; }
 catch(e){ err(o,e); } }
async function execs(){ const o=document.getElementById('out');
 try{ const d=await get('/executions'); const rows=d.executions||[];
  if(!rows.length){ o.innerHTML='<p class=muted>sem execuções ainda</p>'; return; }
  let h='<div class=card><table><tr><th></th><th>id</th><th>issue</th><th>agente</th>'
   +'<th>estado</th><th>tent.</th></tr>';
  for(const r of rows){ h+='<tr><td><button onclick="detail('+r.id+')">ver</button></td>'
   +'<td class=mono>'+r.id+'</td><td class=mono>'+esc(r.issue_id)+'</td><td>'+esc(r.agent)
   +'</td><td>'+pill(r.state)+'</td><td class=mono>'+esc(r.attempt)+'</td></tr>'; }
  o.innerHTML=h+'</table></div>';
 }catch(e){ err(o,e); } }
async function detail(id){ stopAuto(); const o=document.getElementById('out');
 try{ const d=await get('/executions/'+id);
  let h='<button onclick="execs()">&larr; voltar</button>'
   +' <button onclick="term('+id+')">Terminal</button>'
   +' <button onclick="act('+id+',\\'/retry\\')">Retentar</button>'
   +' <button onclick="act('+id+',\\'/cancel\\')">Cancelar</button>';
  h+='<div class=card><h2>Execução #'+id+'</h2>'+kv(d.execution)+'</div>';
  h+='<div class=card><h3>Sessões do motor (Claude Code)</h3>'+table(d.sessions)+'</div>';
  h+='<div class=card><h3>Conversa / interações</h3>'+table(d.interactions)+'</div>';
  h+='<div id=termwrap></div>';
  o.innerHTML=h;
 }catch(e){ err(o,e); } }
async function act(id,path){ try{ await post('/executions/'+id+path); detail(id); }
 catch(e){ alert('erro '+e.message); } }
// Terminal embutido (Fatia 1): mostra a sessão viva (ttyd+tmux) num iframe, sem sair do app.
async function term(id){ try{ const d=await get('/executions/'+id+'/terminal');
  const w=document.getElementById('termwrap');
  if(!d.terminal_url){ const m='<p class=muted>'+esc(d.note||'terminal off')+'</p>';
   if(w) w.innerHTML=m; else alert(d.note||'terminal off'); return; }
  const u=esc(d.terminal_url);
  const html='<div class=card><h3>Terminal da sessão '
   +'<a href="'+u+'" target=_blank rel=noopener>↗ nova aba</a></h3>'
   +'<iframe class=term src="'+u+'"></iframe></div>';
  if(w) w.innerHTML=html; else document.getElementById('out').innerHTML+=html; }
 catch(e){ alert('erro '+e.message); } }
async function costs(){ stopAuto(); const o=document.getElementById('out');
 try{ const d=await get('/costs');
  o.innerHTML='<div class=card><div class=tot>Total: '+d.totals.tokens+' tokens · $'
   +Number(d.totals.cost_usd).toFixed(4)+'</div>'+table(d.calls)+'</div>'; }catch(e){ err(o,e); } }
</script></body></html>
"""
