"""A terminal chat with the agent, on a fresh copy of the seeded scheduling database and a scratch operations
database, so nothing real is changed.

Run: python -m app.cli   (needs ANTHROPIC_API_KEY and VOYAGE_API_KEY in .env)"""

import shutil
import tempfile
import uuid
from pathlib import Path


def build_engine(folder: Path):
    import anthropic

    from app.config import SETTINGS
    from app.core.engine import Engine
    from app.core.pipeline import AgentPipeline
    from app.knowledge.embedder import VoyageEmbedder
    from app.knowledge.index import load_index
    from app.knowledge.search import Searcher
    from app.ops.store import OpsStore
    from app.replies.writer import write
    from app.routing.router import route

    scheduling = folder / "scheduling.sqlite"
    shutil.copy(SETTINGS.seed_db_path, scheduling)
    chunks, embeddings = load_index(Path(__file__).resolve().parents[1] / "data" / "index")
    from app.core.model_log import RecordingClient

    client = RecordingClient(anthropic.Anthropic(timeout=SETTINGS.anthropic_timeout_s, max_retries=1),
                             sdk_version=f"anthropic {anthropic.__version__}")
    pipeline = AgentPipeline(store=OpsStore(folder / "ops.sqlite"), scheduling_db=scheduling, seed_db=SETTINGS.seed_db_path,
                             searcher=Searcher(chunks, VoyageEmbedder(input_type="query"), embeddings),
                             route_fn=lambda text, history: route(text, history, client),
                             writer=lambda reply_type, facts, history: write(reply_type, facts, history, client),
                             threshold=SETTINGS.retrieval_threshold)
    return Engine(pipeline)


def main() -> None:
    from dotenv import load_dotenv

    from app.core.types import DoneEvent, SentenceEvent, Turn

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    folder = Path(tempfile.mkdtemp(prefix="meridian-cli-"))
    engine = build_engine(folder)
    conversation = uuid.uuid4().hex
    print("Meridian Home Comfort assistant (the fixed date is Friday 16 October 2026). Ctrl-D to quit.")
    while True:
        try:
            text = input("\nyou> ").strip()
        except EOFError:
            break
        if not text:
            continue
        for event in engine.handle(Turn(conversation, "cli", uuid.uuid4().hex, text)):
            if isinstance(event, SentenceEvent):
                print(f"agent> {event.text}")
            elif isinstance(event, DoneEvent):
                print(f"       [{event.route} | {event.outcome}" + (f" | ticket #{event.ticket}" if event.ticket else "")
                      + (f" | {', '.join(event.db_actions)}" if event.db_actions else "") + "]")


if __name__ == "__main__":
    main()
