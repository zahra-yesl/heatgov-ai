/**
 * Pull a dollar figure out of what the official typed.
 *
 * Handles "$500,000", "500k", "$1.2 million" and bare "500000". A dollar sign
 * wins over a bare number, so "the top 10 zones for $500,000" reads 500,000 as
 * the budget and not the 10.
 *
 * Lives in its own file so it can be tested without mounting React.
 */

const SCALE: Record<string, number> = {
  k: 1_000,
  thousand: 1_000,
  m: 1_000_000,
  mm: 1_000_000,
  million: 1_000_000,
};

// Below this, a bare number with no dollar sign and no magnitude word is far
// more likely to be "top 10 zones" than a municipal budget.
const BARE_NUMBER_FLOOR = 10_000;

export function parseBudget(text: string): number | null {
  const pattern = /(\$)?\s*([\d][\d,]*(?:\.\d+)?)\s*(k|thousand|mm|m|million)?\b/gi;
  let best: { value: number; hadDollar: boolean } | null = null;

  for (const match of text.matchAll(pattern)) {
    const hadDollar = Boolean(match[1]);
    const suffix = match[3]?.toLowerCase();
    let value = Number(match[2].replace(/,/g, ""));
    if (!Number.isFinite(value) || value <= 0) continue;
    if (suffix) value *= SCALE[suffix] ?? 1;
    if (!hadDollar && !suffix && value < BARE_NUMBER_FLOOR) continue;

    if (!best) {
      best = { value, hadDollar };
      continue;
    }
    // A figure written with a dollar sign always beats a bare number; between
    // two of the same kind, the larger one wins.
    const beatsOnDollar = hadDollar && !best.hadDollar;
    const beatsOnSize = hadDollar === best.hadDollar && value > best.value;
    if (beatsOnDollar || beatsOnSize) {
      best = { value, hadDollar };
    }
  }

  return best ? best.value : null;
}
