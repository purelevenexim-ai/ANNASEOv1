"""
GSC Engine — Main Orchestrator
Coordinates: OAuth status, data sync, processing, and output retrieval.

Phase 1 Upgrade: AI Project Understanding layer.
Phase 2 Upgrade: Intelligence Layer — embeddings, clustering, graph, insights.
Phase 3 Upgrade: Product + Execution — stage bridge, API key connect, export, tasks.

The pipeline is now:
  User Input → AI Config → GSC Sync (1 call) → Config-driven Processing
  → Phase 2: Embeddings → Intent AI → Clustering → Graph → Scoring v2 → Insights
  → Phase 3: Stage Data Bridge → AI Intelligence Summary → Tasks → Export
"""
import logging
from datetime import datetime

from . import gsc_db, gsc_client, gsc_processor
from .gsc_ai_config import ProjectConfig, generate_project_config

log = logging.getLogger(__name__)


class GscEngine:
    """Main entry point for all GSC operations."""

    # ─── Project Intelligence Config ─────────────────────────────────────────

    def generate_config(
        self,
        project_id: str,
        business_description: str,
        goal: str = "sales",
        seed_keywords: list[str] | None = None,
        target_audience: str = "",
    ) -> dict:
        """
        Step 1 of the pipeline: run the AI prompt to generate a structured
        ProjectConfig from user's business description, then store it in DB.

        Returns the config dict (serializable for API response).
        """
        log.info(f"[GSC] Generating AI project config for {project_id}")
        config = generate_project_config(
            business_description=business_description,
            goal=goal,
            seed_keywords=seed_keywords,
            target_audience=target_audience,
        )
        gsc_db.upsert_project_config(project_id, config.to_dict())
        log.info(
            f"[GSC] Config stored: {len(config.pillars)} pillars, "
            f"{len(config.purchase_intent_keywords)} intent signals"
        )
        return config.to_dict()

    def get_config(self, project_id: str) -> dict | None:
        """Return the stored project config or None."""
        return gsc_db.get_project_config(project_id)

    def update_config(self, project_id: str, updates: dict) -> dict:
        """Manually update/override the stored project config."""
        existing = gsc_db.get_project_config(project_id) or {}
        existing.update(updates)
        existing["source"] = "manual"
        gsc_db.upsert_project_config(project_id, existing)
        return gsc_db.get_project_config(project_id)

    # ─── Integration Status ──────────────────────────────────────────────
    def get_status(self, project_id: str) -> dict:
        """Return current GSC integration status for a project."""
        gsc_db.init_tables()
        integration = gsc_db.get_integration(project_id)
        if not integration:
            return {
                "status": "not_connected",
                "connected": False,
                "site_url": None,
                "last_synced": None,
                "raw_count": 0,
                "processed_count": 0,
            }

        stats = gsc_db.get_stats(project_id)
        return {
            "status": integration.get("status", "disconnected"),
            "connected": integration.get("status") in ("connected", "connected_stages"),
            "site_url": integration.get("site_url"),
            "updated_at": integration.get("updated_at"),
            **stats,
        }

    def get_auth_url(self, project_id: str) -> str:
        """Get the Google OAuth URL for this project."""
        return gsc_client.get_auth_url(project_id)

    def handle_callback(self, code: str, project_id: str) -> dict:
        """Exchange authorization code for tokens. Called from OAuth callback."""
        return gsc_client.exchange_code(code, project_id)

    def disconnect(self, project_id: str):
        """Remove stored tokens and reset integration status."""
        gsc_db.upsert_integration(
            project_id,
            access_token=None,
            refresh_token=None,
            token_expiry=None,
            status="disconnected",
        )

    # ─── Site Management ─────────────────────────────────────────────────────

    def list_sites(self, project_id: str) -> list[dict]:
        """List all verified GSC sites for the connected account."""
        return gsc_client.list_sites(project_id)

    def set_site(self, project_id: str, site_url: str):
        """Set the active site URL for this project."""
        gsc_db.upsert_integration(project_id, site_url=site_url)

    # ─── Data Sync ────────────────────────────────────────────────────────────

    def sync(self, project_id: str, days: int = 90) -> dict:
        """
        Fetch all GSC queries for the project's site.
        One API call — stores raw data in DB.
        """
        integration = gsc_db.get_integration(project_id)
        if not integration or integration.get("status") != "connected":
            raise ValueError("GSC not connected — authorize first")

        site_url = integration.get("site_url")
        if not site_url:
            raise ValueError("No site URL selected — call set_site() first")

        log.info(f"[GSC] Starting sync for {project_id} / {site_url} (last {days} days)")
        rows = gsc_client.fetch_queries(project_id, site_url, days=days)

        stats = gsc_db.get_stats(project_id)
        log.info(f"[GSC] Sync complete: {stats['raw_count']} total raw keywords")
        return {
            "fetched": len(rows),
            "total_in_db": stats["raw_count"],
        }

    # ─── Intelligence Processing ──────────────────────────────────────────────

    def process(self, project_id: str, pillars: list[str] | None = None) -> dict:
        """
        Run the full processing pipeline on raw GSC data.
        Uses AI ProjectConfig (if generated) for smarter pillar matching,
        intent classification, and supporting angle detection.

        Pipeline:
          Load config → Filter per pillar → Classify intent → Score → Top 100
        """
        # Build ProjectConfig: stored AI config > provided pillars
        stored_cfg = gsc_db.get_project_config(project_id)
        if stored_cfg:
            config = ProjectConfig.from_dict(stored_cfg)
            # Additive: allow explicit pillars to extend AI config
            if pillars:
                for p in pillars:
                    if p not in config.pillars:
                        config.pillars.append(p)
        elif pillars:
            config = ProjectConfig.from_pillars(pillars)
        else:
            raise ValueError(
                "No project config found and no pillars provided. "
                "Run 'Generate AI Config' first or supply pillars[] in the request body."
            )

        raw = gsc_db.get_raw_keywords(project_id)
        if not raw:
            raise ValueError("No raw GSC data — run sync first")

        log.info(
            f"[GSC] Processing {len(raw)} raw keywords | "
            f"{len(config.pillars)} pillars | source={config.source}"
        )
        processed = gsc_processor.process_keywords(raw, config)

        gsc_db.upsert_processed_keywords(project_id, processed)

        stats = gsc_db.get_stats(project_id)
        log.info(f"[GSC] Done: {stats['processed_count']} processed, {stats['top100_count']} top100")
        return {
            "processed":     len(processed),
            "top100":        stats["top100_count"],
            "pillars":       stats["pillar_count"],
            "config_source": config.source,
        }

    # ─── Output Retrieval ─────────────────────────────────────────────────────

    def get_keywords(self, project_id: str, pillar: str = None) -> list[dict]:
        """Get processed keywords, optionally filtered by pillar."""
        return gsc_db.get_processed_keywords(project_id, pillar=pillar)

    def get_top100(self, project_id: str) -> list[dict]:
        """Get the top 100 keywords per pillar (business-prioritized scoring)."""
        return gsc_db.get_top100(project_id)

    def get_tree(self, project_id: str) -> dict:
        """Get tree-structured output: Universe → Pillar → Intent Group → Keyword."""
        processed = gsc_db.get_processed_keywords(project_id)
        if not processed:
            return {}
        return gsc_processor.build_tree(processed)

    # ─── Phase 2: Intelligence Layer ──────────────────────────────────────────

    def run_intelligence(self, project_id: str, force_embeddings: bool = False) -> dict:
        """
        Run the full Phase 2 intelligence pipeline:
        Embeddings → AI Intent → Clustering → Graph → Scoring v2 → Insights → Authority
        """
        from .gsc_intelligence import run_pipeline
        return run_pipeline(project_id, force_embeddings=force_embeddings)

    def get_clusters(self, project_id: str) -> dict:
        """Return clusters: {cluster_name: [keywords]}."""
        return gsc_db.get_clusters(project_id)

    def get_graph(self, project_id: str, min_similarity: float = 0.3) -> dict:
        """Return keyword graph as {nodes, links} for UI."""
        return gsc_db.get_graph(project_id, min_similarity=min_similarity)

    def get_insights(self, project_id: str, insight_type: str = None) -> dict:
        """Return insights (all types or specific type)."""
        return gsc_db.get_insights(project_id, insight_type=insight_type)

    def get_authority(self, project_id: str) -> dict:
        """Return pillar authority scores."""
        return gsc_db.get_insights(project_id, insight_type="authority")

    # ─── Phase 3: Product + Execution Layer ───────────────────────────────────

    def validate_api_key(self, api_key: str) -> dict:
        """Validate a Gemini API key."""
        return gsc_client.validate_gemini_key(api_key)

    def get_stage_data(self, project_id: str) -> dict:
        """Get all available data from Stage 1 + Stage 2."""
        from .gsc_stage_bridge import get_stage_data
        return get_stage_data(project_id)

    def import_from_stages(self, project_id: str) -> dict:
        """Import keywords from Stage 1+2 into GSC raw data for processing."""
        from .gsc_stage_bridge import import_keywords_to_gsc
        return import_keywords_to_gsc(project_id)

    def generate_intelligence_summary(self, project_id: str) -> dict:
        """Generate AI intelligence summary from Stage 1+2 data."""
        from .gsc_stage_bridge import generate_intelligence_summary
        return generate_intelligence_summary(project_id)

    def get_intelligence_summary(self, project_id: str) -> dict | None:
        """Get stored intelligence summary."""
        return gsc_db.get_intelligence_summary(project_id)

    # ─── Tasks ────────────────────────────────────────────────────────────────

    def create_task(self, project_id: str, task: dict) -> int:
        return gsc_db.create_task(project_id, task)

    def get_tasks(self, project_id: str, status: str = None) -> list[dict]:
        return gsc_db.get_tasks(project_id, status)

    def update_task(self, project_id: str, task_id: int, updates: dict) -> bool:
        return gsc_db.update_task(project_id, task_id, updates)

    def delete_task(self, project_id: str, task_id: int):
        return gsc_db.delete_task(project_id, task_id)

    # ─── Export ───────────────────────────────────────────────────────────────

    def export_data(self, project_id: str, export_type: str = "full") -> dict:
        """Generate an export of all GSC data for the project."""
        stats = self.get_status(project_id)
        keywords = self.get_keywords(project_id)
        top100 = self.get_top100(project_id)
        tree = self.get_tree(project_id)
        clusters = self.get_clusters(project_id)
        insights = self.get_insights(project_id)
        summary = self.get_intelligence_summary(project_id)
        tasks = self.get_tasks(project_id)

        data = {
            "project_id": project_id,
            "exported_at": datetime.utcnow().isoformat(),
            "stats": stats,
            "intelligence_summary": summary,
        }

        if export_type in ("full", "keywords"):
            data["keywords"] = keywords
            data["top100"] = top100

        if export_type in ("full", "strategy"):
            data["tree"] = tree
            data["clusters"] = clusters
            data["insights"] = insights

        if export_type in ("full", "tasks"):
            data["tasks"] = tasks

        eid = gsc_db.save_export(project_id, export_type, data)
        data["export_id"] = eid
        return data
