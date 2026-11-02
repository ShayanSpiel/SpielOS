/* Product shell backed only by the selected company's report API. */
(() => {
  const $ = id => document.getElementById(id);
  const esc = text => String(text ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const icons={overview:'M3 3h6v6H3z M15 3h6v6h-6z M3 15h6v6H3z M15 15h6v6h-6z',history:'M3 11a9 9 0 1 1 2 7 M3 4v7h7 M12 7v6l4 2',checks:'M4 20h16 M6 17V9h3v8 M11 17V4h3v13 M16 17v-6h3v6',activity:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18 M12 7v5l4 2',memory:'M9 4a3 3 0 0 0-5 3v3a3 3 0 0 0 0 5v2a3 3 0 0 0 5 3 M15 4a3 3 0 0 1 5 3v3a3 3 0 0 1 0 5v2a3 3 0 0 1-5 3 M12 3v18',runtime:'m3 7 9-5 9 5-9 5z M3 12l9 5 9-5 M3 17l9 5 9-5',telemetry:'M6 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6 M18 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6 M6 9v12 M18 3v8c0 4-12 0-12 5',company:'M4 21V3h16v18 M8 7h2 M14 7h2 M8 11h2 M14 11h2 M10 21v-5h4v5'};
  const main={overview:'Home',history:'History & examples',checks:'Quality & learning',activity:'Activity & cost'};
  const records={memory:'Memory',runtime:'Loaded context',telemetry:'Langfuse delivery',company:'Company & strategy'};
  const routes={overview:'home',history:'runs',checks:'evaluations',activity:'activity',memory:'memory',runtime:'runtime',telemetry:'telemetry',company:'company'};
  let sequence=0;
  const nav=items=>Object.entries(items).map(([key,label])=>`<button data-tab="${key}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${icons[key]}"></path></svg><span>${label}</span></button>`).join('');
  $('workspace-nav').innerHTML=nav(main);$('company-nav').innerHTML=nav(records);
  const learning=()=>`<section class="report-panel"><h2>Did the correction become a lasting improvement?</h2><div class="learning-proof"><div><b>1 · Feedback</b><p>Attributable feedback against actual work.</p></div><div><b>2 · Saved change</b><p>A scoped memory or bounded change receipt.</p></div><div><b>3 · Used later</b><p>A later selection or execution receipt.</p></div><div><b>4 · Evaluated again</b><p>A later result retaining the correction.</p></div></div><p class="report-muted">These are proof requirements, not a progress claim. A note alone does not establish learning. A complete before/after improvement scorecard is not implemented.</p></section>`;
  async function post(path,payload){const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Spielos-Report':'1'},body:JSON.stringify(payload)});const result=await response.json();if(!response.ok)throw Error(result.error||'The local action could not complete.');return result;}
  async function openConnection(){await post('/api/onboarding/choice',{choice:'connect'});$('connection-message').textContent='';$('connection-dialog').showModal();}
  async function onboardingIntro(){
    const response=await fetch('/api/onboarding',{cache:'no-store'});if(!response.ok)throw Error('Cannot inspect company onboarding.');const state=await response.json();
    $('connect-langfuse').textContent=state.langfuse_configured?'Langfuse settings':'Connect Langfuse';
    if(!state.ask_langfuse&&state.dashboard_tour_shown){$('onboarding-intro').innerHTML='';return;}
    const guide=state.dashboard_tour_shown?'':`<div class="tour-guide"><p><b>Home</b>Your current work, counts and pending decisions.</p><p><b>History & examples</b>Actual runs and outputs; examples remain separate.</p><p><b>Quality & learning</b>Questions, anchored criteria and pending reviews. A judgment is not independent acceptance.</p><p><b>Activity & cost</b>Exposed usage and observed intervals. Missing tokens or billed cost remain unknown.</p><p><b>Memory & loaded context</b>What was saved versus what was actually supplied.</p><p><b>Langfuse delivery</b>Queued records versus exact remote confirmation.</p></div>`;
    $('onboarding-intro').innerHTML=`<section class="onboarding-card"><h2>${state.ask_langfuse?'Connect Langfuse, or start locally?':'Your workspace, at a glance.'}</h2><p>${state.ask_langfuse?'Connect your project for traces, experiments and evaluation evidence. You can keep tracking and testing drafts locally while you decide.':'This dashboard reads your selected company’s actual records. Empty states show where evidence is still missing.'}</p>${guide}<div class="onboarding-actions">${state.ask_langfuse?'<button id="onboarding-connect">Connect now</button><button id="onboarding-local">Keep local for now</button>':''}${state.dashboard_tour_shown?'':'<button id="onboarding-understood">Got it</button>'}</div></section>`;
    if($('onboarding-connect'))$('onboarding-connect').onclick=()=>openConnection().catch(showError);
    if($('onboarding-local'))$('onboarding-local').onclick=async()=>{try{await post('/api/onboarding/choice',{choice:'local'});await render();}catch(error){showError(error);}};
    if($('onboarding-understood'))$('onboarding-understood').onclick=async()=>{try{await post('/api/onboarding/tour',{report_url:location.href});await render();}catch(error){showError(error);}};
  }
  function showError(error){$('record-status').textContent=error.message;}
  $('connect-langfuse').onclick=()=>openConnection().catch(showError);
  $('close-connection').onclick=()=>$('connection-dialog').close();
  $('connection-dialog').addEventListener('close',()=>{$('connection-form').reset();$('connection-message').textContent='';});
  $('connection-form').onsubmit=async event=>{event.preventDefault();$('submit-connection').disabled=true;$('connection-message').textContent='Verifying the selected project…';try{
    const destination=new URL($('langfuse-project').value);const match=destination.pathname.match(/^\/project\/([^/]+)\/?$/);
    if(destination.protocol!=='https:'||destination.username||destination.password||!match)throw Error('Use the HTTPS project URL ending in /project/your-project-id.');
    if(!$('langfuse-consent').checked)throw Error('Approve the evidence policy for this exact project before connecting.');
    await post('/api/onboarding/connect',{base_url:destination.origin,project_id:decodeURIComponent(match[1]),public_key:$('langfuse-public').value,secret_key:$('langfuse-secret').value,approved_evidence_policy:'reviewed_evidence'});
    $('connection-dialog').close();await render();$('record-status').textContent='Langfuse project verified and configured. Delivery remains pending until its records are confirmed remotely.';
  }catch(error){$('connection-message').textContent=error.message;}finally{$('submit-connection').disabled=false;}};
  async function render(){const current=++sequence;try{
    const data=await window.SpielosReport.load();if(current!==sequence)return;
    const params=new URLSearchParams(location.search);let subject=params.get('subject')||'company';const requested=params.get('tab')||'overview';const tab=routes[requested]?requested:'overview';
    const workflow=data.workflows.find(w=>w.id===subject);if(!workflow&&!['company','director'].includes(subject))subject='company';
    const name=workflow?(workflow.purpose||workflow.id):subject==='director'?'Director':'Company overview';
    $('subject').innerHTML='<option value="company">Company overview</option><option value="director">Director</option>'+ (data.workflows.length?'<optgroup label="Workflows">'+data.workflows.map(w=>`<option value="${esc(w.id)}">${esc(w.purpose||w.id)}</option>`).join('')+'</optgroup>':'');$('subject').value=subject;
    $('crumb').textContent='Work & learning / '+name;$('subject-kind').textContent=workflow?'SELECTED WORKFLOW · LIVE':subject==='director'?'DIRECTOR · COMPANY-WIDE VIEW':'SELECTED COMPANY · LIVE';
    $('subject-title').innerHTML=subject==='company'?'Company <em>overview.</em>':esc(name)+' <em>workspace.</em>';
    $('subject-description').textContent=workflow?'Versioned runs, pinned context and actual evaluation evidence for this workflow.':'Workflows, runs, memory and reported usage in one lasting workspace.';
    $('record-status').textContent='Live company records · refreshed '+new Date(data.generated_at).toLocaleTimeString()+'. Missing evidence stays missing.';
    document.querySelectorAll('[data-tab]').forEach(b=>{if(b.dataset.tab===tab)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
    await onboardingIntro();if(current!==sequence)return;
    $('workspace-content').innerHTML='<div id="live-section"></div>';await window.SpielosReport.mount($('live-section'),routes[tab],workflow?.id);
    if(tab==='checks')$('workspace-content').insertAdjacentHTML('beforeend',learning());
    if(tab==='history'&&!data.runs.length)$('workspace-content').insertAdjacentHTML('afterbegin','<section class="workspace-empty"><h2>Your history starts with real work.</h2><p>No registered runs are recorded yet. Ask Director to build a workflow or test a candidate. Company-specific example galleries stay separate from run evidence.</p></section>');
  }catch(error){$('record-status').textContent='Cannot read company records.';$('workspace-content').innerHTML='<p class="report-alert">'+esc(error.message)+'</p>';}}
  function navigate(tab,subject){const params=new URLSearchParams(location.search);if(tab)params.set('tab',tab);if(subject)params.set('subject',subject);history.pushState({},'',location.pathname+'?'+params);render();}
  document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>navigate(b.dataset.tab));$('subject').onchange=e=>navigate(null,e.target.value);$('refresh').onclick=render;window.onpopstate=render;render();
})();
