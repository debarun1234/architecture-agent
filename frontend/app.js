/* ============================================================
   ArchReviewAI — Frontend Application Logic
   ============================================================ */

// Detect environment: use full Cloud Run URL in production, relative paths locally
const API_BASE = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
  ? ''
  : 'https://architecture-review-agent-vtqsnscssq-uc.a.run.app';

// ── State ────────────────────────────────────────────────────
const state = {
  file: null,
  jobId: null,
  results: null,
  eventSource: null,
  polling: null,
};

// ── Init ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  mermaid.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'loose' });
  hljs.highlightAll();
  loadSettings();
  bindEvents();
});

// ── Settings ─────────────────────────────────────────────────
async function loadSettings() {
  const inputModel = document.getElementById('input-model');
  const fallbackDefault = 'gemini-3.1-flash-lite-preview';

  // Populate model list from backend (single source of truth)
  try {
    const { models, default: defaultModel } = await fetch(`${API_BASE}/api/models`).then(r => r.json());
    inputModel.innerHTML = models.map(m =>
      `<option value="${m.value}">${m.label}${m.badge ? ` — ${m.badge}` : ''}</option>`
    ).join('');
    const stored = localStorage.getItem('gemini_model') || defaultModel;
    const valid = models.some(m => m.value === stored);
    inputModel.value = valid ? stored : defaultModel;
  } catch {
    // If API is unreachable, keep whatever options are in the HTML and use fallback
    const stored = localStorage.getItem('gemini_model') || fallbackDefault;
    const valid = Array.from(inputModel.options).some(o => o.value === stored);
    inputModel.value = valid ? stored : fallbackDefault;
  }
}

function saveSettings() {
  const model = document.getElementById('input-model').value;
  localStorage.setItem('gemini_model', model);
  closeModal();
}

function openModal() { document.getElementById('settings-modal').classList.add('open'); }
function closeModal() { document.getElementById('settings-modal').classList.remove('open'); }

// ── Event Bindings ────────────────────────────────────────────
function bindEvents() {
  // Settings
  document.getElementById('btn-settings').addEventListener('click', openModal);
  document.getElementById('modal-close').addEventListener('click', closeModal);
  document.getElementById('modal-cancel').addEventListener('click', closeModal);
  document.getElementById('modal-save').addEventListener('click', saveSettings);
  document.getElementById('settings-modal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeModal();
  });

  // File upload
  const dropZone = document.getElementById('drop-zone');
  const fileInput = document.getElementById('file-input');
  document.getElementById('btn-browse').addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', (e) => { if (e.target.files[0]) setFile(e.target.files[0]); });
  dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault(); dropZone.classList.remove('drag-over');
    if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]);
  });
  document.getElementById('btn-remove').addEventListener('click', removeFile);

  // Analyze
  document.getElementById('btn-analyze').addEventListener('click', startAnalysis);

  // Results actions
  document.getElementById('btn-new').addEventListener('click', resetToUpload);
  document.getElementById('btn-export').addEventListener('click', exportJSON);
  document.getElementById('btn-copy-openapi').addEventListener('click', copyOpenAPI);

  // Tabs
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Artifact sub-tabs
  document.querySelectorAll('.artifact-tab').forEach(btn => {
    btn.addEventListener('click', () => switchArtifactTab(btn.dataset.artifact));
  });

  // Guidelines filter
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => filterGuidelines(btn.dataset.filter, btn));
  });

  // Proposal accordion
  document.getElementById('proposals-list').addEventListener('click', (e) => {
    const header = e.target.closest('.prop-header');
    if (!header) return;
    const body = header.nextElementSibling;
    body.classList.toggle('open');
  });

  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeModal();
      closeFullscreen();
    }
  });

  // Fullscreen diagram
  document.getElementById('btn-fullscreen-diagram').addEventListener('click', openFullscreen);
  document.getElementById('fullscreen-close').addEventListener('click', closeFullscreen);
  document.getElementById('fullscreen-overlay').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeFullscreen();
  });
}

