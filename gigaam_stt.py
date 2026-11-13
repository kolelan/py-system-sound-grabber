"""
GigaAM-v3 ONNX на CPU: распознавание русской речи.

Ожидает файлы модели:
  models/gigaam-v3/
    gigaam_v3_rnnt_encoder.onnx
    gigaam_v3_rnnt_decoder.onnx
    gigaam_v3_rnnt_joint.onnx
    gigaam_v3_rnnt_tokens.txt

Скачать: python stt_download_model.py gigaam-v3
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import List, Optional

import numpy as np
import onnxruntime as ort

from stt_base import SAMPLE_RATE, ProgressFn, SttError, load_audio_16k_mono, maybe_punctuate

warnings.filterwarnings("ignore")

DEFAULT_MODEL_DIR = Path("models") / "gigaam-v3"
# модель рассчитана на короткие куски; длинные режем
CHUNK_SECONDS = 20.0


class GigaAMError(SttError):
    """Ошибка загрузки модели или распознавания GigaAM."""


class GigaAMRecognizer:
    """RNNT ONNX Int8, CPUExecutionProvider."""

    model_id = "gigaam-v3"

    def __init__(
        self,
        model_dir: str | Path = DEFAULT_MODEL_DIR,
        providers: Optional[List[str]] = None,
        max_symbols_per_step: int = 10,
    ):
        model_dir = Path(model_dir)
        if providers is None:
            providers = ["CPUExecutionProvider"]

        self.model_dir = model_dir
        self.max_symbols = max_symbols_per_step
        self._mel_cache = None

        encoder_path = model_dir / "gigaam_v3_rnnt_encoder.onnx"
        if not encoder_path.is_file():
            raise GigaAMError(
                f"Модель не найдена: {encoder_path}\n"
                "Скачайте: python stt_download_model.py gigaam-v3"
            )

        tokens_path = model_dir / "gigaam_v3_rnnt_tokens.txt"
        self.tokens = self._load_tokens(tokens_path)
        # Пробел (id=0) — обычный символ словаря, blank — только <blk>/<blank>.
        self.blank_id = next(
            (i for i, t in enumerate(self.tokens) if t in ("<blk>", "<blank>")),
            len(self.tokens) - 1,
        )

        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        so.enable_cpu_mem_arena = False

        self.encoder = ort.InferenceSession(
            str(encoder_path), so, providers=providers
        )
        self.decoder = ort.InferenceSession(
            str(model_dir / "gigaam_v3_rnnt_decoder.onnx"), so, providers=providers
        )
        self.joint = ort.InferenceSession(
            str(model_dir / "gigaam_v3_rnnt_joint.onnx"), so, providers=providers
        )

    def summary(self) -> str:
        return (
            f"GigaAM-v3 ONNX (CPU)\n"
            f"  dir: {self.model_dir.resolve()}\n"
            f"  provider: {self.encoder.get_providers()[0]}\n"
            f"  tokens: {len(self.tokens)}, blank_id={self.blank_id}"
        )

    def transcribe(
        self,
        audio_path: str | Path,
        punctuate: bool = True,
        on_progress: Optional[ProgressFn] = None,
    ) -> str:
        audio = load_audio_16k_mono(audio_path)
        return self.transcribe_raw(audio, punctuate=punctuate, on_progress=on_progress)

    def transcribe_raw(
        self,
        audio: np.ndarray,
        punctuate: bool = True,
        on_progress: Optional[ProgressFn] = None,
    ) -> str:
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        if audio.size == 0:
            return ""

        chunk = int(CHUNK_SECONDS * SAMPLE_RATE)
        parts: list[str] = []
        total = max(1, (audio.size + chunk - 1) // chunk)

        for i in range(0, audio.size, chunk):
            piece = audio[i : i + chunk]
            if piece.size < SAMPLE_RATE // 4:  # <0.25s — пропуск
                continue
            mel = self._compute_mel(piece)
            enc_out, _ = self.encoder.run(
                None,
                {
                    "audio_signal": mel,
                    "length": np.array([mel.shape[2]], dtype=np.int64),
                },
            )
            parts.append(self._greedy_decode(enc_out))
            if on_progress is not None:
                on_progress(min(1.0, (i // chunk + 1) / total))

        text = " ".join(p for p in parts if p).strip()
        text = re.sub(r"\s+", " ", text)
        return maybe_punctuate(text, punctuate)

    def _compute_mel(self, audio: np.ndarray) -> np.ndarray:
        import torch
        import torchaudio.transforms as T

        if self._mel_cache is None:
            self._mel_cache = T.MelSpectrogram(
                sample_rate=SAMPLE_RATE,
                n_mels=64,
                win_length=320,
                hop_length=160,
                n_fft=320,
                center=False,
            )
        audio_t = torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)
        return torch.log(self._mel_cache(audio_t).clamp(1e-9)).numpy()

    def _greedy_decode(self, enc_out: np.ndarray) -> str:
        _b, _d, t_len = enc_out.shape
        enc_out_t = enc_out.transpose(0, 2, 1)
        hyp: list[int] = []
        dec_state = None
        last_label = np.array([[self.blank_id]], dtype=np.int32)

        for t in range(t_len):
            f = enc_out_t[:, t : t + 1, :].transpose(0, 2, 1)
            not_blank = True
            sym = 0
            while not_blank and sym < self.max_symbols:
                if dec_state is None:
                    h = np.zeros((1, 1, 320), dtype=np.float32)
                    c = np.zeros((1, 1, 320), dtype=np.float32)
                else:
                    h, c = dec_state

                g, _, h_new, c_new = self.decoder.run(
                    None,
                    {
                        "x": last_label,
                        "unused_x_len.1": np.array([1], dtype=np.int32),
                        "h.1": h,
                        "c.1": c,
                    },
                )
                logits = self.joint.run(None, {"enc": f, "dec": g})[0]
                k = int(logits[0, 0, 0, :].argmax())

                if k == self.blank_id:
                    not_blank = False
                else:
                    hyp.append(k)
                    dec_state = (h_new, c_new)
                    last_label = np.array([[hyp[-1]]], dtype=np.int32)
                    sym += 1

        return "".join(self.tokens[tid] for tid in hyp)

    @staticmethod
    def _load_tokens(path: Path) -> List[str]:
        if not path.is_file():
            raise GigaAMError(f"Нет файла токенов: {path}")
        tokens: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^(.*?)\s+(\d+)$", line)
            if m:
                token = m.group(1)
                if token == "":
                    token = " "
                tokens.append(token)
            elif line.strip():
                tokens.append(line.strip())
        return tokens
