"""Setup Kerala Naadan Coffee Powder project with R2 brand story."""
import sqlite3, uuid, json
from datetime import datetime, timezone

DB = "annaseo.db"
NOW = datetime.now(timezone.utc).isoformat()

PROJECT_ID = "proj_kerala_naadan"  # short, predictable
OWNER_ID = "user_testadmin"

con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
cur = con.cursor()

# 0) Wipe any prior run
for tbl in ("bs_snippets","bs_plots","bs_products","business_profiles","projects"):
    cur.execute(f"DELETE FROM {tbl} WHERE project_id=?", (PROJECT_ID,))

# 1) Project row
cur.execute("""
INSERT INTO projects (project_id, name, industry, description, seed_keywords,
  language, region, status, owner_id, created_at, updated_at,
  target_languages, target_locations, business_type, customer_url)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
""", (PROJECT_ID, "Kerala Naadan Coffee Co.", "food_beverages",
      "Traditional single-estate Wayanad filter coffee, zero chicory.",
      json.dumps(["kerala naadan coffee powder","filter coffee","wayanad coffee"]),
      "english","india","active",OWNER_ID,NOW,NOW,
      json.dumps(["english"]), json.dumps(["india","kerala"]),
      "B2C","https://keralanaadancoffee.example.in"))

# 2) Brand profile
cur.execute("""
INSERT INTO business_profiles
(project_id, brand_name, founder_name, founder_story, origin_story,
 mission, values_text, region, state, country, brand_voice,
 what_we_dont_do, free_text_extras, created_at, updated_at, story_mode)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
""", (
    PROJECT_ID,
    "Kerala Naadan Coffee Co.",
    "Mathew Joseph",
    ("Mathew grew up on his grandfather's 12-acre coffee estate in Chundale, "
     "Wayanad. After 18 years in Bangalore IT, he came home in 2018, took over "
     "the estate, and started roasting in his grandmother's cast-iron urli "
     "instead of selling green beans to bulk traders."),
    ("Beans grown at 1,150–1,250m on a single shade-grown estate in Chundale, "
     "Wayanad. Hand-picked at peak ripeness, sun-dried on raised beds, "
     "slow-roasted in small 3-kg batches in a cast-iron urli over a wood fire — "
     "the traditional 'naadan' (native) method."),
    "Bring real single-estate Wayanad filter coffee to South Indian kitchens — without chicory, without blending, without compromise.",
    ("• Single estate, single roaster, zero chicory.\n"
     "• Slow-roast in cast-iron urli — never in industrial drum roasters.\n"
     "• Print roast date on every pack (most brands hide it).\n"
     "• 100% Arabica + Robusta from one farm, never mixed with bought-in beans."),
    "Wayanad",
    "Kerala",
    "India",
    "Warm, grounded, confessional. Talks like a small-batch roaster who knows every plant. Specific numbers (altitude, batch size, roast minutes) over adjectives.",
    ("Never use 'world-class', 'best in the world', 'finest'. "
     "Never claim awards we don't have. "
     "Never call it 'gourmet' — it is naadan, not gourmet."),
    "",
    NOW, NOW, "on"
))

# 3) Products
PROD_FILTER = str(uuid.uuid4())
PROD_PEABERRY = str(uuid.uuid4())
PROD_DECAF = str(uuid.uuid4())
products = [
    (PROD_FILTER, "Naadan Filter Coffee Powder",  "product", "filter_coffee", "70:30 Arabica:Robusta, medium-dark roast", 0),
    (PROD_PEABERRY, "Single-Estate Peaberry",     "product", "specialty",     "Hand-sorted peaberries, light roast", 1),
    (PROD_DECAF, "Naadan Decaf Filter",           "product", "decaf",         "Swiss water process, zero chemicals", 2),
]
for pid, name, typ, cat, tag, sort in products:
    cur.execute("""INSERT INTO bs_products
        (id, project_id, name, type, category, tagline, sort_order, is_active, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,1,?,?)""",
        (pid, PROJECT_ID, name, typ, cat, tag, sort, NOW, NOW))

