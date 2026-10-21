"""Viewer HTML do console (D25) — página leve que lê os endpoints JSON com o bearer token.

Sem framework: um arquivo só, servido em `/`. Os dados exigem o `CONSOLE_TOKEN` (via JS).
Lista execuções/interações/custos e abre o DETALHE de uma execução (sessões + conversa).
"""

VIEWER_HTML = """<!doctype html>
<html lang="pt"><head><meta charset="utf-8"><title>roboto · console</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 body{font-family:system-ui,sans-serif;margin:1.5rem;max-width:1000px;color:#222}
 h1{font-size:1.3rem} h2{font-size:1.1rem;margin:.8rem 0 .2rem}
 h3{font-size:1rem;margin:.8rem 0 .2rem}
 table{border-collapse:collapse;width:100%;margin-top:.4rem}
 td,th{border:1px solid #ddd;padding:4px 8px;font-size:13px;text-align:left}
 td,th{vertical-align:top}
 th{background:#f5f5f5} button{margin:2px;padding:6px 10px;cursor:pointer}
 input{padding:6px;width:280px} .muted{color:#888} .tot{font-weight:bold;margin:.5rem 0}
</style></head><body>
<h1>🤖 roboto · console</h1>
<p>Token: <input id="tok" placeholder="CONSOLE_TOKEN"> <button onclick="save()">salvar</button>
 <span id="s" class="muted"></span></p>
<p>
 <button onclick="execs()">Execuções</button>
 <button onclick="load('/interactions','interactions')">Interações pendentes</button>
 <button onclick="costs()">Custos (tokens)</button>
</p>
<div id="out" class="muted">Salve o token e escolha uma visão.</div>
<script>
let T = localStorage.getItem('rtok') || '';
document.getElementById('tok').value = T;
function save(){ T = document.getElementById('tok').value; localStorage.setItem('rtok', T);
 document.getElementById('s').textContent = 'ok'; }
async function get(p){ const r = await fetch(p, {headers:{Authorization:'Bearer '+T}});
 if(!r.ok) throw new Error(r.status); return r.json(); }
function esc(v){ return String(v==null?'':v); }
function table(rows){ if(!rows || !rows.length) return '<p class=muted>vazio</p>';
 const k = Object.keys(rows[0]);
 const head = '<table><tr>'+k.map(x=>'<th>'+x+'</th>').join('')+'</tr>';
 const cell = (o,x)=>'<td>'+esc(o[x]).slice(0,120)+'</td>';
 const body = rows.map(o=>'<tr>'+k.map(x=>cell(o,x)).join('')+'</tr>');
 return head + body.join('') + '</table>'; }
function kv(o){ return '<table>'+Object.keys(o).map(k=>
 '<tr><th>'+k+'</th><td>'+esc(o[k])+'</td></tr>').join('')+'</table>'; }
async function load(p,key){ const o=document.getElementById('out');
 try{ const d = await get(p); o.innerHTML = table(d[key]); }
 catch(e){ o.innerHTML = '<p class=muted>erro '+e.message+' (token correto?)</p>'; } }
async function execs(){ const o=document.getElementById('out');
 try{ const d = await get('/executions'); const rows = d.executions||[];
  if(!rows.length){ o.innerHTML='<p class=muted>sem execuções</p>'; return; }
  const k = Object.keys(rows[0]);
  let h = '<table><tr><th></th>'+k.map(x=>'<th>'+x+'</th>').join('')+'</tr>';
  for(const r of rows){ h += '<tr><td><button onclick="detail('+r.id+')">ver</button></td>'
   + k.map(x=>'<td>'+esc(r[x]).slice(0,80)+'</td>').join('') + '</tr>'; }
  o.innerHTML = h + '</table>';
 } catch(e){ o.innerHTML = '<p class=muted>erro '+e.message+'</p>'; } }
async function detail(id){ const o=document.getElementById('out');
 try{ const d = await get('/executions/'+id);
  let h = '<button onclick="execs()">&larr; voltar</button>';
  h += '<h2>Execução #'+id+'</h2>' + kv(d.execution);
  h += '<h3>Sessões do motor (Claude Code)</h3>' + table(d.sessions);
  h += '<h3>Conversa / interações</h3>' + table(d.interactions);
  o.innerHTML = h;
 } catch(e){ o.innerHTML = '<p class=muted>erro '+e.message+'</p>'; } }
async function costs(){ const o=document.getElementById('out');
 try{ const d = await get('/costs');
  o.innerHTML = '<div class=tot>Total: '+d.totals.tokens+' tokens · $'+
   Number(d.totals.cost_usd).toFixed(4)+'</div>' + table(d.calls); }
 catch(e){ o.innerHTML = '<p class=muted>erro '+e.message+'</p>'; } }
</script></body></html>
"""
