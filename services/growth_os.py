from __future__ import annotations

import json
import os
import re
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Dict, List, Optional

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from engines.serp import SERPEngine


@dataclass
class ClusterResult:
    cluster_id: int
    cluster_name: str
    pillar: str
    supporting: List[str]
    keywords: List[str]


def _keyword_embeddings_tfidf(keywords: List[str]) -> tuple[np.ndarray, TfidfVectorizer]:
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
    mat = vec.fit_transform(keywords)
    return mat.toarray(), vec


def _cluster_name_from_centroid(
    centroid: np.ndarray,
    vectorizer: TfidfVectorizer,
    fallback: str,
    top_n: int = 2,
) -> str:
    feats = np.array(vectorizer.get_feature_names_out())
    if len(feats) == 0:
        return fallback.title()
    idx = np.argsort(centroid)[::-1][:top_n]
    tokens = [t for t in feats[idx] if t and len(t) > 2]
    if not tokens:
        return fallback.title()
    return " ".join(tokens[:top_n]).title()


def _pillar_from_name(cluster_name: str) -> str:
    return f"Complete Guide to {cluster_name}"


def _supporting_topics(cluster_name: str, keywords: List[str], max_items: int = 5) -> List[str]:
    base = cluster_name.lower()
    items: List[str] = []
    for kw in keywords:
        t = kw.strip().rstrip("?.!")
        if t and t.lower() not in {x.lower() for x in items}:
            items.append(t)
        if len(items) >= max_items:
            break

    templates = [
        f"How {base} is made",
        f"Best {base} options",
        f"{cluster_name} buying checklist",
        f"Common mistakes when choosing {base}",
        f"{cluster_name} FAQs",
    ]
    for t in templates:
        if len(items) >= max_items:
            break
        if t.lower() not in {x.lower() for x in items}:
            items.append(t)
    return items[:max_items]


def semantic_cluster_keywords(
    keywords: List[str],
    n_clusters: Optional[int] = None,
    random_state: int = 42,
) -> List[ClusterResult]:
    clean = [k.strip() for k in keywords if isinstance(k, str) and k.strip()]
    if not clean:
        return []

    if len(clean) == 1:
        name = clean[0].title()
        return [
            ClusterResult(
                cluster_id=0,
                cluster_name=name,
                pillar=_pillar_from_name(name),
                supporting=_supporting_topics(name, clean),
                keywords=clean,
            )
        ]

    arr, vectorizer = _keyword_embeddings_tfidf(clean)
    k = n_clusters or max(2, min(8, int(np.sqrt(len(clean))) + 1))
    k = min(k, len(clean))
    model = KMeans(n_clusters=k, random_state=random_state, n_init="auto")
    labels = model.fit_predict(arr)

    grouped: Dict[int, List[str]] = {}
    for kw, lbl in zip(clean, labels):
        grouped.setdefault(int(lbl), []).append(kw)

    out: List[ClusterResult] = []
    for cid, kws in sorted(grouped.items(), key=lambda kv: kv[0]):
        centroid = model.cluster_centers_[cid]
        fallback = kws[0] if kws else "Topic"
        cname = _cluster_name_from_centroid(centroid, vectorizer, fallback)
        out.append(
            ClusterResult(
                cluster_id=cid,
                cluster_name=cname,
                pillar=_pillar_from_name(cname),
                supporting=_supporting_topics(cname, kws),
                keywords=kws,
            )
        )
    return out


def persist_keyword_embeddings(db, project_id: str, keywords: List[str], labels: List[int]) -> None:
    arr, _ = _keyword_embeddings_tfidf(keywords)
    for kw, emb, lbl in zip(keywords, arr, labels):
        db.execute(
            """
            INSERT INTO keyword_embeddings (project_id, keyword, embedding_json, cluster_id)
            VALUES (?, ?, ?, ?)
            """,
            (project_id, kw, json.dumps(emb.tolist()), int(lbl)),
        )


def find_prospects(query: str, limit: int = 20) -> List[str]:
    if not query.strip():
        return []
    serp = SERPEngine()
    data = serp.get_serp(query)
    organic = data.get("organic_results") or []
    urls: List[str] = []
    for r in organic:
        u = (r or {}).get("link")
        if u and u not in urls:
            urls.append(u)
        if len(urls) >= limit:
            break
    return urls


def extract_email(text: str) -> Optional[str]:
    matches = re.findall(r"[\\w.-]+@[\\w.-]+", text or "")
    return matches[0] if matches else None


def generate_outreach_email(target_site: str, our_content: str, context: str = "") -> Dict[str, str]:
    site_label = target_site.replace("https://", "").replace("http://", "").split("/")[0]
    subject = f"Quick collaboration idea for {site_label}"
    body = (
        f"Hi there,\n\n"
        f"I came across {site_label} while researching this topic and really liked your coverage.\n"
        f"We recently published a resource that complements your audience: {our_content}.\n"
        f"\n"
        f"If you think it adds value, would you consider referencing it in your related article(s)?\n"
        f"Happy to share additional data points or a custom summary for your readers.\n"
        f"\n"
        f"Thanks for your time.\n"
    )
    if context:
        body += f"\nContext we noticed: {context[:240]}\n"
    return {"subject": subject, "body": body}


def send_email_smtp(to_email: str, subject: str, body: str) -> Dict[str, Any]:
    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASS", "")
    sender = os.getenv("SMTP_FROM", user or "noreply@example.com")

    if not host or not user or not password:
        return {
            "sent": False,
            "reason": "SMTP config missing (SMTP_HOST/SMTP_USER/SMTP_PASS)",
        }

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)

    return {"sent": True, "to": to_email}


_LANGUAGE_NAME_MAP = {
    "en": "English",
    "ml": "Malayalam",
    "hi": "Hindi",
    "ta": "Tamil",
}


def _slugify(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\\s-]", "", value or "").strip().lower()
    s = re.sub(r"[\\s_-]+", "-", s)
    return s or "content"


def localize_content_fallback(content: str, language: str) -> str:
    lang_name = _LANGUAGE_NAME_MAP.get(language, language)
    return (
        f"[{lang_name} localized draft]\n\n"
        f"{content}\n\n"
        f"[Note: Configure a translation-capable LLM key to replace fallback localization.]"
    )


def generate_multilingual_map(content: str, languages: List[str], slug_seed: str) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    slug = _slugify(slug_seed)
    for lang in languages:
        code = (lang or "").strip().lower()
        if not code:
            continue
        localized = content if code == "en" else localize_content_fallback(content, code)
        out[code] = {
            "language": _LANGUAGE_NAME_MAP.get(code, code),
            "url": f"/{code}/{slug}",
            "content": localized,
        }

    # hreflang map references all generated alternates
    for code in list(out.keys()):
        out[code]["hreflang"] = json.dumps(
            [{"lang": k, "href": v["url"]} for k, v in out.items()],
            ensure_ascii=False,
        )
    return out
