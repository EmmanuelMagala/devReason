export function formatDate(date: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(date));
}

export function extractRepoName(prUrl: string) {
  const match = prUrl.match(/github\.com\/([^/]+\/[^/]+)/);
  return match ? match[1] : prUrl;
}

export function extractPrNumber(prUrl: string) {
  const match = prUrl.match(/\/pull\/(\d+)/);
  return match ? Number.parseInt(match[1], 10) : null;
}

export function truncate(value: string, maxLength: number) {
  return value.length > maxLength ? `${value.slice(0, maxLength)}...` : value;
}
