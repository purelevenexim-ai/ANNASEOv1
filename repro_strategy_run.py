#!/usr/bin/env python3
import traceback
import json
import os

# Ensure ANNASEOv1 is on path
import sys
sys.path.insert(0, os.path.abspath('.'))

try:
    from engines.ruflo_strategy_dev_engine import StrategyDevelopmentEngine, UserInput, Industry, GeoLevel, Religion, Language
except Exception as e:
    print('Import error:', e)
    raise


def main():
    ui = UserInput(
        business_name='Test Co',
        website_url='https://example.com',
        industry=Industry.FOOD_SPICES,
        business_type='B2C',
        usp='Test USP',
        products=['organic tea'],
        competitor_urls=[],
        target_locations=[GeoLevel.NATIONAL],
        target_religions=[Religion.GENERAL],
        target_languages=[Language.ENGLISH],
        audience_personas=['home cooks'],
        ad_copy='Great tea',
        customer_reviews=['Good tea'],
    )

    try:
        print('Starting StrategyDevelopmentEngine.run()')
        engine = StrategyDevelopmentEngine()
        result = engine.run(ui)
        print('Engine completed. Result summary:')
        print(json.dumps(result if isinstance(result, dict) else {'result': str(result)}, indent=2))
    except Exception as e:
        print('Engine raised exception:')
        traceback.print_exc()

if __name__ == '__main__':
    main()
