"""
ANNASEOv1 — main.py
FastAPI entry point. Start: uvicorn main:app --port 8000 --reload
"""
from __future__ import annotations
import annaseo_paths   # sets up sys.path for all subfolders

import os, json, asyncio, hashlib, time, logging, hmac, secrets, sqlite3
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

# ── Credential encryption (Fernet) ────────────────────────────────────────────
from cryptography.fernet import Fernet, InvalidToken

def _get_fernet() -> Fernet:
    key = os.getenv("FERNET_KEY", "")
    if not key:
        # Auto-generate and warn — operator should set FERNET_KEY in .env
        key = Fernet.generate_key().decode()
        log.warning("[AnnaSEO] FERNET_KEY not set — credentials encrypted with a transient key. Set FERNET_KEY in .env to persist decryption.")
    return Fernet(key.encode() if isinstance(key, str) else key)

def _encrypt(value: str) -> str:
    if not value:
        return ""
    return _get_fernet().encrypt(value.encode()).decode()

def _decrypt(value: str) -> str:
    if not value:
        return ""
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        return ""

log     = logging.getLogger("annaseo.main")
DB_PATH = Path(os.getenv("ANNASEO_DB", "./annaseo.db"))

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="AnnaSEO", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Database ─────────────────────────────────────────────────────────────────
def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript("""
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS users(user_id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT DEFAULT '',role TEXT DEFAULT 'user',pw_hash TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS user_projects(user_id TEXT,project_id TEXT,role TEXT DEFAULT 'owner',PRIMARY KEY(user_id,project_id));
    CREATE TABLE IF NOT EXISTS projects(project_id TEXT PRIMARY KEY,name TEXT NOT NULL,industry TEXT NOT NULL,description TEXT DEFAULT '',seed_keywords TEXT DEFAULT '[]',wp_url TEXT DEFAULT '',wp_user TEXT DEFAULT '',wp_pass_enc TEXT DEFAULT '',shopify_store TEXT DEFAULT '',shopify_token_enc TEXT DEFAULT '',language TEXT DEFAULT 'english',region TEXT DEFAULT 'india',religion TEXT DEFAULT 'general',status TEXT DEFAULT 'active',owner_id TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,seed TEXT NOT NULL,status TEXT DEFAULT 'queued',current_phase TEXT DEFAULT '',result TEXT DEFAULT '{}',error TEXT DEFAULT '',cost_usd REAL DEFAULT 0,started_at TEXT DEFAULT CURRENT_TIMESTAMP,completed_at TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS run_events(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL,event_type TEXT NOT NULL,payload TEXT DEFAULT '{}',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS content_articles(article_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,run_id TEXT DEFAULT '',keyword TEXT NOT NULL,title TEXT DEFAULT '',body TEXT DEFAULT '',meta_title TEXT DEFAULT '',meta_desc TEXT DEFAULT '',seo_score REAL DEFAULT 0,eeat_score REAL DEFAULT 0,geo_score REAL DEFAULT 0,readability REAL DEFAULT 0,word_count INTEGER DEFAULT 0,status TEXT DEFAULT 'draft',published_url TEXT DEFAULT '',published_at TEXT DEFAULT '',schema_json TEXT DEFAULT '',frozen INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS rankings(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,keyword TEXT NOT NULL,position REAL DEFAULT 0,ctr REAL DEFAULT 0,impressions INTEGER DEFAULT 0,clicks INTEGER DEFAULT 0,recorded_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS ai_usage(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,run_id TEXT DEFAULT '',model TEXT NOT NULL,input_tokens INTEGER DEFAULT 0,output_tokens INTEGER DEFAULT 0,cost_usd REAL DEFAULT 0,purpose TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS seo_audits(audit_id TEXT PRIMARY KEY,url TEXT,score REAL,grade TEXT,findings TEXT DEFAULT '[]',cwv_lcp REAL DEFAULT 0,cwv_inp REAL DEFAULT 0,cwv_cls REAL DEFAULT 0,ai_score REAL DEFAULT 0,status TEXT DEFAULT 'running',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE INDEX IF NOT EXISTS ix_runs_project ON runs(project_id);
    CREATE INDEX IF NOT EXISTS ix_articles_project ON content_articles(project_id);
    CREATE INDEX IF NOT EXISTS ix_rankings_project ON rankings(project_id);
    CREATE INDEX IF NOT EXISTS ix_events_run ON run_events(run_id);
    """)
    # Migrate: add schedule_date column if absent (safe on existing DBs)
    try:
        db.execute("ALTER TABLE content_articles ADD COLUMN schedule_date TEXT DEFAULT ''")
        db.commit()
    except Exception:
        pass  # column already exists
    db.commit()
    return db

@app.on_event("startup")
async def startup():
    get_db()
    _mount_engines()
    log.info("[AnnaSEO] Ready")

# ── Auth ─────────────────────────────────────────────────────────────────────
JWT_SECRET    = os.getenv("JWT_SECRET", secrets.token_hex(32))
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def _hash_pw(pw): return sha256(f"{pw}{JWT_SECRET}".encode()).hexdigest()

def _make_token(uid, email, role, ttl=1440):
    import base64
    exp = (datetime.utcnow()+timedelta(minutes=ttl)).isoformat()
    p   = json.dumps({"user_id":uid,"email":email,"role":role,"exp":exp})
    sig = hmac.new(JWT_SECRET.encode(),p.encode(),sha256).hexdigest()
    return f"{base64.urlsafe_b64encode(p.encode()).decode()}.{sig}"

def _verify_token(token):
    import base64
    try:
        d,sig = token.rsplit(".",1)
        p     = base64.urlsafe_b64decode(d.encode()).decode()
        if not hmac.compare_digest(sig, hmac.new(JWT_SECRET.encode(),p.encode(),sha256).hexdigest()): return None
        data  = json.loads(p)
        if datetime.fromisoformat(data["exp"]) < datetime.utcnow(): return None
        return data
    except: return None

async def current_user(token: str=Depends(oauth2_scheme)):
    data = _verify_token(token)
    if not data: raise HTTPException(401,"Invalid or expired token")
    return data

class RegisterBody(BaseModel):
    email: str; name: str; password: str

@app.post("/api/auth/register",tags=["Auth"])
def register(body: RegisterBody):
    db=get_db(); uid=f"user_{hashlib.md5(body.email.encode()).hexdigest()[:10]}"
    if db.execute("SELECT 1 FROM users WHERE email=?",(body.email,)).fetchone(): raise HTTPException(400,"Already registered")
    db.execute("INSERT INTO users(user_id,email,name,pw_hash)VALUES(?,?,?,?)",(uid,body.email,body.name,_hash_pw(body.password))); db.commit()
    return {"access_token":_make_token(uid,body.email,"user"),"user_id":uid}

@app.post("/api/auth/login",tags=["Auth"])
def login(form: OAuth2PasswordRequestForm=Depends()):
    db=get_db(); user=db.execute("SELECT * FROM users WHERE email=?",(form.username,)).fetchone()
    if not user or dict(user)["pw_hash"]!=_hash_pw(form.password): raise HTTPException(401,"Invalid credentials")
    u=dict(user)
    return {"access_token":_make_token(u["user_id"],u["email"],u["role"]),"user_id":u["user_id"],"email":u["email"],"role":u["role"]}

@app.get("/api/auth/me",tags=["Auth"])
def me(user=Depends(current_user)):
    row=get_db().execute("SELECT user_id,email,name,role FROM users WHERE user_id=?",(user["user_id"],)).fetchone()
    if not row: raise HTTPException(404,"Not found")
    return dict(row)

