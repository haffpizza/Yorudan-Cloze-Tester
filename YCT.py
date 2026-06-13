#!/usr/bin/env python3
"""
Yorudan Cloze Tester — single-file cloze deletion testing app.
Requires: PySide6, regex, python-mpv, libmpv-2.dll (placed next to the exe)
Optional:  spacy + en_core_web_sm  (English proper-noun detection)
           fugashi + unidic-lite   (Japanese MeCab tokenisation)
"""

from __future__ import annotations

import html
import json
import os
import random
import re
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

def _find_libmpv() -> None:
    """Register libmpv-2.dll location before python-mpv imports it."""
    if sys.platform != "win32":
        return
    # Check PyInstaller's bundle dir first (_MEIPASS), then fall back to exe dir
    candidates = [
        Path(getattr(sys, "_MEIPASS", "")),   # PyInstaller extracted bundle
        Path(sys.executable).parent,           # next to the .exe (onedir layout)
    ]
    for directory in candidates:
        dll = directory / "libmpv-2.dll"
        if dll.exists():
            os.add_dll_directory(str(directory))
            return

_find_libmpv()

import mpv
import regex
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QKeySequence, QPalette, QShortcut, QIcon
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QPushButton, QSizePolicy,
    QStatusBar, QVBoxLayout, QWidget,
)


# ===========================================================================
# Theme
# ===========================================================================

DARK_BG      = "#0d0f14"
PANEL_BG     = "#13161e"
BORDER       = "#1f2430"
ACCENT       = "#e8c547"
ACCENT2      = "#4fc3f7"
TEXT_PRIMARY = "#e8eaf0"
TEXT_DIM     = "#5a6070"
CORRECT_CLR  = "#4caf79"
WRONG_CLR    = "#e05c5c"

STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {DARK_BG};
    color: {TEXT_PRIMARY};
    font-family: 'Noto Sans', 'Segoe UI', 'Hiragino Sans', sans-serif;
    font-size: 14px;
}}
#header {{
    background: {PANEL_BG};
    border-bottom: 1px solid {BORDER};
}}
#scoreLabel {{
    color: {TEXT_DIM};
    font-size: 13px;
    letter-spacing: 1px;
}}
QPushButton {{
    background: {PANEL_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 6px 16px;
    font-size: 13px;
}}
QPushButton:hover {{
    border-color: {ACCENT};
    color: {ACCENT};
}}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {TEXT_DIM}; border-color: {BORDER}; }}
QPushButton#accentBtn {{
    background: {ACCENT};
    color: {DARK_BG};
    border: none;
    font-weight: bold;
    letter-spacing: 1px;
}}
QPushButton#accentBtn:hover {{ background: #f0d060; color: {DARK_BG}; }}
QPushButton#accentBtn:disabled {{ background: #4a4020; color: {TEXT_DIM}; }}
QLineEdit {{
    background: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 4px;
    color: {TEXT_PRIMARY};
    padding: 6px 10px;
    font-size: 16px;
    selection-background-color: {ACCENT};
    selection-color: {DARK_BG};
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QLineEdit#correctInput {{ border-color: {CORRECT_CLR}; background: #0d2018; }}
QLineEdit#wrongInput   {{ border-color: {WRONG_CLR};   background: #200d0d; }}
QListWidget {{
    background: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 4px;
    outline: none;
}}
QListWidget::item {{
    padding: 8px 12px;
    border-bottom: 1px solid {BORDER};
}}
QListWidget::item:selected {{ background: #1e2430; color: {ACCENT}; }}
QListWidget::item:hover    {{ background: #181c26; }}
QScrollBar:vertical {{
    background: {DARK_BG}; width: 6px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 3px; min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{ background: {TEXT_DIM}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QStatusBar {{
    background: {PANEL_BG};
    color: {TEXT_DIM};
    border-top: 1px solid {BORDER};
    font-size: 12px;
}}
QFrame[frameShape="4"], QFrame[frameShape="5"] {{ color: {BORDER}; }}
#progressLabel {{ color: {TEXT_DIM}; font-size: 12px; letter-spacing: 1px; }}
#clozeLabel {{
    font-size: 22px;
    color: {TEXT_PRIMARY};
    background: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 18px 24px;
}}
#resultLabel  {{ font-size: 15px; font-weight: bold; }}
#answerReveal {{ font-size: 15px; color: {ACCENT2}; }}
"""


def apply_palette(target):
    pal = QPalette()
    pal.setColor(QPalette.Window,          QColor(DARK_BG))
    pal.setColor(QPalette.WindowText,      QColor(TEXT_PRIMARY))
    pal.setColor(QPalette.Base,            QColor(PANEL_BG))
    pal.setColor(QPalette.AlternateBase,   QColor(BORDER))
    pal.setColor(QPalette.Text,            QColor(TEXT_PRIMARY))
    pal.setColor(QPalette.Button,          QColor(PANEL_BG))
    pal.setColor(QPalette.ButtonText,      QColor(TEXT_PRIMARY))
    pal.setColor(QPalette.Highlight,       QColor(ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor(DARK_BG))
    target.setPalette(pal)

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# ===========================================================================
# SRT parser
# ===========================================================================

_SRT_BLOCK_RE = re.compile(
    r"(\d+)\s*\n"
    r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*\n"
    r"([\s\S]*?)(?=\n\s*\n\d+\s*\n|\Z)",
    re.MULTILINE,
)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class SubtitleEntry:
    index: int
    start_ms: int
    end_ms: int
    display_text: str


def _ts_to_ms(ts: str) -> int:
    ts = ts.replace(",", ".")
    h, m, rest = ts.split(":")
    s, ms = rest.split(".")
    return int(h) * 3_600_000 + int(m) * 60_000 + int(s) * 1_000 + int(ms[:3])


def parse_srt(path: str | Path) -> list[SubtitleEntry]:
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n\n"
    entries = []
    for m in _SRT_BLOCK_RE.finditer(text):
        raw = _TAG_RE.sub("", m.group(4).strip()).strip()
        if not raw:
            continue
        raw = " ".join(raw.splitlines())
        entries.append(SubtitleEntry(
            index=int(m.group(1)),
            start_ms=_ts_to_ms(m.group(2)),
            end_ms=_ts_to_ms(m.group(3)),
            display_text=raw,
        ))
    return entries


# ===========================================================================
# Folder scanner
# ===========================================================================

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v"}


@dataclass
class MediaPair:
    video_path: Path
    srt_path: Path

    @property
    def name(self) -> str:
        return self.video_path.stem


def scan_folder(folder: str | Path) -> list[MediaPair]:
    root = Path(folder)
    pairs = []
    for video in sorted(root.rglob("*")):
        if video.suffix.lower() not in VIDEO_EXTS:
            continue
        srt = video.with_suffix(".srt")
        if not srt.exists():
            candidates = [s for s in video.parent.glob("*.srt")
                          if s.stem.lower() == video.stem.lower()]
            if not candidates:
                continue
            srt = candidates[0]
        pairs.append(MediaPair(video_path=video, srt_path=srt))
    return pairs


# ===========================================================================
# Cloze logic
# ===========================================================================
#this should detect all types of parentheses - can also handle recursive parentheses
_ALLPAREN_RE = regex.compile(
    r"""
    (?P<br>
        \(
            (?: [^()\[\]{}（）] | (?&br) )*
        \)
      |
        \[
            (?: [^()\[\]{}（）] | (?&br) )*
        \]
      |
        \{
            (?: [^()\[\]{}（）] | (?&br) )*
        \}
      |
        （
            (?: [^()\[\]{}（）] | (?&br) )*
        ）
    )
    """,
    regex.VERBOSE,
)

_JP_RE       = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff\u3400-\u4dbf]")
_NUMBER_RE   = re.compile(r"^\d+([.,]\d+)*$")
_PUNCT_RE    = re.compile(r"^[\W\d_]+$", re.UNICODE)
_JP_PUNCT_RE = re.compile(
    r"^[\u3000-\u303f\uff01-\uff0f\uff1a-\uff20\uff3b-\uff40\uff5b-\uff65\u2026\u30fb\u30fc]+$"
)


def _strip_parens(text: str) -> str:
    return _ALLPAREN_RE.sub("", text).strip()


def _is_japanese(text: str) -> bool:
    return bool(_JP_RE.search(text))


def _is_punct_or_number(s: str) -> bool:
    if _NUMBER_RE.match(s) or _PUNCT_RE.match(s) or _JP_PUNCT_RE.match(s):
        return True
    cats = {unicodedata.category(c) for c in s}
    return cats.issubset({"Po", "Ps", "Pe", "Pi", "Pf", "Pd", "Pc", "So", "Sm", "No", "Nd"})


@dataclass
class _Token:
    surface: str
    start: int
    end: int
    eligible: bool


_EN_PUNCT = ".,!?;:\"'()[]{}…—–-"


def _strip_en_punct(surface: str, base_offset: int) -> tuple[str, int, int]:
    """
    Strip leading/trailing English punctuation from a token surface and return
    (core, start, end) with offsets adjusted to match the trimmed string.
    """
    lstripped = surface.lstrip(_EN_PUNCT)
    lead = len(surface) - len(lstripped)
    core = lstripped.rstrip(_EN_PUNCT)
    start = base_offset + lead
    end = start + len(core)
    return core, start, end


def _tokenise_english(text: str) -> list[_Token]:
    nlp = getattr(_tokenise_english, "_nlp", None)
    if nlp is None:
        try:
            import spacy
            _tokenise_english._nlp = spacy.load("en_core_web_sm")
            nlp = _tokenise_english._nlp
        except Exception:
            _tokenise_english._nlp = False
            nlp = False

    if nlp:
        tokens = []
        for tok in nlp(text):
            is_proper = tok.ent_type_ in {
                "PERSON", "ORG", "GPE", "LOC", "FAC", "NORP", "PRODUCT", "EVENT", "WORK_OF_ART"
            }
            # spaCy sometimes bundles trailing punctuation into a word token
            # (e.g. "running." at end of sentence). Strip it so the blank and
            # expected answer are punctuation-free.
            core, start, end = _strip_en_punct(tok.text, tok.idx)
            eligible = (
                bool(core)
                and not _is_punct_or_number(core)
                and not is_proper
                and not core.isspace()
            )
            tokens.append(_Token(core, start, end, eligible))
        return tokens

    # Fallback: regex tokeniser
    tokens = []
    for m in re.finditer(r"\S+", text):
        core, start, end = _strip_en_punct(m.group(), m.start())
        eligible = bool(core) and not _is_punct_or_number(core) and not core[0].isupper()
        tokens.append(_Token(core, start, end, eligible))
    return tokens


def _get_fugashi_tagger():
    """
    Initialise a fugashi Tagger, resolving the MeCab dictionary path explicitly.

    When running from a PyInstaller bundle the normal MeCab config lookup fails
    because it tries the hard-coded system path (e.g. C:\\mecab\\mecabrc).
    We pass -d <dicdir> directly so MeCab never needs to consult that file.
    """
    import fugashi

    # PyInstaller extracts bundled files to sys._MEIPASS at runtime.
    # When running from source, _MEIPASS is not set so we fall back to None
    # and let fugashi find the dictionary through its normal mechanisms.
    meipass = getattr(sys, "_MEIPASS", None)

    if meipass:
        # Search for a bundled dictionary (unidic_lite or ipadic)
        import os
        for candidate in ("unidic_lite/dicdir", "ipadic/dicdir", "unidic/dicdir"):
            dict_path = os.path.join(meipass, candidate)
            if os.path.isdir(dict_path):
                return fugashi.Tagger(f'-d "{dict_path}"')
        raise RuntimeError(
            f"fugashi: no MeCab dictionary found under {meipass}. "
            "Make sure unidic-lite (or ipadic) is included in your PyInstaller datas."
        )

    # Running from .py — let fugashi locate the dictionary itself
    return fugashi.Tagger()

def load_excluded(filepath, mode="line"):
    excluded = set()
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if "#" in line:
                line = line.split("#", 1)[0].strip()

            if mode == "line":
                excluded.add(line)
            elif mode == "char":
                excluded.update(line)

    return excluded

def _tokenise_japanese(text: str) -> list[_Token]:
    tagger = getattr(_tokenise_japanese, "_tagger", None)
    if tagger is None:
        try:
            _tokenise_japanese._tagger = _get_fugashi_tagger()
            tagger = _tokenise_japanese._tagger
        except Exception as e:
            import traceback
            print(f"[fugashi failed]: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            _tokenise_japanese._tagger = False
            tagger = False

    EXCLUDE_STRINGS = load_excluded("excluded_strings.txt", mode="line")
    BANNED_CHARS = load_excluded("excluded_chars.txt", mode="line")
    
    if tagger:
        tokens = []
        offset = 0
        for word in tagger(text):
            surface = word.surface
            idx = text.find(surface, offset)
            if idx == -1:
                idx = offset
            offset = idx + len(surface)
            feature = str(word.feature) if word.feature else ""
            pos = feature.split(",")[0] if feature else ""
            is_proper = "固有名詞" in feature
            eligible = (
                not _is_punct_or_number(surface)
                and not is_proper
                and not surface.isspace()
                and len(surface) > 0
                and surface not in EXCLUDE_STRINGS
                and not any(c in BANNED_CHARS for c in surface)
                and not (
                    len(surface) <= 2
                    and re.fullmatch(r"[\u3040-\u309f]+", surface)
                    and pos in ("助詞", "助動詞")
                )
            )
            tokens.append(_Token(surface, idx, idx + len(surface), eligible))
        return tokens

    # Fallback: cluster by script (kanji runs, kana runs, latin runs, etc.)
    return [
    _Token(m.group(), m.start(), m.end(), not _is_punct_or_number(m.group()))
    for m in re.finditer(
        r"[\u4e00-\u9fff\u3400-\u4dbf]+|"   # CJK (kanji)
        r"[\u30a0-\u30ff]+|"                  # Katakana
        r"[\u3040-\u309f]+|"                  # Hiragana
        r"[a-zA-Z0-9]+|"                      # ASCII words/numbers
        r"\S",                                 # anything else, one char
        text,
    )
]


@dataclass
class ClozeResult:
    original_text: str
    display_text: str
    cloze_text: str
    target_word: str
    target_start: int
    target_end: int
    blank: str


def make_cloze(text: str, seed: int | None = None, language: str | None = None) -> ClozeResult | None:
    """
    language: 'japanese', 'english', or None (auto-detect).
    """
    stripped = _strip_parens(text)
    if not stripped:
        return None
    use_japanese = (
        language == "japanese" if language is not None else _is_japanese(stripped)
    )
    tokens = _tokenise_japanese(stripped) if use_japanese else _tokenise_english(stripped)
    eligible = [t for t in tokens if t.eligible]
    if not eligible:
        return None
    chosen = random.Random(seed).choice(eligible)
    blank_char = "＿" if use_japanese else "_"
    blank = blank_char * len(chosen.surface)
    cloze_text = stripped[: chosen.start] + blank + stripped[chosen.end :]
    return ClozeResult(
        original_text=text,
        display_text=stripped,
        cloze_text=cloze_text,
        target_word=chosen.surface,
        target_start=chosen.start,
        target_end=chosen.end,
        blank=blank,
    )

def kata_to_hira(text: str) -> str:
    result = []
    for ch in text:
        code = ord(ch)
        # Katakana → Hiragana
        if 0x30A1 <= code <= 0x30F6:
            result.append(chr(code - 0x60))
        else:
            result.append(ch)
    return "".join(result)


def normalize_answer(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = kata_to_hira(text)
    return text

def check_answer(user_input: str, result: ClozeResult) -> bool:
    return normalize_answer(user_input) == normalize_answer(result.target_word)


# ===========================================================================
# History / persistence
# ===========================================================================

def _app_dir() -> Path:
    # executable folder
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent

    # Running from source
    return Path(__file__).resolve().parent

HISTORY_FILE = _app_dir() / "history.json"


@dataclass
class AnswerRecord:
    timestamp: float
    video_file: str
    subtitle_index: int
    subtitle_text: str
    target_word: str
    user_answer: str
    correct: bool


_PADDING_MIN =    0
_PADDING_MAX = 5000
_PADDING_STEP =  100


@dataclass
class History:
    records: list[AnswerRecord] = field(default_factory=list)
    clip_padding_ms: int = 200   # default matches the original hard-coded value

    def save(self):
        data = {
            "clip_padding_ms": self.clip_padding_ms,
            "records": [asdict(r) for r in self.records],
        }
        HISTORY_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls) -> "History":
        if not HISTORY_FILE.exists():
            return cls()
        try:
            raw = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            # Backwards-compat: old files were a bare list of records
            if isinstance(raw, list):
                return cls(records=[AnswerRecord(**r) for r in raw])
            records = [AnswerRecord(**r) for r in raw.get("records", [])]
            padding = int(raw.get("clip_padding_ms", 200))
            padding = max(_PADDING_MIN, min(_PADDING_MAX, padding))
            return cls(records=records, clip_padding_ms=padding)    
        except Exception:
            return cls()

    def record_answer(self, video_file, subtitle_index, subtitle_text,
                      target_word, user_answer, correct) -> AnswerRecord:
        rec = AnswerRecord(time.time(), video_file, subtitle_index,
                           subtitle_text, target_word, user_answer, correct)
        self.records.append(rec)
        self.save()
        return rec

    @property
    def total(self) -> int:
        return len(self.records)

    @property
    def correct_count(self) -> int:
        return sum(1 for r in self.records if r.correct)

    @property
    def accuracy(self) -> float:
        return self.correct_count / self.total if self.total else 0.0


# ===========================================================================
# MPV widget
# ===========================================================================


class MpvWidget(QWidget):
    playback_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 270)
        self.setStyleSheet("background: #000;")
        self._player: mpv.MPV | None = None
        self._init_player()

    def _init_player(self):
        try:
            self._player = mpv.MPV(
                wid=str(int(self.winId())),
                osc=False,
                osd_level=0,
                keep_open="yes",  # freeze on last frame instead of stopping
                hr_seek=True,       #high-resolution seek
                terminal=False,
                really_quiet=True,
                sub_auto="no", # do not auto-load any subtitles
                sid="no",          # no active subtitle track
                sub_visibility=False, # start subtitles hidden
                loop=False,      # no automatic video looping
            )
            self._player.observe_property("pause", self._on_eof)
        except Exception as e:
            print(f"[MpvWidget] Failed to initialise python-mpv: {e}")
            self._player = None

    def _on_eof(self, name, value):
        if value and self._player and self._player.eof_reached:
            from PySide6.QtCore import QMetaObject, Qt as _Qt
            QMetaObject.invokeMethod(self, "_emit_finished", _Qt.QueuedConnection)

    @Slot()
    def _emit_finished(self):
        self.playback_finished.emit()

    def play_clip(self, video_path: str, start_ms: int, end_ms: int):
        if self._player is None:
            return
        self._player["start"] = f"{start_ms / 1000:.3f}"
        self._player["end"]   = f"{end_ms / 1000:.3f}"
        self._player.play(video_path)
        
        #Remove any existing subtitle tracks
        try:
            self._player.command("sub-remove", "all")
        except Exception:
            pass
        
        # Explicitly load matching .sup if present
        sup_path = Path(video_path).with_suffix(".sup")
        if sup_path.exists():
                try:
                    self._player.command("sub-add", str(sup_path))
                    self._player.sid = -1 # select only the newly added track
                except Exception:
                    pass
        self._player.pause = False  # clear any EOF-induced pause before loading

    def stop(self):
        if self._player:
            try:
                self._player.stop()
            except Exception:
                pass

    def closeEvent(self, event):
        if self._player:
            try:
                self._player.terminate()
            except Exception:
                pass
            self._player = None
        super().closeEvent(event)

    def show_subtitles(self):
        if self._player:
            self._player.sub_visibility = True

    def hide_subtitles(self):
        if self._player:
            self._player.sub_visibility = False


# ===========================================================================
# Language picker dialog
# ===========================================================================

class LanguageDialog(QWidget):
    """
    Modal-style dialog asking the user to choose Japanese or English tokeniser.
    Returns 'japanese' or 'english' via the chosen attribute after exec().
    """

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.setWindowTitle("Select Language")
        self.setFixedSize(320, 140)
        self.chosen: str | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(16)

        lbl = QLabel("Which tokeniser should be used for this folder?")
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        ja_btn = QPushButton("🇯🇵  Japanese")
        ja_btn.setFixedHeight(38)
        ja_btn.clicked.connect(lambda: self._pick("japanese"))
        btn_row.addWidget(ja_btn)

        en_btn = QPushButton("🇬🇧  English")
        en_btn.setFixedHeight(38)
        en_btn.clicked.connect(lambda: self._pick("english"))
        btn_row.addWidget(en_btn)

        lay.addLayout(btn_row)

    def _pick(self, language: str):
        self.chosen = language
        self.close()

    @staticmethod
    def ask(parent=None) -> str | None:
        dlg = LanguageDialog(parent)
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.show()
        # Spin the event loop until the dialog is closed
        from PySide6.QtCore import QEventLoop
        loop = QEventLoop()
        dlg.destroyed.connect(loop.quit)
        dlg.windowHandle()  # ensure native window exists
        # Use close event instead
        original_close = dlg.closeEvent
        def _close(event):
            loop.quit()
            original_close(event)
        dlg.closeEvent = _close
        loop.exec()
        return dlg.chosen




class PaddingSpinBox(QWidget):
    """
    A read-only spin box that changes value only via Up/Down arrow keys.
    Displays the current padding in milliseconds. Emits value_changed(int).
    """
    value_changed = Signal(int)

    def __init__(self, value: int = 200, parent=None):
        super().__init__(parent)
        self._value = max(_PADDING_MIN, min(_PADDING_MAX, value))
        self._build_ui()

    def _build_ui(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._display = QLineEdit()
        self._display.setReadOnly(True)
        self._display.setFixedWidth(108)
        self._display.setFixedHeight(34)
        self._display.setAlignment(Qt.AlignCenter)
        self._display.setToolTip("Clip padding (↑/↓ to adjust, 0–5000 ms)")
        self._display.setFocusPolicy(Qt.NoFocus)
        self._refresh()
        lay.addWidget(self._display)

        btn_col = QVBoxLayout()
        btn_col.setContentsMargins(0, 0, 0, 0)
        btn_col.setSpacing(0)

        self._up_btn = QPushButton("▲")
        self._up_btn.setFixedSize(20, 17)
        self._up_btn.setFocusPolicy(Qt.NoFocus)
        self._up_btn.clicked.connect(self._step_up)

        self._dn_btn = QPushButton("▼")
        self._dn_btn.setFixedSize(20, 17)
        self._dn_btn.setFocusPolicy(Qt.NoFocus)
        self._dn_btn.clicked.connect(self._step_down)

        btn_col.addWidget(self._up_btn)
        btn_col.addWidget(self._dn_btn)
        lay.addLayout(btn_col)

        self.setFocusPolicy(Qt.StrongFocus)

    def value(self) -> int:
        return self._value

    def set_value(self, v: int):
        v = max(_PADDING_MIN, min(_PADDING_MAX, v))
        if v != self._value:
            self._value = v
            self._refresh()
            self.value_changed.emit(self._value)

    def _step_up(self):
        self.set_value(self._value + _PADDING_STEP)

    def _step_down(self):
        self.set_value(self._value - _PADDING_STEP)

    def _refresh(self):
        self._display.setText(f"{self._value} ms")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Up:
            self._step_up()
        elif event.key() == Qt.Key_Down:
            self._step_down()
        else:
            super().keyPressEvent(event)

# Quiz phases
_PHASE_WATCHING  = "watching"   # video playing / can replay; no subtitle shown
_PHASE_CLOZE     = "cloze"      # cloze shown; waiting for typed answer
_PHASE_RESULT    = "result"     # full subtitle + feedback shown; can replay; enter → next


class QuizView(QWidget):
    stats_updated = Signal()

    def __init__(self, history: History, parent=None):
        super().__init__(parent)
        self.history = history

        # All eligible (pair, entry) tuples loaded from the folder
        self._clips: list[tuple[MediaPair, SubtitleEntry]] = []
        self._current_pair: MediaPair | None = None
        self._current_entry: SubtitleEntry | None = None
        self._cloze: ClozeResult | None = None
        self._phase: str = _PHASE_WATCHING
        self._session_score: int = 0
        self._language: str | None = None  # 'japanese', 'english', or None

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Video player — takes all available vertical space
        self.player = MpvWidget()
        self.player.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.player.playback_finished.connect(self._on_playback_finished)
        root.addWidget(self.player, 3)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        root.addWidget(sep)

        # Bottom panel
        bottom = QWidget()
        bottom.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        blay = QVBoxLayout(bottom)
        blay.setContentsMargins(24, 16, 24, 14)
        blay.setSpacing(12)
        root.addWidget(bottom)

        # Subtitle / cloze display
        self.cloze_label = QLabel("")
        self.cloze_label.setObjectName("clozeLabel")
        self.cloze_label.setWordWrap(True)
        self.cloze_label.setAlignment(Qt.AlignCenter)
        self.cloze_label.setMinimumHeight(72)
        self.cloze_label.setTextFormat(Qt.RichText)
        self.cloze_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse |
            Qt.TextSelectableByKeyboard
        )
        blay.addWidget(self.cloze_label)
        
        # Source info label (visible only during _PHASE_RESULT)
        self.source_label = QLabel("")
        self.source_label.setAlignment(Qt.AlignCenter)
        self.source_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        self.source_label.hide()
        blay.addWidget(self.source_label)

        # Answer input row (visible only during _PHASE_CLOZE)
        self.answer_input = QLineEdit()
        self.answer_input.setPlaceholderText("Type the missing word and press Enter…")
        self.answer_input.setAlignment(Qt.AlignCenter)
        self.answer_input.setFixedHeight(42)
        self.answer_input.returnPressed.connect(self._on_enter)
        blay.addWidget(self.answer_input)

        # Result / hint label
        self.result_label = QLabel("")
        self.result_label.setObjectName("resultLabel")
        self.result_label.setAlignment(Qt.AlignCenter)
        blay.addWidget(self.result_label)

        # Bottom bar: score + folder button
        nav_sep = QFrame()
        nav_sep.setFrameShape(QFrame.HLine)
        blay.addWidget(nav_sep)

        nrow = QHBoxLayout()
        nrow.setSpacing(8)

        self.folder_btn = QPushButton("📂  Open Folder")
        self.folder_btn.setFixedHeight(34)
        self.folder_btn.clicked.connect(self._pick_folder)
        nrow.addWidget(self.folder_btn)

        self.padding_spin = PaddingSpinBox(value=self.history.clip_padding_ms)
        self.padding_spin.setToolTip("Clip padding — added before and after each subtitle clip")
        self.padding_spin.value_changed.connect(self._on_padding_changed)
        nrow.addWidget(self.padding_spin)

        nrow.addStretch()

        self.session_score_label = QLabel("")
        self.session_score_label.setObjectName("progressLabel")
        nrow.addWidget(self.session_score_label)

        blay.addLayout(nrow)

        # Spacebar replays; Enter advances through phases
        space = QShortcut(QKeySequence("Space"), self)
        space.activated.connect(self._on_space)
        enter = QShortcut(QKeySequence("Return"), self)
        enter.activated.connect(self._on_enter)

    # ------------------------------------------------------------------
    # Folder loading
    # ------------------------------------------------------------------

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Open Folder", str(Path.home()))
        if not folder:
            return
        self.load_folder(folder)

    def load_folder(self, folder: str):
        # Ask user which tokeniser to use for this folder
        self._language = LanguageDialog.ask(self)
        if self._language is None:
            return  # user closed the dialog without choosing

        pairs = scan_folder(folder)
        # Collect all clips that have at least one eligible cloze word
        self._clips = []
        for pair in pairs:
            try:
                entries = parse_srt(pair.srt_path)
            except Exception:
                continue
            for entry in entries:
                if make_cloze(entry.display_text, language=self._language) is not None:
                    self._clips.append((pair, entry))

        if not self._clips:
            self.cloze_label.setText(
                f'<span style="color:{WRONG_CLR};">No testable clips found in this folder.</span>'
            )
            self.answer_input.hide()
            self.result_label.setText("")
            return

        self._session_score = 0
        self._update_score_label()
        self._next_clip()

    # ------------------------------------------------------------------
    # Clip loading
    # ------------------------------------------------------------------

    def _next_clip(self):
        """Pick a random clip and enter the watching phase."""
        self._current_pair, self._current_entry = random.choice(self._clips)
        # Generate cloze now so the same word is blanked throughout this round
        self._cloze = make_cloze(self._current_entry.display_text, language=self._language)

        self._set_phase(_PHASE_WATCHING)
        self._play_current()

    def _play_current(self):
        e = self._current_entry
        p = self._current_pair
        pad = self.history.clip_padding_ms
        self.player.play_clip(str(p.video_path), max(0, e.start_ms - pad), e.end_ms + pad)

    def _on_padding_changed(self, value: int):
        self.history.clip_padding_ms = value
        self.history.save()

    # ------------------------------------------------------------------
    # Phase management
    # ------------------------------------------------------------------

    def _set_phase(self, phase: str):
        self._phase = phase

        if phase == _PHASE_WATCHING:
            # Blank subtitle area, hide input and result
            self.cloze_label.setText(
                f'<span style="color:{TEXT_DIM}; font-size:13px;">'
                f'[SPACE] replay  ·  [ENTER] show subtitle</span>'
            )
            self.answer_input.hide()
            self.answer_input.clear()
            self.result_label.setText("")
            self.source_label.hide()
            self.player.hide_subtitles()

        elif phase == _PHASE_CLOZE:
            # Show cloze, reveal input box
            self._render_cloze()
            self.answer_input.show()
            self.answer_input.clear()
            self.answer_input.setObjectName("")
            self.answer_input.setStyleSheet("")
            self.answer_input.setFocus()
            self.result_label.setText("")
            self.player.stop()   # no replay during answer phase
            self.source_label.hide()
            self.player.hide_subtitles()

        elif phase == _PHASE_RESULT:
            # Full subtitle shown, feedback shown, replay re-enabled
            self.player.show_subtitles()
            self.answer_input.hide()
            if self._current_pair and self._current_entry:
                ms = self._current_entry.start_ms
                h, rem = divmod(ms, 3_600_000)
                m, rem = divmod(rem, 60_000)
                s, ms_ = divmod(rem, 1_000)
                ts = f"{h:02d}:{m:02d}:{s:02d}.{ms_:03d}"
                self.source_label.setText(
                    f"{self._current_pair.video_path.name}  ·  {ts}"
                )
                self.source_label.show()

    # ------------------------------------------------------------------
    # Input handlers
    # ------------------------------------------------------------------

    def _on_space(self):
        if self._phase in (_PHASE_WATCHING, _PHASE_RESULT):
            self._play_current()

    def _on_enter(self):
        if self._phase == _PHASE_WATCHING:
            self._set_phase(_PHASE_CLOZE)

        elif self._phase == _PHASE_CLOZE:
            self._submit_answer()

        elif self._phase == _PHASE_RESULT:
            self._next_clip()

    def _on_playback_finished(self):
        pass  # user drives all transitions; nothing auto-advances

    # ------------------------------------------------------------------
    # Answer evaluation
    # ------------------------------------------------------------------

    def _submit_answer(self):
        if self._cloze is None:
            return
        user = self.answer_input.text().strip()
        if not user:
            return

        correct = check_answer(user, self._cloze)
        delta = +1 if correct else -1
        self._session_score += delta
        self._update_score_label()

        e = self._current_entry
        p = self._current_pair
        self.history.record_answer(
            str(p.video_path), e.index, e.display_text,
            self._cloze.target_word, user, correct,
        )
        self.stats_updated.emit()

        # Style the input field
        self.answer_input.setObjectName("correctInput" if correct else "wrongInput")
        self.answer_input.style().unpolish(self.answer_input)
        self.answer_input.style().polish(self.answer_input)

        # Result label
        if correct:
            self.result_label.setText("✓  Correct!")
            self.result_label.setStyleSheet(
                f"color:{CORRECT_CLR}; font-size:15px; font-weight:bold;"
            )
        else:
            self.result_label.setText("✗  Incorrect")
            self.result_label.setStyleSheet(
                f"color:{WRONG_CLR}; font-size:15px; font-weight:bold;"
            )

        self._set_phase(_PHASE_RESULT)
        # Show full subtitle with highlighted answer word
        self._render_full_sentence()
        # Hint: press enter to continue
        hint = f"  <span style='color:{TEXT_DIM}; font-size:12px;'>[SPACE] replay  ·  [ENTER] next clip</span>"
        self.result_label.setTextFormat(Qt.RichText)
        current = self.result_label.text()
        self.result_label.setText(current + hint)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_cloze(self):
        if self._cloze is None:
            return
        escaped = html.escape(self._cloze.cloze_text)
        blank_e = html.escape(self._cloze.blank)
        self.cloze_label.setText(escaped.replace(
            blank_e,
            f'<span style="color:{ACCENT}; font-weight:bold; font-size:1.1em;">{blank_e}</span>',
            1,
        ))

    def _render_full_sentence(self):
        c = self._cloze
        before = html.escape(c.display_text[: c.target_start])
        word   = html.escape(c.target_word)
        after  = html.escape(c.display_text[c.target_end :])
        self.cloze_label.setText(
            f'{before}<span style="color:{ACCENT2}; font-weight:bold;">{word}</span>{after}'
        )

    # ------------------------------------------------------------------
    # Score
    # ------------------------------------------------------------------

    def _update_score_label(self):
        h = self.history
        sign = "+" if self._session_score >= 0 else ""
        session_str = f"Session: {sign}{self._session_score}"
        if h.total > 0:
            alltime_str = f"All-time: {h.correct_count}/{h.total} ({int(h.accuracy * 100)}%)"
            self.session_score_label.setText(f"{session_str}  ·  {alltime_str}")
        else:
            self.session_score_label.setText(session_str)


# ===========================================================================
# Main window
# ===========================================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon(resource_path("assets/icon.png")))
        self.setWindowTitle("Yorudan Cloze Tester")
        self.resize(900, 640)
        self.setMinimumSize(700, 500)
        self.history = History.load()
        apply_palette(self)
        self.setStyleSheet(STYLESHEET)
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Quiz view fills the window
        self.quiz = QuizView(self.history, self)
        self.quiz.stats_updated.connect(self.quiz._update_score_label)
        root.addWidget(self.quiz, 1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Open a folder containing video + SRT pairs to begin.")

        # Open folder dialog immediately on launch
        QTimer.singleShot(0, self._prompt_folder)

    def _prompt_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Open Folder", str(Path.home()))
        if folder:
            self.quiz.load_folder(folder)
            self.status.showMessage(f"Loaded: {folder}")
        else:
            self.status.showMessage("No folder selected. Use the Open Folder button to begin.")


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Yorudan Cloze Tester")
    app.setWindowIcon(QIcon(resource_path("assets/icon.png")))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
