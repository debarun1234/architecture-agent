'use client';

import { useState, lazy, Suspense } from 'react';
import {
  Download, RotateCcw, Copy, Check, ChevronDown, ChevronUp,
  AlertTriangle, CheckCircle2, BookOpen, Lightbulb, Layers,
  Quote, FileText, BarChart3,
} from 'lucide-react';
import type {
  AnalysisResults, Bottleneck, Proposal, Guideline, Citation,
} from '@/lib/types';

const MermaidDiagram = lazy(() => import('./MermaidDiagram'));

// ── Helpers ──────────────────────────────────────────────────────────────────

function esc(s: unknown): string {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function mdToHtml(md: string): string {
  return md
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/^#{3} (.+)$/gm, '<h3 class="text-base font-bold text-slate-800 mt-5 mb-2">$1</h3>')
    .replace(/^#{2} (.+)$/gm, '<h2 class="text-lg font-bold text-slate-900 mt-6 mb-2 pb-2 border-b border-slate-200">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-xl font-extrabold text-slate-900 mt-4 mb-3">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-slate-900">$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code class="px-1.5 py-0.5 rounded bg-slate-100 text-indigo-700 font-mono-custom text-xs">$1</code>')
    .replace(/^---$/gm, '<hr class="my-4 border-slate-200">')
    .replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal text-slate-600 text-sm leading-relaxed">$1</li>')
    .replace(/^[-*] (.+)$/gm, '<li class="ml-4 list-disc text-slate-600 text-sm leading-relaxed">$1</li>')
    .replace(/(<li[\s\S]*?<\/li>\n?)+/g, (m) => `<ul class="my-2 space-y-1">${m}</ul>`)
    .replace(/\n\n/g, '</p><p class="text-sm text-slate-600 leading-relaxed mb-2">')
    .replace(/^(?!<[hul]|<hr|<p)(.+)$/gm, '<p class="text-sm text-slate-600 leading-relaxed mb-2">$1</p>')
    .replace(/<p[^>]*><\/p>/g, '');
}

function copyToClipboard(text: string, setCopied: (v: boolean) => void) {
  navigator.clipboard.writeText(text).then(() => {
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  });
}

function downloadJSON(data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `arch-review-${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Severity / Status styles ─────────────────────────────────────────────────

const sev: Record<string, string> = {
  high:   'bg-red-50 text-red-700 border-red-200',
  medium: 'bg-amber-50 text-amber-700 border-amber-200',
  low:    'bg-emerald-50 text-emerald-700 border-emerald-200',
};
const sevBorder: Record<string, string> = {
  high:   'border-l-red-400',
  medium: 'border-l-amber-400',
  low:    'border-l-emerald-400',
};
const effort: Record<string, string> = {
  low:    'bg-emerald-50 text-emerald-700 border-emerald-200',
  medium: 'bg-amber-50 text-amber-700 border-amber-200',
  high:   'bg-red-50 text-red-700 border-red-200',
};
const priority: Record<string, string> = {
  immediate:  'bg-red-50 text-red-600 border-red-200',
  short_term: 'bg-amber-50 text-amber-600 border-amber-200',
  long_term:  'bg-emerald-50 text-emerald-600 border-emerald-200',
};
const citStatus: Record<string, string> = {
  verified:           'bg-emerald-50 text-emerald-700 border-emerald-200',
  partially_verified: 'bg-amber-50 text-amber-700 border-amber-200',
  not_in_evidence:    'bg-red-50 text-red-700 border-red-200',
};
const colBadge: Record<string, string> = {
  architecture_principles: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  design_patterns:         'bg-sky-50 text-sky-700 border-sky-200',
  anti_patterns:           'bg-amber-50 text-amber-700 border-amber-200',
  security_guidelines:     'bg-rose-50 text-rose-700 border-rose-200',
  cloud_reference:         'bg-emerald-50 text-emerald-700 border-emerald-200',
};
const impactColor: Record<string, string> = {
  increase: 'text-red-600 font-semibold',
  decrease: 'text-emerald-600 font-semibold',
  neutral:  'text-slate-500',
};

// ── Tab config ────────────────────────────────────────────────────────────────

type TabId = 'context' | 'guidelines' | 'bottlenecks' | 'proposals' | 'artifacts' | 'citations';

interface TabConfig {
  id: TabId;
  label: string;
  icon: React.ReactNode;
  count?: number;
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function Badge({ className, children }: { className: string; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border ${className}`}>
      {children}
    </span>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-3">{children}</h3>
  );
}

