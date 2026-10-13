import axios from 'axios';
import { Button } from '@/components/ui/button';

// eslint-disable-next-line react-refresh/only-export-components
export function errorText(error: unknown): string {
  const detail = axios.isAxiosError(error) ? error.response?.data?.detail : null;
  return typeof detail === 'string' ? detail : error instanceof Error ? error.message : 'Something went wrong. Please retry.';
}
export function QueryState({loading, error, retry}: {loading?: boolean; error?: unknown; retry?: () => void}) {
  if (error) return <div role="alert" className="state-box border-red-200"><p>{errorText(error)}</p>{retry && <Button variant="outline" onClick={retry}>Try again</Button>}</div>;
  if (loading) return <div role="status" className="state-box"><span className="animate-pulse">Loading…</span></div>;
  return null;
}
