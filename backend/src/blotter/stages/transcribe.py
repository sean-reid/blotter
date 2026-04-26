from pathlib import Path

from blotter.config import TranscriptionConfig
from blotter.log import get_logger
from blotter.models import TranscriptSegment

log = get_logger(__name__)

POLICE_PROMPT = (
    "Police radio dispatch. 10-4, copy, code 3, code 2, suspect vehicle, "
    "responding unit, en route, on scene, clear, dispatch, copy that, "
    "10-97, 10-98, 10-99, welfare check, traffic stop, DUI, 211, 459, 487, "
    "San Jose, Santa Clara, Sunnyvale, Mountain View, Palo Alto, Cupertino, "
    "El Camino Real, Stevens Creek, Lawrence Expressway, Highway 101, Interstate 280."
)


class Transcriber:
    def __init__(self, config: TranscriptionConfig) -> None:
        self.config = config
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            log.info(
                "loading model",
                model=self.config.model_size,
                device=self.config.device,
                compute_type=self.config.compute_type,
            )
            self._model = WhisperModel(
                self.config.model_size,
                device=self.config.device,
                compute_type=self.config.compute_type,
            )
        return self._model

    def transcribe(self, audio_path: Path) -> tuple[list[TranscriptSegment], str]:
        log.info("transcribing", path=str(audio_path))

        vad_params = {
            "min_silence_duration_ms": self.config.vad_min_silence_ms,
            "speech_pad_ms": self.config.vad_speech_pad_ms,
        }

        segments_iter, info = self.model.transcribe(
            str(audio_path),
            beam_size=self.config.beam_size,
            language=self.config.language,
            vad_filter=self.config.vad_filter,
            vad_parameters=vad_params,
            initial_prompt=POLICE_PROMPT,
        )

        segments = []
        texts = []
        for seg in segments_iter:
            segments.append(TranscriptSegment(
                start=seg.start,
                end=seg.end,
                text=seg.text.strip(),
            ))
            texts.append(seg.text.strip())

        full_text = " ".join(texts)
        log.info(
            "transcription complete",
            path=str(audio_path),
            segments=len(segments),
            duration=info.duration,
            language=info.language,
            language_prob=round(info.language_probability, 3),
            chars=len(full_text),
        )
        return segments, full_text
