import colors from 'tailwindcss/colors'

export interface ApplicationColorRow {
  Outcome?: unknown
  Application_Status?: unknown
}

type ColorRow = ApplicationColorRow | null | undefined

interface RowColors {
  background: string
  hover: string
  foreground: string
  link: string
}

function palette(
  background: string,
  hover: string,
  foreground: string = colors.slate[900],
  link: string = colors.indigo[600],
): Readonly<RowColors> {
  return { background, hover, foreground, link }
}

// One palette for both row styling and chart fills; use Tailwind's actual values.
const PALETTE = {
  default: palette(colors.white, colors.slate[50]),
  earlyInterest: palette('#E8EEF6', '#D8E2EF', '#52647A'),
  withdrawn: palette(colors.slate[600], colors.slate[700], colors.slate[50], colors.indigo[100]),
  rejected: palette(colors.red[100], colors.red[200]),
  success: palette(colors.emerald[100], colors.emerald[200]),
  notApplied: palette(colors.yellow[100], colors.yellow[200]),
  screening: palette(colors.sky[100], colors.sky[200]),
  technical: palette(colors.orange[100], colors.orange[200]),
  final: palette(colors.violet[100], colors.violet[200]),
}

/** Keep legacy records readable after the Outcome rename to Early interest. */
export function outcomeLabel(value: unknown): string {
  const label = value == null ? '' : String(value)
  return label === 'Some interest' ? 'Early interest' : label
}

/** All row-color priority rules live here. Badges have their own independent styles. */
export function resolveRowColors(row: ColorRow): Readonly<RowColors> {
  const outcome = outcomeLabel(row?.Outcome)
  const status = row?.Application_Status == null ? '' : String(row.Application_Status)
  if (outcome === 'Early interest' && status === 'Applied') return PALETTE.earlyInterest
  if (outcome === 'Withdrawn') return PALETTE.withdrawn
  if (outcome === 'Rejected') return PALETTE.rejected
  if (outcome === 'Offer' || outcome === 'Accepted') return PALETTE.success
  if (outcome === 'Pending' || outcome === '' || outcome === 'Early interest') {
    if (status === 'Not Applied') return PALETTE.notApplied
    if (status === 'Recruiter-Screening') return PALETTE.screening
    if (status === 'Technical Interview') return PALETTE.technical
    if (status === 'Final Round') return PALETTE.final
  }
  return PALETTE.default
}

export function rowColorStyle(row: ColorRow): Record<string, string> {
  const palette = resolveRowColors(row)
  return {
    '--application-row-bg': palette.background,
    '--application-row-hover': palette.hover,
    '--application-row-text': palette.foreground,
    '--application-row-link': palette.link,
  }
}

export interface OutcomeColorBucket {
  key: string
  label: string
  n: number
  color: string
}

/** Split each outcome by its resolved row background, counting every application once. */
export function outcomeColorBuckets(rows: readonly ColorRow[]): OutcomeColorBucket[] {
  const buckets = new Map<string, OutcomeColorBucket & { outcome: string; statuses: Set<string> }>()
  const colorsPerOutcome = new Map<string, Set<string>>()
  for (const row of rows) {
    const outcome = outcomeLabel(row?.Outcome) || 'Not set'
    const status = row?.Application_Status == null || row.Application_Status === ''
      ? 'No status' : String(row.Application_Status)
    const color = resolveRowColors(row).background
    const key = JSON.stringify([outcome, color])
    let bucket = buckets.get(key)
    if (!bucket) {
      bucket = { key, outcome, label: outcome, n: 0, color, statuses: new Set() }
      buckets.set(key, bucket)
    }
    bucket.n += 1
    bucket.statuses.add(status)
    const outcomeColors = colorsPerOutcome.get(outcome) ?? new Set<string>()
    outcomeColors.add(color)
    colorsPerOutcome.set(outcome, outcomeColors)
  }
  return [...buckets.values()]
    .map(({ key, outcome, n, color, statuses }) => ({
      key,
      label: colorsPerOutcome.get(outcome)!.size > 1
        ? `${outcome} — ${[...statuses].sort().join(' / ')}` : outcome,
      n,
      color,
    }))
    .sort((a, b) => b.n - a.n || a.label.localeCompare(b.label))
}
