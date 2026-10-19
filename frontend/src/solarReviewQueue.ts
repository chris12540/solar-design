export type BatchResult = { checked_count: number; cached_count: number; failed_count: number; remaining_count: number }

/** Run bounded API batches after one explicit user action. Pausing finishes the current batch. */
export async function runSolarReviewQueue<T>(options: {
  checkBatch: () => Promise<BatchResult>
  refresh: () => Promise<T>
  onProgress: (report: T, checked: number, remaining: number) => void
  shouldStop: () => boolean
}) {
  let checked = 0
  let remaining = 0
  let previousRemaining = Infinity
  while (!options.shouldStop()) {
    const batch = await options.checkBatch()
    checked += batch.checked_count
    remaining = batch.remaining_count
    const report = await options.refresh()
    options.onProgress(report, checked, remaining)
    if (remaining === 0) return { checked, remaining, paused: false }
    if (remaining >= previousRemaining) throw new Error('Checks stopped because remaining homes did not decrease. Completed results are retained.')
    previousRemaining = remaining
    if (batch.checked_count === 0) throw new Error('Checks stopped because no homes advanced. Completed results are retained.')
  }
  return { checked, remaining, paused: true }
}