// ── Toast Notifications ──────────────────────────────────────
function showToast(msg, type = 'success') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  requestAnimationFrame(() => {
    requestAnimationFrame(() => toast.classList.add('show'));
  });
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 350);
  }, 3000);
}

// ── Fullscreen Diagram ────────────────────────────────────────
function openFullscreen() {
  const overlay = document.getElementById('fullscreen-overlay');
  const src = document.getElementById('mermaid-container').innerHTML;
  document.getElementById('fullscreen-diagram').innerHTML = src;
  overlay.classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeFullscreen() {
  document.getElementById('fullscreen-overlay').classList.remove('open');
  document.body.style.overflow = '';
}

// ── File Handling ─────────────────────────────────────────────
function setFile(file) {
  state.file = file;
  document.getElementById('drop-zone').hidden = true;
  const preview = document.getElementById('file-preview');
  preview.hidden = false;
  document.getElementById('file-name').textContent = file.name;
  document.getElementById('file-size').textContent = formatBytes(file.size);
  checkAnalyzeReady();
}

function removeFile() {
  state.file = null;
  document.getElementById('drop-zone').hidden = false;
  document.getElementById('file-preview').hidden = true;
  document.getElementById('file-input').value = '';
  checkAnalyzeReady();
}

function checkAnalyzeReady() {
  document.getElementById('btn-analyze').disabled = !state.file;
}

// ── Analysis ─────────────────────────────────────────────────
async function startAnalysis() {
  const model = document.getElementById('input-model').value;

  if (!state.file) { alert('Please upload a document.'); return; }

  // Switch to analysis section
  document.getElementById('upload-section').classList.add('hidden');
  document.getElementById('analysis-section').classList.remove('hidden');
  document.getElementById('error-banner').classList.add('hidden');
  document.getElementById('results-panel').classList.add('hidden');

  // Toggle button loading state
  setAnalyzeLoading(true);
  resetSteps();

  const formData = new FormData();
  formData.append('document', state.file);
  formData.append('model', model);

  try {
    const resp = await fetch(`${API_BASE}/api/analyze`, { method: 'POST', body: formData });
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || 'Server error');
    }
    const data = await resp.json();
    state.jobId = data.job_id;
    startPolling();
  } catch (err) {
    showError(err.message);
    setAnalyzeLoading(false);
  }
}

