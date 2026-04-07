import { test, expect } from 'vitest'

function calcArticleInterval(articles) {
  if (!articles || articles.length === 0) return false
  return articles.some(a => a.status === "generating") ? 3000 : false
}

test('returns false for empty array', () => {
  expect(calcArticleInterval([])).toBe(false)
})

test('returns false when no articles are generating', () => {
  const articles = [
    { status: "draft" },
    { status: "approved" },
    { status: "published" },
  ]
  expect(calcArticleInterval(articles)).toBe(false)
})

test('returns 3000 when any article is generating', () => {
  const articles = [
    { status: "draft" },
    { status: "generating" },
  ]
  expect(calcArticleInterval(articles)).toBe(3000)
})

test('returns 3000 when generating article is also paused (paused = sub-state of generating)', () => {
  // is_paused is a sub-state; top-level status remains "generating"
  const articles = [{ status: "generating", is_paused: true }]
  expect(calcArticleInterval(articles)).toBe(3000)
})
