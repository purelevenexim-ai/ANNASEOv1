export function parseError(detail) {
  if (!detail) return { title: "Strategy Failed", items: ["Unknown error"] }

  const raw = String(detail)
  const parts = raw.split(";").map(p => p.trim()).filter(Boolean)

  const items = parts.map(p => {
    if (/persona/i.test(p)) return "Add at least 1 Customer Persona"
    if (/product/i.test(p)) return "Add at least 1 Product"
    return p
  })

  return { title: "Strategy Failed", items }
}

export default parseError