# 4) Snippets — verified facts the model can weave in
def snip(prod_id, kind, text):
    cur.execute("""INSERT INTO bs_snippets
        (id, product_id, project_id, kind, text, tags, confidence, source,
         is_active, usage_count, avg_performance, last_used_at, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,1,0,0.5,?,?,?)""",
        (str(uuid.uuid4()), prod_id, PROJECT_ID, kind, text,
         json.dumps([]), "verified", "founder_input", "", NOW, NOW))

# Brand-level snippets (no product_id)
snip("", "brand_origin", "Our estate sits in Chundale village, Wayanad, at 1,150–1,250 metres — high enough for slow cherry maturation and that classic Wayanad acidity.")
snip("", "brand_origin", "Mathew Joseph took over the family's 12-acre Chundale estate in 2018 after 18 years in Bangalore IT, and re-started slow-roasting in his grandmother's cast-iron urli.")
snip("", "key_process", "We slow-roast in a cast-iron urli over a wood fire in 3-kg batches — about 22–25 minutes per batch, never the 12-minute drum-roaster shortcut.")
snip("", "key_process", "Every Naadan Coffee pack carries the actual roast date — not a 'best before' — printed on the side.")
snip("", "what_we_dont_do", "Zero chicory. Most South Indian filter coffee powders are 51–80% chicory; ours is 100% coffee.")
snip("", "market_context", "FSSAI rules require chicory percentage to be declared on the label only when it exceeds 2%. Brands that blend 40–50% chicory can legally print just 'coffee and chicory powder' without the ratio — so most South Indian filter packs do exactly that.")
snip("", "market_context", "A pack of filter coffee powder goes stale within 3–6 weeks of roasting. Most supermarket brands are roasted 4–8 months before you buy; the lack of a roast date is the tell.")
snip("", "content_anchor", "You can tell real naadan filter coffee from a diluted blend by three things: whether the label shows the chicory percentage, whether the roast date (not best-before) is printed, and whether the origin estate is named.")

# Product snippets
snip(PROD_FILTER, "flagship_product", "Naadan Filter Coffee Powder is our flagship: a 70:30 blend of estate Arabica and Robusta, ground to South Indian filter mesh (~600 microns).")
snip(PROD_FILTER, "hero_ingredient", "The Arabica comes from shade-grown plots above 1,200m; the Robusta from the lower slope at 1,150m — both from the same 12-acre Chundale estate.")
snip(PROD_FILTER, "key_process", "We grind only after roasting cools to room temperature, never hot — hot grinding burns off the top notes that give naadan filter coffee its caramel finish.")
snip(PROD_PEABERRY, "flagship_product", "Single-Estate Peaberry is hand-sorted from a single harvest — only 6–8% of cherries naturally produce peaberries.")
snip(PROD_DECAF, "flagship_product", "Naadan Decaf uses Swiss Water Process — water and activated charcoal, zero chemical solvents, retaining 99.9% caffeine-free.")

# 5) Plot — ONE simple high-value plot
PLOT_ID = str(uuid.uuid4())
plot_thesis = (
    "Real naadan filter coffee is easy to recognize when three things are visible "
    "on the label: the chicory percentage, the roast date (not just a best-before), "
    "and the origin estate — generic supermarket blends hide at least two of those signals."
)
cur.execute("""INSERT INTO bs_plots
    (id, product_id, project_id, title, thesis, snippet_ids, plot_type,
     conflicts_with, priority, status, used_count, avg_performance,
     continuity_notes, created_at, updated_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,0,0.5,?,?,?)""",
    (PLOT_ID, "", PROJECT_ID,
     "The Label Transparency Test",
     plot_thesis,
     json.dumps([]), "hero", json.dumps([]), 1, "active", "", NOW, NOW))

con.commit()

# Verify
print("Project:", PROJECT_ID)
print("Products:", cur.execute("SELECT COUNT(*) FROM bs_products WHERE project_id=?",(PROJECT_ID,)).fetchone()[0])
print("Snippets:", cur.execute("SELECT COUNT(*) FROM bs_snippets WHERE project_id=?",(PROJECT_ID,)).fetchone()[0])
print("Plots:",    cur.execute("SELECT COUNT(*) FROM bs_plots WHERE project_id=?",(PROJECT_ID,)).fetchone()[0])
print("Active plot id:", PLOT_ID)
print("Plot thesis:", plot_thesis)
con.close()
