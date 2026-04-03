'use client';

import { useState, useCallback, useRef } from 'react';
import {
  Upload, FileText, X, ChevronDown, CheckCircle, AlertTriangle,
  BookOpen, Zap, GitBranch, Brain, Shield, BarChart2,
} from 'lucide-react';

const STEP_CARDS = [
  {
    icon: FileText,
    step: '01',
    title: 'Extract Context',
    description:
      'Parses your document to extract all components, APIs, services, data stores, traffic patterns, SLOs, and security mechanisms into structured JSON.',
    color: 'indigo',
  },
  {
    icon: BookOpen,
    step: '02',
    title: 'Retrieve Knowledge',
    description:
      'Generates 8 targeted search queries and runs vector similarity search in AlloyDB pgvector across 56 curated architectural guidelines.',
    color: 'sky',
  },
  {
    icon: AlertTriangle,
    step: '03',
    title: 'Detect Bottlenecks',
    description:
      'Gemini AI cross-references your architecture with retrieved best practices to identify scalability, reliability, security, and operational risks with severity ratings.',
    color: 'amber',
  },
  {
    icon: Brain,
    step: '04',
    title: 'Propose Improvements',
    description:
      'Generates actionable improvement proposals with recommended changes, tradeoff analysis, impact ratings (cost/performance/security), effort estimates, and a 3-phase roadmap.',
    color: 'violet',
  },
  {
    icon: GitBranch,
    step: '05',
    title: 'Generate Artifacts',
    description:
      'Produces a Mermaid sequence diagram of component interactions, an OpenAPI 3.1 specification, and an executive architecture review summary report.',
    color: 'emerald',
  },
  {
    icon: CheckCircle,
    step: '06',
    title: 'Verify & Cite',
    description:
      'Validates every finding against the retrieved knowledge base. Claims not backed by evidence are explicitly flagged "Not in Evidence" — no hallucinations.',
    color: 'rose',
  },
];

const MODELS = [
  { value: 'gemini-3.1-flash-lite-preview', label: 'Gemini 3.1 Flash Lite', badge: 'Recommended' },
  { value: 'gemini-2.0-flash-001', label: 'Gemini 2.0 Flash', badge: '' },
  { value: 'gemini-1.5-pro-001', label: 'Gemini 1.5 Pro', badge: 'Highest Quality' },
];

const COLOR_CLASSES: Record<string, { bg: string; icon: string; border: string; step: string }> = {
  indigo: { bg: 'bg-indigo-50', icon: 'text-indigo-600', border: 'border-indigo-100', step: 'text-indigo-500' },
  sky:    { bg: 'bg-sky-50',    icon: 'text-sky-600',    border: 'border-sky-100',    step: 'text-sky-500'    },
  amber:  { bg: 'bg-amber-50',  icon: 'text-amber-600',  border: 'border-amber-100',  step: 'text-amber-500'  },
  violet: { bg: 'bg-violet-50', icon: 'text-violet-600', border: 'border-violet-100', step: 'text-violet-500' },
  emerald:{ bg: 'bg-emerald-50',icon: 'text-emerald-600',border: 'border-emerald-100',step: 'text-emerald-500'},
  rose:   { bg: 'bg-rose-50',   icon: 'text-rose-600',   border: 'border-rose-100',   step: 'text-rose-500'   },
};

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

interface UploadSectionProps {
  onAnalyze: (file: File, model: string) => void;
  error?: string | null;
}

