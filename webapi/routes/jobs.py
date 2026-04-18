"""
Jobs API — exposes cron/jobs.py via FastAPI at /api/jobs.
"""
from fastapi import APIRouter, HTTPException, Query

from cron.jobs import (
    create_job,
    get_job,
    list_jobs,
    pause_job,
    remove_job,
    resume_job,
    trigger_job,
    update_job,
)


router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# ── helpers ─────────────────────────────────────────────────────────────────

def _job_not_found(job_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Job '{job_id}' not found")


def _output_files(job_id: str) -> list[dict]:
    """Return recent job output files."""
    from cron.jobs import OUTPUT_DIR

    job_dir = OUTPUT_DIR / job_id
    if not job_dir.is_dir():
        return []

    outputs = []
    for f in sorted(job_dir.glob("*.md"), reverse=True):
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            content = ""
        outputs.append({
            "filename": f.name,
            "timestamp": f.stem,
            "content": content,
            "size": len(content),
        })
    return outputs


# ── routes ───────────────────────────────────────────────────────────────────

@router.get("")
async def list_all_jobs(
    include_disabled: bool = Query(False),
) -> dict:
    """GET /api/jobs?include_disabled=true"""
    jobs = list_jobs(include_disabled=include_disabled)
    return {"jobs": jobs, "ok": True}


@router.post("")
async def create(
    schedule: str = Query(...),
    prompt: str = Query(...),
    name: str | None = Query(None),
    deliver: str | None = Query(None),
    skills: str | None = Query(None),  # comma-separated
    repeat: int | None = Query(None),
) -> dict:
    """POST /api/jobs"""
    skill_list = [s.strip() for s in skills.split(",")] if skills else None

    try:
        job = create_job(
            prompt=prompt,
            schedule=schedule,
            name=name or None,
            deliver=deliver or None,
            skills=skill_list,
            repeat=repeat,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {"job": job, "ok": True}


@router.get("/{job_id}")
async def get_one(job_id: str) -> dict:
    """GET /api/jobs/{job_id}"""
    job = get_job(job_id)
    if not job:
        raise _job_not_found(job_id)
    return {"job": job, "ok": True}


@router.patch("/{job_id}")
async def patch_one(job_id: str, updates: dict) -> dict:
    """PATCH /api/jobs/{job_id}"""
    job = update_job(job_id, dict(updates))
    if not job:
        raise _job_not_found(job_id)
    return {"job": job, "ok": True}


@router.delete("/{job_id}")
async def delete_one(job_id: str) -> dict:
    """DELETE /api/jobs/{job_id}"""
    if not remove_job(job_id):
        raise _job_not_found(job_id)
    return {"ok": True}


# ── action sub-resources ──────────────────────────────────────────────────────

@router.post("/{job_id}/run")
async def run_job(job_id: str) -> dict:
    """POST /api/jobs/{job_id}/run"""
    job = trigger_job(job_id)
    if not job:
        raise _job_not_found(job_id)
    return {"job": job, "ok": True}


@router.post("/{job_id}/pause")
async def pause_job_endpoint(job_id: str) -> dict:
    """POST /api/jobs/{job_id}/pause"""
    job = pause_job(job_id)
    if not job:
        raise _job_not_found(job_id)
    return {"job": job, "ok": True}


@router.post("/{job_id}/resume")
async def resume_job_endpoint(job_id: str) -> dict:
    """POST /api/jobs/{job_id}/resume"""
    job = resume_job(job_id)
    if not job:
        raise _job_not_found(job_id)
    return {"job": job, "ok": True}


@router.get("/{job_id}/output")
async def get_output(
    job_id: str,
    limit: int = Query(10, ge=1, le=100),
) -> dict:
    """GET /api/jobs/{job_id}/output"""
    job = get_job(job_id)
    if not job:
        raise _job_not_found(job_id)
    outputs = _output_files(job_id)[:limit]
    return {"outputs": outputs, "ok": True}
