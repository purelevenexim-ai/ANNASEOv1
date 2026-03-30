from jsonschema import validate, ValidationError
from pydantic import BaseModel, StrictStr, StrictFloat, StrictInt, ValidationError as PydanticValidationError
from typing import List, Dict, Any


class StrategyOutputModel(BaseModel):
    audience: Dict[str, Any]
    angles: List[Any]
    outline: List[Any]
    links: List[Any]
    scores: Dict[str, Any]

    class Config:
        extra = "forbid"


def validate_strategy_output(data: dict, schema: dict):
    try:
        validate(instance=data, schema=schema)
        return True, None
    except ValidationError as e:
        return False, str(e)


def validate_strategy(strategy: dict) -> None:
    required_keys = ["audience", "angles", "outline", "links", "scores"]

    if not isinstance(strategy, dict):
        raise ValueError("strategy must be an object")

    for key in required_keys:
        if key not in strategy:
            raise ValueError(f"Missing key: {key}")

    if not isinstance(strategy["angles"], list):
        raise ValueError("angles must be list")

    if not isinstance(strategy["outline"], list):
        raise ValueError("outline must be list")

    if not isinstance(strategy["links"], list):
        raise ValueError("links must be list")

    if not isinstance(strategy["scores"], dict):
        raise ValueError("scores must be object")