export default function UploadSection({ onAnalyze, error }: UploadSectionProps) {
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [model, setModel] = useState(MODELS[0].value);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) setFile(dropped);
  }, []);

  return (
    <main>
      {/* ── Hero ── */}
      <section className="relative overflow-hidden py-20 sm:py-28 px-4 sm:px-6 lg:px-8">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,rgba(99,102,241,0.08),transparent)]" />
        <div className="relative max-w-4xl mx-auto text-center">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-indigo-50 border border-indigo-100 text-indigo-700 text-xs font-semibold mb-8 tracking-wide">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 dot-pulse" />
            Gemini AI · AlloyDB pgvector RAG · Zero-Trust PII Protection
          </div>

          <h1 className="text-4xl sm:text-5xl lg:text-[3.5rem] font-extrabold tracking-tight text-slate-900 leading-[1.1] mb-6">
            From Design Doc to{' '}
            <span className="gradient-text">Architectural Insights</span>{' '}
            in Seconds
          </h1>

          <p className="text-lg sm:text-xl text-slate-500 max-w-2xl mx-auto mb-10 leading-relaxed">
            Upload a PRD, HLD, or LLD. Our 6-step AI agent extracts structure, retrieves grounded best
            practices, detects risks, and generates actionable proposals — all with zero hallucinations
            through citation verification.
          </p>

          {/* Stats row */}
          <div className="inline-flex items-center divide-x divide-slate-200 bg-slate-50 border border-slate-200 rounded-2xl overflow-hidden mb-14">
            {[
              ['56', 'Curated guidelines'],
              ['6', 'AI-powered steps'],
              ['4', 'File formats'],
              ['100%', 'PII Protected'],
            ].map(([num, label]) => (
              <div key={label} className="px-6 py-3 text-center">
                <p className="text-xl font-extrabold text-indigo-600 font-mono-custom">{num}</p>
                <p className="text-[11px] text-slate-400 uppercase tracking-wide mt-0.5">{label}</p>
              </div>
            ))}
          </div>

          {/* ── Upload Card ── */}
          <div
            id="upload-card"
            className="bg-white rounded-2xl shadow-lg border border-slate-200 p-8 max-w-xl mx-auto"
          >
            {error && (
              <div className="mb-5 flex items-start gap-3 p-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm text-left">
                <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {/* Drop zone */}
            {!file ? (
              <div
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all select-none ${
                  dragging
                    ? 'border-indigo-400 bg-indigo-50/60 scale-[1.01]'
                    : 'border-slate-200 hover:border-indigo-300 hover:bg-slate-50'
                }`}
              >
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-indigo-100 to-sky-100 flex items-center justify-center mx-auto mb-4">
                  <Upload className="w-7 h-7 text-indigo-500" />
                </div>
                <p className="text-sm font-semibold text-slate-700 mb-1">
                  {dragging ? 'Release to upload' : 'Drop your document here'}
                </p>
                <p className="text-xs text-slate-400 mb-4">or click to browse</p>
                <div className="flex items-center justify-center gap-1.5 flex-wrap">
                  {['.txt', '.md', '.pdf', '.docx'].map((ext) => (
                    <span key={ext} className="px-2 py-0.5 rounded bg-slate-100 text-slate-500 text-xs font-mono-custom">
                      {ext}
                    </span>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-3 p-4 rounded-xl bg-indigo-50 border border-indigo-200 mb-0">
                <div className="w-10 h-10 rounded-lg bg-indigo-100 flex items-center justify-center flex-shrink-0">
                  <FileText className="w-5 h-5 text-indigo-600" />
                </div>
                <div className="flex-1 min-w-0 text-left">
                  <p className="text-sm font-semibold text-slate-800 truncate">{file.name}</p>
                  <p className="text-xs text-slate-500">{formatBytes(file.size)}</p>
                </div>
                <button
                  onClick={() => setFile(null)}
                  className="p-1.5 rounded-lg hover:bg-indigo-200 text-indigo-400 transition-colors"
                  title="Remove file"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.md,.pdf,.docx"
              className="hidden"
              onChange={(e) => { if (e.target.files?.[0]) setFile(e.target.files[0]); }}
            />

            {/* Model selector */}
            <div className="mt-5 mb-5">
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                AI Model
              </label>
              <div className="relative">
                <select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 cursor-pointer pr-9"
                >
                  {MODELS.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.label} — {m.badge}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
              </div>
            </div>

            {/* Analyze button */}
            <button
              disabled={!file}
              onClick={() => file && onAnalyze(file, model)}
              className="w-full py-3.5 rounded-xl font-bold text-white text-sm tracking-wide transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-700 hover:to-indigo-600 shadow-md hover:shadow-lg disabled:shadow-none"
            >
              {file ? '→ Run Architecture Review' : 'Select a document to begin'}
            </button>

            <p className="mt-3 text-xs text-slate-400 text-center">
              PII is redacted locally before leaving your browser · No document is stored
            </p>
          </div>
        </div>
      </section>

      {/* ── How It Works ── */}
      <section id="how-it-works" className="py-20 px-4 sm:px-6 lg:px-8 bg-slate-50 border-t border-slate-100">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight mb-3">
              How it works
            </h2>
            <p className="text-slate-500 max-w-lg mx-auto text-base">
              Six sequential AI-powered steps transform your design document into grounded, actionable architectural insights.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {STEP_CARDS.map((card) => {
              const Icon = card.icon;
              const c = COLOR_CLASSES[card.color];
              return (
                <div
                  key={card.step}
                  className="bg-white rounded-2xl border border-slate-200 p-6 hover:shadow-md hover:border-slate-300 transition-all group"
                >
                  <div className="flex items-start gap-4 mb-4">
                    <div className={`w-11 h-11 rounded-xl border flex items-center justify-center flex-shrink-0 ${c.bg} ${c.border}`}>
                      <Icon className={`w-5 h-5 ${c.icon}`} />
                    </div>
                    <span className={`text-xs font-bold uppercase tracking-widest mt-3 ${c.step}`}>
                      Step {card.step}
                    </span>
                  </div>
                  <h3 className="text-[15px] font-bold text-slate-800 mb-2">{card.title}</h3>
                  <p className="text-sm text-slate-500 leading-relaxed">{card.description}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Features ── */}
      <section id="features" className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight mb-3">
              Production-grade by design
            </h2>
            <p className="text-slate-500 max-w-md mx-auto">
              Built on GCP with enterprise security, structured AI outputs, and zero hallucinations.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            {[
              {
                icon: Shield,
                title: 'Zero-Trust PII',
                body: 'Microsoft Presidio redacts names, emails, IPs, and other PII locally before any text reaches the AI model.',
                color: 'rose',
              },
              {
                icon: Zap,
                title: 'Grounded Outputs',
                body: 'Every insight cites a specific knowledge base entry. Claims with no backing evidence are flagged — not fabricated.',
                color: 'amber',
              },
              {
                icon: BarChart2,
                title: 'Structured Knowledge',
                body: '56 curated entries across architecture principles, design patterns, anti-patterns, security guidelines, and cloud references.',
                color: 'indigo',
              },
            ].map((feat) => {
              const Icon = feat.icon;
              const c = COLOR_CLASSES[feat.color];
              return (
                <div key={feat.title} className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
                  <div className={`w-10 h-10 rounded-xl border mb-4 flex items-center justify-center ${c.bg} ${c.border}`}>
                    <Icon className={`w-5 h-5 ${c.icon}`} />
                  </div>
                  <h3 className="text-sm font-bold text-slate-800 mb-2">{feat.title}</h3>
                  <p className="text-sm text-slate-500 leading-relaxed">{feat.body}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="py-8 px-4 border-t border-slate-100">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-sm text-slate-400">
            ArchReview AI — Enterprise Architecture Agent
          </p>
          <p className="text-xs text-slate-300">
            Powered by Gemini AI · AlloyDB pgvector RAG · GCP Cloud Run · Deployed on Vercel
          </p>
        </div>
      </footer>
    </main>
  );
}
