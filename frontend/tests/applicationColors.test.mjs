import assert from 'node:assert/strict'
import test from 'node:test'
import colors from 'tailwindcss/colors'
import { outcomeColorBuckets, resolveRowColors, rowColorStyle } from '../src/applicationColors.ts'

const row = (Outcome, Application_Status) => ({ Outcome, Application_Status })
const statuses = ['Applied', 'Not Applied', 'Recruiter-Screening', 'Technical Interview', 'Final Round', '', 'Custom status']

test('Early interest wins only for Applied; other statuses retain their row colors', () => {
  assert.equal(resolveRowColors(row('Early interest', 'Applied')).background, '#E8EEF6')
  for (const [status, expected] of [
    ['Not Applied', colors.yellow[100]],
    ['Recruiter-Screening', colors.sky[100]],
    ['Technical Interview', colors.orange[100]],
    ['Final Round', colors.violet[100]],
    ['', colors.white],
    ['Custom status', colors.white],
  ]) {
    assert.equal(resolveRowColors(row('Early interest', status)).background, expected)
  }
})

test('final outcomes continue to override every status, including light links on Withdrawn', () => {
  for (const status of statuses) {
    assert.equal(resolveRowColors(row('Withdrawn', status)).background, colors.slate[600])
    assert.equal(rowColorStyle(row('Withdrawn', status))['--application-row-link'], colors.indigo[100])
    assert.equal(resolveRowColors(row('Rejected', status)).background, colors.red[100])
    for (const outcome of ['Offer', 'Accepted']) {
      assert.equal(resolveRowColors(row(outcome, status)).background, colors.emerald[100])
    }
  }
})

test('mixed outcomes split into the correct colors and keep all application counts', () => {
  const rows = [
    row('Early interest', 'Applied'), row('Early interest', 'Applied'),
    row('Early interest', 'Technical Interview'),
    row('Pending', 'Not Applied'), row('Pending', 'Applied'),
  ]
  const buckets = outcomeColorBuckets(rows)
  assert.equal(buckets.length, 4)
  assert.equal(buckets.reduce((sum, bucket) => sum + bucket.n, 0), rows.length)
  assert.deepEqual(buckets.map(({ label, n, color }) => ({ label, n, color })), [
    { label: 'Early interest — Applied', n: 2, color: '#E8EEF6' },
    { label: 'Early interest — Technical Interview', n: 1, color: colors.orange[100] },
    { label: 'Pending — Applied', n: 1, color: colors.white },
    { label: 'Pending — Not Applied', n: 1, color: colors.yellow[100] },
  ])
})

test('row backgrounds and aggregated chart fills agree for every supported combination', () => {
  const outcomes = ['Pending', '', 'Early interest', 'Some interest', 'Withdrawn', 'Rejected', 'Offer', 'Accepted', 'Custom outcome']
  const rows = outcomes.flatMap((outcome) => statuses.map((status) => row(outcome, status)))
  rows.push(null, undefined, {})
  const rowCounts = new Map()
  for (const application of rows) {
    const color = rowColorStyle(application)['--application-row-bg']
    rowCounts.set(color, (rowCounts.get(color) ?? 0) + 1)
  }
  const buckets = outcomeColorBuckets(rows)
  const chartCounts = new Map()
  for (const bucket of buckets) chartCounts.set(bucket.color, (chartCounts.get(bucket.color) ?? 0) + bucket.n)
  assert.deepEqual(chartCounts, rowCounts)
  assert.equal(new Set(buckets.map((bucket) => bucket.key)).size, buckets.length)
  assert.equal(buckets.reduce((sum, bucket) => sum + bucket.n, 0), rows.length)
  assert.equal(resolveRowColors(row('Custom outcome', 'Technical Interview')).background, colors.white)
})

test('legacy outcomes merge, but Offer and Accepted remain distinct outcomes with the same color', () => {
  const buckets = outcomeColorBuckets([
    row('Some interest', 'Applied'), row('Early interest', 'Applied'),
    row('Offer', 'Applied'), row('Offer', 'Final Round'), row('Accepted', 'Final Round'),
  ])
  assert.equal(buckets.find((bucket) => bucket.label === 'Early interest').n, 2)
  assert.equal(buckets.find((bucket) => bucket.label === 'Offer').n, 2)
  assert.equal(buckets.find((bucket) => bucket.label === 'Accepted').n, 1)
  assert.equal(buckets.length, 3)
  assert.deepEqual(outcomeColorBuckets([]), [])
})

test('changing a status updates both the row background and chart fill', () => {
  const application = row('Early interest', 'Applied')
  const initial = outcomeColorBuckets([application])[0].color
  application.Application_Status = 'Technical Interview'
  const updated = outcomeColorBuckets([application])[0].color
  assert.notEqual(updated, initial)
  assert.equal(updated, rowColorStyle(application)['--application-row-bg'])
  assert.equal(updated, colors.orange[100])
})