function startPolling() {
  if (state.polling) clearInterval(state.polling);
  state.polling = setInterval(async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/status/${state.jobId}`);
      const data = await resp.json();
      updateProgress(data);
      if (data.status === 'complete') {
        clearInterval(state.polling);
        fetchResults();
      } else if (data.status === 'error') {
        clearInterval(state.polling);
        showError(data.error || 'Unknown error');
        setAnalyzeLoading(false);
      }
    } catch (e) { /* network hiccup, retry next tick */ }
  }, 800);
}

async function fetchResults() {
  const resp = await fetch(`${API_BASE}/api/results/${state.jobId}`);
  state.results = await resp.json();
  setAnalyzeLoading(false);
  renderResults(state.results);
}

function updateProgress(data) {
  const pct = data.progress || 0;
  document.getElementById('progress-bar').style.width = pct + '%';
  document.getElementById('progress-pct').textContent = pct + '%';
  const steps = data.steps || {};
  Object.keys(steps).forEach(n => {
    const el = document.getElementById(`step-${n}`);
    if (!el) return;
    const s = steps[n];
    el.classList.remove('active', 'complete');
    if (s.status === 'complete') el.classList.add('complete');
    else if (s.status === 'running') el.classList.add('active');
  });
}

// ── Render Results ────────────────────────────────────────────
function renderResults(results) {
  document.getElementById('results-panel').classList.remove('hidden');
  renderContext(results.context || {});
  renderGuidelines(results.retrieved_guidelines || []);
  renderBottlenecks(results.bottlenecks || {});
  renderProposals(results.proposed_changes || {});
  renderArtifacts(results.artifacts || {});
  renderCitations(results.citations || [], results.verification_notes || {});
  updateTabBadges(results);
  switchTab('context');
  showToast('Architecture review complete!', 'success');
}

function updateTabBadges(results) {
  const counts = {
    'badge-guidelines': (results.retrieved_guidelines || []).length,
    'badge-bottlenecks': ((results.bottlenecks || {}).bottlenecks || []).length,
    'badge-proposals': ((results.proposed_changes || {}).proposals || []).length,
    'badge-citations': (results.citations || []).length,
  };
  Object.entries(counts).forEach(([id, count]) => {
    const el = document.getElementById(id);
    if (el) el.textContent = count > 0 ? count : '';
  });
}

// Context
function renderContext(ctx) {
  const grid = document.getElementById('context-grid');
  grid.innerHTML = '';

  const cards = [
    {
      title: 'System Overview',
      items: [
        ['System Name', ctx.system_name],
        ['Document Type', ctx.document_type],
        ['Document Title', ctx.document_title],
        ['Deployment Model', ctx.deployment_model],
        ['Cloud Provider', ctx.cloud_provider],
      ]
    },
    {
      title: 'Traffic Expectations',
      items: Object.entries(ctx.traffic_expectations || {}).map(([k, v]) => [k.replace(/_/g, ' '), v])
    },
    {
      title: 'Reliability Requirements',
      items: Object.entries(ctx.reliability_requirements || {}).map(([k, v]) => [k.toUpperCase(), v])
    },
    {
      title: 'Architectural Patterns',
      tags: ctx.architectural_patterns || []
    },
    {
      title: 'Components',
      list: (ctx.components || []).map(c => `${c.name} (${c.type}) — ${c.technology || 'N/A'}`)
    },
    {
      title: 'Security Mechanisms',
      list: (ctx.security_mechanisms || []).map(s => s.mechanism)
    },
    {
      title: 'Data Stores',
      list: (ctx.data_stores || []).map(d => `${d.name}: ${d.technology} (${d.type})`)
    },
    {
      title: 'Notable Gaps',
      list: ctx.notable_gaps || []
    }
  ];

  cards.forEach(card => {
    const el = makeCtxCard(card);
    if (el) grid.appendChild(el);
  });
}

function makeCtxCard({ title, items, tags, list }) {
  const card = document.createElement('div');
  card.className = 'ctx-card';
  card.innerHTML = `<div class="ctx-card-title">${title}</div>`;

  if (tags && tags.length) {
    const tagDiv = document.createElement('div');
    tagDiv.className = 'ctx-list';
    tags.forEach(t => {
      const span = document.createElement('span');
      span.className = 'ctx-tag'; span.textContent = t;
      tagDiv.appendChild(span);
    });
    card.appendChild(tagDiv);
    return card;
  }
  if (list && list.length) {
    list.forEach(txt => {
      const row = document.createElement('div');
      row.className = 'ctx-item';
      row.innerHTML = `<span class="ctx-val">${esc(txt)}</span>`;
      card.appendChild(row);
    });
    return card;
  }
  if (items) {
    items.forEach(([k, v]) => {
      if (!v || v === 'Not specified') return;
      const row = document.createElement('div');
      row.className = 'ctx-item';
      row.innerHTML = `<span class="ctx-key">${esc(k)}</span><span class="ctx-val">${esc(v)}</span>`;
      card.appendChild(row);
    });
    if (card.children.length === 1) return null; // Empty card
    return card;
  }
  return card;
}

// Guidelines
let _allGuidelines = [];
function renderGuidelines(guidelines) {
  _allGuidelines = guidelines;
  filterGuidelines('all', document.querySelector('.filter-btn[data-filter="all"]'));
}

function filterGuidelines(filter, btn) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');

  const filtered = filter === 'all' ? _allGuidelines : _allGuidelines.filter(g => g.collection === filter);
  const list = document.getElementById('guidelines-list');
  list.innerHTML = '';
  filtered.forEach(g => list.appendChild(makeGuidelineCard(g)));
}

function makeGuidelineCard(g) {
  const el = document.createElement('div');
  el.className = 'guideline-card';
  el.dataset.collection = g.collection;
  el.innerHTML = `
    <div class="guideline-header">
      <span class="guideline-id">${esc(g.source_id)}</span>
      <span class="guideline-collection">${esc(g.collection?.replace(/_/g, ' '))}</span>
      <span class="guideline-score">${(g.score * 100).toFixed(0)}% match</span>
    </div>
    <div class="guideline-ref">${esc(g.section_reference)}</div>
    <div class="guideline-text">${esc(g.guideline_summary)}</div>
  `;
  return el;
}

// Bottlenecks
function renderBottlenecks(data) {
  const bns = data.bottlenecks || [];
  const summary = data.summary || {};
  const sumEl = document.getElementById('bn-summary');
  sumEl.innerHTML = `
    <div class="bn-stat"><div class="bn-stat-num">${summary.total_issues || bns.length}</div><div class="bn-stat-label">Total Issues</div></div>
    <div class="bn-stat high"><div class="bn-stat-num">${summary.high_severity || 0}</div><div class="bn-stat-label">High Severity</div></div>
    <div class="bn-stat medium"><div class="bn-stat-num">${summary.medium_severity || 0}</div><div class="bn-stat-label">Medium Severity</div></div>
    <div class="bn-stat low"><div class="bn-stat-num">${summary.low_severity || 0}</div><div class="bn-stat-label">Low Severity</div></div>
  `;
  const list = document.getElementById('bottlenecks-list');
  list.innerHTML = '';
  bns.forEach(bn => {
    const el = document.createElement('div');
    el.className = `bn-card ${bn.severity}`;
    el.innerHTML = `
      <div class="bn-header">
        <span class="bn-id">${esc(bn.id)}</span>
        <span class="severity-badge ${bn.severity}">${bn.severity?.toUpperCase()}</span>
        <span class="area-badge">${esc(bn.area)}</span>
      </div>
      <div class="bn-title">${esc(bn.title)}</div>
      <div class="bn-desc">${esc(bn.description)}</div>
      ${bn.supporting_evidence ? `<div class="bn-evidence">Evidence: ${esc(bn.supporting_evidence)}</div>` : ''}
    `;
    list.appendChild(el);
  });
}

// Proposals
function renderProposals(data) {
  const proposals = data.proposals || [];
  const quickWins = data.quick_wins || [];
  const roadmap = data.roadmap || {};

  const phdr = document.getElementById('proposals-header');
  phdr.innerHTML = '';
  if (quickWins.length) {
    const div = document.createElement('div');
    div.innerHTML = `<p style="font-size:0.8rem;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;">⚡ Quick Wins</p>`;
    quickWins.forEach(qw => {
      const el = document.createElement('div');
      el.className = 'quick-win';
      el.innerHTML = `<span>→</span><span>${esc(qw)}</span>`;
      div.appendChild(el);
    });
    phdr.appendChild(div);
  }

  const list = document.getElementById('proposals-list');
  list.innerHTML = '';
  proposals.forEach(p => {
    const el = document.createElement('div');
    el.className = 'prop-card';
    const changes = (p.recommended_changes || []).map(c => `
      <div class="change-item">
        <div class="change-type">${esc(c.change_type)} — ${esc(c.component)}</div>
        <div class="change-desc">${esc(c.description)}</div>
      </div>
    `).join('');

    const impact = p.impact_analysis || {};
    const impactHtml = ['cost', 'performance', 'operations', 'security'].map(area => `
      <div class="impact-item">
        <div class="impact-area">${area}</div>
        <div class="impact-val ${impact[area] || 'neutral'}">${(impact[area] || 'neutral').toUpperCase()}</div>
        <div class="impact-detail">${esc(impact[`${area}_detail`] || '')}</div>
      </div>
    `).join('');

    el.innerHTML = `
      <div class="prop-header">
        <span class="prop-id">${esc(p.id)} → ${esc(p.addresses_bottleneck)}</span>
        <span class="prop-title">${esc(p.title)}</span>
        <span class="effort-badge ${p.effort}">${esc(p.effort)}</span>
        <span class="priority-badge">${esc(p.priority)}</span>
      </div>
      <div class="prop-body">
        <div class="prop-section">
          <div class="prop-section-title">Rationale</div>
          <div class="prop-rationale">${esc(p.rationale)}</div>
        </div>
        ${changes ? `<div class="prop-section"><div class="prop-section-title">Recommended Changes</div><div class="changes-list">${changes}</div></div>` : ''}
        <div class="prop-section">
          <div class="prop-section-title">Impact Analysis</div>
          <div class="impact-grid">${impactHtml}</div>
        </div>
        ${p.tradeoffs ? `
        <div class="prop-section">
          <div class="prop-section-title">Tradeoffs</div>
          <div class="prop-rationale">
            <strong>Pros:</strong> ${esc((p.tradeoffs.pros || []).join('; '))}<br/>
            <strong>Cons:</strong> ${esc((p.tradeoffs.cons || []).join('; '))}
          </div>
        </div>` : ''}
      </div>
    `;
    list.appendChild(el);
  });

  const rm = document.getElementById('roadmap');
  if (Object.keys(roadmap).length) {
    rm.innerHTML = `
      <div class="roadmap-title">📅 Implementation Roadmap</div>
      <div class="roadmap-phases">
        <div class="roadmap-phase">
          <div class="phase-label p1">Phase 1 — Immediate</div>
          ${(roadmap.phase_1_immediate || []).map(i => `<div class="phase-item">${esc(i)}</div>`).join('')}
        </div>
        <div class="roadmap-phase">
          <div class="phase-label p2">Phase 2 — Short Term</div>
          ${(roadmap.phase_2_short_term || []).map(i => `<div class="phase-item">${esc(i)}</div>`).join('')}
        </div>
        <div class="roadmap-phase">
          <div class="phase-label p3">Phase 3 — Long Term</div>
          ${(roadmap.phase_3_long_term || []).map(i => `<div class="phase-item">${esc(i)}</div>`).join('')}
        </div>
      </div>
    `;
  }
}

// Artifacts
async function renderArtifacts(artifacts) {
  // Mermaid
  const mermaidSrc = artifacts.mermaid_diagram || 'sequenceDiagram\n  Note over System: No diagram generated';
  const container = document.getElementById('mermaid-container');
  try {
    const { svg } = await mermaid.render('mermaid-svg', mermaidSrc);
    container.innerHTML = svg;
  } catch (e) {
    container.innerHTML = `<pre style="color:var(--text-muted);font-size:0.8rem;">${esc(mermaidSrc)}</pre>`;
  }

  // OpenAPI
  const codeEl = document.getElementById('openapi-code');
  codeEl.textContent = artifacts.openapi_spec || '# No OpenAPI spec generated';
  hljs.highlightElement(codeEl);

  // Summary
  const summaryEl = document.getElementById('summary-content');
  summaryEl.innerHTML = markdownToHtml(artifacts.review_summary || 'No summary generated.');
}

// Citations
function renderCitations(citations, notes) {
  const stats = document.getElementById('citations-stats');
  const verified = citations.filter(c => c.verification_status === 'verified').length;
  const nie = citations.filter(c => c.verification_status === 'not_in_evidence').length;
  const partial = citations.filter(c => c.verification_status === 'partially_verified').length;
  stats.innerHTML = `
    <div class="cit-stat"><div class="cit-stat-num">${citations.length}</div><div class="cit-stat-label">Total Citations</div></div>
    <div class="cit-stat"><div class="cit-stat-num" style="color:var(--success)">${verified}</div><div class="cit-stat-label">Verified</div></div>
    <div class="cit-stat"><div class="cit-stat-num" style="color:var(--warning)">${partial}</div><div class="cit-stat-label">Partial</div></div>
    <div class="cit-stat"><div class="cit-stat-num" style="color:var(--danger)">${nie}</div><div class="cit-stat-label">Not in Evidence</div></div>
  `;

  const list = document.getElementById('citations-list');
  list.innerHTML = '';
  citations.forEach(c => {
    const el = document.createElement('div');
    el.className = 'cit-card';
    el.innerHTML = `
      <div class="cit-header">
        <span class="cit-finding">${esc(c.finding_id)}</span>
        <span class="cit-status ${c.verification_status}">${esc(c.verification_status?.replace(/_/g, ' '))}</span>
      </div>
      <div class="cit-title">${esc(c.finding_title)}</div>
      <div class="cit-claim">${esc(c.claim)}</div>
      <div class="cit-source">
        <span>Source: ${esc(c.source_id)}</span>
        <span>${esc(c.section_reference)}</span>
      </div>
    `;
    list.appendChild(el);
  });

  const vn = document.getElementById('verification-notes');
  if (notes.reviewer_notes) {
    vn.innerHTML = `
      <div class="vn-title">Reviewer Notes</div>
      <div class="vn-text">${esc(notes.reviewer_notes)}</div>
    `;
  }
}

// ── Tab Switching ─────────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.toggle('active', p.id === `tab-${name}`));
}

function switchArtifactTab(name) {
  document.querySelectorAll('.artifact-tab').forEach(t => t.classList.toggle('active', t.dataset.artifact === name));
  document.querySelectorAll('.artifact-pane').forEach(p => p.classList.toggle('active', p.id === `artifact-${name}`));
}

// ── Utilities ─────────────────────────────────────────────────
function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function formatBytes(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

function setAnalyzeLoading(loading) {
  const btn = document.getElementById('btn-analyze');
  btn.querySelector('.btn-text').classList.toggle('hidden', loading);
  btn.querySelector('.btn-spinner').classList.toggle('hidden', !loading);
  btn.disabled = loading;
}

function resetSteps() {
  document.querySelectorAll('.step-item').forEach(el => el.classList.remove('active', 'complete'));
  document.getElementById('progress-bar').style.width = '0%';
  document.getElementById('progress-pct').textContent = '0%';
}

function showError(msg) {
  document.getElementById('error-banner').classList.remove('hidden');
  document.getElementById('error-msg').textContent = msg;
}

function resetToUpload() {
  if (state.polling) clearInterval(state.polling);
  state.jobId = null; state.results = null;
  document.getElementById('analysis-section').classList.add('hidden');
  document.getElementById('upload-section').classList.remove('hidden');
}

function exportJSON() {
  if (!state.results) return;
  const blob = new Blob([JSON.stringify(state.results, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'architecture_review.json';
  a.click();
  showToast('Exported architecture_review.json', 'info');
}

function copyOpenAPI() {
  const code = document.getElementById('openapi-code').textContent;
  navigator.clipboard.writeText(code).then(() => {
    showToast('OpenAPI spec copied to clipboard', 'info');
  }).catch(() => {
    showToast('Failed to copy — try selecting and copying manually', 'error');
  });
}

// Simple markdown → HTML converter (headings, bold, lists, hr, code)
function markdownToHtml(md) {
  return md
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/^#{3} (.+)$/gm, '<h3>$1</h3>')
    .replace(/^#{2} (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/^---$/gm, '<hr>')
    .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
    .replace(/^[-*] (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, m => `<ul>${m}</ul>`)
    .replace(/\n\n/g, '</p><p>')
    .replace(/^(?!<[hul]|<hr|<p)(.+)$/gm, '<p>$1</p>')
    .replace(/<p><\/p>/g, '');
}
