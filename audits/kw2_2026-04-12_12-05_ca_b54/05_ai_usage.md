# AI Usage

## Reduce AI Cost Plan

The provided code has several AI calls that can be reduced or replaced with more efficient methods. Here's a plan to reduce the AI cost:

1. **Replace `kw2_ai_call` with `kw2_extract_json`**: The `kw2_ai_call` function is used to call an external AI service, which can be expensive. Instead, we can use the `kw2_extract_json` function, which extracts JSON data from a URL and returns it as a Python dictionary. This will eliminate the need for an external API call.
```python
from engines.kw2.ai_caller import kw2_extract_json

# ...
def analyze(
    # ...
    ai_provider: str = "auto",
    force: bool = False,
) -> dict:
    # ...
    if ai_provider == "auto":
        response = kw2_extract_json("https://api.example.com/ai-service")
        result = response["result"]
        # ...
```
1. **Replace `kw2_ai_call` with a custom function**: If the external AI service is not available or too expensive, we can create a custom function that performs similar tasks using deterministic rules. For example, if we need to extract entities from text, we can use regular expressions or NLP libraries like NLTK or spaCy instead of an external API.
```python
import re
from nltk.tokenize import word_tokenize
from nltk.tag import pos_tag

def extract_entities(text: str) -> dict:
    entities = {}
    words = word_tokenize(text)
    tagged_words = pos_tag(words)
    
    for word, tag in tagged_words:
        if tag.startswith("NN") or tag.startswith("NNS"):
            entity = re.search(r"[A-Z][a-z]+", word).group()
            entities[entity] = True
            
    return entities
```
1. **Replace `kw2_ai_call` with a custom function**: If the external AI service is not available or too expensive, we can create a custom function that performs similar tasks using deterministic rules. For example, if we need to compute a confidence score, we can use a simple rule-based approach instead of an external API.
```python
def compute_confidence(score: float) -> float:
    if score >= 0.9:
        return 1.0
    elif score >= 0.8:
        return 0.9
    else: