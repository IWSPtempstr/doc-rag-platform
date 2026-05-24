export function normalizeAshareTicker(input: string | null | undefined): string {
  const raw = String(input || "").trim().toUpperCase();
  const prefixed = raw.match(/^(SH|SZ|BJ)(\d{6})$/);
  if (prefixed) return prefixed[2];
  const embedded = raw.match(/(\d{6})/);
  return embedded ? embedded[1] : raw;
}

export function isAshareLikeTicker(input: string | null | undefined): boolean {
  return /^\d{6}$/.test(normalizeAshareTicker(input));
}

export function inferAshareMarket(input: string | null | undefined): string {
  const ticker = normalizeAshareTicker(input);
  return ticker.startsWith("6") || ticker.startsWith("5") || ticker.startsWith("9") ? "SSE" : "SZSE";
}
