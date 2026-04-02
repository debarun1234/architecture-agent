'use client';

import { FileText, CheckCircle2, Loader2, Circle } from 'lucide-react';
import type { JobStatus } from '@/lib/types';

const STEP_META = [
  {
    name: 'Extract Context',
    idle: 'Parses components, APIs, data stores, traffic patterns, and reliability requirements.',
    active:
      'Calling Gemini to extract structured JSON — components, APIs, data stores, traffic expectations, SLOs, and security mechanisms from your document...',
    icon: '📄',
  },
  {
    name: 'Retrieve Knowledge',
    idle: 'Searches 56 curated guidelines using vector similarity across 5 knowledge collections.',
    active:
      'Building 8 targeted queries, generating embeddings via Vertex AI, and running cosine similarity search in AlloyDB pgvector...',
    icon: '🔍',
  },
  {
    name: 'Detect Bottlenecks',
    idle: 'Cross-references architecture against retrieved guidelines to identify risks.',
    active:
      'Analysing your architecture for scalability, reliability, security, and operational bottlenecks — assigning severity ratings and supporting evidence...',
    icon: '⚠️',
  },
  {
    name: 'Propose Improvements',
    idle: 'Generates actionable recommendations with tradeoffs and a 3-phase roadmap.',
    active:
      'Creating PROP-00x proposals with change details, effort estimates, impact analysis (cost/perf/security), and an implementation roadmap...',
    icon: '💡',
  },
  {
    name: 'Generate Artifacts',
    idle: 'Produces a Mermaid diagram, OpenAPI 3.1 spec, and executive summary.',
    active:
      'Generating the Mermaid sequence diagram, OpenAPI 3.1.0 YAML specification, and a full markdown architecture review report...',
    icon: '🎨',
  },
  {
    name: 'Verify & Cite',
    idle: 'Cross-checks every finding — flags claims not in evidence.',
    active:
      'Matching each bottleneck and proposal against the retrieved knowledge base. Marking confidence levels and flagging unsupported claims...',
    icon: '✅',
  },
];

interface Props {
  status: JobStatus;
  fileName: string;
}

export default function AnalysisProgress({ status, fileName }: Props) {
  const progress = status.progress ?? 0;
  const activeStep = Object.entries(status.steps ?? {}).find(
    ([, s]) => s.status === 'running'
  )?.[0];

  return (
    <main className="min-h-[calc(100vh-64px)] bg-slate-50">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-12">

        {/* File banner */}
        <div className="flex items-center gap-3 bg-white border border-slate-200 rounded-2xl p-5 mb-8 shadow-sm">
          <div className="w-11 h-11 rounded-xl bg-indigo-50 flex items-center justify-center flex-shrink-0">
            <FileText className="w-5 h-5 text-indigo-600" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-slate-800 truncate">{fileName}</p>
            <p className="text-xs text-slate-400 mt-0.5">Architecture review in progress</p>
          </div>
          <div className="text-right flex-shrink-0">
            <p className="text-2xl font-extrabold text-indigo-600 font-mono-custom leading-none">{progress}%</p>
            <p className="text-xs text-slate-400 mt-0.5">complete</p>
          </div>
        </div>

        {/* Progress bar */}
        <div className="mb-10">
          <div className="h-2.5 bg-slate-200 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full progress-bar-animated transition-all duration-700 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* What's happening banner */}
        {activeStep && (
          <div className="flex items-start gap-3 bg-indigo-50 border border-indigo-200 rounded-xl px-4 py-3.5 mb-6">
            <Loader2 className="w-4 h-4 text-indigo-500 animate-spin mt-0.5 flex-shrink-0" />
            <p className="text-sm text-indigo-700 font-medium leading-relaxed">
              <span className="font-bold">Step {activeStep}:</span>{' '}
              {STEP_META[Number(activeStep) - 1]?.active}
            </p>
          </div>
        )}

        {/* Step cards */}
        <div className="space-y-3">
          {STEP_META.map((meta, i) => {
            const key = String(i + 1);
            const step = status.steps?.[key];
            const st = step?.status ?? 'pending';
            const isRunning = st === 'running';
            const isDone = st === 'complete';

            return (
              <div
                key={i}
                className={`bg-white rounded-xl border p-4 transition-all duration-300 ${
                  isRunning
                    ? 'border-indigo-300 shadow-md ring-1 ring-indigo-100'
                    : isDone
                    ? 'border-emerald-200 bg-emerald-50/40'
                    : 'border-slate-200 opacity-50'
                }`}
              >
                <div className="flex items-start gap-3.5">
                  {/* Status icon */}
                  <div className="mt-0.5 flex-shrink-0 w-5">
                    {isDone ? (
                      <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                    ) : isRunning ? (
                      <Loader2 className="w-5 h-5 text-indigo-500 animate-spin" />
                    ) : (
                      <Circle className="w-5 h-5 text-slate-300" />
                    )}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                        Step {i + 1}
                      </span>
                      {isRunning && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-100 text-indigo-700 uppercase tracking-wide">
                          <span className="w-1 h-1 rounded-full bg-indigo-500 dot-pulse" />
                          Running
                        </span>
                      )}
                      {isDone && (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-700 uppercase tracking-wide">
                          Done
                        </span>
                      )}
                    </div>
                    <p
                      className={`text-sm font-bold leading-tight mb-1 ${
                        isRunning ? 'text-indigo-900' : isDone ? 'text-emerald-800' : 'text-slate-600'
                      }`}
                    >
                      {meta.icon} {meta.name}
                    </p>
                    <p className="text-xs text-slate-500 leading-relaxed">
                      {meta.idle}
                    </p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <p className="text-center text-xs text-slate-400 mt-8">
          This typically takes 30–90 seconds depending on document size and model.
        </p>
      </div>
    </main>
  );
}
