import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { reviewsApi } from '@/api/reviews';
import { getClerkToken } from '@/lib/clerk';
import { apiClient } from '@/api/client';
import type { StreamEvent } from '@/types';

export function useLiveReview(id: string, enabled: boolean) {
  const qc = useQueryClient();
  const [live, setLive] = useState({id: '', report: '', phase: '', reconnecting: false});
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController(); let cursor = '0-0'; let report = ''; let disconnected = false;
    const update = (data: Partial<typeof live>) => { if (!controller.signal.aborted) setLive(prev => ({...prev, id, ...data})); };
    update({report: '', phase: '', reconnecting: false});
    async function listen() {
      while (!controller.signal.aborted) {
        try {
          const token = await getClerkToken();
          const response = await fetch(`${reviewsApi.streamUrl(id)}?cursor=${cursor}`, {signal: controller.signal, headers: token ? {Authorization: `Bearer ${token}`} : {}});
          if (!response.ok || !response.body) throw new Error('Event connection unavailable');
          if (disconnected) { void apiClient.post('/api/metrics', {event: 'review_reconnected'}).catch(() => {}); disconnected = false; }
          update({reconnecting: false});
          const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
          while (!controller.signal.aborted) {
            const next = await reader.read(); if (next.done) break;
            buffer += decoder.decode(next.value, {stream: true});
            let boundary: number;
            while ((boundary = buffer.indexOf('\n\n')) >= 0) {
              const block = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
              const eventId = block.match(/^id: (.+)$/m)?.[1]; if (eventId) cursor = eventId;
              const data = block.match(/^data: (.+)$/m)?.[1]; if (!data) continue;
              const event: StreamEvent = JSON.parse(data);
              if (event.event === 'agent_start') update({phase: event.agent?.replaceAll('_', ' ') ?? ''});
              if (event.event === 'report_token' && typeof event.data.token === 'string') { report += event.data.token; update({report}); }
              if (event.event === 'report_ready' && typeof event.data.report === 'string') { report = event.data.report; update({report}); }
              if (['complete', 'error', 'findings_ready'].includes(event.event)) {
                void qc.invalidateQueries({queryKey: ['review', id]});
                if (event.event === 'complete' || event.event === 'error') { await reader.cancel(); return; }
              }
            }
          }
        } catch { if (controller.signal.aborted) return; }
        disconnected = true; update({reconnecting: true});
        void qc.invalidateQueries({queryKey: ['review', id]});
        await new Promise<void>(resolve => { const timer = setTimeout(resolve, 2000); controller.signal.addEventListener('abort', () => { clearTimeout(timer); resolve(); }, {once: true}); });
      }
    }
    void listen();
    return () => controller.abort();
    // State is output; only the review identity and running status own the connection.
  }, [id, enabled, qc]);
  return live.id === id ? live : {id, report: '', phase: '', reconnecting: false};
}
