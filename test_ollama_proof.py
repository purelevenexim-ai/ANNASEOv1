#!/usr/bin/env python3
"""Single Ollama article — proof point for the architecture plan."""
import sys, asyncio, uuid, time, re, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from engines.content_generation_engine import SEOContentPipeline, AIRoutingConfig, StepAIConfig
from bs4 import BeautifulSoup

async def main():
    cfg = StepAIConfig("ollama", "skip", "skip")
    routing = AIRoutingConfig(
        research=cfg, structure=cfg, verify=cfg, links=cfg, references=cfg,
        draft=cfg, recovery=cfg, review=cfg, issues=cfg, humanize=cfg, redevelop=cfg,
    )
    p = SEOContentPipeline(
        article_id=f"ollama_proof_{uuid.uuid4().hex[:6]}",
        keyword="how to choose kitchen spices",
        project_id="proj_ollama_proof",
        page_type="blog",
        intent="informational",
        word_count=1500,  # Smaller for time
        pipeline_mode="lean",
        ai_routing=routing,
    )
    t0 = time.time()
    try:
        await p.run()
        elapsed = time.time() - t0
        html = p.state.final_html or ""
        Path("/tmp/ollama_proof.html").write_text(html)
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text()
        print(json.dumps({
            "elapsed_sec": round(elapsed, 1),
            "words": len(text.split()),
            "h2_count": len(soup.find_all("h2")),
            "h3_count": len(soup.find_all("h3")),
            "lists": len(soup.find_all(["ul", "ol"])),
            "tables": len(soup.find_all("table")),
            "html_chars": len(html),
            "saved_to": "/tmp/ollama_proof.html",
        }, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e), "elapsed_sec": round(time.time() - t0, 1)}))

asyncio.run(main())
