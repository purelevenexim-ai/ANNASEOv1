# AI Usage

The provided code uses several AI functions and libraries to perform various tasks such as audience chain expansion, intent classification, scoring, persona elaboration, context keyword generation, and final strategy synthesis. Here is an audit of the AI usage in this code:

1. **Audience Chain Expansion**: The `DeepSeek` function from Ollama library is used to expand the audience chain. However, it's not clear if this expansion is necessary or if deterministic rules could be used instead. To reduce AI cost, we can replace the `DeepSeek` function with a simple rule-based approach that expands the audience chain based on predefined criteria.
2. **Intent Classification and Scoring**: The `DeepSeek` function is also used for intent classification and scoring. Again, it's not clear if this step is necessary or if deterministic rules could be used instead. To reduce AI cost, we can replace the `DeepSeek` function with a simple rule-based approach that classifies intents and assigns scores based on predefined criteria.
3. **Persona Elaboration**: The `Gemini` function is used for persona elaboration. However, it's not clear if this step is necessary or if deterministic rules could be used instead. To reduce AI cost, we can replace the `Gemini` function with a simple rule-based approach that generates personas based on predefined criteria.
4. **Context Keyword Generation**: The `DeepSeek` function is used for context keyword generation. Again, it's not clear if this step is necessary or if deterministic rules could be used instead. To reduce AI cost, we can replace the `DeepSeek` function with a simple rule-based approach that generates keywords based on predefined criteria.
5. **Final Strategy Synthesis**: The `Claude Sonnet` function is used for final strategy synthesis. However, it's not clear if this step is necessary or if deterministic rules could be used instead. To reduce AI cost, we can replace the `Claude Sonnet` function with a simple rule-based approach that generates strategies based on predefined criteria.

Based on the above audit, here is a plan to reduce AI cost:

1. Replace the `DeepSeek` function with a simple rule-based approach for audience chain expansion, intent classification and scoring, context keyword generation, and final strategy synthesis.
2. Use deterministic rules instead of AI for persona elaboration.
3. Implement a predefined criteria-based approach for each AI step to reduce unnecessary AI usage and expensive calls.