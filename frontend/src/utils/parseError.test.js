import { parseError } from './parseError'
import { test, expect } from 'vitest'

test('maps persona/product messages to friendly items', () => {
  const detail = 'At least one persona is required; At least one product is required.'
  const out = parseError(detail)
  expect(out.title).toBe('Strategy Failed')
  expect(out.items).toContain('Add at least 1 Customer Persona')
  expect(out.items).toContain('Add at least 1 Product')
})
