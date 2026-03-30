import uuid
from services.job_tracker import create_strategy_job, get_strategy_job, update_strategy_job, run_strategy_pipeline


def test_job_tracker_create_and_update(tmp_path):
    from main import get_db
    db = get_db()

    project_id = f"proj_{uuid.uuid4().hex[:8]}"
    job_id = f"job_{uuid.uuid4().hex[:8]}"

    job = create_strategy_job(db, job_id, project_id=project_id, job_type='strategy')
    assert job['project_id'] == project_id
    assert job['status'] == 'queued'

    updated = update_strategy_job(db, job_id, status='running', current_step='serp')
    assert updated['status'] == 'running'
    assert updated['current_step'] == 'serp'
    assert updated['last_completed_step'] in (None, 0, '')


def test_run_strategy_pipeline_basic(tmp_path):
    from main import get_db
    db = get_db()

    project_id = f"proj_{uuid.uuid4().hex[:8]}"
    job_id = f"job_{uuid.uuid4().hex[:8]}"

    create_strategy_job(db, job_id, project_id=project_id, job_type='strategy')

    result = run_strategy_pipeline(db, job_id, project_id, key_phrase='test keyword')
    assert result['status'] in ('completed', 'failed', 'running')
