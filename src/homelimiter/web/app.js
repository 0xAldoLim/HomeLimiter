const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const nav = [ ['overview','◫','Overview'], ['devices','▣','Connected devices'], ['bandwidth','⇅','Bandwidth'], ['access','⊘','Internet access'], ['scheduling','◷','Scheduling'], ['agents','◇','Enforcement agents'], ['diagnostics','⌁','Network diagnostics'], ['logs','≡','Audit logs'], ['settings','⚙','Settings'] ];
let token = '', status, devices = [], policies = [], logs = [], routeVersion = 0;
let presets;
try { presets = JSON.parse(localStorage.getItem('hl-presets') || '[]'); if (!Array.isArray(presets)) presets = []; } catch { presets = []; }
const date = value => value ? new Date(value).toLocaleString([], {dateStyle:'medium',timeStyle:'short'}) : 'No expiry';
const name = id => devices.find(d => d.id === id)?.nickname || id;
const badge = (text, type='') => `<span class="badge ${type}">${esc(text)}</span>`;
function notice(title, description, type='') { return `<div class="notice ${type}"><span>ⓘ</span><div><strong>${esc(title)}</strong><p>${esc(description)}</p></div></div>`; }
function empty(title, description, icon='◇') { return `<div class="empty"><div class="empty-icon">${icon}</div><strong>${esc(title)}</strong><p>${esc(description)}</p></div>`; }
function toast(message) { $('#toast').textContent = message; $('#toast').hidden = false; clearTimeout(toast.timer); toast.timer = setTimeout(() => $('#toast').hidden = true, 6000); }
async function api(path, options={}) {
  const response = await fetch('/api'+path, {...options, headers:{'Authorization':'Bearer '+token, ...(options.method ? {'Content-Type':'application/json'} : {}), ...options.headers}});
  const data = await response.json();
  if (!response.ok) { const message = typeof data.detail === 'string' ? data.detail : 'Check the form values and try again.'; throw new Error(message); }
  return data;
}
const post = (path, data={}) => api(path,{method:'POST',body:JSON.stringify(data)});
function heading(title, subtitle, action='') { return `<div class="page-heading"><div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><div class="heading-actions">${action}</div></div>`; }
function capsNotice() {
  const c = status.capabilities;
  return notice(c.simulated ? 'You’re exploring a demo workspace' : c.mode === 'MONITOR ONLY' ? 'Observe first. Connect an agent when you’re ready.' : 'Your enforcement point is connected', c.reason, c.simulated ? 'warn' : '');
}
function controlsAllowed(device, kind='bandwidth') { return status.capabilities[kind] && device?.confirmed && device?.status === 'online' && !device?.protected; }
function deviceRow(d) {
  const count = policies.filter(p=>p.device_id===d.id).length;
  return `<a href="#device/${encodeURIComponent(d.id)}" class="device-row"><div class="device-icon">${d.protected?'⌂':'▣'}</div><div><div class="device-name">${esc(d.nickname)}</div><div class="device-meta">${esc(d.addresses[0] || 'No address')} · ${esc(d.source)}</div></div><div class="row-end">${count?badge(count+' policies'):d.protected?badge('Protected','neutral'):''}<span class="status-dot">${d.status==='online'?'<span class="dot"></span>':''}${esc(d.status)}</span><span class="muted">↗</span></div></a>`;
}
function activities(items) { return items.length ? items.map(l=>`<div class="activity-row"><span class="activity-icon">${l.outcome==='failed'?'!':'✓'}</span><div><strong>${esc(l.action.replaceAll('.',' / '))}</strong><p>${esc(l.outcome)}</p></div><span class="activity-time">${esc(date(l.time))}</span></div>`).join('') : empty('Your activity starts here','Changes and recovery events will appear in your local audit trail.','◷'); }
function overview() {
  const online = devices.filter(d=>d.status==='online').length, protectedCount = devices.filter(d=>d.protected).length;
  const scheduled = policies.filter(p=>p.window||p.starts_at||p.expires_at).length;
  const stats = [['Connected devices',online,`${devices.length} devices in your inventory`,'▣'],['Configured policies',policies.length,'Includes active and scheduled policies','⇅'],['Scheduled restrictions',scheduled,'Timezone-aware and persistent','◷'],['Protected devices',protectedCount,'Excluded from restrictions','⌂']];
  return heading('A clearer view of your network.','A little visibility. A little balance. All in one place.', '<button class="secondary" data-action="refresh">↻ Refresh inventory</button><a class="primary" href="#devices">View devices ↗</a>') + capsNotice() +
    `<div class="stats-grid">${stats.map(([label,n,note,icon])=>`<div class="stat"><div class="stat-top"><span>${label}</span><span class="stat-icon">${icon}</span></div><div class="stat-number">${n}</div><div class="stat-note">${note}</div></div>`).join('')}</div>
    <div class="columns"><section class="panel"><div class="panel-header"><div><h2>Your devices</h2><p>Familiar names. Clear identities.</p></div><a class="quiet" href="#devices">View all ↗</a></div>${devices.slice(0,4).map(deviceRow).join('') || empty('Make your network familiar','Add authorized network ranges in settings, then refresh your passive inventory.','▣')}</section>
    <section class="panel"><div class="panel-header"><div><h2>Connection at a glance</h2><p>Know where control lives.</p></div>${badge(status.capabilities.simulated?'SIMULATION':'LOCAL','neutral')}</div><div class="panel-content"><div class="path"><div class="path-node"><span>▣</span>Controller</div><span class="path-arrow">···</span><div class="path-node"><span>◇</span>${status.capabilities.adapter==='gateway'?'Linux gateway':'No live agent'}</div><span class="path-arrow">···</span><div class="path-node"><span>◎</span>Network</div></div><div class="fact-row"><span>Operating mode</span><strong>${esc(status.capabilities.mode)}</strong></div><div class="fact-row"><span>Measured throughput</span><span>Unavailable</span></div><div class="fact-row"><span>Last reconciliation</span><span>${status.last_reconciled?esc(date(status.last_reconciled)):'Waiting'}</span></div></div></section></div>
    <section class="panel"><div class="panel-header"><div><h2>Recent activity</h2><p>A transparent record of what changed.</p></div><a class="quiet" href="#logs">Open audit log ↗</a></div><div class="panel-content">${activities(logs.slice(0,4))}</div></section>`;
}
function deviceCards(filter='', state='all') {
  const selected = devices.filter(d => `${d.nickname} ${d.mac} ${d.addresses.join(' ')}`.toLowerCase().includes(filter.toLowerCase()) && (state==='all'||d.status===state));
  return selected.map(d=>`<article class="panel device-card"><div class="device-card-top"><span class="device-icon">${d.protected?'⌂':'▣'}</span>${badge(d.simulated?'Simulated':d.status,d.status==='online'?'':'neutral')}</div><h2>${esc(d.nickname)}</h2><p class="address">${esc(d.addresses[0] || 'No address')}</p><div class="facts"><span class="muted">Identity</span><span>${d.confirmed?'Confirmed':'Needs review'}</span></div><div class="facts"><span class="muted">Policies</span><span>${policies.filter(p=>p.device_id===d.id).length} configured</span></div><div class="card-footer">${d.protected?badge('Protected','neutral'):`<span class="muted hint">${esc(d.source)}</span>`}<a href="#device/${encodeURIComponent(d.id)}">View device ↗</a></div></article>`).join('') || empty('No matching devices','Refresh inventory or update your search. Passive discovery requires configured authorized CIDRs.','▣');
}
function connected() { return heading('Your connected devices.','Put a familiar name to every connection.','<button class="secondary" data-action="refresh">↻ Refresh inventory</button>') + capsNotice() + '<div class="toolbar"><input id="search" aria-label="Search devices" placeholder="⌕  Search name, IP, or MAC address"><select id="filter" aria-label="Filter connection status"><option value="all">All devices</option><option value="online">Online</option><option value="offline">Offline</option><option value="unknown">Unknown</option></select><span class="count">'+devices.length+' devices in your inventory</span></div><div id="device-grid" class="device-grid">'+deviceCards()+'</div>'; }
function detail(id) {
  const d = devices.find(d=>d.id===id); if(!d) return empty('Device not found','Refresh inventory to check the latest observations.');
  const facts = [['IPv4 / IPv6',d.addresses.join(' · ')],['MAC address',d.mac || 'Unknown'],['Discovery source',d.source],['Interface',d.interface||'Simulated'],['Connection',d.status],['Last seen',date(d.last_seen)],['Vendor',d.vendor||'Unknown'],['Identity',d.confirmed?'Confirmed by administrator':'Unconfirmed'],['Protected',d.protected?'Yes':'No']];
  return heading(d.nickname,'Device details · '+d.id,`<button class="secondary" data-action="rename" data-id="${esc(id)}">Edit device</button><button class="primary" data-action="limit" data-id="${esc(id)}" ${controlsAllowed(d)?'':'disabled'}>Set a limit</button>`) + (d.simulated?notice('Simulated device','Changes affect this demo workspace only.','warn'):'') + `<div class="detail-grid"><section class="panel"><div class="panel-header"><h2>Identity & connection</h2></div><div class="panel-content">${facts.map(([k,v])=>`<div class="fact-row"><span>${k}</span><span>${esc(v)}</span></div>`).join('')}${!d.confirmed?`<button class="secondary section-gap" data-action="identify" data-id="${esc(id)}">Confirm this identity</button>`:''}</div></section><section class="panel"><div class="panel-header"><h2>Device policies</h2><button class="quiet" data-action="resume" data-id="${esc(id)}">Restore all ↗</button></div>${policyRows(policies.filter(p=>p.device_id===id))}<div class="panel-content">${notice('Throughput is unavailable','No measured traffic statistics are supplied by this adapter. Configured caps are not measurements.')}</div></section></div>`;
}
function policyRows(items) {
  return items.length ? items.map(p=>`<div class="policy-row"><span class="device-icon">${p.blocked?'⊘':'⇅'}</span><div class="policy-info"><h3>${esc(p.label)} <span class="muted">/ ${esc(name(p.device_id))}</span></h3><p>${p.window?esc(`${p.window.start.slice(0,5)}–${p.window.end.slice(0,5)} · ${p.window.timezone} · ${p.window.weekdays.map(d=>['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][d]).join(', ')}`):p.starts_at?'Starts '+esc(date(p.starts_at)):'Immediate'} · ${p.expires_at?'Expires '+esc(date(p.expires_at)):'No expiry'}</p>${p.download_mbps||p.upload_mbps?'<div class="limit-bar" title="Configured cap; not measured traffic"><div class="limit-fill"></div></div>':''}</div><div class="rate">${p.blocked?'Internet pause':`↓ ${esc(p.download_mbps??'—')} / ↑ ${esc(p.upload_mbps??'—')}<span>Mbps cap</span>`}</div><button class="quiet" data-action="remove" data-id="${esc(p.id)}" aria-label="Remove ${esc(p.label)}">Remove ×</button></div>`).join('') : empty('A little room to breathe','No policies here. Restrictions appear after you explicitly confirm a target.','⇅');
}
function policyPage(kind) {
  const schedule=kind==='scheduling', access=kind==='access';
  const items=policies.filter(p=>schedule?(p.window||p.starts_at||p.expires_at):access?p.blocked:!p.blocked);
  return heading(schedule?'Make balance a routine.':access?'A pause when it matters.':'More bandwidth. Less friction.',schedule?'Set recurring windows or one-time restrictions in your timezone.':access?'Manage internet access without losing sight of your devices.':'Set separate upload and download caps for confirmed devices.',`<button class="primary" data-action="${schedule?'schedule':access?'pause':'limit'}" ${status.capabilities[access?'access':'bandwidth']||schedule&&status.capabilities.access?'':'disabled'}>+ ${schedule?'New schedule':access?'Pause a device':'Set a limit'}</button>`) + capsNotice() + notice('Predictable policy conflicts','An internet pause takes precedence. For overlapping limits, the lowest active cap in each direction wins. Restoring a device removes its future schedules too.') + `<section class="panel"><div class="panel-header"><h2>${schedule?'Scheduled policies':access?'Internet access policies':'Bandwidth policies'}</h2>${badge(items.length+' CONFIGURED','neutral')}</div>${policyRows(items)}</section>` + (!access&&!schedule?notice('Caps, not traffic measurements','The bars represent configured limits only. Live throughput statistics are unavailable.'):'');
}
async function agents() {
  const data = await api('/adapters'), c = data.current;
  return heading('Control starts with the right path.','An authorized enforcement point makes network policies possible.')+capsNotice()+`<div class="settings-grid"><section class="panel"><div class="panel-header"><h2>Current adapter</h2>${badge(c.adapter.toUpperCase())}</div><div class="panel-content"><h2>${esc(c.mode)}</h2><p class="muted hint">${esc(c.reason)}</p>${[['Discovery',c.discovery],['Bandwidth limits',c.bandwidth],['Internet access',c.access],['IPv6',c.ipv6],['Live statistics',c.statistics]].map(([k,v])=>`<div class="fact-row"><span>${k}</span><span>${v?'Available':'Unavailable'}</span></div>`).join('')}</div></section><section class="panel"><div class="panel-header"><h2>Deployment notes</h2></div><div class="panel-content"><div class="setting-item"><strong>Linux routed gateway</strong><p>Requires an explicitly configured traffic path, forwarding, authorized CIDRs and delegated interfaces. Experimental enforcement.</p></div><div class="setting-item"><strong>Inline bridge</strong><p>${esc(data.bridge)}.</p></div><div class="setting-item"><strong>Windows & Kali VMware</strong><p>The controller runs directly on Windows. A VM’s network mode does not establish control of household traffic. Use a secure connection to an authorized Linux gateway.</p></div></div></section></div>`;
}
async function diagnostics() {
  const d=await api('/diagnostics');
  return heading('A clear picture of your environment.','Read-only diagnostics. No host networking is changed.')+notice('Configuration does not prove traffic coverage',d.note)+`<section class="panel"><div class="panel-header"><h2>${esc(d.os)} · Python ${esc(d.python)}</h2>${badge(d.administrator?'ADMINISTRATOR':'STANDARD USER','neutral')}</div><div class="panel-content"><div class="fact-row"><span>Virtualization</span><span>${esc(d.virtualization)}</span></div><div class="fact-row"><span>Network tools</span><span>${esc(Object.entries(d.tools).map(([k,v])=>`${k}: ${v?'available':'unavailable'}`).join(' · '))}</span></div><pre>${esc(JSON.stringify(d,null,2))}</pre></div></section>`;
}
function audit() { return heading('Every change has a record.','Local, structured history of policy decisions and recovery.')+`<section class="panel"><div class="table-wrap"><table><thead><tr><th>TIME</th><th>ACTION</th><th>OUTCOME</th><th>DETAIL</th></tr></thead><tbody>${logs.map(l=>`<tr><td>${esc(date(l.time))}</td><td>${esc(l.action)}</td><td>${badge(l.outcome,l.outcome==='failed'?'warning':'neutral')}</td><td>${esc(l.detail)}</td></tr>`).join('')}</tbody></table></div>${!logs.length?empty('No events yet','Administrative actions will be recorded here.'):''}</section>`; }
async function settings() {
  const s=await api('/settings');
  return heading('A workspace that stays yours.','Local settings, explicit permissions, and a way back.')+`<div class="settings-grid"><section class="panel"><div class="panel-header"><h2>Network & privacy</h2></div><div class="panel-content"><div class="setting-item"><strong>Authorized networks</strong><p>${esc(s.authorized_cidrs.join(', ')||'No ranges configured. Passive discovery is disabled.')}</p></div><div class="setting-item"><strong>Protected addresses</strong><p>${esc(s.protected_addresses.join(', ')||'No additional addresses configured.')}</p></div><div class="setting-item"><strong>Loopback binding · No telemetry</strong><p>${esc(s.configuration)}</p></div></div></section><section class="panel"><div class="panel-header"><h2>Your preferences</h2></div><div class="panel-content"><div class="setting-item"><strong>Appearance</strong><p>Choose the light or dark workspace.</p><button class="secondary section-gap" data-action="theme">Toggle theme ◐</button></div><div class="setting-item"><strong>Custom bandwidth presets</strong><p>${presets.length} saved in this browser. Save new presets while setting a limit.</p></div><div class="setting-item"><strong>Emergency restoration</strong><p>Remove HomeLimiter restrictions and future policies. Other firewall rules remain under their existing administrator.</p><button class="danger section-gap" data-action="emergency">Restore all HomeLimiter policies</button></div></div></section></div>`;
}
async function render() {
  if (!token) return;
  const version=++routeVersion, hash=(location.hash.slice(1)||'overview'), [route,id]=hash.split('/');
  $('#breadcrumb').textContent=route==='device'?'Device details':nav.find(n=>n[0]===route)?.[2]||'Overview';
  $('#navigation').innerHTML=nav.map(([key,icon,label])=>`<a class="nav-link ${key===route||key==='devices'&&route==='device'?'active':''}" href="#${key}" title="${label}"><span class="nav-icon" aria-hidden="true">${icon}</span><span class="nav-text">${label}</span></a>`).join('');
  try {
    [status,devices,policies,logs] = await Promise.all([api('/status'),api('/devices'),api('/policies'),api('/logs')]);
    const routes={overview,devices:connected,bandwidth:()=>policyPage('bandwidth'),access:()=>policyPage('access'),scheduling:()=>policyPage('scheduling'),agents,diagnostics,logs:audit,settings,device:()=>detail(decodeURIComponent(id||''))};
    const html=await (routes[route]||overview)();
    if(version!==routeVersion) return;
    $('#mode').textContent=status.capabilities.mode;
    $('#mode').className='badge '+(status.capabilities.simulated?'warning':'');
    $('#main').innerHTML=(status.last_error?notice('A reconciliation needs attention',status.last_error,'error'):'')+html;
  } catch(e) { if(version===routeVersion) $('#main').innerHTML=notice('Unable to load this view',e.message,'error'); }
}
function modal(html, submit, label='Confirm') {
  $('#modal-body').innerHTML=html; $('#modal-submit').textContent=label; $('#modal').showModal();
  $('#modal-form').onsubmit=async e=>{e.preventDefault();$('#modal-submit').disabled=true;try{await submit(new FormData(e.target));$('#modal').close();await render();}catch(e){toast(e.message);}finally{$('#modal-submit').disabled=false;}};
}
function policyDialog(action,id) {
  const access=action==='pause',schedule=action==='schedule';
  const candidates=devices.filter(d=>controlsAllowed(d,access?'access':'bandwidth')||schedule&&controlsAllowed(d,'access'));
  if(!candidates.length){toast('No confirmed, online, unprotected device supports this control.');return;}
  modal(`<h2>${schedule?'Create a schedule':access?'Pause internet access':'Set a bandwidth limit'}</h2><p>${status.capabilities.simulated?'This is a simulation. No real traffic will change.':'This changes traffic only at your authorized enforcement point.'} Confirm the exact device before applying.</p><label for="target">Target device</label><select id="target" name="device_id">${candidates.map(d=>`<option value="${esc(d.id)}" ${d.id===id?'selected':''}>${esc(d.nickname)} · ${esc(d.addresses[0])} · ${esc(d.mac)}</option>`).join('')}</select><label for="label">Policy name</label><input id="label" name="label" value="${schedule?'Evening routine':access?'Take a break':'Custom limit'}" required maxlength="80">${schedule?'<label for="kind">Restriction</label><select id="kind" name="kind"><option value="block">Internet pause</option><option value="limit">Bandwidth limit</option></select>':''}${!access?`<div class="field-pair"><div><label for="download">Download cap / Mbps</label><input id="download" name="download" type="number" min="0.008" max="10000" step="any" placeholder="Unlimited"></div><div><label for="upload">Upload cap / Mbps</label><input id="upload" name="upload" type="number" min="0.008" max="10000" step="any" placeholder="Unlimited"></div></div><div class="preset-list">${[{name:'Study · 2 / 1',download:2,upload:1},{name:'Balanced · 10 / 5',download:10,upload:5},...presets].map((p,i)=>`<button type="button" data-preset="${i}">${esc(p.name)}</button>`).join('')}<button type="button" data-action="save-preset">+ Save preset</button></div>`:''}${schedule?`<label for="recurrence">Schedule type</label><select id="recurrence" name="recurrence"><option value="weekly">Recurring weekly window</option><option value="once">One-time window</option></select><div id="weekly-fields"><label for="zone">IANA timezone</label><input id="zone" name="timezone" value="${esc(Intl.DateTimeFormat().resolvedOptions().timeZone)}"><label for="days">Start days (0 = Monday, 6 = Sunday)</label><input id="days" name="days" value="0,1,2,3,4" required><div class="field-pair"><div><label for="start">Start time</label><input id="start" name="start" type="time" value="22:30"></div><div><label for="end">End time</label><input id="end" name="end" type="time" value="06:30"></div></div><p class="hint">An overnight window belongs to its start day. Repeated DST hours follow the same local window.</p></div><div id="once-fields" hidden><label for="starts">Starts at (your local time)</label><input id="starts" name="starts" type="datetime-local"><label for="expires">Ends at (your local time)</label><input id="expires" name="expires" type="datetime-local"></div>`:`<label for="duration">Automatically restore after</label><select id="duration" name="duration"><option value="30">30 minutes</option><option value="60">1 hour</option><option value="120">2 hours</option>${!access?'<option value="">No expiry</option>':''}</select>`}<label class="checkbox-label"><input type="checkbox" required>I confirm this target is authorized for this restriction.</label>`,async f=>{
    const blocked=access||schedule&&f.get('kind')==='block';
    if(!status.capabilities[blocked?'access':'bandwidth']) throw new Error('The adapter does not support this restriction.');
    const target=f.get('device_id'), data={device_id:target,confirm_device_id:target,label:f.get('label'),blocked};
    if(!blocked){if(f.get('download'))data.download_mbps=Number(f.get('download'));if(f.get('upload'))data.upload_mbps=Number(f.get('upload'));}
    if(schedule){if(f.get('recurrence')==='weekly'){data.window={timezone:f.get('timezone'),weekdays:f.get('days').split(',').map(x=>Number(x.trim())),start:f.get('start'),end:f.get('end')};}else{if(!f.get('starts')||!f.get('expires'))throw new Error('Choose both one-time timestamps.');data.starts_at=new Date(f.get('starts')).toISOString();data.expires_at=new Date(f.get('expires')).toISOString();}}
    else if(f.get('duration')) data.expires_at=new Date(Date.now()+Number(f.get('duration'))*60000).toISOString();
    const result=await post('/policies',data);toast(result.simulated?'Simulated policy saved.':'Policy saved and reconciled.');
  },'Confirm & apply');
}
async function actionHandler(action,id){
  if(['limit','pause','schedule'].includes(action))return policyDialog(action,id);
  if(action==='theme'){document.body.classList.toggle('dark');localStorage.setItem('hl-theme',document.body.classList.contains('dark')?'dark':'light');return;}
  if(action==='refresh'){await post('/discover');await render();toast('Inventory refreshed from the configured source.');return;}
  if(action==='remove'){await api('/policies/'+encodeURIComponent(id),{method:'DELETE',body:'{}'});await render();toast('Policy removed.');return;}
  if(action==='resume'){modal('<h2>Restore this device?</h2><p>Remove all HomeLimiter policies for '+esc(name(id))+', including future schedules.</p>',()=>post('/devices/'+encodeURIComponent(id)+'/resume'),'Restore device');return;}
  if(action==='emergency'){modal('<h2>Restore all devices?</h2><p>Remove every HomeLimiter restriction and future policy. This is recorded in your audit log.</p>',()=>post('/emergency',{confirm:true}),'Restore all');return;}
  if(action==='rename'||action==='identify'){
    const d=devices.find(d=>d.id===id);
    modal(`<h2>${action==='identify'?'Confirm this identity':'Edit your device'}</h2><p>Verify the MAC address against the device itself before allowing restrictions.</p><p><code>${esc(d.mac)}</code> · ${esc(d.addresses.join(', '))}</p><label for="nickname">Nickname</label><input id="nickname" name="nickname" value="${esc(d.nickname)}" maxlength="80" required><label class="checkbox-label"><input type="checkbox" name="confirm" ${d.confirmed?'checked':''}>I have verified this device identity.</label><label class="checkbox-label"><input type="checkbox" name="protect" ${d.protected?'checked disabled':''}>Protect this device from restrictions.</label>`,f=>api('/devices/'+encodeURIComponent(id),{method:'PATCH',body:JSON.stringify({nickname:f.get('nickname'),confirm_identity:f.has('confirm'),protect:f.has('protect')})}),'Save device');return;
  }
  if(action==='save-preset'){
    const download=Number($('#download').value)||null,upload=Number($('#upload').value)||null;
    if(!download&&!upload){toast('Enter a cap before saving a preset.');return;}
    if(presets.length>=12){toast('You can save up to 12 custom presets.');return;}
    presets.push({name:`Custom · ${download??'∞'} / ${upload??'∞'}`,download,upload});localStorage.setItem('hl-presets',JSON.stringify(presets));toast('Preset saved for your next limit.');
  }
}
document.addEventListener('click',e=>{
  const button=e.target.closest('[data-action]');if(button&&!button.disabled)actionHandler(button.dataset.action,button.dataset.id).catch(e=>toast(e.message));
  const preset=e.target.closest('[data-preset]');if(preset){const p=[{download:2,upload:1},{download:10,upload:5},...presets][Number(preset.dataset.preset)];if(p){$('#download').value=p.download??'';$('#upload').value=p.upload??'';}}
});
document.addEventListener('input',e=>{if(e.target.matches('#search,#filter'))$('#device-grid').innerHTML=deviceCards($('#search').value,$('#filter').value);});
document.addEventListener('change',e=>{if(e.target.id==='recurrence'){const once=e.target.value==='once';$('#weekly-fields').hidden=once;$('#once-fields').hidden=!once;}});
$('#modal-cancel').onclick=()=>$('#modal').close();
$('#theme').onclick=()=>actionHandler('theme');
$('#logout').onclick=()=>{token='';routeVersion++;$('#app').hidden=true;$('#login').hidden=false;$('#main').replaceChildren();};
$('#login-form').onsubmit=async e=>{e.preventDefault();token=$('#token').value.trim();try{await api('/status');$('#token').value='';$('#login-error').textContent='';$('#login').hidden=true;$('#app').hidden=false;await render();}catch(e){token='';$('#login-error').textContent=e.message;}};
window.addEventListener('hashchange',render);
if(localStorage.getItem('hl-theme')==='dark')document.body.classList.add('dark');
setInterval(()=>{if(token&&!$('#modal').open)render();},30000);
