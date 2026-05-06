import httpx

from blotter.config import OllamaConfig
from blotter.log import get_logger

log = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are a police scanner analyst. Given radio dispatch transcripts, "
    "write ONE sentence (max 30 words) summarizing what happened. "
    "Include: incident type, location, key details (suspect description, vehicle, etc). "
    "Do not include unit numbers, radio codes, or dispatch jargon. "
    "If the transcripts are unclear or routine, say so briefly."
)


class Summarizer:
    def __init__(self, config: OllamaConfig) -> None:
        self.config = config
        self._client = httpx.Client(timeout=config.timeout)

    def summarize(self, context: str, location: str = "") -> str | None:
        if not self.config.enabled or not context.strip():
            return None

        prompt = f"Location: {location}\n\nTranscripts:\n{context[:2000]}"

        try:
            resp = self._client.post(
                f"{self.config.host}/api/generate",
                json={
                    "model": self.config.model,
                    "prompt": prompt,
                    "system": SYSTEM_PROMPT,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 80,
                        "top_p": 0.9,
                    },
                },
            )
            resp.raise_for_status()
            result = resp.json().get("response", "").strip()
            if ". " in result:
                result = result[: result.index(". ") + 1]
            return result[:200] if result else None
        except Exception:
            log.warning("ollama summarization failed", exc_info=True)
            return None
