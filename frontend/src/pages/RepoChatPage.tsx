import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { workspaceApi } from '@/api/workspace';
import { reposApi } from '@/api/repos';
import { QueryState, errorText } from '@/components/shared/QueryState';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import type { ChatMessage } from '@/types';

export function RepoChatPage() { const {repoId = ''} = useParams(); return <ChatWorkspace key={repoId} repoId={repoId} />; }
function ChatWorkspace({repoId}: {repoId: string}) {
  const history = useQuery({queryKey: ['conversation', repoId], queryFn: () => workspaceApi.conversation(repoId)});
  const repo = useQuery({queryKey: ['repo', repoId], queryFn: () => workspaceApi.repo(repoId)}); const qc = useQueryClient();
  const [input, setInput] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [reply, setReply] = useState(''); const [question, setQuestion] = useState('');
  const [older, setOlder] = useState<ChatMessage[]>([]); const [cursor, setCursor] = useState<string | null>(null); const [loadingOlder, setLoadingOlder] = useState(false); const [more, setMore] = useState(true);
  const controller = useRef<AbortController | null>(null); const end = useRef<HTMLDivElement>(null);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => { end.current?.scrollIntoView({block: 'nearest'}); }, [reply, busy]);
  async function send(message = input) {
    if (!message.trim() || busy) return;
    setQuestion(message); setInput(''); setReply(''); setError(''); setBusy(true);
    const abort = new AbortController(); controller.current = abort;
    try { await reposApi.streamChat(repoId, message, chunk => { if (!abort.signal.aborted) setReply(prev => prev + chunk); }, abort.signal); }
    catch(e) { if (!abort.signal.aborted) setError(errorText(e)); }
    finally { if (controller.current === abort) { setBusy(false); if (!abort.signal.aborted) { await qc.invalidateQueries({queryKey: ['conversation', repoId]}); setReply(''); } } }
  }
  async function loadOlder() {
    setLoadingOlder(true);
    try { const page = await workspaceApi.conversation(repoId, cursor || history.data?.next_cursor || undefined); setOlder(prev => [...page.items, ...prev]); setCursor(page.next_cursor); setMore(page.has_more); }
    catch(e) { setError(errorText(e)); } finally { setLoadingOlder(false); }
  }
  return <div className="page-stack"><nav aria-label="Breadcrumb" className="breadcrumbs"><Link to="/repositories">Repositories</Link><span>/</span><Link to={`/repos/${repoId}`}>{repo.data?.name || 'Repository'}</Link><span>/</span><span>Chat</span></nav><div className="page-heading"><div><h1>Review assistant</h1><p>Ask about saved findings, recurring patterns, and review history.</p></div></div>
    <QueryState loading={history.isPending} error={history.error} retry={() => void history.refetch()} />
    <section className="panel chat-panel"><p className="notice text-sm">Answers use saved review history and findings. Full repository source is not retrieved for chat.</p>
      {history.data?.has_more && more && <Button variant="outline" disabled={loadingOlder} onClick={() => void loadOlder()}>Load older messages</Button>}
      <div className="chat-messages" aria-label="Conversation">{[...older, ...(history.data?.items || [])].map((m, i) => <article key={i} className={`chat-message ${m.role}`}><p className="message-role">{m.role === 'user' ? 'You' : 'DevReason'}</p><div className="prose"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown></div></article>)}{busy && <article className="chat-message user"><p className="message-role">You</p><p>{question}</p></article>}{reply && <article className="chat-message assistant"><p className="message-role">DevReason</p><div className="prose"><ReactMarkdown remarkPlugins={[remarkGfm]}>{reply}</ReactMarkdown></div></article>}<div ref={end} /></div>
      {!history.data?.items.length && !busy && <div className="prompt-starters"><p className="text-sm text-muted-foreground">Start a conversation</p>{['What should I fix first?', 'Which security issues recur?', 'Summarize the latest review.'].map(p => <Button variant="outline" key={p} onClick={() => setInput(p)}>{p}</Button>)}</div>}
      {error && <div role="alert" className="notice">{error}<Button variant="outline" onClick={() => void send(question)}>Retry response</Button></div>}
      <form onSubmit={e => { e.preventDefault(); void send(); }} className="chat-composer"><label htmlFor="chat-message">Message</label><Textarea id="chat-message" maxLength={8000} placeholder="Ask about this repository’s reviews…" value={input} onChange={e => setInput(e.target.value)} disabled={busy} /><div className="flex items-center justify-between gap-2"><p role="status" className="text-xs text-muted-foreground">{busy ? 'Generating response…' : 'Your conversation is saved.'}</p>{busy ? <Button type="button" variant="outline" onClick={() => { controller.current?.abort(); setBusy(false); setError('Response stopped. Retry to continue.'); }}>Stop response</Button> : <Button disabled={!input.trim() || history.isPending || history.isError}>Send message</Button>}</div></form>
    </section></div>;
}
