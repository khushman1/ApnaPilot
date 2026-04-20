"""ApplyPilot HTML dashboard for scored jobs and human-review routing."""

from __future__ import annotations

import webbrowser
from html import escape
from pathlib import Path

from rich.console import Console

from applypilot.config import APP_DIR
from applypilot.database import get_connection

console = Console()


def _bucket_for_score(score: int) -> tuple[str, str, str]:
    """Return bucket id, label, and color for a fit score."""
    if score >= 90:
        return ("human_review", "Human Review (90-100)", "#f97316")
    return ("auto_eligible", "Auto-Eligible (70-89)", "#10b981")


def generate_dashboard(output_path: str | None = None) -> str:
    """Generate an HTML dashboard of scored jobs."""
    out = Path(output_path) if output_path else APP_DIR / "dashboard.html"
    conn = get_connection()

    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    ready = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL AND application_url IS NOT NULL"
    ).fetchone()[0]
    scored = conn.execute("SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL").fetchone()[0]
    human_review = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE fit_score >= 90"
    ).fetchone()[0]
    auto_eligible = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE fit_score BETWEEN 70 AND 89"
    ).fetchone()[0]
    skipped = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL AND fit_score < 70"
    ).fetchone()[0]
    synced = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE COALESCE(human_review_required, 0) = 1 "
        "AND human_review_synced_at IS NOT NULL"
    ).fetchone()[0]

    site_stats = conn.execute(
        """
        SELECT site,
               COUNT(*) AS total,
               SUM(CASE WHEN fit_score >= 90 THEN 1 ELSE 0 END) AS human_review,
               SUM(CASE WHEN fit_score BETWEEN 70 AND 89 THEN 1 ELSE 0 END) AS auto_eligible,
               ROUND(AVG(fit_score), 1) AS avg_score
        FROM jobs
        GROUP BY site
        ORDER BY human_review DESC, auto_eligible DESC, total DESC
        """
    ).fetchall()

    jobs = conn.execute(
        """
        SELECT url, title, salary, location, site, full_description, application_url,
               fit_score, score_reasoning, human_review_required, human_review_synced_at,
               human_review_sync_error
        FROM jobs
        WHERE fit_score >= 70
        ORDER BY human_review_required DESC, fit_score DESC, site, title
        """
    ).fetchall()

    bucket_counts = [
        ("Human Review (90-100)", human_review, "#f97316"),
        ("Auto-Eligible (70-89)", auto_eligible, "#10b981"),
        ("Skip (<70)", skipped, "#64748b"),
    ]
    max_count = max((count for _, count, _ in bucket_counts), default=1) or 1
    score_bars = ""
    for label, count, color in bucket_counts:
        pct = count / max_count * 100 if max_count else 0
        score_bars += f"""
        <div class="score-row">
          <span class="score-label">{escape(label)}</span>
          <div class="score-bar-track">
            <div class="score-bar-fill" style="width:{pct:.1f}%;background:{color}"></div>
          </div>
          <span class="score-count">{count}</span>
        </div>"""

    colors = {
        "indeed": "#2164f3",
        "linkedin": "#0a66c2",
        "Glassdoor": "#0caa41",
        "Dice": "#eb1c26",
    }

    site_rows = ""
    for row in site_stats:
        site = row["site"] or "Unknown"
        color = colors.get(site, "#94a3b8")
        site_rows += f"""
        <div class="site-row">
          <div class="site-name" style="color:{color}">{escape(site)}</div>
          <div class="site-nums">{row['total']} jobs &middot; {row['human_review']} human review &middot; {row['auto_eligible']} auto-eligible &middot; avg {row['avg_score'] or 0}</div>
          <div class="bar-track">
            <div class="bar-fill" style="width:{row['human_review']/max(row['total'],1)*100:.1f}%;background:#f97316"></div>
            <div class="bar-fill" style="width:{row['auto_eligible']/max(row['total'],1)*100:.1f}%;background:#10b981"></div>
          </div>
        </div>"""

    section_markup: dict[str, list[str]] = {"human_review": [], "auto_eligible": []}
    section_meta = {
        "human_review": {"label": "Human Review (90-100)", "color": "#f97316"},
        "auto_eligible": {"label": "Auto-Eligible (70-89)", "color": "#10b981"},
    }

    for job in jobs:
        score = job["fit_score"] or 0
        bucket_id, _, bucket_color = _bucket_for_score(score)
        title = escape(job["title"] or "Untitled")
        job_url = escape(job["url"] or "")
        apply_url = escape(job["application_url"] or "")
        salary = escape(job["salary"] or "")
        location = escape(job["location"] or "")
        site = escape(job["site"] or "")
        reasoning_raw = job["score_reasoning"] or ""
        reasoning_lines = reasoning_raw.split("\n")
        keywords = reasoning_lines[0][:140] if reasoning_lines else ""
        reasoning = reasoning_lines[1][:220] if len(reasoning_lines) > 1 else ""
        desc_preview = escape(job["full_description"] or "")[:320]
        sync_tag = ""
        if bucket_id == "human_review":
            if job["human_review_synced_at"]:
                sync_tag = '<span class="meta-tag sync-ok">Sheet synced</span>'
            elif job["human_review_sync_error"]:
                sync_tag = '<span class="meta-tag sync-error">Sheet sync error</span>'

        meta_parts = [
            f'<span class="meta-tag site-tag">{site}</span>',
            f'<span class="meta-tag location">{location[:40]}</span>' if location else "",
            f'<span class="meta-tag salary">{salary}</span>' if salary else "",
            sync_tag,
        ]

        apply_link = f'<a href="{apply_url}" class="apply-link" target="_blank">Apply</a>' if apply_url else ""
        card = f"""
        <div class="job-card" data-score="{score}" data-bucket="{bucket_id}">
          <div class="card-header">
            <span class="score-pill" style="background:{bucket_color}">{score}</span>
            <a href="{job_url}" class="job-title" target="_blank">{title}</a>
          </div>
          <div class="meta-row">{''.join(meta_parts)}</div>
          {f'<div class="keywords-row">{escape(keywords)}</div>' if keywords else ''}
          {f'<div class="reasoning-row">{escape(reasoning)}</div>' if reasoning else ''}
          <p class="desc-preview">{desc_preview}...</p>
          <div class="card-footer">{apply_link}</div>
        </div>"""
        section_markup[bucket_id].append(card)

    job_sections = ""
    for bucket_id in ("human_review", "auto_eligible"):
        cards = section_markup[bucket_id]
        if not cards:
            continue
        meta = section_meta[bucket_id]
        job_sections += f"""
        <section class="bucket-section" data-section="{bucket_id}">
          <h2 class="score-header" style="border-color:{meta['color']}">
            <span class="score-badge" style="background:{meta['color']}">{len(cards)}</span>
            {meta['label']}
          </h2>
          <div class="job-grid">
            {''.join(cards)}
          </div>
        </section>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ApplyPilot Dashboard</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; }}
  h1 {{ margin: 0 0 0.5rem; font-size: 1.9rem; }}
  .subtitle {{ color: #94a3b8; margin-bottom: 2rem; }}
  .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
  .stat-card, .filters, .score-dist, .sites-section, .job-card {{ background: #1e293b; border-radius: 12px; }}
  .stat-card {{ padding: 1.1rem; }}
  .stat-num {{ font-size: 1.9rem; font-weight: 700; }}
  .stat-label {{ color: #94a3b8; font-size: 0.85rem; margin-top: 0.25rem; }}
  .filters {{ padding: 1rem 1.25rem; margin-bottom: 2rem; display: flex; gap: 0.8rem; flex-wrap: wrap; align-items: center; }}
  .filter-label {{ color: #94a3b8; font-size: 0.85rem; font-weight: 600; }}
  .filter-btn {{ background: #334155; border: none; color: #cbd5e1; padding: 0.45rem 0.8rem; border-radius: 999px; cursor: pointer; }}
  .filter-btn.active {{ background: #60a5fa; color: #0f172a; font-weight: 700; }}
  .search-input {{ background: #334155; border: 1px solid #475569; color: #e2e8f0; padding: 0.45rem 0.8rem; border-radius: 8px; min-width: 240px; }}
  .score-section {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 2rem; }}
  .score-dist, .sites-section {{ padding: 1.25rem; }}
  .score-row {{ display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.55rem; }}
  .score-label {{ width: 160px; font-size: 0.82rem; color: #cbd5e1; }}
  .score-bar-track {{ flex: 1; height: 12px; background: #334155; border-radius: 999px; overflow: hidden; }}
  .score-bar-fill {{ height: 100%; border-radius: 999px; }}
  .score-count {{ width: 2.5rem; color: #94a3b8; font-size: 0.8rem; text-align: right; }}
  .site-row {{ margin-bottom: 0.85rem; }}
  .site-name {{ font-weight: 700; }}
  .site-nums {{ color: #94a3b8; font-size: 0.8rem; margin: 0.2rem 0; }}
  .bar-track {{ height: 8px; display: flex; background: #334155; border-radius: 999px; overflow: hidden; }}
  .bar-fill {{ height: 100%; }}
  .job-count {{ color: #94a3b8; font-size: 0.9rem; margin-bottom: 1rem; }}
  .score-header {{ display: flex; align-items: center; gap: 0.8rem; font-size: 1.15rem; margin: 2rem 0 1rem; padding-bottom: 0.6rem; border-bottom: 3px solid; }}
  .score-badge, .score-pill {{ display: inline-flex; align-items: center; justify-content: center; color: #0f172a; font-weight: 800; }}
  .score-badge {{ min-width: 2rem; height: 2rem; border-radius: 10px; }}
  .job-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 1rem; }}
  .job-card {{ padding: 1rem; border-left: 4px solid #334155; }}
  .job-card[data-bucket="human_review"] {{ border-left-color: #f97316; }}
  .job-card[data-bucket="auto_eligible"] {{ border-left-color: #10b981; }}
  .card-header {{ display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.55rem; }}
  .score-pill {{ min-width: 2.1rem; height: 2.1rem; border-radius: 8px; font-size: 0.9rem; }}
  .job-title {{ color: #e2e8f0; text-decoration: none; font-weight: 700; }}
  .job-title:hover {{ color: #93c5fd; }}
  .meta-row {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.45rem; }}
  .meta-tag {{ font-size: 0.72rem; padding: 0.18rem 0.5rem; border-radius: 999px; background: #334155; color: #cbd5e1; }}
  .meta-tag.salary {{ background: #14532d; color: #bbf7d0; }}
  .meta-tag.location {{ background: #1e3a5f; color: #bfdbfe; }}
  .meta-tag.sync-ok {{ background: #0f766e; color: #ccfbf1; }}
  .meta-tag.sync-error {{ background: #7f1d1d; color: #fecaca; }}
  .keywords-row {{ font-size: 0.76rem; color: #86efac; margin-bottom: 0.25rem; }}
  .reasoning-row {{ font-size: 0.76rem; color: #94a3b8; margin-bottom: 0.55rem; font-style: italic; line-height: 1.4; }}
  .desc-preview {{ font-size: 0.82rem; color: #cbd5e1; line-height: 1.5; margin: 0 0 0.85rem; max-height: 4.8em; overflow: hidden; }}
  .card-footer {{ display: flex; justify-content: flex-end; }}
  .apply-link {{ color: #60a5fa; text-decoration: none; border: 1px solid #60a5fa33; padding: 0.35rem 0.8rem; border-radius: 8px; font-size: 0.8rem; }}
  .apply-link:hover {{ background: #60a5fa22; }}
  .hidden {{ display: none !important; }}
  @media (max-width: 900px) {{ .score-section {{ grid-template-columns: 1fr; }} body {{ padding: 1rem; }} }}
</style>
</head>
<body>
<h1>ApplyPilot Dashboard</h1>
<p class="subtitle">{total} jobs &middot; {scored} scored &middot; {human_review} human review &middot; {auto_eligible} auto-eligible &middot; {synced} synced to Sheets</p>

<div class="summary">
  <div class="stat-card"><div class="stat-num">{total}</div><div class="stat-label">Total jobs</div></div>
  <div class="stat-card"><div class="stat-num">{ready}</div><div class="stat-label">Ready (desc + apply URL)</div></div>
  <div class="stat-card"><div class="stat-num">{human_review}</div><div class="stat-label">Human review (90+)</div></div>
  <div class="stat-card"><div class="stat-num">{auto_eligible}</div><div class="stat-label">Auto-eligible (70-89)</div></div>
  <div class="stat-card"><div class="stat-num">{skipped}</div><div class="stat-label">Skip (&lt;70)</div></div>
</div>

<div class="filters">
  <span class="filter-label">View</span>
  <button class="filter-btn active" onclick="setBucket('all', event)">All 70+</button>
  <button class="filter-btn" onclick="setBucket('human_review', event)">Human review</button>
  <button class="filter-btn" onclick="setBucket('auto_eligible', event)">Auto-eligible</button>
  <button class="filter-btn" onclick="setMinScore(85, event)">85+</button>
  <button class="filter-btn" onclick="setMinScore(95, event)">95+</button>
  <span class="filter-label" style="margin-left:1rem">Search</span>
  <input type="text" class="search-input" placeholder="Filter by title, site, reasoning..." oninput="setSearch(this.value)">
</div>

<div class="score-section">
  <div class="score-dist">
    <h3>Routing Buckets</h3>
    {score_bars}
  </div>
  <div class="sites-section">
    <h3>By Source</h3>
    {site_rows}
  </div>
</div>

<div id="job-count" class="job-count"></div>
{job_sections}

<script>
let bucketFilter = 'all';
let minScore = 70;
let searchText = '';

function activateButton(target) {{
  document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
  target.classList.add('active');
}}

function setBucket(bucket, event) {{
  bucketFilter = bucket;
  minScore = 70;
  activateButton(event.target);
  applyFilters();
}}

function setMinScore(score, event) {{
  bucketFilter = 'all';
  minScore = score;
  activateButton(event.target);
  applyFilters();
}}

function setSearch(text) {{
  searchText = text.toLowerCase();
  applyFilters();
}}

function applyFilters() {{
  let shown = 0;
  let total = 0;
  document.querySelectorAll('.job-card').forEach(card => {{
    total++;
    const score = parseInt(card.dataset.score) || 0;
    const bucket = card.dataset.bucket;
    const text = card.textContent.toLowerCase();
    const bucketMatch = bucketFilter === 'all' || bucket === bucketFilter;
    const scoreMatch = score >= minScore;
    const textMatch = !searchText || text.includes(searchText);
    const visible = bucketMatch && scoreMatch && textMatch;
    card.classList.toggle('hidden', !visible);
    if (visible) shown++;
  }});

  document.getElementById('job-count').textContent = `Showing ${{shown}} of ${{total}} routed jobs`;

  document.querySelectorAll('.bucket-section').forEach(section => {{
    const visible = section.querySelectorAll('.job-card:not(.hidden)').length;
    section.classList.toggle('hidden', visible === 0);
  }});
}}

applyFilters();
</script>
</body>
</html>"""

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    abs_path = str(out.resolve())
    console.print(f"[green]Dashboard written to {abs_path}[/green]")
    return abs_path


def open_dashboard(output_path: str | None = None) -> None:
    """Generate the dashboard and open it in the default browser."""
    path = generate_dashboard(output_path)
    console.print("[dim]Opening in browser...[/dim]")
    webbrowser.open(f"file:///{path}")
