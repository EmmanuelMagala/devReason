import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CopyButton } from "@/components/shared/CopyButton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function ReportViewer({
  report,
  isStreaming,
  isFinalizing,
}: {
  report: string;
  isStreaming: boolean;
  isFinalizing: boolean;
}) {
  if (!report && !isStreaming) {
    return null;
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-4">
        <CardTitle className="text-base">Review report</CardTitle>
        {report ? <CopyButton text={report} /> : null}
      </CardHeader>
      <CardContent>
        {report ? (
          isStreaming ? (
            <pre className="streaming-cursor whitespace-pre-wrap text-sm leading-7 text-foreground">
              {report}
            </pre>
          ) : (
            <div className="prose prose-sm max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {report}
              </ReactMarkdown>
            </div>
          )
        ) : (
          <p className="text-sm text-muted-foreground">
            Generating the final report...
          </p>
        )}
        {report && isFinalizing ? (
          <p className="mt-3 text-sm text-muted-foreground">
            Saving review results…
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
