'use client';

import { useEffect, useRef } from 'react';

interface Props {
  src: string;
}

export default function MermaidDiagram({ src }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const mermaid = (await import('mermaid')).default;
      mermaid.initialize({
        startOnLoad: false,
        theme: 'default',
        securityLevel: 'loose',
        themeVariables: {
          primaryColor: '#eef2ff',
          primaryTextColor: '#1e293b',
          primaryBorderColor: '#c7d2fe',
          lineColor: '#94a3b8',
          secondaryColor: '#f0f9ff',
          tertiaryColor: '#f8fafc',
          background: '#ffffff',
          mainBkg: '#f8fafc',
          nodeBorder: '#e2e8f0',
          clusterBkg: '#f1f5f9',
          titleColor: '#1e293b',
          edgeLabelBackground: '#ffffff',
          fontFamily: 'Inter, system-ui, sans-serif',
          fontSize: '13px',
        },
      });
      if (cancelled || !ref.current) return;

      const id = `mermaid-${Math.random().toString(36).slice(2, 9)}`;
      try {
        const { svg } = await mermaid.render(id, src);
        if (!cancelled && ref.current) {
          ref.current.innerHTML = svg;
        }
      } catch {
        if (!cancelled && ref.current) {
          ref.current.innerHTML = `<pre class="text-xs text-slate-400 p-4 whitespace-pre-wrap">${src}</pre>`;
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [src]);

  return (
    <div
      ref={ref}
      className="mermaid-output w-full min-h-[200px] flex items-center justify-center text-sm text-slate-300"
    >
      Loading diagram…
    </div>
  );
}