function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-white rounded-xl border border-slate-200 p-5 ${className}`}>{children}</div>
  );
}

// ── Context Tab ───────────────────────────────────────────────────────────────

function ContextTab({ ctx }: { ctx: AnalysisResults['context'] }) {
  const metaRows = [
    ['Document Title', ctx.document_title],
    ['Document Type', ctx.document_type],
    ['System Name', ctx.system_name],
    ['Cloud Provider', ctx.cloud_provider],
    ['Deployment Model', ctx.deployment_model],
  ].filter(([, v]) => v && v !== 'Not specified') as [string, string][];

  return (
    <div className="space-y-5 tab-enter">
      {/* Meta */}
      {metaRows.length > 0 && (
        <Card>
          <SectionTitle>System Overview</SectionTitle>
          <dl className="divide-y divide-slate-100">
            {metaRows.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 py-2">
                <dt className="text-xs text-slate-400">{k}</dt>
                <dd className="text-xs font-semibold text-slate-700 text-right">{v}</dd>
              </div>
            ))}
          </dl>
        </Card>
      )}

      {/* Traffic & Reliability */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {ctx.traffic_expectations && Object.keys(ctx.traffic_expectations).length > 0 && (
          <Card>
            <SectionTitle>Traffic Expectations</SectionTitle>
            <dl className="divide-y divide-slate-100">
              {Object.entries(ctx.traffic_expectations).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3 py-2">
                  <dt className="text-xs text-slate-400 capitalize">{k.replace(/_/g, ' ')}</dt>
                  <dd className="text-xs font-semibold text-slate-700">{v}</dd>
                </div>
              ))}
            </dl>
          </Card>
        )}
        {ctx.reliability_requirements && Object.keys(ctx.reliability_requirements).length > 0 && (
          <Card>
            <SectionTitle>Reliability Requirements</SectionTitle>
            <dl className="divide-y divide-slate-100">
              {Object.entries(ctx.reliability_requirements).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3 py-2">
                  <dt className="text-xs text-slate-400 uppercase">{k}</dt>
                  <dd className="text-xs font-semibold text-slate-700">{v}</dd>
                </div>
              ))}
            </dl>
          </Card>
        )}
      </div>

      {/* Patterns */}
      {(ctx.architectural_patterns?.length ?? 0) > 0 && (
        <Card>
          <SectionTitle>Architectural Patterns</SectionTitle>
          <div className="flex flex-wrap gap-2">
            {ctx.architectural_patterns!.map((p) => (
              <span key={p} className="px-3 py-1 rounded-full bg-indigo-50 border border-indigo-100 text-xs font-medium text-indigo-700">{p}</span>
            ))}
          </div>
        </Card>
      )}

      {/* Components */}
      {(ctx.components?.length ?? 0) > 0 && (
        <Card>
          <SectionTitle>Components ({ctx.components!.length})</SectionTitle>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {ctx.components!.map((c, i) => (
              <div key={i} className="flex items-start gap-2 p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                <Layers className="w-3.5 h-3.5 text-indigo-400 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-xs font-semibold text-slate-700">{c.name}</p>
                  <p className="text-[11px] text-slate-400">{c.type}{c.technology ? ` · ${c.technology}` : ''}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Security + Data stores */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {(ctx.security_mechanisms?.length ?? 0) > 0 && (
          <Card>
            <SectionTitle>Security Mechanisms</SectionTitle>
            <ul className="space-y-1.5">
              {ctx.security_mechanisms!.map((s, i) => (
                <li key={i} className="flex items-center gap-2 text-xs text-slate-600">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                  {s.mechanism}
                </li>
              ))}
            </ul>
          </Card>
        )}
        {(ctx.data_stores?.length ?? 0) > 0 && (
          <Card>
            <SectionTitle>Data Stores</SectionTitle>
            <ul className="space-y-1.5">
              {ctx.data_stores!.map((d, i) => (
                <li key={i} className="text-xs text-slate-600">
                  <span className="font-semibold">{d.name}</span>
                  <span className="text-slate-400"> · {d.technology} ({d.type})</span>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>

      {/* Notable gaps */}
      {(ctx.notable_gaps?.length ?? 0) > 0 && (
        <Card className="border-amber-200 bg-amber-50/30">
          <SectionTitle>Notable Gaps</SectionTitle>
          <ul className="space-y-2">
            {ctx.notable_gaps!.map((g, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-amber-800">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0 mt-0.5" />
                {g}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

// ── Guidelines Tab ────────────────────────────────────────────────────────────

const COLLECTIONS = [
  { id: 'all', label: 'All' },
  { id: 'architecture_principles', label: 'Principles' },
  { id: 'design_patterns', label: 'Patterns' },
  { id: 'anti_patterns', label: 'Anti-Patterns' },
  { id: 'security_guidelines', label: 'Security' },
  { id: 'cloud_reference', label: 'Cloud Ref' },
];

function GuidelinesTab({ guidelines }: { guidelines: Guideline[] }) {
  const [filter, setFilter] = useState('all');
  const filtered = filter === 'all' ? guidelines : guidelines.filter((g) => g.collection === filter);

  return (
    <div className="tab-enter">
      <div className="flex gap-2 flex-wrap mb-5">
        {COLLECTIONS.map((c) => {
          const count = c.id === 'all' ? guidelines.length : guidelines.filter((g) => g.collection === c.id).length;
          return (
            <button
              key={c.id}
              onClick={() => setFilter(c.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all border ${
                filter === c.id
                  ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm'
                  : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300'
              }`}
            >
              {c.label}
              <span className={`px-1.5 py-0 rounded-full text-[10px] ${filter === c.id ? 'bg-indigo-500 text-white' : 'bg-slate-100 text-slate-500'}`}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      <div className="space-y-3 max-h-[600px] overflow-y-auto pr-1">
        {filtered.length === 0 && (
          <p className="text-sm text-slate-400 text-center py-8">No guidelines in this category.</p>
        )}
        {filtered.map((g, i) => (
          <div key={i} className="bg-white rounded-xl border border-slate-200 p-4 hover:border-slate-300 transition-colors">
            <div className="flex items-center gap-2 flex-wrap mb-2">
              <span className="font-mono-custom text-[11px] bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded border border-indigo-100 font-semibold">
                {g.source_id}
              </span>
              <Badge className={colBadge[g.collection] || 'bg-slate-50 text-slate-600 border-slate-200'}>
                {g.collection?.replace(/_/g, ' ')}
              </Badge>
              <span className="ml-auto text-[11px] font-semibold text-emerald-600 font-mono-custom">
                {(g.score * 100).toFixed(0)}% match
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mb-1.5">{g.section_reference}</p>
            <p className="text-sm text-slate-600 leading-relaxed">{g.guideline_summary}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Bottlenecks Tab ───────────────────────────────────────────────────────────

function BottlenecksTab({ data }: { data: AnalysisResults['bottlenecks'] }) {
  const bns: Bottleneck[] = data?.bottlenecks ?? [];
  const s = data?.summary ?? { total_issues: 0, high_severity: 0, medium_severity: 0, low_severity: 0 };

  return (
    <div className="tab-enter">
      {/* Stats */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        {[
          { label: 'Total', value: s.total_issues || bns.length, color: 'text-slate-700' },
          { label: 'High', value: s.high_severity, color: 'text-red-600' },
          { label: 'Medium', value: s.medium_severity, color: 'text-amber-600' },
          { label: 'Low', value: s.low_severity, color: 'text-emerald-600' },
        ].map((stat) => (
          <div key={stat.label} className="bg-white rounded-xl border border-slate-200 p-4 text-center">
            <p className={`text-2xl font-extrabold font-mono-custom ${stat.color}`}>{stat.value}</p>
            <p className="text-[11px] text-slate-400 uppercase tracking-wide mt-1">{stat.label}</p>
          </div>
        ))}
      </div>
      {s.most_critical_area && (
        <p className="text-xs text-slate-500 mb-4">
          Most critical area: <span className="font-semibold text-slate-700 capitalize">{s.most_critical_area}</span>
        </p>
      )}

      {/* Cards */}
      <div className="space-y-3">
        {bns.map((bn) => (
          <div
            key={bn.id}
            className={`bg-white rounded-xl border border-l-4 p-5 ${sevBorder[bn.severity] ?? 'border-l-slate-300'} border-slate-200`}
          >
            <div className="flex items-center gap-2 flex-wrap mb-3">
              <span className="font-mono-custom text-[11px] text-slate-400 bg-slate-50 px-2 py-0.5 rounded border border-slate-200">
                {bn.id}
              </span>
              <Badge className={sev[bn.severity] ?? 'bg-slate-50 text-slate-600 border-slate-200'}>
                {bn.severity?.toUpperCase()}
              </Badge>
              <Badge className="bg-slate-50 text-slate-600 border-slate-200 capitalize">
                {bn.area?.replace(/_/g, ' ')}
              </Badge>
            </div>
            <p className="text-sm font-bold text-slate-800 mb-2">{bn.title}</p>
            <p className="text-sm text-slate-600 leading-relaxed mb-3">{bn.description}</p>
            {bn.supporting_evidence && (
              <div className="flex items-start gap-2 bg-slate-50 border border-slate-100 rounded-lg px-3 py-2.5">
                <Quote className="w-3.5 h-3.5 text-slate-400 flex-shrink-0 mt-0.5" />
                <p className="text-xs text-slate-500 italic leading-relaxed">{bn.supporting_evidence}</p>
              </div>
            )}
            {(bn.affected_components?.length ?? 0) > 0 && (
              <div className="flex gap-1.5 flex-wrap mt-3">
                {bn.affected_components!.map((c) => (
                  <span key={c} className="text-[11px] px-2 py-0.5 rounded bg-slate-50 border border-slate-200 text-slate-500">
                    {c}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Proposals Tab ─────────────────────────────────────────────────────────────

function ProposalsTab({ data }: { data: AnalysisResults['proposed_changes'] }) {
  const [open, setOpen] = useState<Set<string>>(new Set());
  const proposals: Proposal[] = data?.proposals ?? [];
  const quickWins: string[] = data?.quick_wins ?? [];
  const roadmap = data?.roadmap ?? {};

  const toggle = (id: string) =>
    setOpen((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });

  return (
    <div className="tab-enter space-y-6">
      {/* Quick wins */}
      {quickWins.length > 0 && (
        <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-4">
          <p className="text-[10px] font-bold uppercase tracking-widest text-indigo-500 mb-3">⚡ Quick Wins</p>
          <ul className="space-y-2">
            {quickWins.map((qw, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-indigo-800">
                <span className="text-indigo-400 mt-0.5">→</span>
                {qw}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Proposals */}
      <div className="space-y-3">
        {proposals.map((p) => {
          const isOpen = open.has(p.id);
          return (
            <div key={p.id} className="bg-white rounded-xl border border-slate-200 overflow-hidden">
              <button
                onClick={() => toggle(p.id)}
                className="w-full flex items-center gap-3 p-5 text-left hover:bg-slate-50 transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1.5">
                    <span className="font-mono-custom text-[11px] text-slate-400">
                      {p.id} → {p.addresses_bottleneck}
                    </span>
                    <Badge className={effort[p.effort] ?? 'bg-slate-50 text-slate-600 border-slate-200'}>
                      {p.effort} effort
                    </Badge>
                    <Badge className={priority[p.priority] ?? 'bg-slate-50 text-slate-600 border-slate-200'}>
                      {p.priority?.replace(/_/g, ' ')}
                    </Badge>
                  </div>
                  <p className="text-sm font-bold text-slate-800">{p.title}</p>
                </div>
                {isOpen ? <ChevronUp className="w-4 h-4 text-slate-400 flex-shrink-0" /> : <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" />}
              </button>

              <div className={`proposal-body ${isOpen ? 'open' : ''}`}>
                <div className="px-5 pb-5 border-t border-slate-100 space-y-4 pt-4">
                  <div>
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Rationale</p>
                    <p className="text-sm text-slate-600 leading-relaxed">{p.rationale}</p>
                  </div>

                  {(p.recommended_changes?.length ?? 0) > 0 && (
                    <div>
                      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">Recommended Changes</p>
                      <div className="space-y-2">
                        {p.recommended_changes!.map((c, i) => (
                          <div key={i} className="border-l-2 border-indigo-200 pl-3 py-1">
                            <p className="text-[11px] font-bold text-indigo-600 uppercase tracking-wide mb-0.5">
                              {c.change_type} — {c.component}
                            </p>
                            <p className="text-xs text-slate-600">{c.description}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {p.impact_analysis && Object.keys(p.impact_analysis).length > 0 && (
                    <div>
                      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">Impact Analysis</p>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                        {['cost', 'performance', 'operations', 'security'].map((area) => {
                          const val = p.impact_analysis?.[area];
                          const detail = p.impact_analysis?.[`${area}_detail`];
                          return val ? (
                            <div key={area} className="bg-slate-50 border border-slate-100 rounded-lg p-2.5">
                              <p className="text-[10px] text-slate-400 capitalize mb-1">{area}</p>
                              <p className={`text-xs ${impactColor[val] ?? 'text-slate-600'} capitalize`}>{val}</p>
                              {detail && <p className="text-[10px] text-slate-400 mt-1 leading-tight">{detail}</p>}
                            </div>
                          ) : null;
                        })}
                      </div>
                    </div>
                  )}

                  {p.tradeoffs && (
                    <div>
                      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">Tradeoffs</p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div className="bg-emerald-50 border border-emerald-100 rounded-lg p-3">
                          <p className="text-[10px] font-bold text-emerald-600 mb-1.5">Pros</p>
                          <ul className="space-y-1">
                            {(p.tradeoffs.pros ?? []).map((pro, i) => (
                              <li key={i} className="text-xs text-emerald-800 flex items-start gap-1.5">
                                <span>+</span>{pro}
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div className="bg-red-50 border border-red-100 rounded-lg p-3">
                          <p className="text-[10px] font-bold text-red-600 mb-1.5">Cons</p>
                          <ul className="space-y-1">
                            {(p.tradeoffs.cons ?? []).map((con, i) => (
                              <li key={i} className="text-xs text-red-800 flex items-start gap-1.5">
                                <span>−</span>{con}
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Roadmap */}
      {Object.keys(roadmap).length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <p className="text-sm font-bold text-slate-800 mb-4">📅 Implementation Roadmap</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[
              { key: 'phase_1_immediate', label: 'Phase 1 — Immediate', color: 'border-l-red-400 bg-red-50/40', title: 'text-red-700' },
              { key: 'phase_2_short_term', label: 'Phase 2 — Short Term', color: 'border-l-amber-400 bg-amber-50/40', title: 'text-amber-700' },
              { key: 'phase_3_long_term', label: 'Phase 3 — Long Term', color: 'border-l-emerald-400 bg-emerald-50/40', title: 'text-emerald-700' },
            ].map((phase) => {
              const items: string[] = (roadmap as Record<string, string[]>)[phase.key] ?? [];
              return items.length > 0 ? (
                <div key={phase.key} className={`border-l-4 rounded-r-xl p-4 ${phase.color}`}>
                  <p className={`text-[11px] font-bold uppercase tracking-wide mb-3 ${phase.title}`}>{phase.label}</p>
                  <ul className="space-y-2">
                    {items.map((item, i) => (
                      <li key={i} className="text-xs text-slate-600 flex items-start gap-1.5">
                        <span className="text-slate-400 mt-0.5">→</span>{item}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null;
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Artifacts Tab ─────────────────────────────────────────────────────────────

function ArtifactsTab({ artifacts }: { artifacts: AnalysisResults['artifacts'] }) {
  const [sub, setSub] = useState<'diagram' | 'openapi' | 'summary'>('diagram');
  const [copied, setCopied] = useState(false);

  const subTabs: Array<{ id: 'diagram' | 'openapi' | 'summary'; label: string }> = [
    { id: 'diagram', label: 'Sequence Diagram' },
    { id: 'openapi', label: 'OpenAPI 3.1' },
    { id: 'summary', label: 'Review Summary' },
  ];

  return (
    <div className="tab-enter">
      {/* Sub-tabs */}
      <div className="flex gap-1 border-b border-slate-200 mb-5">
        {subTabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setSub(t.id)}
            className={`px-4 py-2.5 text-sm font-medium transition-all border-b-2 -mb-px ${
              sub === t.id
                ? 'text-indigo-600 border-indigo-600'
                : 'text-slate-500 border-transparent hover:text-slate-800'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Diagram */}
      {sub === 'diagram' && (
        <div className="bg-white border border-slate-200 rounded-xl overflow-auto p-6 min-h-[300px] flex items-center justify-center">
          {artifacts.mermaid_diagram ? (
            <Suspense fallback={<p className="text-sm text-slate-400">Loading diagram…</p>}>
              <MermaidDiagram src={artifacts.mermaid_diagram} />
            </Suspense>
          ) : (
            <p className="text-sm text-slate-400">No diagram generated.</p>
          )}
        </div>
      )}

      {/* OpenAPI */}
      {sub === 'openapi' && (
        <div>
          <div className="flex items-center justify-between bg-slate-800 px-4 py-2.5 rounded-t-xl">
            <span className="text-xs text-slate-400 font-mono-custom">YAML · OpenAPI 3.1</span>
            <button
              onClick={() => copyToClipboard(artifacts.openapi_spec ?? '', setCopied)}
              className="flex items-center gap-1.5 text-xs text-slate-300 hover:text-white transition-colors px-2 py-1 rounded hover:bg-slate-700"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              {copied ? 'Copied!' : 'Copy'}
            </button>
          </div>
          <pre className="bg-slate-900 text-slate-200 rounded-b-xl p-5 overflow-auto max-h-[500px] text-xs leading-relaxed">
            {artifacts.openapi_spec ?? '# No OpenAPI spec generated'}
          </pre>
        </div>
      )}

      {/* Summary */}
      {sub === 'summary' && (
        <div className="bg-white border border-slate-200 rounded-xl p-6 prose max-w-none">
          {artifacts.review_summary ? (
            <div dangerouslySetInnerHTML={{ __html: mdToHtml(artifacts.review_summary) }} />
          ) : (
            <p className="text-sm text-slate-400">No summary generated.</p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Citations Tab ─────────────────────────────────────────────────────────────

function CitationsTab({ citations, notes }: { citations: Citation[]; notes: AnalysisResults['verification_notes'] }) {
  const verified = citations.filter((c) => c.verification_status === 'verified').length;
  const partial = citations.filter((c) => c.verification_status === 'partially_verified').length;
  const nie = citations.filter((c) => c.verification_status === 'not_in_evidence').length;

  return (
    <div className="tab-enter space-y-5">
      {/* Stats */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'Total', value: citations.length, color: 'text-slate-700' },
          { label: 'Verified', value: verified, color: 'text-emerald-600' },
          { label: 'Partial', value: partial, color: 'text-amber-600' },
          { label: 'Not in Evidence', value: nie, color: 'text-red-600' },
        ].map((s) => (
          <div key={s.label} className="bg-white border border-slate-200 rounded-xl p-4 text-center">
            <p className={`text-2xl font-extrabold font-mono-custom ${s.color}`}>{s.value}</p>
            <p className="text-[11px] text-slate-400 uppercase tracking-wide mt-1">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Confidence */}
      {notes.overall_confidence && (
        <div className="flex items-center gap-2 bg-indigo-50 border border-indigo-100 rounded-xl px-4 py-3">
          <BarChart3 className="w-4 h-4 text-indigo-500" />
          <p className="text-sm text-indigo-800">
            Overall confidence: <span className="font-bold capitalize">{notes.overall_confidence}</span>
          </p>
        </div>
      )}

      {/* Citation cards */}
      <div className="space-y-2.5 max-h-[600px] overflow-y-auto pr-1">
        {citations.map((c, i) => (
          <div key={i} className="bg-white border border-slate-200 rounded-xl p-4">
            <div className="flex items-center gap-2 flex-wrap mb-2">
              <span className="font-mono-custom text-[11px] bg-sky-50 text-sky-700 px-2 py-0.5 rounded border border-sky-100">
                {c.finding_id}
              </span>
              <Badge className={citStatus[c.verification_status] ?? 'bg-slate-50 text-slate-600 border-slate-200'}>
                {c.verification_status?.replace(/_/g, ' ')}
              </Badge>
              {c.confidence && (
                <span className="text-[11px] text-slate-400 ml-auto">
                  confidence: <span className="font-semibold capitalize">{c.confidence}</span>
                </span>
              )}
            </div>
            <p className="text-sm font-semibold text-slate-800 mb-1.5">{c.finding_title}</p>
            <p className="text-xs text-slate-600 leading-relaxed mb-3">{c.claim}</p>
            <div className="flex items-center gap-2 text-[11px] text-slate-400 font-mono-custom">
              <span className="bg-slate-50 border border-slate-100 px-2 py-0.5 rounded">{c.source_id}</span>
              {c.section_reference && (
                <span className="bg-slate-50 border border-slate-100 px-2 py-0.5 rounded">{c.section_reference}</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Reviewer notes */}
      {notes.reviewer_notes && (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4">
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-2">Reviewer Notes</p>
          <p className="text-sm text-slate-600 leading-relaxed">{notes.reviewer_notes}</p>
        </div>
      )}
    </div>
  );
}

// ── Main ResultsPanel ─────────────────────────────────────────────────────────

interface ResultsPanelProps {
  results: AnalysisResults;
  onReset: () => void;
  fileName: string;
}

export default function ResultsPanel({ results, onReset, fileName }: ResultsPanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>('context');
  const [copied, setCopied] = useState(false);

  const bns = results.bottlenecks?.bottlenecks ?? [];
  const proposals = results.proposed_changes?.proposals ?? [];
  const guidelines = results.retrieved_guidelines ?? [];
  const citations = results.citations ?? [];
  const high = bns.filter((b) => b.severity === 'high').length;

  const tabs: TabConfig[] = [
    { id: 'context',     label: 'Context',     icon: <FileText className="w-3.5 h-3.5" /> },
    { id: 'guidelines',  label: 'Guidelines',  icon: <BookOpen className="w-3.5 h-3.5" />,    count: guidelines.length },
    { id: 'bottlenecks', label: 'Bottlenecks', icon: <AlertTriangle className="w-3.5 h-3.5" />, count: bns.length },
    { id: 'proposals',   label: 'Proposals',   icon: <Lightbulb className="w-3.5 h-3.5" />,   count: proposals.length },
    { id: 'artifacts',   label: 'Artifacts',   icon: <Layers className="w-3.5 h-3.5" /> },
    { id: 'citations',   label: 'Citations',   icon: <Quote className="w-3.5 h-3.5" />,        count: citations.length },
  ];

  return (
    <main className="min-h-[calc(100vh-64px)] bg-slate-50">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">

        {/* Summary header */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 mb-6">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                <p className="text-base font-bold text-slate-800">Review Complete</p>
              </div>
              <p className="text-sm text-slate-500 flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5" />
                {fileName}
              </p>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {high > 0 && (
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-red-50 border border-red-200">
                  <AlertTriangle className="w-3.5 h-3.5 text-red-500" />
                  <span className="text-xs font-semibold text-red-700">{high} High Severity</span>
                </div>
              )}
              <button
                onClick={() => downloadJSON(results)}
                className="flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium text-slate-600 hover:text-slate-900 border border-slate-200 hover:border-slate-300 bg-white transition-colors"
              >
                <Download className="w-4 h-4" />
                Export JSON
              </button>
              <button
                onClick={onReset}
                className="flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-700 transition-colors shadow-sm"
              >
                <RotateCcw className="w-4 h-4" />
                New Review
              </button>
            </div>
          </div>

          {/* Quick metrics */}
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-3 mt-5 pt-5 border-t border-slate-100">
            {[
              { label: 'Components', value: results.context?.components?.length ?? '—', color: 'text-indigo-600' },
              { label: 'Guidelines', value: guidelines.length, color: 'text-sky-600' },
              { label: 'Bottlenecks', value: bns.length, color: 'text-red-500' },
              { label: 'Proposals', value: proposals.length, color: 'text-violet-600' },
              { label: 'Citations', value: citations.length, color: 'text-slate-600' },
              { label: 'Verified', value: citations.filter((c) => c.verification_status === 'verified').length, color: 'text-emerald-600' },
            ].map((m) => (
              <div key={m.label} className="text-center">
                <p className={`text-xl font-extrabold font-mono-custom ${m.color}`}>{m.value}</p>
                <p className="text-[11px] text-slate-400 uppercase tracking-wide mt-0.5">{m.label}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Tabs */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          {/* Tab bar */}
          <div className="flex gap-0 border-b border-slate-200 overflow-x-auto">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-4 py-3.5 text-sm font-medium whitespace-nowrap transition-all border-b-2 -mb-px ${
                  activeTab === tab.id
                    ? 'text-indigo-600 border-indigo-600 bg-indigo-50/50'
                    : 'text-slate-500 border-transparent hover:text-slate-800 hover:bg-slate-50'
                }`}
              >
                {tab.icon}
                {tab.label}
                {tab.count !== undefined && tab.count > 0 && (
                  <span className={`ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold ${
                    activeTab === tab.id ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-500'
                  }`}>
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="p-5">
            {activeTab === 'context'     && <ContextTab ctx={results.context} />}
            {activeTab === 'guidelines'  && <GuidelinesTab guidelines={guidelines} />}
            {activeTab === 'bottlenecks' && <BottlenecksTab data={results.bottlenecks} />}
            {activeTab === 'proposals'   && <ProposalsTab data={results.proposed_changes} />}
            {activeTab === 'artifacts'   && <ArtifactsTab artifacts={results.artifacts ?? {}} />}
            {activeTab === 'citations'   && <CitationsTab citations={citations} notes={results.verification_notes ?? {}} />}
          </div>
        </div>

      </div>
    </main>
  );
}
