# Test Generator

```python
import pytest
from ruflo_strategy_dev_engine import AudienceChainExpander, PersonaElaborator, StrategySynthesizer

def test_audience_chain_expansion():
    # Test with valid input
    audience_data = {
        "location": "Malaysia",
        "religion": "Islam",
        "language": "Malay"
    }
    expected_keyword_clusters = ["Malaysian Muslim", "Malaysian Islam"]
    actual_keyword_clusters = AudienceChainExpander(audience_data).expand_chain()
    assert actual_keyword_clusters == expected_keyword_clusters

def test_persona_elaboration():
    # Test with valid input
    persona_data = {
        "name": "Mary",
        "age": 35,
        "gender": "female",
        "location": "Malaysia",
        "religion": "Islam",
        "language": "Malay"
    }
    expected_persona = PersonaElaborator(persona_data).elaborate()
    actual_persona = PersonaElaborator(persona_data).elaborate()
    assert actual_persona == expected_persona

def test_strategy_synthesis():
    # Test with valid input
    keyword_clusters = ["Malaysian Muslim", "Malaysian Islam"]
    persona = {
        "name": "Mary",
        "age": 35,
        "gender": "female",
        "location": "Malaysia",
        "religion": "Islam",
        "language": "Malay"
    }
    expected_strategy = StrategySynthesizer(keyword_clusters, persona).synthesize()
    actual_strategy = StrategySynthesizer(keyword_clusters, persona).synthesize()
    assert actual_strategy == expected_strategy
```