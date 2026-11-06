/* Read-only views of attributable company evidence. UI actions never grant quality approval. */
(() => {
  'use strict';
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const human = x => String(x ?? 'Unknown').replaceAll('_', ' ');
  const compact = x => x == null ? 'Unknown' : Intl.NumberFormat(undefined, {notation:'compact',maximumFractionDigits:1}).format(x);
  const time = x => x ? new Date(x).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'}) : 'Not recorded';
  const badge = (text, tone='quiet') => `<span class="status status-${tone}">${esc(text)}</span>`;
  const metric = (label, value, note='') => `<div class="report-metric"><span>${esc(label)}</span><b>${esc(value ?? 'Unknown')}</b><small>${esc(note)}</small></div>`;
  const panel = (title, body, extra='') => `<section class="report-panel ${extra}"><h2>${esc(title)}</h2>${body}</section>`;
  const table = (heads, rows) => `<div class="report-scroll"><table class="report-table"><thead><tr>${heads.map(x=>`<th scope="col">${esc(x)}</th>`).join('')}</tr></thead><tbody>${rows.length ? rows.map(r=>`<tr>${r.map(x=>`<td>${x}</td>`).join('')}</tr>`).join('') : `<tr><td colspan="${heads.length}" class="empty">No matching records. Try another filter.</td></tr>`}</tbody></table></div>`;
  const href = (label,url) => `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(label)} ↗</a>`;
  const navigate = (label,tab,subject) => `<a class="text-action" href="?tab=${encodeURIComponent(tab)}${subject?'&subject='+encodeURIComponent(subject):''}">${esc(label)} →</a>`;
  const search = (value,label='Search records') => `<input data-filter="search" aria-label="${esc(label)}" type="search" placeholder="${esc(label)}…" value="${esc(value||'')}">`;
  const options = (name,values,current) => `<select data-filter="${name}" aria-label="${esc(name)}">${values.map(([v,t])=>`<option value="${esc(v)}" ${v===current?'selected':''}>${esc(t)}</option>`).join('')}</select>`;
  const pages = (n,s) => `<div class="report-pages"><span>${n} matching records</span><div><button data-page="-1" ${!s.page?'disabled':''}>Previous</button><span>Page ${s.page+1}</span><button data-page="1" ${(s.page+1)*12>=n?'disabled':''}>Next</button></div></div>`;
  const slice = (rows,s) => {s.page=Math.max(0,Math.min(s.page||0,Math.ceil(rows.length/12)-1));return rows.slice(s.page*12,s.page*12+12);};
  const matches = (row,q) => !q || JSON.stringify(row).toLocaleLowerCase().includes(q.toLocaleLowerCase());
  const historyMemory = r => r.status!=='active'||['historical_authorization','historical_owner_record'].includes(r.classification?.category);
  const memoryGroup = r => historyMemory(r)?'history':r.scope==='workflow'?'lessons':'active';
  const workflowName = (d,id) => {const w=d.workflows.find(w=>w.id===id);return w?.name||w?.purpose||String(id||'Company activity').replaceAll('-',' ');};
  const readiness = w => w.readiness?.includes('accepted')?'Accepted':w.candidate_runs || w.readiness?.includes('candidate')?'Candidate':'Draft';
  const judgeState = r => !r.evaluation?'Awaiting evaluation':r.evaluation.state==='pass'?'Passed checks':human(r.evaluation.state);
  const reviewState = r => r.status==='completed'?'Accepted':r.status==='awaiting_review'?'Awaiting owner':r.status==='failed'?'Changes needed':'Waiting for checks';
  function delivery(d,r) {
    const items=(d.telemetry.recent||[]).filter(x=>x.kind==='workflow'&&x.run_id===r.id);
    return !items.length?'Not in displayed delivery window':items.every(x=>x.status==='verified')?'Confirmed':items.find(x=>x.last_error)?.last_error||'Awaiting confirmation';
  }
  function workflowRows(d,rows) {return rows.map(w=>[navigate(w.name||w.purpose||w.id,'history',w.id)+`<small>Version ${esc(w.version||'not pinned')}</small>`,badge(readiness(w),readiness(w)==='Accepted'?'good':'quiet'),`${w.runs||0} production · ${w.candidate_runs||0} candidate`,w.path?'Definition available':'Recorded history · definition unavailable',navigate('Inspect workflow','history',w.id)]);}
  function workflows(d,s) {
    const rows=d.workflows.filter(w=>matches(w,s.search)&&(s.filter==='all'||readiness(w).toLowerCase()===s.filter));
    return panel('Workflow library',`<div class="report-toolbar">${search(s.search,'Search workflows')}${options('filter',[['all','All workflows'],['accepted','Accepted'],['candidate','Candidates'],['draft','Drafts']],s.filter)}</div>${table(['Workflow','Release status','Recorded runs','Definition',''],workflowRows(d,slice(rows,s)))}${pages(rows.length,s)}<p class="report-muted">Candidates and drafts require testing or configuration. Production execution is available through Director for independently accepted releases.</p>`);
  }
  function home(d,s) {
    const counts=d.evaluation_counts||{},pending=counts.pending||0,t=d.telemetry,den=(t.verified||0)+(t.pending||0);
    const attention=[];
    if(pending)attention.push(navigate(`${pending} reviews awaiting attributable judgment`,'checks'));
    if(t.pending)attention.push(navigate(`${compact(t.pending)} delivery records awaiting confirmation`,'telemetry'));
    if(t.native_pending)attention.push(navigate(`${t.native_pending} evaluator setups need attention`,'telemetry'));
    const recent=d.runs.slice(0,5);
    return `<div class="report-metrics overview-metrics">${metric('Workflows',d.workflows.length)}${metric('Registered runs',d.totals.production_runs+d.totals.candidate_runs,'Production and candidate runs')}${metric('Reviews need attention',pending)}${metric('Delivery confirmed',den?Math.round(t.verified/den*100)+'%':'Not connected',den?`${compact(t.verified)} of ${compact(den)} recorded events`:'No cloud confirmation claimed')}</div>`+
      (pending?`<div class="attention-strip"><b>${pending} reviews need attention</b><span>Open a review to see its judge, evidence and blocker.</span>${navigate('View reviews','checks')}</div>`:'')+
      `<div class="overview-columns">${panel('Recent work',table(['Workflow','Output / checks','Owner review','Delivery'],recent.map(r=>[navigate(workflowName(d,r.workflow_id),'history',r.workflow_id),badge(judgeState(r),r.evaluation?.state==='pass'?'good':'warn'),badge(reviewState(r)),esc(delivery(d,r))]))+(recent.length?'':`<p class="report-muted">No registered Runs yet. Direct chat work appears under Activity &amp; cost.</p>`))}${panel('Needs attention',attention.length?`<ul class="attention-list">${attention.map(a=>`<li>${a}</li>`).join('')}</ul>`:'<p>No outstanding items in these recorded populations.</p>')}
      </div>${workflows(d,s)}`;
  }
  function runs(d,s) {
    const rows=d.runs.filter(r=>matches([workflowName(d,r.workflow_id),r],s.search)&&(s.filter==='all'||r.kind===s.filter));
    return panel('Recorded runs',`<div class="report-toolbar">${search(s.search,'Search runs')}${options('filter',[['all','Production and candidate'],['production','Production'],['candidate','Candidate']],s.filter)}</div>${table(['Workflow / version','Recorded','Kind','Quality judgment','Owner review',''],slice(rows,s).map(r=>[esc(workflowName(d,r.workflow_id))+`<small>Version ${esc(r.version)}</small>`,time(r.created_at),badge(human(r.kind)),badge(judgeState(r),r.evaluation?.state==='pass'?'good':r.evaluation?.state==='fail'?'bad':'warn'),badge(reviewState(r)),`<button data-inspect="${esc(r.id)}">Inspect</button>`]))}${pages(rows.length,s)}${s.selected?runDetail(d,s.selected):''}`);
  }
  function runDetail(d,id) {
    const r=d.runs.find(x=>x.id===id);if(!r)return '';
    return `<div class="detail-panel"><h3>${esc(workflowName(d,r.workflow_id))}</h3><p>${badge(judgeState(r))} ${badge(reviewState(r))}</p><p class="report-muted">${esc(r.context_basis)}. ${esc(r.time_basis)}.</p><h4>Pinned documents</h4><ul>${r.pinned_context.map(x=>`<li>${esc(x.name)}</li>`).join('')||'<li>No pinned documents</li>'}</ul><h4>Selected memory</h4><ul>${(r.selected_memory||[]).map(m=>`<li>${esc(m.claim||m.id||m)}</li>`).join('')||'<li>No memory selected</li>'}</ul><details><summary>Evaluation evidence</summary><pre>${esc(JSON.stringify(r.evaluation,null,2)||'No evaluation recorded')}</pre></details></div>`;
  }
  function evaluations(d,s) {
    const verdicts=new Map(d.evaluations.map(e=>[e.request_id,e]));
    const rows=(d.evaluation_requests||[]).filter(r=>matches([r.subject,r.model,r.blocker],s.search)&&(s.filter==='all'||s.filter==='pending'&&r.status==='pending'||s.filter==='reviewed'&&r.status==='reviewed'||s.filter==='reassigned'&&r.status==='reassigned'));
    const selected=rows.find(r=>r.id===s.selected)||rows[0];
    const renderRow=r=>{const e=verdicts.get(r.id),v=e?.verdict.verdicts||{},failed=Object.values(v).some(x=>x.state==='fail'),missing=Object.values(v).some(x=>x.state==='missing');return [ `<button class="row-title" data-inspect="${esc(r.id)}">${esc(r.subject)}</button><small>${time(r.created_at)}</small>`,badge(r.status==='reviewed'?(failed?'Failed checks':missing?'Evidence missing':'Judgment recorded'):r.status==='reassigned'?'Reassigned':r.model?'Awaiting judgment':'Judge identity unavailable',r.status==='pending'?'warn':failed?'bad':'quiet'),badge('Independent review separate'),esc(requestDelivery(d,r))];};
    const counts=d.evaluation_counts||{};
    return `<div class="report-metrics">${metric('Diagnostic records',counts.reviewed||0,'Includes missing evidence; no independent acceptance')}${metric('Awaiting judgment',counts.pending||0)}${metric('Reassigned',counts.reassigned||0,'Original request preserved')}</div><div class="inspector-layout">${panel('Evaluation, with evidence',`<p class="report-muted">Quality judgment, owner decision and cloud delivery are separate.</p><div class="report-toolbar">${search(s.search,'Search evaluations')}${options('filter',[['all','All reviews'],['pending','Needs attention'],['reviewed','Judged'],['reassigned','Reassigned']],s.filter)}</div>${table(['Output','Quality judgment','Owner review','Cloud delivery'],slice(rows,s).map(renderRow))}${pages(rows.length,s)}`)}${selected?evaluationDetail(d,selected,verdicts.get(selected.id)):panel('Review details','<p>Select a recorded review to inspect its evidence.</p>')}</div>`;
  }
  function requestDelivery(d,r) {
    if(r.delivery)return r.delivery.state==='confirmed'?'Confirmed':r.delivery.state==='pending'?'Awaiting confirmation':'No delivery receipt recorded';
    return 'Not in displayed delivery window';
  }
  function evaluationDetail(d,r,e) {
    return panel(r.subject,`${badge(r.status==='pending'?'Review awaiting judgment':human(r.status),r.status==='pending'?'warn':'quiet')}<p>${esc(r.blocker||'Inspect the attributable verdict and its evidence below.')}</p><dl class="facts"><dt>Output captured</dt><dd>${r.output_captured?'Yes':'Not exposed'}</dd><dt>Judge runtime</dt><dd>${esc(r.runtime||'Selected host')}</dd><dt>Judge identity</dt><dd>${esc(e?.verdict.model||r.model||'Not exposed')}</dd><dt>Cloud evidence</dt><dd>${esc(requestDelivery(d,r))}</dd></dl>${r.original_request_id?'<p class="report-muted">This review preserves an earlier frozen request. '+esc(r.reassignment_reason)+'</p>':''}<button data-copy-review="${esc(r.id)}">Prepare a new review</button><p class="report-muted">Copies a review brief for Director. No judgment or approval is created by this button.</p><details><summary>Frozen output preview</summary><pre>${esc(r.output_preview||'No output captured')}</pre><p class="report-muted">Preview limited to 6,000 characters; original evidence remains preserved.</p></details><h3>Rubric &amp; evidence</h3>${r.criteria.map(c=>{const v=e?.verdict.verdicts?.[c.id];return `<details><summary>${esc(c.question||c.id)} ${badge(v?human(v.state):'Not judged',v?.state==='fail'?'bad':'quiet')}</summary><p>${esc(v?.reason||'No attributable verdict recorded.')}</p><p class="report-muted">${esc(v?.evidence||'Evidence not yet supplied')}</p></details>`;}).join('')}`,'detail-panel');
  }
  function memory(d,s) {
    const counts={active:0,lessons:0,history:0};d.memory.records.forEach(r=>counts[memoryGroup(r)]++);
    const rows=d.memory.records.filter(r=>(s.filter==='all'||memoryGroup(r)===s.filter)&&matches([r.claim,r.source,r.classification?.topics],s.search)&&(s.scope==='all'||r.scope===s.scope));
    const selected=rows.find(r=>r.id===s.selected)||rows[0];
    return `<div class="segmented" role="group" aria-label="Memory category">${[['active','Active guidance'],['lessons','Workflow lessons'],['history','History'],['all','All records']].map(([key,label])=>`<button data-group="${key}" aria-pressed="${s.filter===key}">${label} <span>${key==='all'?d.memory.records.length:counts[key]}</span></button>`).join('')}</div><div class="inspector-layout">${panel('Saved memory',`<div class="report-toolbar">${search(s.search,'Search memory')}${options('scope',[['all','All scopes'],['owner','Owner'],['workflow','Workflow'],['strategy','Strategy']],s.scope||'all')}</div>${table(['Memory','Scope','Source','Retrieval'],slice(rows,s).map(r=>[`<button class="row-title" data-inspect="${esc(r.id)}">${esc(r.claim)}</button>`,esc(human(r.classification?.category||r.scope)),esc(r.source||'Source not supplied'),badge(historyMemory(r)?'Excluded':'Eligible when relevant',historyMemory(r)?'quiet':'good')]))}${pages(rows.length,s)}<p class="report-muted">${d.memory.truncated?'This is a bounded record window. ':''}Saved memory is not proof of learning. Historical permissions never authorize a new external action.</p>`)}${selected?memoryDetail(d,selected):panel('Memory details','<p>No matching memory. Existing records are preserved.</p>')}</div>`;
  }
  function memoryDetail(d,r) {
    const used=d.runs.filter(x=>(x.selected_memory||[]).some(m=>m.id===r.id));
    return panel('Why this memory is available',`${badge(historyMemory(r)?'Historical · excluded':'Active guidance',historyMemory(r)?'quiet':'good')}<p class="memory-claim">${esc(r.claim)}</p><dl class="facts"><dt>Scope</dt><dd>${esc(r.workflow_id?workflowName(d,r.workflow_id):human(r.scope))}</dd><dt>Source</dt><dd>${esc(r.source||'Not recorded')}</dd><dt>Topics</dt><dd>${esc((r.classification?.topics||[]).join(', ')||'No topic restriction')}</dd><dt>Selection policy</dt><dd>${historyMemory(r)?'Excluded from normal retrieval':r.classification?.critical?'Critical guidance; always eligible':'Topic relevance and per-scope retrieval budget apply'}</dd></dl><h3>Included in recorded runs</h3>${used.length?`<ul>${used.map(x=>`<li>${esc(workflowName(d,x.workflow_id))} · ${time(x.created_at)}</li>`).join('')}</ul>`:'<p class="report-muted">No selection found in the displayed run window. This does not establish that a host read or followed it.</p>'}<h3>Learning evidence</h3><p>${r.evidence.length} evaluated run references</p>${r.evidence.length?`<details><summary>Inspect references</summary><pre>${esc(JSON.stringify(r.evidence,null,2))}</pre></details>`:''}<button data-copy-memory="${esc(r.id)}">Propose revision or retirement</button><p class="report-muted">Copies a scoped change brief for Director. A reason and review are required; no record is deleted or changed here.</p>${r.retirement_reason?`<p>Retirement reason: ${esc(r.retirement_reason)}</p>`:''}`,'detail-panel');
  }
  function context(d,s) {
    const rows=d.context.filter(c=>matches([c.reason,c.documents],s.search));const selected=rows.find(c=>c.id===s.selected)||rows[0];
    return panel('Context supplied to a run or chat',`<p class="report-muted">Supplied to host; reading and attention are not confirmed. Showing ${d.context.length} of ${d.context_total??d.context.length} snapshots${d.context_truncated?' (bounded history window)':''}.</p><div class="report-toolbar">${search(s.search,'Search supplied context')}</div>${table(['Recorded','Selection reason','Documents',''],slice(rows,s).map(c=>[time(c.created_at),esc(c.reason||'Reason not recorded'),String(c.documents.length),`<button data-inspect="${esc(c.id)}">Inspect selection</button>`]))}${pages(rows.length,s)}${selected?`<div class="detail-panel"><h3>Supplied context · ${time(selected.created_at)}</h3><p>${esc(selected.reason)}</p>${selected.documents.map(doc=>`<details><summary>${esc(doc.name)} ${badge('Supplied to host')} ${badge('Read not confirmed')}</summary><p class="report-muted">${selected.changed.includes(doc.name)?'Changed in this selection · ':''}Content digest: ${esc(doc.sha256)}</p><pre>${esc(doc.preview)}</pre><p class="report-muted">Document preview limited to 1,200 characters.</p></details>`).join('')}</div>`:''}`);
  }
  function telemetry(d,s) {
    const t=d.telemetry;if(!t.enabled)return panel('Local records','<p>Langfuse is not connected. Captured evidence remains local; cloud confirmation is unknown.</p>');
    const rows=(t.recent||[]).filter(r=>matches([r.name,r.last_error],s.search)&&(s.filter==='all'||s.filter==='pending'&&r.status!=='verified'||s.filter==='verified'&&r.status==='verified'));
    const rate=t.health?.rate_limit||{},retry=Math.max(0,...['delivery','definitions'].map(k=>(rate[k]||0)-Date.now()/1000));
    return `<div class="report-metrics">${metric('Confirmed events',compact(t.verified))}${metric('Awaiting confirmation',compact(t.pending))}${metric('Evaluator setups pending',t.native_pending)}${metric('Rate-limit retry',retry?Math.ceil(retry)+'s':'Eligible on next wake')}</div>${panel('Langfuse delivery',`${t.project_url?href('Open selected project',t.project_url):''}<p class="report-muted">Only exact remote readback is confirmation. This view shows up to 200 records per queue, prioritizing unconfirmed records; counts above cover the full queues.</p><div class="report-toolbar">${search(s.search,'Search delivery')}${options('filter',[['all','All displayed records'],['pending','Needs attention'],['verified','Confirmed']],s.filter)}</div>${table(['Record','Recorded','Delivery state','Attempts','Reason / evidence'],slice(rows,s).map(r=>[esc(r.name||'Recorded event'),time(r.at),badge(human(r.status),r.status==='verified'?'good':'warn'),String(r.attempts??0),esc(r.last_error||(r.status==='verified'?'Exact readback confirmed':'Waiting for a bounded host wake or remote readback'))+(r.remote_reference?'<br>'+href('Confirmed observation',r.remote_reference):r.trace_url?'<br>'+href('Trace destination · may be empty',r.trace_url):'')]))}${pages(rows.length,s)}`)}${panel('Evaluator setup',table(['Definition','Setup state','Blocker'],(t.native_definitions||[]).map(r=>[esc(human(r.key.split(':')[0]))+'<details><summary>Definition reference</summary>'+esc(r.key)+'</details>',badge(human(r.status),r.status==='verified'?'good':'warn'),esc(r.last_error||(r.status==='verified'?'Confirmed evaluator and rule':'An uncertain creation requires exact readback; no blind resend'))])))}`;
  }
  function activity(d,s) {
    const x=d.usage.codex;const after=s.period==='all'?0:Date.now()-Number(s.period||7)*86400000;
    const turns=(x?.turns||[]).filter(t=>(!after||Date.parse(t.started_at)>=after)&&matches(t.model,s.search));
    const totals=turns.reduce((a,t)=>{for(const key of ['input_tokens','cached_input_tokens','output_tokens'])a[key]+=t.usage[key]||0;return a;},{input_tokens:0,cached_input_tokens:0,output_tokens:0});
    return panel('Activity & cost',`<div class="report-toolbar">${search(s.search,'Search model')}${options('period',[['7','Last 7 days'],['30','Last 30 days'],['all','All recorded time']],s.period||'7')}</div>${x?`<div class="report-metrics">${metric('Input tokens',compact(totals.input_tokens),'Includes cached input')}${metric('Cached input',compact(totals.cached_input_tokens),'Included above; not added again')}${metric('Output tokens',compact(totals.output_tokens))}${metric('Actual bill','Unknown','Reference prices are estimates')}</div><p class="report-muted">${esc(x.scope)} Chat and workflow totals are separate to avoid double counting. Prices do not establish a bill.</p>${table(['Turn started','Model','Input / cached / output','Elapsed','Reference estimate'],slice(turns,s).map(t=>[time(t.started_at),esc(t.model||'Not exposed'),`<span title="${esc(JSON.stringify(t.usage))}">${compact(t.usage.input_tokens)} / ${compact(t.usage.cached_input_tokens)} / ${compact(t.usage.output_tokens)}</span>`,t.duration_ms==null?'Completion not recorded':Math.round(t.duration_ms/1000)+'s including waits',t.pricing.api_unpriced_events?'Unknown for unpriced events':Number(t.pricing.api_standard_equivalent_usd).toFixed(4)+' USD API equivalent']))}${pages(turns.length,s)}`:table(['Recorded','Input / output','Actual cost'],d.activity.slice(0,30).map(a=>[time(a.created_at),compact(a.usage.input_tokens)+' / '+compact(a.usage.output_tokens),a.usage.cost==null?'Unknown':esc(a.usage.cost+' '+a.usage.currency)]))}<details><summary>Separately attributed workflow usage</summary>${table(['Workflow / stage','Input / output','Cost'],(d.workflow_usage||[]).map(r=>[esc(workflowName(d,r.workflow_id)+' · '+r.stage),compact(r.usage.input_tokens)+' / '+compact(r.usage.output_tokens),r.usage.cost==null?'Unknown':esc(r.usage.cost+' '+r.usage.currency+' '+r.usage.status)]))}</details>`);
  }
  function company(d) {return panel('Company profile & strategy',`${d.extension.ui_root?'<p>'+href('Open preserved custom history','/'+d.extension.ui_root+'/index.html')+'</p>':''}${d.documents.map(doc=>`<details><summary>${esc(doc.name)} · ${time(doc.modified_at)}</summary><pre>${esc(doc.text)}</pre><button data-open="${esc(doc.path)}">Show in Files</button></details>`).join('')}`);}
  function scoped(d,scope) {
    const workflow=d.workflows.find(w=>w.id===scope);if(!workflow)return d;
    const runs=d.runs.filter(r=>r.workflow_id===scope),ids=new Set(runs.map(r=>r.id));
    const requests=(d.evaluation_requests||[]).filter(r=>r.target?.kind==='run'&&ids.has(r.target.id)),requestIds=new Set(requests.map(r=>r.id));
    const memories=d.memory.records.filter(r=>r.workflow_id===scope),categories={};for(const row of memories){const key=row.classification?.category||row.scope;categories[key]=(categories[key]||0)+1;}
    const counts={};for(const row of requests)counts[row.status]=(counts[row.status]||0)+1;
    return {...d,workflows:[workflow],runs,context:d.context.filter(c=>runs.some(r=>r.session_id===c.session_id)),activity:[],evaluation_requests:requests,evaluation_counts:counts,evaluations:d.evaluations.filter(e=>requestIds.has(e.request_id)),
      memory:{...d.memory,records:memories,categories,total:memories.length,truncated:false},workflow_usage:(d.workflow_usage||[]).filter(r=>r.workflow_id===scope),
      agents:d.agents.filter(a=>(a.workflow_ids||[]).includes(scope)),
      totals:{...d.totals,workflows:1,production_runs:runs.filter(r=>r.kind==='production').length,candidate_runs:runs.filter(r=>r.kind==='candidate').length,memory_records:memories.length},
      usage:{...d.usage,codex:null,chat:{meaning:'Company chat usage is not attributed without an explicit run receipt.'}},
      scope_note:'Run and evaluation lists are workflow-scoped. Delivery counters remain company-wide.'};
  }
  const views={home,workflows,runs,evaluations,memory,runtime:context,telemetry,activity,company};
  const states=new Map();
  async function load() {const r=await fetch('/api/report',{cache:'no-store'});if(!r.ok)throw Error('Open the selected company through /report to authorize this browser.');return r.json();}
  async function mount(node,section='home',scope=null,supplied=null) {
    try {
      const d=scoped(supplied||await load(),scope),key=section+':'+scope;
      const s=states.get(key)||{search:new URLSearchParams(location.search).get('q')||'',filter:section==='memory'?'active':'all',scope:'all',period:'7',page:0};states.set(key,s);
      const draw=()=>{node.innerHTML=(d.scope_note?`<p class="report-muted">${esc(d.scope_note)}</p>`:'')+views[section](d,s);};draw();
      node.oninput=e=>{if(!e.target.dataset.filter)return;const key=e.target.dataset.filter,pos=e.target.selectionStart;s[key]=e.target.value;s.page=0;draw();const f=node.querySelector(`[data-filter="${key}"]`);if(f){f.focus();if(f.type==='search')f.setSelectionRange(pos,pos);}};
      node.onchange=e=>{if(e.target.tagName==='SELECT'&&e.target.dataset.filter){s[e.target.dataset.filter]=e.target.value;s.page=0;draw();}};
      node.onclick=async e=>{const b=e.target.closest('button');if(!b)return;try {
        if(b.dataset.page){s.page+=Number(b.dataset.page);draw();}
        if(b.dataset.group){s.filter=b.dataset.group;s.page=0;s.selected=null;draw();}
        if(b.dataset.inspect){s.selected=b.dataset.inspect;draw();}
        if(b.dataset.copyReview){const r=d.evaluation_requests.find(x=>x.id===b.dataset.copyReview);await navigator.clipboard.writeText(`Review the preserved output for ${r.subject}. Keep the original request and artifact unchanged; record any reassignment and the actual host model. This is a diagnostic, not independent acceptance.\nReview reference: ${r.id}`);b.textContent='Review brief copied';}
        if(b.dataset.copyMemory){const r=d.memory.records.find(x=>x.id===b.dataset.copyMemory);await navigator.clipboard.writeText(`Propose a scoped revision or retirement for this memory, show the reason and retain its source/history before recording a change.\n${r.claim}\nMemory reference: ${r.id}`);b.textContent='Change brief copied';}
        if(b.dataset.open){const r=await fetch('/api/open-file',{method:'POST',headers:{'Content-Type':'application/json','X-Spielos-Report':'1'},body:JSON.stringify({path:b.dataset.open})});const a=await r.json();b.textContent=a.opened?'Shown in Files':a.error||'Could not reveal file';}
      }catch(error){b.textContent=error.message||'Action unavailable';}};
    }catch(error){node.innerHTML=`<p class="report-alert">${esc(error.message)}</p>`;}
  }
  const api={load,mount,scoped,views,memoryGroup,historyMemory,readiness,esc};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  if(typeof window!=='undefined')window.SpielosReport=api;
})();
