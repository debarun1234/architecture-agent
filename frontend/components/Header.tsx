'use client';

import { Cpu, Plus } from 'lucide-react';

interface HeaderProps {
  onNewAnalysis?: () => void;
}

export default function Header({ onNewAnalysis }: HeaderProps) {
  return (
    <header className="sticky top-0 z-50 bg-white/90 backdrop-blur-md border-b border-slate-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-600 to-sky-500 shadow-sm flex-shrink-0">
              <Cpu className="w-5 h-5 text-white" />
            </div>
            <div>
              <p className="text-[15px] font-bold text-slate-900 tracking-tight leading-none">
                ArchReview<span className="text-indigo-600">AI</span>
              </p>
              <p className="text-[10px] text-slate-400 uppercase tracking-widest mt-0.5">
                Enterprise Architecture Agent
              </p>
            </div>
          </div>

          {/* Nav */}
          <nav className="hidden md:flex items-center gap-7">
            <a
              href="#how-it-works"
              className="text-sm text-slate-500 hover:text-slate-900 transition-colors font-medium"
            >
              How it works
            </a>
            <a
              href="#features"
              className="text-sm text-slate-500 hover:text-slate-900 transition-colors font-medium"
            >
              Features
            </a>
            <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-50 border border-emerald-200">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 dot-pulse" />
              <span className="text-xs font-semibold text-emerald-700">Backend Live</span>
            </div>
          </nav>

          {/* CTA */}
          {onNewAnalysis ? (
            <button
              onClick={onNewAnalysis}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold bg-indigo-600 text-white hover:bg-indigo-700 transition-colors shadow-sm"
            >
              <Plus className="w-4 h-4" />
              New Review
            </button>
          ) : (
            <button
              onClick={() => document.getElementById('upload-card')?.scrollIntoView({ behavior: 'smooth' })}
              className="px-4 py-2 rounded-lg text-sm font-semibold bg-indigo-600 text-white hover:bg-indigo-700 transition-colors shadow-sm"
            >
              Get Started →
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
