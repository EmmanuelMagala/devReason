import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";

export function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text); setError(''); setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch { setError('Copy failed. Download the report instead.'); }
  }

  return (
    <><Button type="button" variant="ghost" size="icon" aria-label={copied ? 'Report copied' : 'Copy report'} onClick={handleCopy}>
      {copied ? (
        <Check className="h-4 w-4 text-devreason-teal" />
      ) : (
        <Copy className="h-4 w-4" />
      )}
    </Button><span className="sr-only" role="status">{copied ? 'Report copied to clipboard' : ''}</span>{error && <span role="alert" className="text-xs text-destructive">{error}</span>}</>
  );
}
