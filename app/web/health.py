"""GET /health (R76): 200 {"ok": true} when both databases open, 503 otherwise. Fly.io's health check restarts the
machine when it stops answering, and the outside uptime monitor alerts the author."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.accounts.lookups import read_only


def health_routes(store, scheduling_db: Path) -> APIRouter:
    router = APIRouter()

    @router.api_route("/health", methods=["GET", "HEAD"])  # HEAD for uptime monitors
    def health():
        try:
            if not Path(scheduling_db).exists():  # a read-only open would fail too, but say why
                raise FileNotFoundError(f"{scheduling_db} is missing")
            db = read_only(scheduling_db)
            try:
                db.execute("select 1 from appointment_slots limit 1").fetchall()
            finally:
                db.close()
            store.read("select 1")
        except Exception as error:
            return JSONResponse({"ok": False, "error": type(error).__name__}, status_code=503)
        return {"ok": True}

    return router
