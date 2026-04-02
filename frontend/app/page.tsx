'use client';

import { useState, useCallback } from 'react';
import Header from '@/components/Header';
import UploadSection from '@/components/UploadSection';
import AnalysisProgress from '@/components/AnalysisProgress';
import ResultsPanel from '@/components/ResultsPanel';
import type { AnalysisResults, JobStatus } from '@/lib/types';
import { submitAnalysis, pollJobStatus, fetchResults } from '@/lib/api';

type View = 'home' | 'analyzing' | 'results';

export default function Home() {
  const [view, setView] = useState<View>('home');
  const [fileName, setFileName] = useState('');
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [results, setResults] = useState<AnalysisResults | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleAnalyze = useCallback(async (file: File, model: string) => {
    setFileName(file.name);
    setError(null);
    setView('analyzing');
    setJobStatus({ status: 'pending', progress: 0, steps: {} });

    try {
      const jobId = await submitAnalysis(file, model);

      const poll = setInterval(async () => {
        try {
          const status: JobStatus = await pollJobStatus(jobId);
          setJobStatus(status);
          if (status.status === 'complete') {
            clearInterval(poll);
            const data = await fetchResults(jobId);
            setResults(data as AnalysisResults);
            setView('results');
          } else if (status.status === 'error') {
            clearInterval(poll);
            setError(status.error || 'Analysis failed. Please try again.');
            setView('home');
          }
        } catch {
          // Network blip — keep polling
        }
      }, 800);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to start analysis. Is the backend reachable?';
      setError(msg);
      setView('home');
    }
  }, []);

  const handleReset = useCallback(() => {
    setView('home');
    setFileName('');
    setJobStatus(null);
    setResults(null);
    setError(null);
  }, []);

  return (
    <div className="min-h-screen bg-white">
      <Header onNewAnalysis={view !== 'home' ? handleReset : undefined} />
      {view === 'home' && <UploadSection onAnalyze={handleAnalyze} error={error} />}
      {view === 'analyzing' && jobStatus && (
        <AnalysisProgress status={jobStatus} fileName={fileName} />
      )}
      {view === 'results' && results && (
        <ResultsPanel results={results} onReset={handleReset} fileName={fileName} />
      )}
    </div>
  );
}
