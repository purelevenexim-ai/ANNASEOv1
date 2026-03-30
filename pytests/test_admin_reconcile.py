from fastapi.testclient import TestClient
from main import app, get_db


def test_admin_reconcile_dry_run_and_apply():
    client = TestClient(app)

    # register a user (will be promoted to admin in DB)
    r = client.post('/api/auth/register', json={'email': 'admin@example.com', 'name': 'Admin', 'password': 'adminpass'})
    assert r.status_code == 200
    token = r.json().get('access_token')
    assert token

    # promote to admin (update DB role then re-login to get a token with admin role)
    db = get_db()
    row = db.execute('SELECT user_id FROM users WHERE email=?', ('admin@example.com',)).fetchone()
    assert row is not None
    uid = row['user_id']
    db.execute('UPDATE users SET role=? WHERE user_id=?', ('admin', uid))
    db.commit()

    # re-login to get a token that encodes the updated role
    login = client.post('/api/auth/login', data={'username': 'admin@example.com', 'password': 'adminpass'})
    assert login.status_code == 200
    token = login.json().get('access_token')
    assert token

    # create a project with owner_id but no user_projects mapping
    pid_owner_missing = 'proj_admin_missing'
    db.execute('INSERT OR IGNORE INTO projects(project_id,name,industry,owner_id,created_at,updated_at) VALUES(?,?,?,?,datetime("now"),datetime("now"))', (pid_owner_missing, 'OwnerMissing', 'general', uid))
    db.commit()

    # create strategy_session referencing a missing project id
    missing_proj_ref = 'proj_referenced_only'
    db.execute('INSERT OR IGNORE INTO strategy_sessions(session_id, project_id, engine_type, status) VALUES(?,?,?,?)', ('sess_ref_1', missing_proj_ref, 'audience', 'pending'))
    db.commit()

    headers = {'Authorization': f'Bearer {token}'}

    # Dry-run
    resp = client.post('/api/admin/reconcile-projects', json={'apply': False}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert any(m['project_id'] == pid_owner_missing for m in data['missing_mappings'])
    assert missing_proj_ref in data['missing_projects']

    # Apply changes
    resp2 = client.post('/api/admin/reconcile-projects', json={'apply': True}, headers=headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    # mapping should have been added
    mp = db.execute('SELECT 1 FROM user_projects WHERE project_id=? AND user_id=?', (pid_owner_missing, uid)).fetchone()
    assert mp is not None
    # placeholder project should have been created
    pr = db.execute('SELECT project_id FROM projects WHERE project_id=?', (missing_proj_ref,)).fetchone()
    assert pr is not None
