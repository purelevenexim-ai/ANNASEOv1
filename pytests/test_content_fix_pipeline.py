from services.content_fix_generator import ContentFixGenerator
from services.section_scorer import SectionScorer


def test_content_fix_generator_basic():
    generator = ContentFixGenerator()
    fix = generator.generate_fix(
        keyword='best spices for chicken',
        root_causes=['keyword_gap', 'content_depth'],
        gaps=['spice combinations', 'cooking tips'],
        competitor_insights=[{'url':'https://example.com','headings':['h1','h2'],'word_count':1800}]
    )

    assert 'sections_to_add' in fix
    assert 'title_suggestion' in fix


def test_section_scorer_ranking():
    scorer = SectionScorer()
    ranked = scorer.rank_sections([
        {'heading':'A','content':'good content','keywords':['spice','chicken'], 'reason':'gap'},
        {'heading':'B','content':'short','keywords':[], 'reason':''}
    ], {'content_score':0.5}, [{'content_score':0.6}, {'content_score':0.7}])

    assert isinstance(ranked, list)
    assert ranked[0]['boost_score'] >= ranked[1]['boost_score']
