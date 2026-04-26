# Test Generator

## Unit Tests
```python
import pytest
from unittest import TestCase
from engines.kw2.business_analyzer import BusinessIntelligenceEngine

class TestBusinessIntelligenceEngine(TestCase):
    def test_crawl(self):
        engine = BusinessIntelligenceEngine()
        url = "https://example.com"
        pages = engine._crawl(url)
        assert len(pages) == 10, f"Expected 10 pages but got {len(pages)}"
```
## Integration Tests
```python
import pytest
from unittest import TestCase
from engines.kw2.business_analyzer import BusinessIntelligenceEngine

class TestBusinessIntelligenceEngineIntegration(TestCase):
    def test_full_analysis(self):
        engine = BusinessIntelligenceEngine()
        project_id = "test-project"
        url = "https://example.com"
        manual_input = {"name": "Example Company", "industry": "Technology"}
        competitor_urls = ["https://competitor1.com", "https://competitor2.com"]
        ai_provider = "auto"
        force = False

        result = engine.analyze(project_id, url, manual_input, competitor_urls, ai_provider, force)
        assert isinstance(result, dict), f"Expected a dictionary but got {type(result)}"
        assert "confidence_score" in result, f"Expected 'confidence_score' but it's not present in the result"
```
## Edge Case Tests
```python
import pytest
from unittest import TestCase
from engines.kw2.business_analyzer import BusinessIntelligenceEngine

class TestBusinessIntelligenceEngineEdgeCases(TestCase):
    def test_empty_input(self):
        engine = BusinessIntelligenceEngine()
        project_id = ""
        url = None
        manual_input = {}
        competitor_urls = []
        ai_provider = "auto"
        force = False

        with self.assertRaises(ValueError):
            engine.analyze(project_id, url, manual_input, competitor_urls, ai_provider, force)

    def test_null_input(self):
        engine = BusinessIntelligenceEngine()
        project_id = None
        url = None
        manual_input = {}
        competitor_urls = []
        ai_provider = "auto"
        force = False

        with self.assertRaises(TypeError):
            engine.analyze(project_id, url