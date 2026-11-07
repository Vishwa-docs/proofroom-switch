const $ = id => document.getElementById(id);
let state = null;
const rules = [
  ['five_cases_replayed', 'Five checkout cases replayed'],
  ['zero_candidate_errors', 'Zero errors in candidate'],
  ['no_healthy_regression', 'No healthy response regression'],
  ['candidate_allowlisted', 'Release in allowlist'],
  ['no_schema_change', 'No schema change'],
];
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function time(s){return s?new Date(s).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}):'';}
function render(){
  if(!state)return;
  const phase=state.phase, proof=state.proof, mode=state.switch.demo_mode;
  $('room-name').textContent=state.switch.room_name;
  $('incident-number').textContent=state.incident_id?.replace('INC-','')||'—';
  $('phase-seal').textContent=phase.replaceAll('_',' ').toUpperCase();
  $('active-release').textContent=state.active_version;
  $('error-count').textContent=state.baseline.length?`${state.baseline.filter(x=>!x.ok).length} → ${proof?.canary_errors??'—'}`:'—';
  $('canary-state').textContent=proof?'PASSED':'NOT RUN';
  $('decision-state').textContent=state.decision?'SIGNED':phase==='awaiting_approval'?'AWAITING HUMAN':'PENDING';
  $('from-version').textContent=proof?.from||'v2.14.0';
  $('digest').textContent=proof?.sha256||'Awaiting canary replay';
  const connected=Object.values(state.switch.connected).every(Boolean)&&state.switch.configured;
  $('switch-status').textContent=connected?'Switch room live':state.switch.configured?'Connecting to Switch':'Local replay';
  $('switch-detail').textContent=connected?'Three agents are listening':state.switch.configured?'Agent protocol reconnecting':'Switch bridge not configured';
  $('switch-dot').classList.toggle('connected',connected);
  $('rule-list').innerHTML=rules.map(([key,label],i)=>`<div class="rule ${proof?(proof.checks[key]?'pass':'fail'):''}"><span>${String(i+1).padStart(2,'0')} &nbsp; ${label}</span><span class="rule-state">${proof?(proof.checks[key]?'✓ PASS':'✕ FAIL'):'— WAITING'}</span></div>`).join('');
  const events=state.events;
  $('messages').innerHTML=events.length?events.map(e=>{
    const type=e.speaker==='Signal Agent'?'signal':e.speaker==='Release Agent'?'release':'investigator';
    return `<div class="message"><span class="avatar ${type}">${type==='release'?'R':type==='signal'?'S':'C'}</span><div style="min-width:0;flex:1"><div class="message-top"><span class="message-name">${esc(e.speaker)}</span><span class="message-role">${type==='investigator'?'CODEX AI':'SWITCH AGENT'}</span><span class="message-time">${time(e.at)}</span></div><div class="message-body">${esc(e.body)}</div></div></div>`;
  }).join(''):'<div class="empty-message"><div><span>⌁</span><p>The room is quiet. Trigger the checkout failure to begin an evidence-backed handoff.</p></div></div>';
  $('messages').scrollTop=$('messages').scrollHeight;
  const actions=[];
  if(mode){
    if(phase==='idle')actions.push(['Inject checkout failure','/api/trigger',{}]);
    if(phase==='investigating')actions.push(['Run canary replay','/api/prepare',{}]);
    if(phase==='awaiting_approval')actions.push(['Simulate human approval','/api/demo/approve',{sha256:proof.sha256}]);
    if(phase==='recovered')actions.push(['Reset replay','/api/reset',{}]);
  }
  $('actions').innerHTML=actions.map(([label,path,payload],i)=>`<button class="${i?'secondary':'primary'}-btn" data-path="${path}" data-payload='${JSON.stringify(payload)}'>${esc(label)} <span aria-hidden="true">↗</span></button>`).join('')||`<span class="room-caption">In Switch, send <b>INVESTIGATE</b>, then <b>PREPARE</b>, then <b>APPROVE &lt;evidence digest&gt;</b>.</span>`;
  $('room-caption').textContent=mode?'Demo controls inject local room events. Production approval requires the configured Switch participant and exact digest.':'Actions originate in the Switch room; this view displays the shared evidence and outcome.';
  $('audit-content').innerHTML=state.decision?`<span>✓ ${esc(state.decision.action)} · ${esc(state.decision.actor_id)}</span><small>${esc(state.decision.evidence_sha256.slice(0,16))}… · audit chain ${state.audit_valid?'valid':'invalid'}</small>`:'<span class="audit-empty">No decision recorded yet.</span>';
}
async function refresh(){try{state=await (await fetch('/api/state',{cache:'no-store'})).json();render();}catch(e){console.error(e)}}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-path]');if(!b)return;b.disabled=true;try{const r=await fetch(b.dataset.path,{method:'POST',headers:{'Content-Type':'application/json'},body:b.dataset.payload});const data=await r.json();if(!r.ok)alert(data.error||'Action failed');await refresh();}finally{b.disabled=false}});
$('copy-digest').onclick=()=>{if(state?.proof)navigator.clipboard.writeText(state.proof.sha256)};
function tick(){$('clock').textContent=new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});}tick();setInterval(tick,1000);
refresh();const stream=new EventSource('/api/events');stream.onmessage=refresh;stream.onerror=()=>setTimeout(refresh,1000);setInterval(refresh,10000);
