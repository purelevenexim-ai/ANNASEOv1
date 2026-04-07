import { test, expect } from 'vitest'

// Test the refetchInterval logic in isolation (pure function)
function calcRefetchInterval(articleId, data) {
  if (!articleId || !data || data.status !== "generating") return false
  return data.is_paused ? 5000 : 2000
}

test('returns false when articleId is null', () => {
  expect(calcRefetchInterval(null, { status: "generating" })).toBe(false)
})

test('returns false when data is null', () => {
  expect(calcRefetchInterval("art-1", null)).toBe(false)
})

test('returns false when status is draft', () => {
  expect(calcRefetchInterval("art-1", { status: "draft" })).toBe(false)
})

test('returns 2000 when generating and not paused', () => {
  expect(calcRefetchInterval("art-1", { status: "generating", is_paused: false })).toBe(2000)
})

test('returns 5000 when generating and paused', () => {
  expect(calcRefetchInterval("art-1", { status: "generating", is_paused: true })).toBe(5000)
})
