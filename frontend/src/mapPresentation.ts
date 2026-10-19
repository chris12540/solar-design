export type Notice = {
  code: string
  severity: 'warning' | 'info'
  message: string
}

export type AreaPresentation = {
  level: 'problem' | 'review' | 'clear' | 'pending'
  color: string
  label: string
  notice: Notice | null
}

const RED = '#a63745'
const ORANGE = '#a85e12'
const GREEN = '#28724d'
const BLUE = '#386d9b'

const knownWarningColors: Record<string, string> = {
  coverage_incomplete: ORANGE,
  estimated_boundary: ORANGE,
  ahj_unresolved: RED,
  ahj_conflict: RED,
  ahj_provisional: ORANGE,
  recorded_scope: ORANGE,
}

const explicitlyInformational = new Set([
  'single_parcel_scope',
  'ahj_mixed',
])

/** Color for a notice in details. Informational notes always stay blue. */
export function noticeColor(notice: Notice): string {
  if (explicitlyInformational.has(notice.code) || notice.code.startsWith('construction_year_')) return BLUE
  if (knownWarningColors[notice.code]) return knownWarningColors[notice.code]
  if (notice.severity === 'info') return BLUE
  return ORANGE
}

function warningRank(notice: Notice): number {
  if (notice.code === 'ahj_unresolved' || notice.code === 'ahj_conflict') return 3
  if (knownWarningColors[notice.code]) return 2
  if (explicitlyInformational.has(notice.code) || notice.code.startsWith('construction_year_')) return 0
  if (notice.severity !== 'warning') return 0
  return 2
}

function selectHighestNotice(notices: Notice[]): Notice | null {
  return notices.reduce<Notice | null>((highest, notice) => {
    if (!highest || warningRank(notice) > warningRank(highest)) return notice
    return highest
  }, null)
}

/** Summarize the highest actionable notice without letting info notes dominate. */
export function areaPresentation(
  notices: Notice[],
  state: 'ready' | 'pending' | 'failed',
): AreaPresentation {
  const notice = selectHighestNotice(notices)
  if (notice && warningRank(notice) > 0) {
    const critical = notice.code === 'ahj_unresolved' || notice.code === 'ahj_conflict'
    return {
      level: critical ? 'problem' : 'review',
      color: noticeColor(notice),
      label: `${critical ? 'AHJ problem' : 'Review needed'} · ${notice.message}`,
      notice,
    }
  }

  if (state === 'pending') {
    return { level: 'pending', color: '#66736a', label: 'Review pending', notice: null }
  }
  if (state === 'failed') {
    return { level: 'review', color: ORANGE, label: 'Review unavailable', notice: null }
  }

  return { level: 'clear', color: GREEN, label: 'No review notices', notice: null }
}

/** Rental status is a category; sample and removal states retain precedence. */
export function parcelPresentation(areaColor: string, rental: boolean, sampled: boolean, removed: boolean) {
  return {
    color: removed ? '#a3aaa4' : sampled ? '#243d30' : rental ? '#77549b' : areaColor,
    weight: removed ? 1 : sampled ? 3.5 : rental ? 2 : 1,
    dashArray: rental && !removed ? '4 3' : undefined,
    fillColor: removed ? '#a3aaa4' : areaColor,
    fillOpacity: removed ? .03 : sampled ? .3 : .12,
  }
}
