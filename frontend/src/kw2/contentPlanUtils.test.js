import { test, expect } from 'vitest'

// ── Pagination helpers ────────────────────────────────────────────────────────

function paginate(items, page, pageSize) {
  return items.slice(page * pageSize, (page + 1) * pageSize)
}

function totalPages(items, pageSize) {
  return Math.ceil(items.length / pageSize)
}

test('paginate returns correct slice for page 0', () => {
  const items = Array.from({ length: 507 }, (_, i) => i)
  expect(paginate(items, 0, 50)).toEqual(items.slice(0, 50))
})

test('paginate returns correct slice for last page', () => {
  const items = Array.from({ length: 507 }, (_, i) => i)
  const lastPage = totalPages(items, 50) - 1  // page 10 (0-indexed)
  const result = paginate(items, lastPage, 50)
  expect(result).toEqual(items.slice(500, 507))
  expect(result.length).toBe(7)
})

test('totalPages for 507 items at 50/page is 11', () => {
  const items = Array.from({ length: 507 })
  expect(totalPages(items, 50)).toBe(11)
})

test('totalPages for exactly 50 items is 1', () => {
  expect(totalPages(Array.from({ length: 50 }), 50)).toBe(1)
})

// ── Session-scoped articleMap ─────────────────────────────────────────────────

function buildSessionArticleMap(articleList, calendarKeywords) {
  const map = {}
  articleList
    .filter(a => calendarKeywords.has((a.keyword || '').toLowerCase()))
    .forEach(a => { map[(a.keyword || '').toLowerCase()] = a })
  return map
}

test('buildSessionArticleMap excludes articles not in calendar', () => {
  const articles = [
    { keyword: 'spices online', status: 'published' },
    { keyword: 'other project topic', status: 'published' },
  ]
  const calendarKeywords = new Set(['spices online'])
  const map = buildSessionArticleMap(articles, calendarKeywords)
  expect(Object.keys(map)).toEqual(['spices online'])
  expect(map['other project topic']).toBeUndefined()
})

test('buildSessionArticleMap is case-insensitive', () => {
  const articles = [{ keyword: 'Kerala Spices', status: 'draft' }]
  const calendarKeywords = new Set(['kerala spices'])
  const map = buildSessionArticleMap(articles, calendarKeywords)
  expect(map['kerala spices']).toBeDefined()
})

test('buildSessionArticleMap returns empty map when no overlap', () => {
  const articles = [{ keyword: 'foo', status: 'draft' }]
  const calendarKeywords = new Set(['bar'])
  expect(buildSessionArticleMap(articles, calendarKeywords)).toEqual({})
})