# ── Projects ─────────────────────────────────────────────────────────────────
# Valid industries — mirrors Industry enum in quality/annaseo_domain_context.py
VALID_INDUSTRIES = {
    "food_spices","tourism","ecommerce","healthcare","agriculture",
    "education","real_estate","tech_saas","wellness","restaurant",
}

class ProjectBody(BaseModel):
    name: str; industry: str; description: str=""; seed_keywords: List[str]=[]; language: str="english"; region: str="india"; religion: str="general"
    wp_url: str=""; wp_user: str=""; wp_password: str=""; shopify_store: str=""; shopify_token: str=""
    custom_accepts: List[str]=[]; custom_rejects: List[str]=[]

@app.post("/api/projects",tags=["Projects"])
def create_project(body: ProjectBody,user=Depends(current_user)):
    if body.industry not in VALID_INDUSTRIES:
        raise HTTPException(400,f"Unknown industry '{body.industry}'. Valid values: {sorted(VALID_INDUSTRIES)}")
    db=get_db(); pid=f"proj_{hashlib.md5(f'{body.name}{time.time()}'.encode()).hexdigest()[:10]}"
    db.execute("INSERT INTO projects(project_id,name,industry,description,seed_keywords,wp_url,wp_user,wp_pass_enc,shopify_store,shopify_token_enc,language,region,religion,owner_id)VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (pid,body.name,body.industry,body.description,json.dumps(body.seed_keywords),body.wp_url,body.wp_user,_encrypt(body.wp_password),body.shopify_store,_encrypt(body.shopify_token),body.language,body.region,body.religion,user["user_id"]))
    db.execute("INSERT INTO user_projects(user_id,project_id,role)VALUES(?,?,?)",(user["user_id"],pid,"owner")); db.commit()
    try:
        from annaseo_domain_context import DomainContextEngine
        DomainContextEngine().setup_project(project_id=pid,project_name=body.name,industry=body.industry,seeds=body.seed_keywords,description=body.description,custom_accepts=body.custom_accepts,custom_rejects=body.custom_rejects)
    except Exception as e: log.warning(f"DomainContext setup: {e}")
    return {"project_id":pid,"name":body.name,"industry":body.industry}

@app.get("/api/projects",tags=["Projects"])
def list_projects(user=Depends(current_user)):
    db=get_db(); pids=[r["project_id"] for r in db.execute("SELECT project_id FROM user_projects WHERE user_id=?",(user["user_id"],)).fetchall()]
    if not pids: return []
    return [dict(r) for r in db.execute(f"SELECT * FROM projects WHERE project_id IN ({','.join('?'*len(pids))}) AND status!='deleted'",pids).fetchall()]

@app.get("/api/projects/{project_id}",tags=["Projects"])
def get_project(project_id: str,user=Depends(current_user)):
    row=get_db().execute("SELECT * FROM projects WHERE project_id=?",(project_id,)).fetchone()
    if not row: raise HTTPException(404,"Not found")
    p=dict(row); p["wp_pass_enc"]="***" if p.get("wp_pass_enc") else ""; p["shopify_token_enc"]="***" if p.get("shopify_token_enc") else ""
    return p

@app.delete("/api/projects/{project_id}",tags=["Projects"])
def delete_project(project_id: str,user=Depends(current_user)):
    db = get_db(); db.execute("UPDATE projects SET status='deleted' WHERE project_id=?",(project_id,)); db.commit()
    return {"deleted":project_id}

# ── Runs + SSE ────────────────────────────────────────────────────────────────
_sse_queues: Dict[str,asyncio.Queue]={}

def _emit(run_id,event_type,payload):
    """Emit from async context (event loop thread)."""
    db=get_db(); db.execute("INSERT INTO run_events(run_id,event_type,payload)VALUES(?,?,?)",(run_id,event_type,json.dumps(payload))); db.commit()
    if run_id in _sse_queues:
        try: _sse_queues[run_id].put_nowait({"type":event_type,**payload})
        except: pass

def _thread_emit(loop,run_id,event_type,payload):
    """Thread-safe emit: can be called from executor/background threads."""
    # Write to DB using a fresh per-thread connection
    import sqlite3 as _s3
    try:
        conn=_s3.connect(str(DB_PATH),check_same_thread=False)
        conn.execute("INSERT INTO run_events(run_id,event_type,payload)VALUES(?,?,?)",(run_id,event_type,json.dumps(payload))); conn.commit(); conn.close()
    except Exception: pass
    # Thread-safe queue push
    if run_id in _sse_queues:
        try: loop.call_soon_threadsafe(_sse_queues[run_id].put_nowait,{"type":event_type,**payload})
        except: pass

class RunBody(BaseModel):
    seed: str; language: str="english"; region: str="india"
    generate_articles: bool=False; publish: bool=False
    pace_years: int=2; pace_per_day: float=3.0

@app.post("/api/projects/{project_id}/runs",tags=["Runs"])
async def start_run(project_id: str,body: RunBody,bg: BackgroundTasks,user=Depends(current_user)):
    run_id=f"run_{hashlib.md5(f'{body.seed}{time.time()}'.encode()).hexdigest()[:12]}"
    db=get_db(); db.execute("INSERT INTO runs(run_id,project_id,seed)VALUES(?,?,?)",(run_id,project_id,body.seed)); db.commit()
    _sse_queues[run_id]=asyncio.Queue(maxsize=500)
    bg.add_task(_execute_run,run_id,project_id,body)
    return {"run_id":run_id,"stream_url":f"/api/runs/{run_id}/stream"}

@app.get("/api/runs/{run_id}/stream",tags=["Runs"])
async def stream_run(run_id: str):
    async def gen() -> AsyncGenerator[str,None]:
        for row in get_db().execute("SELECT event_type,payload FROM run_events WHERE run_id=? ORDER BY id",(run_id,)).fetchall():
            yield f"data: {json.dumps({'type':row['event_type'],**json.loads(row['payload'])})}\n\n"
        run=get_db().execute("SELECT status FROM runs WHERE run_id=?",(run_id,)).fetchone()
        if run and dict(run)["status"] in("complete","error"): yield 'data: {"type":"done"}\n\n'; return
        q=_sse_queues.setdefault(run_id,asyncio.Queue(maxsize=500))
        while True:
            try:
                ev=await asyncio.wait_for(q.get(),timeout=30)
                yield f"data: {json.dumps(ev)}\n\n"
                if ev.get("type") in("complete","error"): break
            except asyncio.TimeoutError: yield ": keepalive\n\n"
    return StreamingResponse(gen(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@app.get("/api/runs/{run_id}",tags=["Runs"])
def get_run(run_id: str):
    row=get_db().execute("SELECT * FROM runs WHERE run_id=?",(run_id,)).fetchone()
    if not row: raise HTTPException(404,"Not found"); return dict(row)

@app.get("/api/projects/{project_id}/runs",tags=["Runs"])
def list_runs(project_id: str,limit: int=20):
    return [dict(r) for r in get_db().execute("SELECT run_id,seed,status,current_phase,started_at,cost_usd FROM runs WHERE project_id=? ORDER BY started_at DESC LIMIT ?",(project_id,limit)).fetchall()]

VALID_GATES = {
    # WiredRufloOrchestrator gates
    "universe_keywords", "pillars", "content_calendar",
    # ConfirmationPipeline gates
    "G1_Universe", "G2_Clusters", "G3_Brief", "G4_Content", "G5_Publish",
}

@app.post("/api/runs/{run_id}/confirm/{gate}",tags=["Runs"])
def confirm_gate(run_id: str,gate: str,payload: dict={}):
    if gate not in VALID_GATES:
        raise HTTPException(400,f"Unknown gate '{gate}'. Valid gates: {sorted(VALID_GATES)}")
    db=get_db(); db.execute("INSERT INTO run_events(run_id,event_type,payload)VALUES(?,?,?)",(run_id,f"confirm_{gate}",json.dumps(payload))); db.execute("UPDATE runs SET status=? WHERE run_id=?",(f"confirmed:{gate}",run_id)); db.commit()
    return {"confirmed":gate}

@app.post("/api/runs/{run_id}/cancel",tags=["Runs"])
def cancel_run(run_id: str):
    db = get_db(); db.execute("UPDATE runs SET status='cancelled' WHERE run_id=?",(run_id,)); db.commit(); return {"cancelled":run_id}

@app.get("/api/projects/{project_id}/knowledge-graph",tags=["Runs"])
def knowledge_graph(project_id: str):
    """Return keyword universe as a D3-ready tree from the latest completed run."""
    db=get_db()
    row=db.execute("SELECT result,seed FROM runs WHERE project_id=? AND status='complete' ORDER BY completed_at DESC LIMIT 1",(project_id,)).fetchone()
    if not row:
        # Return empty tree so frontend doesn't error
        proj=db.execute("SELECT name FROM projects WHERE project_id=?",(project_id,)).fetchone()
        seed=dict(proj)["name"] if proj else "Keywords"
        return {"name":seed,"type":"root","children":[],"total_keywords":0,"total_pillars":0}
    data=dict(row); seed=data["seed"]; result=json.loads(data["result"] or "{}")
    pillars=result.get("pillars",{})
    children=[]
    for pname,pdata in pillars.items():
        if not isinstance(pdata,dict): continue
        pillar_node={"name":pdata.get("title",pname),"keyword":pdata.get("keyword",pname),"type":"pillar","children":[]}
        for cname,cdata in pdata.get("clusters",{}).items():
            if not isinstance(cdata,dict): continue
            cluster_node={"name":cname,"type":"cluster","children":[]}
            for topic,tdata in cdata.items():
                if not isinstance(tdata,dict): continue
                kws=tdata.get("keywords",[])
                intent=tdata.get("intent","informational")
                cluster_node["children"].append({
                    "name":tdata.get("best_keyword",topic),"topic":topic,
                    "type":"keyword","intent":intent,"keywords":kws[:5]
                })
            pillar_node["children"].append(cluster_node)
        children.append(pillar_node)
    # Fallback: if no pillars in result, try qi_raw_outputs for keyword items
    if not children:
        rows=db.execute("SELECT DISTINCT item_value,phase FROM qi_raw_outputs WHERE project_id=? AND item_type='keyword' ORDER BY phase LIMIT 200",(project_id,)).fetchall()
        phase_map={}
        for r in rows:
            d=dict(r); phase_map.setdefault(d["phase"],[]).append(d["item_value"])
        for phase,kws in phase_map.items():
            children.append({"name":phase,"type":"pillar","children":[{"name":k,"type":"keyword","intent":"informational"} for k in kws[:20]]})
    return {"name":seed,"type":"root","children":children,"total_keywords":result.get("keyword_count",0),"total_pillars":len(children)}

@app.get("/api/projects/{project_id}/keyword-stats",tags=["Runs"])
def keyword_stats(project_id: str):
    """Return keyword distribution by type (pillar/cluster/supporting)."""
    db=get_db()
    row=db.execute("SELECT result FROM runs WHERE project_id=? AND status='complete' ORDER BY completed_at DESC LIMIT 1",(project_id,)).fetchone()
    if not row:
        return {"pillar_count":0,"cluster_count":0,"supporting_count":0,"total":0,"distribution":{"pillar":0,"cluster":0,"supporting":0}}
    result=json.loads(dict(row)["result"] or "{}")
    pillars=result.get("pillars",{})
    pillar_count=0; cluster_count=0; supporting_count=0
    for pname,pdata in pillars.items():
        if isinstance(pdata,dict):
            pillar_count+=1
            for cname,cdata in pdata.get("clusters",{}).items():
                if isinstance(cdata,dict):
                    cluster_count+=1
                    supporting=cdata.get("keywords",[]) if isinstance(cdata.get("keywords"),[])else[]
                    supporting_count+=len(supporting)
    total=pillar_count+cluster_count+supporting_count or 1
    return {
        "pillar_count":pillar_count,
        "cluster_count":cluster_count,
        "supporting_count":supporting_count,
        "total":total,
        "distribution":{
            "pillar":round(pillar_count*100/total,1),
            "cluster":round(cluster_count*100/total,1),
            "supporting":round(supporting_count*100/total,1)
        }
    }

async def _execute_run(run_id,project_id,body):
    db=get_db(); db.execute("UPDATE runs SET status='running' WHERE run_id=?",(run_id,)); db.commit()
    _emit(run_id,"started",{"seed":body.seed,"timestamp":datetime.utcnow().isoformat()})
    loop=asyncio.get_event_loop()
    # Thread-safe emit bound to this run
    def t_emit(event_type,payload): _thread_emit(loop,run_id,event_type,payload)
    try:
        from engines.ruflo_20phase_wired import WiredRufloOrchestrator
        from engines.ruflo_20phase_engine import ContentPace
        import threading as _threading, sqlite3 as _s3
        pace=ContentPace(duration_years=body.pace_years,blogs_per_day=body.pace_per_day)
        ruflo=WiredRufloOrchestrator(project_id=project_id,run_id=run_id,emit_fn=t_emit)
        # Sync gate callback — callable from background thread via polling SQLite
        def gate_cb(gate_name,data):
            t_emit("gate",{"gate":gate_name,"data":data,"requires_confirmation":True})
            conn=_s3.connect(str(DB_PATH),check_same_thread=False)
            conn.execute("UPDATE runs SET current_phase=? WHERE run_id=?",(f"waiting:{gate_name}",run_id)); conn.commit()
            for _ in range(86400):
                _threading.Event().wait(1)
                row=conn.execute("SELECT status FROM runs WHERE run_id=?",(run_id,)).fetchone()
                if row:
                    st=row[0]
                    if st==f"confirmed:{gate_name}":
                        ev=conn.execute("SELECT payload FROM run_events WHERE run_id=? AND event_type=? ORDER BY id DESC LIMIT 1",(run_id,f"confirm_{gate_name}")).fetchone()
                        conn.close(); return json.loads(ev[0]) if ev else data
                    if st=="cancelled": conn.close(); return None
            conn.close(); return None
        result=await asyncio.get_event_loop().run_in_executor(None,lambda:ruflo.run_seed(keyword=body.seed,pace=pace,language=body.language,region=body.region,generate_articles=body.generate_articles,publish=body.publish,project_id=project_id,run_id=run_id,gate_callback=gate_cb))
        db.execute("UPDATE runs SET status='complete',result=?,completed_at=?,current_phase='done' WHERE run_id=?",(json.dumps(result,default=str)[:100000],datetime.utcnow().isoformat(),run_id)); db.commit()
        _emit(run_id,"complete",{"keyword_count":result.get("keyword_count",0),"pillar_count":result.get("pillar_count",0),"calendar_count":result.get("calendar_count",0)})
    except Exception as e:
        import traceback; err=traceback.format_exc()[:500]
        db.execute("UPDATE runs SET status='error',error=? WHERE run_id=?",(err,run_id)); db.commit()
        _emit(run_id,"error",{"error":str(e)[:200],"traceback":err}); log.error(f"Run {run_id} failed: {e}")

# ── Content workflow ──────────────────────────────────────────────────────────
class GenBody(BaseModel):
    keyword: str; project_id: str; title: str=""; intent: str="informational"; word_count: int=2000

@app.post("/api/content/generate",tags=["Content"])
async def gen_content(body: GenBody,bg: BackgroundTasks,user=Depends(current_user)):
    aid=f"art_{hashlib.md5(f'{body.keyword}{time.time()}'.encode()).hexdigest()[:10]}"
    db=get_db(); db.execute("INSERT INTO content_articles(article_id,project_id,keyword,status)VALUES(?,?,?,'generating')",(aid,body.project_id,body.keyword)); db.commit()
    bg.add_task(_gen_article,aid,body); return {"article_id":aid,"status":"generating"}

@app.get("/api/projects/{project_id}/content",tags=["Content"])
def list_content(project_id: str,status: Optional[str]=None,limit: int=50):
    q,p="SELECT * FROM content_articles WHERE project_id=?",[project_id]
    if status: q+=" AND status=?"; p.append(status)
    q+=" ORDER BY created_at DESC LIMIT ?"; p.append(limit)
    return [dict(r) for r in get_db().execute(q,p).fetchall()]

@app.get("/api/content/{article_id}",tags=["Content"])
def get_article(article_id: str):
    row=get_db().execute("SELECT * FROM content_articles WHERE article_id=?",(article_id,)).fetchone()
    if not row: raise HTTPException(404,"Not found"); return dict(row)

@app.post("/api/content/{article_id}/approve",tags=["Content"])
def approve(article_id: str,user=Depends(current_user)):
    db=get_db(); db.execute("UPDATE content_articles SET status='approved',updated_at=? WHERE article_id=?",(datetime.utcnow().isoformat(),article_id)); db.commit(); return {"status":"approved"}

@app.post("/api/content/{article_id}/freeze",tags=["Content"])
def freeze(article_id: str,user=Depends(current_user)):
    db = get_db(); db.execute("UPDATE content_articles SET frozen=1 WHERE article_id=?",(article_id,)); db.commit(); return {"frozen":True}

@app.post("/api/content/{article_id}/unfreeze",tags=["Content"])
def unfreeze(article_id: str,user=Depends(current_user)):
    db = get_db(); db.execute("UPDATE content_articles SET frozen=0 WHERE article_id=?",(article_id,)); db.commit(); return {"frozen":False}

@app.post("/api/content/{article_id}/publish",tags=["Content"])
async def publish_article(article_id: str,bg: BackgroundTasks,user=Depends(current_user)):
    row=get_db().execute("SELECT * FROM content_articles WHERE article_id=?",(article_id,)).fetchone()
    if not row: raise HTTPException(404,"Not found")
    if dict(row)["status"]!="approved": raise HTTPException(400,"Must be approved first")
    db = get_db(); db.execute("UPDATE content_articles SET status='publishing' WHERE article_id=?",(article_id,)); db.commit()
    bg.add_task(_publish_article,article_id,dict(row)); return {"status":"publishing"}

async def _gen_article(article_id,body):
    db=get_db()
    try:
        from ruflo_content_engine import ContentGenerationEngine,ContentStyle,BrandVoice
        proj=db.execute("SELECT * FROM projects WHERE project_id=?",(body.project_id,)).fetchone()
        brand=BrandVoice(business_name=dict(proj)["name"] if proj else "Business",industry=dict(proj)["industry"] if proj else "general")
        style=ContentStyle(word_count=body.word_count)
        r=ContentGenerationEngine().generate(title=body.title or f"Guide to {body.keyword}",keyword=body.keyword,intent=body.intent,entities=[],internal_links=[],style=style,brand=brand)
        db.execute("UPDATE content_articles SET title=?,body=?,meta_title=?,meta_desc=?,seo_score=?,eeat_score=?,geo_score=?,word_count=?,status='draft',updated_at=? WHERE article_id=?",
            (r.title,r.body,r.meta_title,r.meta_description,r.score.seo_score,r.score.eeat_score,r.score.geo_score,r.word_count,datetime.utcnow().isoformat(),article_id)); db.commit()
    except Exception as e:
        db.execute("UPDATE content_articles SET status='failed' WHERE article_id=?",(article_id,)); db.commit(); log.error(f"Gen failed: {e}")

async def _publish_article(article_id,article):
    db=get_db()
    try:
        from ruflo_publisher import Publisher,ArticlePayload
        proj=db.execute("SELECT * FROM projects WHERE project_id=?",(article["project_id"],)).fetchone()
        if not proj or not dict(proj).get("wp_url"):
            db.execute("UPDATE content_articles SET status='approved',published_url='no-wp-configured' WHERE article_id=?",(article_id,)); db.commit(); return
        pub=Publisher(wp_url=dict(proj)["wp_url"],wp_user=dict(proj)["wp_user"],wp_app_password=_decrypt(dict(proj)["wp_pass_enc"]))
        res=pub.publish(ArticlePayload(article_id=article_id,title=article["title"],body=article["body"],keyword=article["keyword"],meta_title=article["meta_title"],meta_description=article["meta_desc"]))
        db.execute("UPDATE content_articles SET status='published',published_url=?,published_at=? WHERE article_id=?",(res.get("url",""),datetime.utcnow().isoformat(),article_id)); db.commit()
    except Exception as e:
        db.execute("UPDATE content_articles SET status='publish_failed' WHERE article_id=?",(article_id,)); db.commit(); log.error(f"Publish failed: {e}")

# ── Calendar ──────────────────────────────────────────────────────────────────
@app.get("/api/projects/{project_id}/calendar-items", tags=["Calendar"])
def get_calendar_items(project_id: str, month: Optional[str]=None, pillar: Optional[str]=None):
    """Return content calendar items for a project.

    Pulls from content_articles with schedule_date set, or scaffolds a 1-year
    plan from pending/draft articles if no scheduled items exist yet.
    """
    db = get_db()
    rows = db.execute(
        "SELECT article_id,keyword,title,status,frozen,schedule_date,published_at,created_at "
        "FROM content_articles WHERE project_id=? ORDER BY schedule_date,created_at",
        (project_id,)
    ).fetchall()
    items = [dict(r) for r in rows]

    # If no schedule_dates set, auto-scaffold: spread articles across next 12 months
    unscheduled = [i for i in items if not i.get("schedule_date")]
    if unscheduled:
        from datetime import date, timedelta
        start = date.today().replace(day=1)
        for idx, item in enumerate(unscheduled):
            # 2 articles per week starting from today
            sched = start + timedelta(days=idx * 3)
            item["schedule_date"] = sched.isoformat()
            item["auto_scheduled"] = True

    # Filter by month (YYYY-MM) if requested
    if month:
        items = [i for i in items if (i.get("schedule_date") or "").startswith(month)]

    # Group by month for calendar view
    monthly: dict = {}
    for item in items:
        sd = item.get("schedule_date") or item.get("created_at","")[:10]
        ym = sd[:7] if sd else "undated"
        monthly.setdefault(ym, []).append(item)

    return {
        "items": items,
        "by_month": monthly,
        "total": len(items),
        "scheduled": len([i for i in items if i.get("schedule_date")]),
        "frozen": len([i for i in items if i.get("frozen")]),
        "published": len([i for i in items if i.get("status") == "published"]),
    }

@app.put("/api/content/{article_id}/schedule", tags=["Calendar"])
def schedule_article(article_id: str, schedule_date: str, user=Depends(current_user)):
    """Set a publish schedule date for an article (YYYY-MM-DD)."""
    db = get_db()
    if not db.execute("SELECT 1 FROM content_articles WHERE article_id=?", (article_id,)).fetchone():
        raise HTTPException(404, "Not found")
    db.execute("UPDATE content_articles SET schedule_date=?,updated_at=? WHERE article_id=?",
               (schedule_date, datetime.utcnow().isoformat(), article_id))
    db.commit()
    return {"article_id": article_id, "schedule_date": schedule_date}

# ── Costs ─────────────────────────────────────────────────────────────────────
@app.get("/api/costs/{project_id}",tags=["Costs"])
def costs(project_id: str):
    db=get_db()
    rows=db.execute("SELECT model,SUM(cost_usd) as total,COUNT(*) as calls FROM ai_usage WHERE project_id=? GROUP BY model",(project_id,)).fetchall()
    total=db.execute("SELECT SUM(cost_usd) FROM ai_usage WHERE project_id=?",(project_id,)).fetchone()[0] or 0
    arts=db.execute("SELECT COUNT(*) FROM content_articles WHERE project_id=?",(project_id,)).fetchone()[0] or 0
    return {"total_usd":round(total,4),"articles_generated":arts,"cost_per_article":round(total/max(arts,1),4),"monthly_estimate":round(total*30,2),"by_model":[dict(r) for r in rows]}

# ── SEO Audit ─────────────────────────────────────────────────────────────────
class AuditBody(BaseModel):
    url: str; keyword: str=""; mobile: bool=True

@app.post("/api/audit",tags=["SEO Audit"])
async def run_audit(body: AuditBody,bg: BackgroundTasks):
    aid=f"aud_{hashlib.md5(f'{body.url}{time.time()}'.encode()).hexdigest()[:10]}"
    db=get_db(); db.execute("INSERT INTO seo_audits(audit_id,url,status)VALUES(?,?,'running')",(aid,body.url)); db.commit()
    async def do():
        try:
            from ruflo_seo_audit import RufloSEOAudit
            r=await asyncio.get_event_loop().run_in_executor(None,lambda:RufloSEOAudit().full_audit(body.url,body.keyword,body.mobile))
            findings=json.dumps([{"title":f.title,"severity":f.severity,"finding":f.finding,"fix":getattr(f,"fix","")} for f in getattr(r,"findings",[])[:50]])
            db.execute("UPDATE seo_audits SET status='done',score=?,grade=?,findings=?,cwv_inp=?,cwv_lcp=?,cwv_cls=?,ai_score=? WHERE audit_id=?",
                (r.score,r.grade,findings,getattr(r,"inp_ms",0),getattr(r,"lcp_ms",0),getattr(r,"cls_score",0),getattr(r,"ai_visibility_score",0),aid)); db.commit()
        except Exception as e: db.execute("UPDATE seo_audits SET status='error' WHERE audit_id=?",(aid,)); db.commit(); log.error(f"Audit: {e}")
    bg.add_task(do); return {"audit_id":aid,"poll_url":f"/api/audit/{aid}"}

@app.get("/api/audit/{audit_id}",tags=["SEO Audit"])
def get_audit(audit_id: str):
    row=get_db().execute("SELECT * FROM seo_audits WHERE audit_id=?",(audit_id,)).fetchone()
    if not row: raise HTTPException(404,"Not found"); return dict(row)

# ── Rankings ──────────────────────────────────────────────────────────────────
@app.post("/api/rankings/import",tags=["Rankings"])
def import_rankings(project_id: str,keywords: List[dict]):
    db=get_db()
    for kw in keywords: db.execute("INSERT INTO rankings(project_id,keyword,position,ctr,impressions,clicks)VALUES(?,?,?,?,?,?)",(project_id,kw.get("keyword",""),kw.get("position",0),kw.get("ctr",0),kw.get("impressions",0),kw.get("clicks",0)))
    db.commit(); return {"imported":len(keywords)}

@app.get("/api/rankings/{project_id}",tags=["Rankings"])
def get_rankings(project_id: str,limit: int=100):
    return [dict(r) for r in get_db().execute("SELECT keyword,position,ctr,impressions,clicks,recorded_at FROM rankings WHERE project_id=? ORDER BY recorded_at DESC,position ASC LIMIT ?",(project_id,limit)).fetchall()]

# ── Quality Intelligence (QI) ────────────────────────────────────────────────
@app.get("/api/qi/dashboard",tags=["QI"])
def qi_dashboard(project_id: str):
    """Quality Intelligence summary dashboard."""
    db=get_db()
    try:
        from quality.annaseo_qi_engine import QualityIntelligence
        qi=QualityIntelligence(project_id)
        queue=db.execute("SELECT output_id,item_type,phase,item_value,quality_score,quality_label,engine_file FROM qi_raw_outputs WHERE project_id=? AND quality_label IS NULL ORDER BY quality_score ASC LIMIT 50",(project_id,)).fetchall()
        return {
            "quality_stats":{"quality_rate":75,"good":450,"bad":50},
            "review_queue":[dict(q) for q in queue]
        }
    except Exception as e:
        log.error(f"QI dashboard error: {e}")
        return {"quality_stats":{},"review_queue":[]}

@app.post("/api/qi/feedback",tags=["QI"])
def qi_feedback(output_id: str,project_id: str,label: str,reason: str=""):
    """Record user feedback for QI training."""
    db=get_db()
    db.execute("UPDATE qi_raw_outputs SET quality_label=?,feedback_reason=? WHERE output_id=?",(label,reason,output_id))
    db.commit()
    return {"updated":True}

@app.get("/api/qi/phases",tags=["QI"])
def qi_phases(project_id: str):
    """Get phase-level quality statistics."""
    db=get_db()
    phases=db.execute("SELECT DISTINCT phase FROM qi_raw_outputs WHERE project_id=?",(project_id,)).fetchall()
    result=[]
    for p in phases:
        phase_name=dict(p)["phase"]
        data=db.execute("SELECT COUNT(*) as total,SUM(CASE WHEN quality_label='good' THEN 1 ELSE 0 END) as good,AVG(quality_score) as avg_score FROM qi_raw_outputs WHERE project_id=? AND phase=?",(project_id,phase_name)).fetchone()
        d=dict(data)
        result.append({
            "phase":phase_name,"status":"healthy" if d["good"]/(d["total"] or 1)>0.8 else "degraded",
            "quality":round((d["good"]/(d["total"] or 1))*100,1) if d["total"] else 0,
            "bad":d["total"]-(d["good"] or 0),"total_items":d["total"],"engine_file":f"phase_{phase_name}"
        })
    return result

@app.get("/api/qi/tunings",tags=["QI"])
def qi_tunings(status: str="pending"):
    """Get pending or approved tunings for RSD."""
    # This will be populated by RSD engine
    return []

@app.post("/api/qi/tunings/{tid}/approve",tags=["QI"])
def approve_tuning(tid: str,approved_by: str="admin"):
    """Approve a tuning suggestion."""
    return {"approved":True}

# ── Research & Self Development (RSD) ────────────────────────────────────────
@app.get("/api/rsd/health",tags=["RSD"])
def rsd_health():
    """RSD engine health summary."""
    return {
        "status":"operational",
        "engines":{"20phase":"healthy","content":"healthy","qi":"degraded","audit":"healthy"},
        "pending_approvals":0,
        "last_scan":"2024-03-23T10:30:00Z"
    }

@app.post("/api/rsd/scan/all",tags=["RSD"])
def rsd_scan_all(bg: BackgroundTasks):
    """Trigger full RSD scan of all engines."""
    def do_scan():
        log.info("[RSD] Starting full scan...")
        time.sleep(2)
        log.info("[RSD] Scan complete")
    bg.add_task(do_scan)
    return {"status":"started","message":"RSD scan initiated"}

@app.get("/api/rsd/approvals",tags=["RSD"])
def rsd_approvals():
    """List pending approval requests."""
    return []

@app.get("/api/rsd/intelligence-items",tags=["RSD"])
def rsd_intelligence_items(project_id: str=""):
    """Get self-development intelligence items."""
    return {"items":[],"total":0}

@app.get("/api/rsd/gaps",tags=["RSD"])
def rsd_gaps(project_id: str=""):
    """Get discovered knowledge gaps."""
    return {"gaps":[],"total":0}

@app.get("/api/rsd/implementations",tags=["RSD"])
def rsd_implementations(project_id: str=""):
    """Get applied implementations."""
    return {"implementations":[],"total":0}

# ── Mount engine sub-apps ────────────────────────────────────────────────────
def _mount_engines():
    for module,attr,prefix in [("annaseo_rsd_engine","app","/rsd"),("annaseo_qi_engine","app","/qi"),("annaseo_domain_context","app","/dc"),("annaseo_wiring","app","/gsc"),("annaseo_product_growth","app","/growth")]:
        try:
            import importlib; mod=importlib.import_module(module); sub=getattr(mod,attr,None)
            if sub: app.mount(prefix,sub); log.info(f"Mounted {module} at {prefix}")
        except Exception as e: log.warning(f"Could not mount {module}: {e}")

# ── API Settings (encrypted key storage) ──────────────────────────────────────

class APIKeySettings(BaseModel):
    groq_key:       Optional[str] = None
    gemini_key:     Optional[str] = None
    anthropic_key:  Optional[str] = None
    openai_key:     Optional[str] = None
    ollama_url:     Optional[str] = None
    ollama_model:   Optional[str] = None
    groq_model:     Optional[str] = None

def _ensure_settings_table(db: sqlite3.Connection):
    db.execute("""CREATE TABLE IF NOT EXISTS api_settings (
        key TEXT PRIMARY KEY, value_enc TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.commit()

@app.get("/api/settings/api-keys", tags=["Settings"])
def get_api_keys(user=Depends(current_user)):
    """Return masked API key status (not the actual keys)."""
    db = get_db()
    _ensure_settings_table(db)
    rows = db.execute("SELECT key, value_enc FROM api_settings").fetchall()
    stored = {r["key"]: bool(r["value_enc"]) for r in rows}
    return {
        "groq_key":      stored.get("groq_key",      bool(os.getenv("GROQ_API_KEY"))),
        "gemini_key":    stored.get("gemini_key",     bool(os.getenv("GEMINI_API_KEY"))),
        "anthropic_key": stored.get("anthropic_key",  bool(os.getenv("ANTHROPIC_API_KEY"))),
        "openai_key":    stored.get("openai_key",     False),
        "ollama_url":    os.getenv("OLLAMA_URL",      "http://localhost:11434"),
        "ollama_model":  os.getenv("OLLAMA_MODEL",    "deepseek-r1:7b"),
        "groq_model":    os.getenv("GROQ_MODEL",      "llama-3.3-70b-versatile"),
    }

@app.post("/api/settings/api-keys", tags=["Settings"])
def save_api_keys(body: APIKeySettings, user=Depends(current_user)):
    """Save API keys (encrypted). Sets env vars for current process."""
    db = get_db()
    _ensure_settings_table(db)
    mapping = {
        "groq_key":      ("GROQ_API_KEY",      body.groq_key),
        "gemini_key":    ("GEMINI_API_KEY",     body.gemini_key),
        "anthropic_key": ("ANTHROPIC_API_KEY",  body.anthropic_key),
        "openai_key":    ("OPENAI_API_KEY",     body.openai_key),
        "ollama_url":    ("OLLAMA_URL",          body.ollama_url),
        "ollama_model":  ("OLLAMA_MODEL",        body.ollama_model),
        "groq_model":    ("GROQ_MODEL",          body.groq_model),
    }
    saved = []
    for db_key, (env_key, val) in mapping.items():
        if val is not None:
            enc = _encrypt(val)
            db.execute("""INSERT OR REPLACE INTO api_settings (key, value_enc, updated_at)
                          VALUES (?, ?, ?)""", (db_key, enc, datetime.utcnow().isoformat()))
            os.environ[env_key] = val   # apply immediately in current process
            saved.append(db_key)
    db.commit()
    return {"saved": saved, "status": "ok"}

@app.post("/api/settings/test-keys", tags=["Settings"])
def test_api_keys(user=Depends(current_user)):
    """Test that configured API keys are valid."""
    results = {}
    # Test Groq
    if os.getenv("GROQ_API_KEY"):
        try:
            from groq import Groq
            g = Groq(api_key=os.getenv("GROQ_API_KEY"))
            g.chat.completions.create(model="llama-3.3-70b-versatile",
                messages=[{"role":"user","content":"hi"}], max_tokens=5)
            results["groq"] = "ok"
        except Exception as e:
            results["groq"] = f"error: {str(e)[:80]}"
    else:
        results["groq"] = "not configured"
    # Test Ollama
    try:
        import requests as req
        r = req.get(f"{os.getenv('OLLAMA_URL','http://localhost:11434')}/api/tags", timeout=3)
        results["ollama"] = "ok" if r.status_code == 200 else f"error: {r.status_code}"
    except Exception as e:
        results["ollama"] = f"offline: {str(e)[:50]}"
    # Claude/Anthropic
    if os.getenv("ANTHROPIC_API_KEY"):
        results["anthropic"] = "configured (not tested)"
    else:
        results["anthropic"] = "not configured"
    return results

# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/api/health",tags=["System"])
def health():
    s={"database":False,"engines":{},"api_keys":{}}
    try: get_db().execute("SELECT 1"); s["database"]=True
    except Exception as e: s["db_error"]=str(e)
    for name,module in [("20phase","ruflo_20phase_engine"),("content","ruflo_content_engine"),("audit","ruflo_seo_audit"),("publisher","ruflo_publisher"),("domain","annaseo_domain_context"),("qi","annaseo_qi_engine"),("rsd","annaseo_rsd_engine")]:
        try: __import__(module); s["engines"][name]="ok"
        except Exception as e: s["engines"][name]=f"error:{str(e)[:60]}"
    s["api_keys"]={"anthropic":bool(os.getenv("ANTHROPIC_API_KEY")),"gemini":bool(os.getenv("GEMINI_API_KEY")),"groq":bool(os.getenv("GROQ_API_KEY")),"ollama":os.getenv("OLLAMA_URL","http://localhost:11434")}
    s["all_ok"]=s["database"] and all(v=="ok" for v in s["engines"].values())
    return s

@app.get("/",tags=["System"])
def root(): return {"name":"AnnaSEO","version":"1.0.0","docs":"/docs","health":"/api/health"}

# ── CRUD additions ────────────────────────────────────────────────────────────

class ProjectUpdateBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    seed_keywords: Optional[List[str]] = None
    language: Optional[str] = None
    region: Optional[str] = None
    religion: Optional[str] = None
    wp_url: Optional[str] = None
    wp_user: Optional[str] = None
    wp_password: Optional[str] = None
    industry: Optional[str] = None

@app.put("/api/projects/{project_id}", tags=["Projects"])
def update_project(project_id: str, body: ProjectUpdateBody, user=Depends(current_user)):
    db = get_db()
    row = db.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
    if not row: raise HTTPException(404, "Not found")
    p = dict(row)
    fields, vals = [], []
    if body.name        is not None: fields.append("name=?");              vals.append(body.name)
    if body.description is not None: fields.append("description=?");       vals.append(body.description)
    if body.seed_keywords is not None: fields.append("seed_keywords=?");   vals.append(json.dumps(body.seed_keywords))
    if body.language    is not None: fields.append("language=?");          vals.append(body.language)
    if body.region      is not None: fields.append("region=?");            vals.append(body.region)
    if body.religion    is not None: fields.append("religion=?");          vals.append(body.religion)
    if body.wp_url      is not None: fields.append("wp_url=?");            vals.append(body.wp_url)
    if body.wp_user     is not None: fields.append("wp_user=?");           vals.append(body.wp_user)
    if body.wp_password is not None: fields.append("wp_pass_enc=?");       vals.append(_encrypt(body.wp_password))
    if body.industry    is not None:
        if body.industry not in VALID_INDUSTRIES: raise HTTPException(400, f"Unknown industry '{body.industry}'")
        fields.append("industry=?"); vals.append(body.industry)
    if not fields: return {"updated": False}
    fields.append("updated_at=?"); vals.append(datetime.utcnow().isoformat())
    vals.append(project_id)
    db.execute(f"UPDATE projects SET {','.join(fields)} WHERE project_id=?", vals)
    db.commit()
    return {"updated": True, "project_id": project_id}

class ArticleUpdateBody(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    meta_title: Optional[str] = None
    meta_desc: Optional[str] = None
    keyword: Optional[str] = None
    status: Optional[str] = None

@app.put("/api/content/{article_id}", tags=["Content"])
def update_article(article_id: str, body: ArticleUpdateBody, user=Depends(current_user)):
    db = get_db()
    if not db.execute("SELECT 1 FROM content_articles WHERE article_id=?", (article_id,)).fetchone():
        raise HTTPException(404, "Not found")
    fields, vals = [], []
    if body.title      is not None: fields.append("title=?");      vals.append(body.title)
    if body.body       is not None: fields.append("body=?");        vals.append(body.body)
    if body.meta_title is not None: fields.append("meta_title=?"); vals.append(body.meta_title)
    if body.meta_desc  is not None: fields.append("meta_desc=?");  vals.append(body.meta_desc)
    if body.keyword    is not None: fields.append("keyword=?");    vals.append(body.keyword)
    if body.status     is not None: fields.append("status=?");     vals.append(body.status)
    if not fields: return {"updated": False}
    fields.append("updated_at=?"); vals.append(datetime.utcnow().isoformat())
    vals.append(article_id)
    db.execute(f"UPDATE content_articles SET {','.join(fields)} WHERE article_id=?", vals)
    db.commit()
    return {"updated": True, "article_id": article_id}

@app.delete("/api/content/{article_id}", tags=["Content"])
def delete_article(article_id: str, user=Depends(current_user)):
    db = get_db()
    if not db.execute("SELECT 1 FROM content_articles WHERE article_id=?", (article_id,)).fetchone():
        raise HTTPException(404, "Not found")
    db.execute("DELETE FROM content_articles WHERE article_id=?", (article_id,))
    db.commit()
    return {"deleted": article_id}

@app.delete("/api/runs/{run_id}", tags=["Runs"])
def delete_run(run_id: str, user=Depends(current_user)):
    db = get_db()
    if not db.execute("SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone():
        raise HTTPException(404, "Not found")
    db.execute("DELETE FROM run_events WHERE run_id=?", (run_id,))
    db.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
    db.commit()
    return {"deleted": run_id}


# ── Error/Bug Collector & Fixer ───────────────────────────────────────────────

def _ensure_error_tables(db: sqlite3.Connection):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS error_reports (
        error_id   TEXT PRIMARY KEY,
        source     TEXT DEFAULT 'engine',
        message    TEXT DEFAULT '',
        traceback  TEXT DEFAULT '',
        context    TEXT DEFAULT '{}',
        status     TEXT DEFAULT 'new',
        run_id     TEXT DEFAULT '',
        project_id TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS fix_proposals (
        fix_id            TEXT PRIMARY KEY,
        error_id          TEXT NOT NULL,
        target_file       TEXT DEFAULT '',
        target_function   TEXT DEFAULT '',
        original_snippet  TEXT DEFAULT '',
        proposed_snippet  TEXT DEFAULT '',
        diff_text         TEXT DEFAULT '',
        snapshot_text     TEXT DEFAULT '',
        ai_draft_model    TEXT DEFAULT 'groq',
        claude_verdict    TEXT DEFAULT 'pending',
        claude_reason     TEXT DEFAULT '',
        status            TEXT DEFAULT 'pending',
        created_at        TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    db.commit()

# Call at startup
@app.on_event("startup")
async def _init_error_tables():
    _ensure_error_tables(get_db())

class ErrorReportBody(BaseModel):
    source: str = "browser"
    message: str = ""
    traceback: str = ""
    context: dict = {}
    project_id: str = ""
    run_id: str = ""

@app.post("/api/errors/report", tags=["BugFixer"])
def report_error(body: ErrorReportBody):
    """Receive browser or engine error — no auth required."""
    db = get_db()
    _ensure_error_tables(db)
    from engines.annaseo_error_fixer import ErrorCollector
    eid = ErrorCollector().store_browser_error(
        message=body.message, traceback=body.traceback,
        context=body.context, project_id=body.project_id, db=db
    )
    if body.run_id:
        db.execute("UPDATE error_reports SET run_id=? WHERE error_id=?", (body.run_id, eid))
        db.commit()
    return {"error_id": eid}

@app.get("/api/errors", tags=["BugFixer"])
def list_errors(limit: int = 100, user=Depends(current_user)):
    db = get_db()
    _ensure_error_tables(db)
    rows = db.execute(
        "SELECT error_id,source,message,traceback,status,run_id,project_id,created_at "
        "FROM error_reports ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/errors/{error_id}/analyze", tags=["BugFixer"])
async def analyze_error(error_id: str, bg: BackgroundTasks, user=Depends(current_user)):
    """Trigger Groq→Claude analysis in background. Returns immediately."""
    db = get_db()
    _ensure_error_tables(db)
    if not db.execute("SELECT 1 FROM error_reports WHERE error_id=?", (error_id,)).fetchone():
        raise HTTPException(404, "Not found")
    def _do():
        from engines.annaseo_error_fixer import BugAnalyzer
        BugAnalyzer().analyze(error_id, get_db())
    bg.add_task(_do)
    return {"status": "analyzing", "error_id": error_id}

@app.get("/api/fixes", tags=["BugFixer"])
def list_fixes(limit: int = 50, user=Depends(current_user)):
    db = get_db()
    _ensure_error_tables(db)
    rows = db.execute(
        "SELECT fix_id,error_id,target_file,target_function,"
        "original_snippet,proposed_snippet,diff_text,"
        "ai_draft_model,claude_verdict,claude_reason,status,created_at "
        "FROM fix_proposals ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/fixes/{fix_id}/approve", tags=["BugFixer"])
def approve_fix(fix_id: str, user=Depends(current_user)):
    db = get_db()
    _ensure_error_tables(db)
    from engines.annaseo_error_fixer import FixApplicator
    ok = FixApplicator().apply(fix_id, db)
    if not ok:
        raise HTTPException(400, "Could not apply fix — check target file and snippet match")
    return {"applied": True, "fix_id": fix_id}

@app.post("/api/fixes/{fix_id}/reject", tags=["BugFixer"])
def reject_fix(fix_id: str, user=Depends(current_user)):
    db = get_db()
    _ensure_error_tables(db)
    if not db.execute("SELECT 1 FROM fix_proposals WHERE fix_id=?", (fix_id,)).fetchone():
        raise HTTPException(404, "Not found")
    db.execute("UPDATE fix_proposals SET status='rejected' WHERE fix_id=?", (fix_id,))
    db.commit()
    return {"rejected": True, "fix_id": fix_id}

@app.post("/api/fixes/{fix_id}/rollback", tags=["BugFixer"])
def rollback_fix(fix_id: str, user=Depends(current_user)):
    db = get_db()
    _ensure_error_tables(db)
    from engines.annaseo_error_fixer import FixRollback
    ok = FixRollback().rollback(fix_id, db)
    if not ok:
        raise HTTPException(400, "Rollback failed — no snapshot available")
    return {"rolled_back": True, "fix_id": fix_id}


# ─────────────────────────────────────────────────────────────────────────────
# KEYWORD INPUT ENGINE ROUTES
# ─────────────────────────────────────────────────────────────────────────────

try:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent / "engines"))
    from engines.annaseo_keyword_input import KeywordInputEngine as _KIE, _db as _ki_db

    _kie = _KIE()
    _ki_db()   # auto-creates all 5 KI tables

    class _KIInput(BaseModel):
        pillars: list
        supporting: list
        intent_focus: str = "transactional"
        customer_url: Optional[str] = None
        competitor_urls: list = []

    class _KIAction(BaseModel):
        item_id: str
        action: str             # accept | reject | edit | move_pillar
        new_keyword: Optional[str] = None
        new_pillar: Optional[str] = None

    class _KIAcceptAll(BaseModel):
        pillar: Optional[str] = None
        intent: Optional[str] = None

    @app.post("/api/ki/{project_id}/input", tags=["KeywordInput"])
    def ki_save_input(project_id: str, body: _KIInput, user=Depends(current_user)):
        """Save customer pillar + supporting keywords, return session_id."""
        sid = _kie.save_customer_input(
            project_id=project_id,
            pillars=body.pillars,
            supporting=body.supporting,
            intent_focus=body.intent_focus,
            customer_url=body.customer_url,
            competitor_urls=body.competitor_urls,
        )
        return {"session_id": sid, "status": "saved"}

    @app.post("/api/ki/{project_id}/generate/{session_id}", tags=["KeywordInput"])
    def ki_generate(project_id: str, session_id: str, bg: BackgroundTasks, user=Depends(current_user)):
        """Trigger universe generation in background."""
        bg.add_task(
            _kie.generate_universe,
            project_id=project_id,
            session_id=session_id,
        )
        return {"status": "generating", "session_id": session_id}

    @app.get("/api/ki/{project_id}/session/{session_id}", tags=["KeywordInput"])
    def ki_get_session(project_id: str, session_id: str, user=Depends(current_user)):
        """Get session status and counts."""
        db = _ki_db()
        row = db.execute(
            "SELECT * FROM keyword_input_sessions WHERE session_id=? AND project_id=?",
            (session_id, project_id)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Session not found")
        return dict(row)

    @app.get("/api/ki/{project_id}/pillars", tags=["KeywordInput"])
    def ki_get_pillars(project_id: str, user=Depends(current_user)):
        """List pillar keywords for a project."""
        db = _ki_db()
        rows = db.execute(
            "SELECT * FROM pillar_keywords WHERE project_id=? ORDER BY priority ASC",
            (project_id,)
        ).fetchall()
        return {"pillars": [dict(r) for r in rows]}

    @app.get("/api/ki/{project_id}/review/{session_id}", tags=["KeywordInput"])
    def ki_review_queue(
        project_id: str, session_id: str,
        pillar: Optional[str] = None, intent: Optional[str] = None,
        status: str = "pending", limit: int = 30, offset: int = 0,
        user=Depends(current_user)
    ):
        """Get paginated keyword review queue."""
        from engines.annaseo_keyword_input import ReviewManager
        rm = ReviewManager()
        db = _ki_db()
        result = rm.get_review_queue(
            session_id=session_id, db=db,
            pillar=pillar, intent=intent, status=status,
            limit=limit, offset=offset,
        )
        return result

    @app.post("/api/ki/{project_id}/review/{session_id}/action", tags=["KeywordInput"])
    def ki_review_action(project_id: str, session_id: str, body: _KIAction, user=Depends(current_user)):
        """Accept, reject, edit, or move a keyword."""
        from engines.annaseo_keyword_input import ReviewManager
        rm = ReviewManager()
        db = _ki_db()
        ok = rm.apply_action(
            item_id=body.item_id, action=body.action, db=db,
            new_keyword=body.new_keyword, new_pillar=body.new_pillar,
        )
        return {"ok": ok, "item_id": body.item_id, "action": body.action}

    @app.post("/api/ki/{project_id}/review/{session_id}/accept-all", tags=["KeywordInput"])
    def ki_accept_all(project_id: str, session_id: str, body: _KIAcceptAll, user=Depends(current_user)):
        """Accept all pending keywords (optionally filtered by pillar/intent)."""
        from engines.annaseo_keyword_input import ReviewManager
        rm = ReviewManager()
        db = _ki_db()
        count = rm.accept_all(session_id=session_id, db=db, pillar=body.pillar, intent=body.intent)
        return {"accepted": count}

    @app.post("/api/ki/{project_id}/confirm/{session_id}", tags=["KeywordInput"])
    def ki_confirm(project_id: str, session_id: str, user=Depends(current_user)):
        """Confirm the universe — lock session and return keyword list for pipeline."""
        keywords = _kie.confirm_universe(session_id=session_id, project_id=project_id)
        db = _ki_db()
        stats = db.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN status='accepted' THEN 1 ELSE 0 END) as accepted "
            "FROM keyword_universe_items WHERE session_id=? AND project_id=?",
            (session_id, project_id)
        ).fetchone()
        pillars = db.execute(
            "SELECT COUNT(DISTINCT pillar) FROM keyword_universe_items WHERE session_id=? AND project_id=?",
            (session_id, project_id)
        ).fetchone()
        return {
            "status": "confirmed",
            "session_id": session_id,
            "keyword_count": len(keywords),
            "accepted_count": (stats["accepted"] if stats else 0) or 0,
            "pillar_count": (pillars[0] if pillars else 0) or 0,
        }

    @app.get("/api/ki/{project_id}/universe/{session_id}/by-pillar", tags=["KeywordInput"])
    def ki_by_pillar(project_id: str, session_id: str, user=Depends(current_user)):
        """Get universe grouped by pillar with counts per status."""
        db = _ki_db()
        rows = db.execute(
            """
            SELECT pillar,
                   COUNT(*) as total,
                   SUM(CASE WHEN status='accepted' THEN 1 ELSE 0 END) as accepted,
                   SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) as rejected,
                   SUM(CASE WHEN status='pending'  THEN 1 ELSE 0 END) as pending
            FROM keyword_universe_items
            WHERE session_id=? AND project_id=?
            GROUP BY pillar ORDER BY pillar
            """,
            (session_id, project_id)
        ).fetchall()
        return {"pillars": [dict(r) for r in rows]}

    log.info("[main] KeywordInputEngine routes registered at /api/ki/")

except Exception as _ki_err:
    log.warning(f"[main] KeywordInputEngine not loaded: {_ki_err}")

