import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import calendar
from datetime import datetime, date
import json
import os
from typing import Dict, List, Tuple, Optional
import random
from collections import Counter, defaultdict
import copy
import wave
import struct
import math
import tempfile
import threading


# ─────────────── レトロゲーム風サウンドエンジン ───────────────

class SoundManager:
    """ドラクエ・マリオ風の8bitサウンドをプログラム生成して再生するマネージャー
    
    高速化: WAVデータをメモリ上にプリロードし、再生時のファイルI/Oを最小化。
    pygameの場合はSoundオブジェクトをキャッシュして即時再生。
    """

    SAMPLE_RATE = 22050

    def __init__(self):
        self.muted = False
        self._sound_dir = tempfile.mkdtemp(prefix="cal_sfx_")
        self._sounds: Dict[str, str] = {}
        self._pygame_cache: Dict[str, object] = {}
        self._playback_method = self._detect_playback_method()
        self._generate_all_sounds()
        self._preload_sounds()

    def _detect_playback_method(self) -> str:
        try:
            import pygame
            pygame.mixer.init(frequency=self.SAMPLE_RATE, size=-16, channels=1, buffer=256)
            return "pygame"
        except Exception:
            pass
        try:
            import simpleaudio
            return "simpleaudio"
        except ImportError:
            pass
        try:
            import winsound
            return "winsound"
        except ImportError:
            pass
        import shutil
        if shutil.which("aplay"):
            return "aplay"
        if shutil.which("afplay"):
            return "afplay"
        return "none"

    @staticmethod
    def _square_wave(freq, t, duty=0.5):
        if freq == 0: return 0
        phase = (t * freq) % 1.0
        return 1.0 if phase < duty else -1.0

    @staticmethod
    def _triangle_wave(freq, t):
        if freq == 0: return 0
        phase = (t * freq) % 1.0
        return 4.0 * abs(phase - 0.5) - 1.0

    @staticmethod
    def _sine_wave(freq, t):
        if freq == 0: return 0
        return math.sin(2 * math.pi * freq * t)

    @staticmethod
    def _noise(t):
        return random.uniform(-1, 1)

    def _render_wav(self, filename: str, duration: float, generator_func):
        n_samples = int(self.SAMPLE_RATE * duration)
        filepath = os.path.join(self._sound_dir, filename)
        frames = bytearray()
        for i in range(n_samples):
            t = i / self.SAMPLE_RATE
            sample = generator_func(t, duration)
            sample = max(-1.0, min(1.0, sample))
            frames += struct.pack('<h', int(sample * 28000))
        with wave.open(filepath, 'w') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(bytes(frames))
        return filepath

    def _generate_all_sounds(self):
        self._sounds["bright"]      = self._render_wav("bright.wav",      0.25, self._gen_bright)
        self._sounds["levelup"]     = self._render_wav("levelup.wav",     0.65, self._gen_levelup)
        self._sounds["coin"]        = self._render_wav("coin.wav",        0.35, self._gen_coin)
        self._sounds["snap"]        = self._render_wav("snap.wav",        0.18, self._gen_snap)
        self._sounds["oneup"]       = self._render_wav("oneup.wav",       0.55, self._gen_oneup)
        self._sounds["move"]        = self._render_wav("move.wav",        0.10, self._gen_move)
        self._sounds["vroom"]       = self._render_wav("vroom.wav",       0.50, self._gen_vroom)
        self._sounds["sheen"]       = self._render_wav("sheen.wav",       0.35, self._gen_sheen)
        self._sounds["complete"]    = self._render_wav("complete.wav",    1.20, self._gen_complete)

    def _gen_bright(self, t, dur):
        if t < 0.10:
            freq = 659
            env = math.cos(t / 0.10 * math.pi * 0.3)
        elif t < 0.23:
            freq = 880
            env = 1.0 - ((t - 0.10) / 0.13) ** 0.7
        else:
            return 0
        w = self._sine_wave(freq, t) * 0.55
        w += self._sine_wave(freq * 2, t) * 0.10
        w += self._sine_wave(freq * 3, t) * 0.03
        return w * env * 0.35

    def _gen_levelup(self, t, dur):
        notes = [
            (0.000, 0.100, 523),
            (0.100, 0.200, 659),
            (0.200, 0.320, 784),
            (0.320, 0.620, 1047),
        ]
        w = 0
        for start, end, freq in notes:
            if start <= t < end:
                local_t = t - start
                note_dur = end - start
                attack = min(1.0, local_t / 0.008)
                if freq == 1047:
                    decay = max(0, 1.0 - (local_t / note_dur) ** 0.8)
                else:
                    decay = max(0, 1.0 - (local_t / note_dur) ** 0.4)
                env = attack * decay
                w = self._square_wave(freq, t, 0.30) * 0.35 * env
                w += self._triangle_wave(freq, t) * 0.20 * env
                w += self._square_wave(freq * 0.5, t, 0.25) * 0.12 * env
                if freq == 1047:
                    sparkle = self._sine_wave(freq * 2, t) * 0.08 * env
                    sparkle += self._sine_wave(freq * 3, t) * 0.04 * env
                    w += sparkle
                break
        return w * 0.55

    def _gen_coin(self, t, dur):
        if t < 0.08:
            freq = 988
            local_t = t
            attack = min(1.0, local_t / 0.003)
            decay = max(0, 1.0 - (local_t / 0.08) ** 0.6)
            env = attack * decay
            w = self._square_wave(freq, t, 0.125) * 0.45 * env
            w += self._sine_wave(freq * 2, t) * 0.08 * env
            return w * 0.50
        elif t < 0.30:
            freq = 1319
            local_t = t - 0.08
            attack = min(1.0, local_t / 0.003)
            decay = max(0, 1.0 - (local_t / 0.22) ** 0.8)
            env = attack * decay
            w = self._square_wave(freq, t, 0.125) * 0.40 * env
            w += self._sine_wave(freq * 2, t) * 0.06 * env
            return w * 0.50
        return 0

    def _gen_snap(self, t, dur):
        if t < 0.02:
            env = 1.0
            return self._square_wave(800 - t * 20000, t, 0.5) * env * 0.7
        elif t < 0.08:
            env = 1.0 - ((t - 0.02) / 0.06)
            freq = 600 * (1.0 - (t - 0.02) / 0.06)
            return (self._square_wave(freq, t, 0.5) * 0.35 + self._noise(t) * 0.20) * env
        elif t < 0.16:
            env = 1.0 - ((t - 0.08) / 0.08)
            return self._noise(t) * env * 0.10
        return 0

    def _gen_oneup(self, t, dur):
        notes = [
            (0.000, 0.070, 659),
            (0.070, 0.140, 784),
            (0.140, 0.210, 1319),
            (0.210, 0.300, 1047),
            (0.300, 0.380, 1175),
            (0.380, 0.530, 1568),
        ]
        w = 0
        for start, end, freq in notes:
            if start <= t < end:
                local_t = t - start
                note_dur = end - start
                attack = min(1.0, local_t / 0.005)
                decay = max(0, 1.0 - (local_t / note_dur) ** 0.5)
                env = attack * decay
                w = self._square_wave(freq, t, 0.25) * 0.40 * env
                w += self._sine_wave(freq, t) * 0.20 * env
                break
        global_env = max(0, 1.0 - (t / dur) ** 3)
        return w * global_env * 0.50

    def _gen_move(self, t, dur):
        freq = 500 + (t / dur) * 500
        env = max(0, 1.0 - t / dur)
        return self._square_wave(freq, t, 0.25) * env * 0.30

    def _gen_vroom(self, t, dur):
        base_freq = 80 + (t / dur) ** 1.5 * 300
        w = self._square_wave(base_freq, t, 0.3) * 0.30
        w += self._square_wave(base_freq * 2, t, 0.4) * 0.15
        w += self._square_wave(base_freq * 3, t, 0.5) * 0.08
        exhaust = self._noise(t) * 0.12
        pulse_rate = base_freq / 4
        pulse = 0.7 + 0.3 * math.sin(2 * math.pi * pulse_rate * t)
        w *= pulse
        w += exhaust * pulse
        if t < 0.08:
            env = t / 0.08
        elif t < dur - 0.10:
            env = 1.0
        else:
            env = max(0, (dur - t) / 0.10)
        return w * env * 0.55

    def _gen_sheen(self, t, dur):
        sweep_freq = 2000 + 3000 * math.exp(-t * 12)
        if t < 0.005:
            attack = t / 0.005
        else:
            attack = 1.0
        w = self._sine_wave(sweep_freq, t) * 0.25
        w += self._sine_wave(sweep_freq * 1.5, t) * 0.15
        w += self._sine_wave(sweep_freq * 2.3, t) * 0.10
        shimmer = 0.7 + 0.3 * math.sin(2 * math.pi * 40 * t)
        w *= shimmer
        if t < 0.03:
            noise_env = 1.0 - t / 0.03
            w += self._noise(t) * noise_env * 0.30
        if t > 0.05:
            ring_env = max(0, 1.0 - (t - 0.05) / 0.30) ** 1.5
            w += self._sine_wave(3520, t) * ring_env * 0.12
            w += self._sine_wave(4186, t) * ring_env * 0.08
        env = attack * max(0, 1.0 - (t / dur) ** 1.2)
        return w * env * 0.55

    def _gen_complete(self, t, dur):
        notes = [
            (0.000, 0.130, 523),
            (0.130, 0.260, 659),
            (0.260, 0.400, 784),
            (0.400, 0.560, 1047),
            (0.560, 0.740, 1319),
            (0.740, 0.950, 1568),
            (0.950, 1.200, 2093),
        ]
        w = 0
        for start, end, freq in notes:
            if start <= t < end:
                local_t = t - start
                note_dur = end - start
                attack = min(1.0, local_t / 0.006)
                if freq == 2093:
                    decay = max(0, 1.0 - (local_t / note_dur) ** 1.2)
                else:
                    decay = max(0, 1.0 - (local_t / note_dur) ** 0.5)
                env = attack * decay
                
                w = self._square_wave(freq, t, 0.25) * 0.40 * env
                w += self._sine_wave(freq, t) * 0.25 * env
                w += self._sine_wave(freq * 2, t) * 0.12 * env
                w += self._sine_wave(freq * 3, t) * 0.06 * env
                
                if freq == 2093:
                    w += self._sine_wave(freq * 1.5, t) * 0.08 * env
                    w += self._sine_wave(freq * 2.5, t) * 0.04 * env
                    tremolo = 0.85 + 0.15 * math.sin(2 * math.pi * 8 * t)
                    w *= tremolo
                break
        
        if t > 1.0:
            global_fade = max(0, (dur - t) / 0.20)
            w *= global_fade
        
        return w * 0.60

    def _preload_sounds(self):
        if self._playback_method == "pygame":
            try:
                import pygame
                for name, filepath in self._sounds.items():
                    self._pygame_cache[name] = pygame.mixer.Sound(filepath)
            except Exception:
                pass

    def play(self, sound_name: str):
        if self.muted:
            return
        if self._playback_method == "pygame" and sound_name in self._pygame_cache:
            try:
                self._pygame_cache[sound_name].play()
            except Exception:
                pass
            return
        filepath = self._sounds.get(sound_name)
        if not filepath or not os.path.exists(filepath):
            return
        threading.Thread(target=self._play_sync, args=(filepath,), daemon=True).start()

    def _play_sync(self, filepath: str):
        try:
            if self._playback_method == "simpleaudio":
                import simpleaudio as sa
                sa.WaveObject.from_wave_file(filepath).play()
            elif self._playback_method == "winsound":
                import winsound
                winsound.PlaySound(filepath, winsound.SND_FILENAME | winsound.SND_ASYNC)
            elif self._playback_method == "aplay":
                import subprocess
                subprocess.run(["aplay", "-q", filepath], timeout=3,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif self._playback_method == "afplay":
                import subprocess
                subprocess.run(["afplay", filepath], timeout=3,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def play_for_label(self, label_name: str):
        if label_name in ("ER", "A", "B"):
            self.play("bright")
        elif label_name == "当直":
            self.play("levelup")
        elif label_name == "外勤":
            self.play("coin")
        elif label_name == "出張":
            self.play("snap")
        elif label_name == "休み":
            self.play("oneup")

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        return self.muted

    def cleanup(self):
        import shutil
        try:
            shutil.rmtree(self._sound_dir, ignore_errors=True)
        except Exception:
            pass

# セルキー型: (日, ラベル行インデックス, 列インデックス)
CellKey = Tuple[int, int, int]


class CalendarApp:
    def __init__(self, root):
        self.root = root
        self.root.title("カレンダー管理システム（AI支援機能付き）")
        
        # ✨ 画面サイズに応じて自動調整
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # 画面サイズの90%を使用（余白を確保）
        window_width = min(1600, int(screen_width * 0.9))
        window_height = min(900, int(screen_height * 0.9))
        
        # 最小サイズを確保（メンバー管理ボタンが見える）
        window_width = max(1200, window_width)
        window_height = max(700, window_height)
        
        # ウィンドウを画面中央に配置
        x_position = (screen_width - window_width) // 2
        y_position = (screen_height - window_height) // 2
        
        self.root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")
        
        # 最大化を試みる（画面に収まる場合のみ）
        if screen_width >= 1600 and screen_height >= 900:
            try:
                self.root.state('zoomed')
            except:
                pass

        self.BLOCK_H = 11
        self.BLOCK_W = 6
        
        self.CELL_W = 60
        self.CELL_H = 25
        
        self.LABELS = ["", "ER", "A", "B", "当直", "明け", "外勤", "出張", "休み", " ", " "]
        self.WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]
        self.HEADER_H = 30
        self.TITLE_H = 45
        self.LABEL_COL_W = 50

        self.current_year = 2026
        self.current_month = 4
        self.cell_data: Dict[CellKey, str] = {}
        self.cell_colors: Dict[CellKey, str] = {}
        self.cell_sequence: Dict[CellKey, int] = {}
        self.er_marks: set = set()
        self.next_sequence = 1
        
        self.locked_cells: set = set()
        self.locked_cell_borders: Dict[CellKey, int] = {}
        
        self.completed_days: set = set()
        self.day_complete_rects: Dict[int, int] = {}
        
        # ✨ 日付メモ帳機能
        self.day_memos: Dict[int, str] = {}  # {day: memo_text}
        self.memo_windows: Dict[int, tk.Toplevel] = {}  # {day: window}
        
        self.undo_stack: List[Dict] = []
        self.redo_stack: List[Dict] = []
        self.max_history = 3
        
        self.stats_mode = "person"
        
        self.value_colors: Dict[str, str] = {
            "ER": "#98fb98",
            "A": "#ffcc99",
            "B": "#add8e6",
            "当直": "#ffb6c1",
            "外勤": "#dda0dd",
            "出張": "#f0e68c",
            "休み": "#e0ffff",
            "秋": "#FFE4B2",
            "桜": "#FFD1DC",
            "小": "#D8D8E8",
            "金": "#C5EDD6",
            "坪": "#FFDCB5",
            "東": "#DDD0F5",
            "長": "#BDE3F8",
            "矢": "#FFF0B5",
            "宮": "#E0E0E0",
        }

        self._rect_ids: Dict[CellKey, int] = {}
        self._text_ids: Dict[CellKey, int] = {}
        self._cell_bounds: Dict[CellKey, Tuple[int, int, int, int]] = {}

        self._edit_entry: Optional[tk.Entry] = None
        self._edit_key: Optional[CellKey] = None
        self._edit_window_id: Optional[int] = None
        self._drag_source: Optional[CellKey] = None
        self._drag_start_cx: float = 0
        self._drag_start_cy: float = 0
        self._dragging: bool = False
        self._drag_ghost_rect: Optional[int] = None
        self._drag_ghost_text: Optional[int] = None
        self._drag_highlight: Optional[int] = None
        self.DRAG_THRESHOLD = 5
        
        self.selected_value: Optional[str] = None
        self.mask_opacity = 0.6
        
        self.special_borders: Dict[CellKey, str] = {}
        self.special_border_ids: Dict[CellKey, List[int]] = {}

        self._day_positions: Dict[int, Tuple[int, int, int, int]] = {}

        self.sound_manager = SoundManager()
        
        # ✨ メンバー管理機能の変数
        self.team_rules = ""  # 全体の決まり事
        self.members_data = []  # メンバーリスト
        self._next_member_id = 1  # メンバーID自動採番
        self._load_default_members()  # デフォルトメンバーを読み込み

        # ✨ サブカレンダー機能の変数
        # key: (表示名, 日, スロット)  スロット: 'duty'|'free'|'s0'|'s1'|'s2'|'s3'
        self.sub_cell_data: Dict[Tuple[str, int, str], str] = {}
        self._sub_cell_bounds: Dict[Tuple[str, int, str], Tuple[int, int, int, int]] = {}
        self._sub_edit_entry = None
        self._sub_edit_key: Optional[Tuple] = None
        self._sub_edit_win_id = None
        self._sub_ctx_menu: Optional[tk.Menu] = None
        
        # ✨ AI支援機能の変数
        # ✨ 特別項目マスターデータ（外勤・委員会・コース・訓練）
        self.special_items: Dict[str, List[str]] = {
            "外勤": [],
            "委員会": [],
            "コース": [],
            "訓練": [],
        }
        # 特別項目管理ウィンドウの参照
        self._special_item_windows: Dict[str, tk.Toplevel] = {}

        # ✨ 疲労度インジケーター用ツールチップ
        self._hp_tooltip_win: Optional[tk.Toplevel] = None
        self._hp_tooltip_areas: List[tuple] = []  # (x1,y1,x2,y2, tooltip_text)

        self.ai_conversation_history: List[Dict] = []
        self.ai_latest_proposal: Optional[Dict] = None
        self.ai_preview_active: bool = False
        self.ai_preview_data: Dict = {}
        self._ai_retry_count: int = 0  # ✨ 提案違反時の自動修正リトライ回数
        
        # APIキー管理（OSの資格情報ストアを優先、非対応環境はメモリのみ）
        self._keyring_service = "CalendarAI_Anthropic"
        self._keyring_username = "api_key"
        self._keyring_available = self._check_keyring()
        self.api_key: str = self._load_api_key()

        self.setup_ui()
        self.root.update_idletasks()
        self.root.after(100, self.create_calendar)
        
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def setup_ui(self):
        # ✨ 最小サイズを設定（ボタンが切れないように）
        self.root.minsize(1200, 700)
        
        # ✨ 画面サイズを取得してレイアウトを決定
        screen_width = self.root.winfo_screenwidth()
        is_small_screen = screen_width < 1600
        
        # ✨ 画面サイズに応じてボタンサイズを調整
        if is_small_screen:
            # 小画面用: 小さめのボタン
            btn_kw = {"font": ("Meiryo UI", 10), "width": 12, "height": 1}
            undo_redo_kw = {"font": ("Meiryo UI", 10), "width": 7, "height": 1}
            ai_btn_kw = {"font": ("Meiryo UI", 10, "bold"), "width": 10, "height": 1}
            sound_btn_kw = {"font": ("Meiryo UI", 9, "bold"), "width": 8, "height": 1}
        else:
            # 大画面用: 通常サイズのボタン
            btn_kw = {"font": ("Meiryo UI", 11), "width": 15, "height": 1}
            undo_redo_kw = {"font": ("Meiryo UI", 11), "width": 8, "height": 1}
            ai_btn_kw = {"font": ("Meiryo UI", 11, "bold"), "width": 12, "height": 1}
            sound_btn_kw = {"font": ("Meiryo UI", 10, "bold"), "width": 10, "height": 1}
        
        # 上部フレーム
        if is_small_screen:
            # ✨ 小画面: 高さ自動調整（2行分）
            top_frame = tk.Frame(self.root, bg="#f0f0f0")
            top_frame.pack(fill=tk.X, padx=10, pady=10)
        else:
            # 大画面: 高さ自動調整（2行分）
            top_frame = tk.Frame(self.root, bg="#f0f0f0")
            top_frame.pack(fill=tk.X, padx=10, pady=6)
        
        if is_small_screen:
            # ========== 小画面レイアウト: 2行構成 ==========
            
            # --- 1行目 ---
            row1 = tk.Frame(top_frame, bg="#f0f0f0")
            row1.pack(fill=tk.X, pady=2)
            
            tk.Label(row1, text="年:", bg="#f0f0f0", font=("Meiryo UI", 11)).pack(side=tk.LEFT, padx=5)
            self.year_var = tk.StringVar(value=str(self.current_year))
            ttk.Spinbox(row1, from_=2020, to=2030, textvariable=self.year_var,
                         width=8, font=("Meiryo UI", 10)).pack(side=tk.LEFT, padx=5)

            tk.Label(row1, text="月:", bg="#f0f0f0", font=("Meiryo UI", 11)).pack(side=tk.LEFT, padx=5)
            self.month_var = tk.StringVar(value=str(self.current_month))
            ttk.Spinbox(row1, from_=1, to=12, textvariable=self.month_var,
                         width=8, font=("Meiryo UI", 10)).pack(side=tk.LEFT, padx=5)

            tk.Button(row1, text="カレンダー生成", command=self.create_calendar,
                      bg="#2d5a7b", fg="white", **btn_kw).pack(side=tk.LEFT, padx=5)
            
            tk.Button(row1, text="◀ 戻る", command=self.undo,
                      bg="#6c757d", fg="white", **undo_redo_kw).pack(side=tk.LEFT, padx=2)
            tk.Button(row1, text="進む ▶", command=self.redo,
                      bg="#6c757d", fg="white", **undo_redo_kw).pack(side=tk.LEFT, padx=2)
            
            tk.Button(row1, text="クリア", command=self.clear_data,
                      bg="#e76f51", fg="white", **btn_kw).pack(side=tk.LEFT, padx=5)
            
            # SE:ONボタンを1行目の右端に
            self.sound_btn = tk.Button(row1, text="🔊 SE:ON", command=self._toggle_sound,
                                        bg="#4CAF50", fg="white", cursor="hand2", **sound_btn_kw)
            self.sound_btn.pack(side=tk.RIGHT, padx=5)
            
            # AI支援ボタンを1行目の右端に
            self.ai_open_btn = tk.Button(row1, text="🤖 AI支援", command=self._open_ai_window,
                                          bg="#805ad5", fg="white", cursor="hand2", **ai_btn_kw)
            self.ai_open_btn.pack(side=tk.RIGHT, padx=5)
            
            # --- 2行目 ---
            row2 = tk.Frame(top_frame, bg="#f0f0f0")
            row2.pack(fill=tk.X, pady=2)
            
            tk.Button(row2, text="Excel出力", command=self.export_to_excel,
                      bg="#f4a261", fg="white", **btn_kw).pack(side=tk.LEFT, padx=5)
            tk.Button(row2, text="データ保存", command=self.save_data,
                      bg="#264653", fg="white", **btn_kw).pack(side=tk.LEFT, padx=5)
            tk.Button(row2, text="データ読込", command=self.load_data,
                      bg="#2a9d8f", fg="white", **btn_kw).pack(side=tk.LEFT, padx=5)
            tk.Button(row2, text="👥 メンバー管理", command=self.open_member_management,
                      bg="#8b5cf6", fg="white", **btn_kw).pack(side=tk.LEFT, padx=5)

            # --- 3行目: 特別項目ボタン ---
            row3 = tk.Frame(top_frame, bg="#f0f0f0")
            row3.pack(fill=tk.X, pady=2)
            special_btn_kw = {"font": ("Meiryo UI", 10, "bold"), "width": 10, "height": 1}
            tk.Label(row3, text="特別項目:", bg="#f0f0f0", font=("Meiryo UI", 10)).pack(side=tk.LEFT, padx=(5, 2))
            tk.Button(row3, text="🚗 外勤",
                      command=lambda: self._open_special_item_window("外勤"),
                      bg="#5b8dd9", fg="white", cursor="hand2", **special_btn_kw).pack(side=tk.LEFT, padx=3)
            tk.Button(row3, text="🏛 委員会",
                      command=lambda: self._open_special_item_window("委員会"),
                      bg="#5b8dd9", fg="white", cursor="hand2", **special_btn_kw).pack(side=tk.LEFT, padx=3)
            tk.Button(row3, text="📚 コース",
                      command=lambda: self._open_special_item_window("コース"),
                      bg="#5b8dd9", fg="white", cursor="hand2", **special_btn_kw).pack(side=tk.LEFT, padx=3)
            tk.Button(row3, text="🎯 訓練",
                      command=lambda: self._open_special_item_window("訓練"),
                      bg="#5b8dd9", fg="white", cursor="hand2", **special_btn_kw).pack(side=tk.LEFT, padx=3)

        else:
            # ========== 大画面レイアウト: 2行構成 ==========

            # --- 1行目（既存ボタン群） ---
            row1 = tk.Frame(top_frame, bg="#f0f0f0")
            row1.pack(fill=tk.X, pady=2)

            tk.Label(row1, text="年:", bg="#f0f0f0", font=("Meiryo UI", 12)).pack(side=tk.LEFT, padx=5)
            self.year_var = tk.StringVar(value=str(self.current_year))
            ttk.Spinbox(row1, from_=2020, to=2030, textvariable=self.year_var,
                         width=10, font=("Meiryo UI", 11)).pack(side=tk.LEFT, padx=5)

            tk.Label(row1, text="月:", bg="#f0f0f0", font=("Meiryo UI", 12)).pack(side=tk.LEFT, padx=5)
            self.month_var = tk.StringVar(value=str(self.current_month))
            ttk.Spinbox(row1, from_=1, to=12, textvariable=self.month_var,
                         width=10, font=("Meiryo UI", 11)).pack(side=tk.LEFT, padx=5)

            tk.Button(row1, text="カレンダー生成", command=self.create_calendar,
                      bg="#2d5a7b", fg="white", **btn_kw).pack(side=tk.LEFT, padx=10)

            tk.Button(row1, text="◀ 戻る", command=self.undo,
                      bg="#6c757d", fg="white", **undo_redo_kw).pack(side=tk.LEFT, padx=2)
            tk.Button(row1, text="進む ▶", command=self.redo,
                      bg="#6c757d", fg="white", **undo_redo_kw).pack(side=tk.LEFT, padx=2)

            tk.Button(row1, text="クリア", command=self.clear_data,
                      bg="#e76f51", fg="white", **btn_kw).pack(side=tk.LEFT, padx=5)
            tk.Button(row1, text="Excel出力", command=self.export_to_excel,
                      bg="#f4a261", fg="white", **btn_kw).pack(side=tk.LEFT, padx=5)
            tk.Button(row1, text="データ保存", command=self.save_data,
                      bg="#264653", fg="white", **btn_kw).pack(side=tk.LEFT, padx=5)
            tk.Button(row1, text="データ読込", command=self.load_data,
                      bg="#2a9d8f", fg="white", **btn_kw).pack(side=tk.LEFT, padx=5)

            tk.Button(row1, text="👥 メンバー管理", command=self.open_member_management,
                      bg="#8b5cf6", fg="white", **btn_kw).pack(side=tk.LEFT, padx=5)

            self.sound_btn = tk.Button(row1, text="🔊 SE:ON", command=self._toggle_sound,
                                        bg="#4CAF50", fg="white", cursor="hand2", **sound_btn_kw)
            self.sound_btn.pack(side=tk.RIGHT, padx=10)

            self.ai_open_btn = tk.Button(row1, text="🤖 AI支援", command=self._open_ai_window,
                                          bg="#805ad5", fg="white", cursor="hand2", **ai_btn_kw)
            self.ai_open_btn.pack(side=tk.RIGHT, padx=5)

            # --- 2行目: 特別項目ボタン ---
            row2 = tk.Frame(top_frame, bg="#f0f0f0")
            row2.pack(fill=tk.X, pady=2)
            special_btn_kw = {"font": ("Meiryo UI", 10, "bold"), "width": 10, "height": 1}
            tk.Label(row2, text="特別項目:", bg="#f0f0f0", font=("Meiryo UI", 10)).pack(side=tk.LEFT, padx=(5, 2))
            for label, cat in [("🚗 外勤", "外勤"), ("🏛 委員会", "委員会"), ("📚 コース", "コース"), ("🎯 訓練", "訓練")]:
                tk.Button(row2, text=label,
                          command=lambda c=cat: self._open_special_item_window(c),
                          bg="#5b8dd9", fg="white", cursor="hand2", **special_btn_kw).pack(side=tk.LEFT, padx=3)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tab_main = tk.Frame(self.notebook)
        self.notebook.add(self.tab_main, text="📅 メインカレンダー")

        # ✨ メインカレンダー上部: カレンダー同期ボタン
        main_sync_bar = tk.Frame(self.tab_main, bg="#e8f4f8", bd=1, relief=tk.GROOVE)
        main_sync_bar.pack(fill=tk.X, padx=5, pady=(5, 0))
        tk.Button(main_sync_bar,
                  text="🔄 カレンダー同期（メインをサブに合わせる）",
                  command=self._on_main_sync_btn,
                  bg="#2a9d8f", fg="white",
                  font=("Meiryo UI", 10, "bold"),
                  relief=tk.FLAT, padx=15, pady=3, cursor="hand2"
                  ).pack(side=tk.LEFT, padx=8, pady=4)
        tk.Label(main_sync_bar,
                 text="← サブカレンダーの内容でメインを上書き",
                 bg="#e8f4f8", font=("Meiryo UI", 9), fg="#444"
                 ).pack(side=tk.LEFT, padx=4)

        self.paned = tk.PanedWindow(self.tab_main, orient=tk.HORIZONTAL, sashwidth=5, bg="#d9d9d9")
        self.paned.pack(fill=tk.BOTH, expand=True)

        self.left_frame = tk.Frame(self.paned, bg="white")
        self.paned.add(self.left_frame, minsize=800, stretch="always")

        v_scroll = tk.Scrollbar(self.left_frame, orient=tk.VERTICAL)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll = tk.Scrollbar(self.left_frame, orient=tk.HORIZONTAL)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas = tk.Canvas(self.left_frame, bg="white",
                                yscrollcommand=v_scroll.set,
                                xscrollcommand=h_scroll.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scroll.config(command=self.canvas.yview)
        h_scroll.config(command=self.canvas.xview)

        self.canvas.bind("<Double-1>", self._on_double_click)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._on_right_click)
        # canvas 専用スクロール（bind_all は他ウィジェットに干渉するため使わない）
        self._bind_mousewheel(self.canvas, self.canvas)
        
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-y>", lambda e: self.redo())

        self.right_frame = tk.Frame(self.paned, bg="#f9f9f9", width=400)
        self.paned.add(self.right_frame, minsize=350, stretch="never")
        
        stats_header = tk.Frame(self.right_frame, bg="#f9f9f9")
        stats_header.pack(fill=tk.X, pady=5)
        
        tk.Label(stats_header, text="【集計・グラフ】", font=("Meiryo UI", 13, "bold"), 
                bg="#f9f9f9").pack(side=tk.TOP, pady=5)
        
        button_frame = tk.Frame(stats_header, bg="#f9f9f9")
        button_frame.pack(side=tk.TOP, pady=5)
        
        self.btn_person = tk.Button(button_frame, text="人別集計", 
                                     command=lambda: self.switch_stats_mode("person"),
                                     bg="#4a90e2", fg="white", font=("Meiryo UI", 10, "bold"),
                                     width=12, relief=tk.SUNKEN)
        self.btn_person.pack(side=tk.LEFT, padx=5)
        
        self.btn_category = tk.Button(button_frame, text="項目別集計",
                                       command=lambda: self.switch_stats_mode("category"),
                                       bg="#7c8a9e", fg="white", font=("Meiryo UI", 10),
                                       width=12, relief=tk.RAISED)
        self.btn_category.pack(side=tk.LEFT, padx=5)
        
        stats_container = tk.Frame(self.right_frame, bg="white")
        stats_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        stats_vscroll = tk.Scrollbar(stats_container, orient=tk.VERTICAL)
        stats_vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        stats_hscroll = tk.Scrollbar(stats_container, orient=tk.HORIZONTAL)
        stats_hscroll.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.stats_canvas = tk.Canvas(stats_container, bg="white", highlightthickness=0,
                                      yscrollcommand=stats_vscroll.set,
                                      xscrollcommand=stats_hscroll.set)
        self.stats_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        stats_vscroll.config(command=self.stats_canvas.yview)
        stats_hscroll.config(command=self.stats_canvas.xview)
        # 集計エリアにマウスホイールスクロールを追加
        self._bind_mousewheel(stats_container, self.stats_canvas)
        self._bind_mousewheel(self.stats_canvas, self.stats_canvas)
        # ✨ 疲労度ツールチップ用マウスイベント
        self.stats_canvas.bind("<Motion>", self._on_stats_motion)
        self.stats_canvas.bind("<Leave>",  self._hide_hp_tooltip)

        # ✨ サブカレンダータブ（メインの右に追加）
        self.tab_sub = tk.Frame(self.notebook)
        self.notebook.add(self.tab_sub, text="📋 サブカレンダー")

        # サブカレンダー上部: カレンダー同期ボタン
        sub_sync_bar = tk.Frame(self.tab_sub, bg="#f0f8ee", bd=1, relief=tk.GROOVE)
        sub_sync_bar.pack(fill=tk.X, padx=5, pady=(5, 0))
        tk.Button(sub_sync_bar,
                  text="🔄 カレンダー同期（サブをメインに合わせる）",
                  command=self._on_sub_sync_btn,
                  bg="#2d6a4f", fg="white",
                  font=("Meiryo UI", 10, "bold"),
                  relief=tk.FLAT, padx=15, pady=3, cursor="hand2"
                  ).pack(side=tk.LEFT, padx=8, pady=4)
        tk.Label(sub_sync_bar,
                 text="← メインカレンダーの内容でサブを上書き",
                 bg="#f0f8ee", font=("Meiryo UI", 9), fg="#444"
                 ).pack(side=tk.LEFT, padx=4)

        sub_vscroll = tk.Scrollbar(self.tab_sub, orient=tk.VERTICAL)
        sub_vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        sub_hscroll = tk.Scrollbar(self.tab_sub, orient=tk.HORIZONTAL)
        sub_hscroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.sub_canvas = tk.Canvas(self.tab_sub, bg="white",
                                    yscrollcommand=sub_vscroll.set,
                                    xscrollcommand=sub_hscroll.set)
        self.sub_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sub_vscroll.config(command=self.sub_canvas.yview)
        sub_hscroll.config(command=self.sub_canvas.xview)
        self._bind_mousewheel(self.sub_canvas, self.sub_canvas)
        self.sub_canvas.bind("<Button-1>", self._on_sub_canvas_click)
        self.sub_canvas.bind("<Button-3>", self._on_sub_canvas_right_click)

        self.tab_personal = tk.Frame(self.notebook)
        self.notebook.add(self.tab_personal, text="👤 個人別一覧")
        
        personal_vscroll = tk.Scrollbar(self.tab_personal, orient=tk.VERTICAL)
        personal_vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        personal_hscroll = tk.Scrollbar(self.tab_personal, orient=tk.HORIZONTAL)
        personal_hscroll.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.personal_canvas = tk.Canvas(self.tab_personal, bg="white",
                                        yscrollcommand=personal_vscroll.set,
                                        xscrollcommand=personal_hscroll.set)
        self.personal_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        personal_vscroll.config(command=self.personal_canvas.yview)
        personal_hscroll.config(command=self.personal_canvas.xview)
        
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        
        # ✨ AI支援ウィンドウの参照（まだ開いていない）
        self.ai_window = None

    def _bind_mousewheel(self, widget, target_canvas):
        """widget上でマウスホイール操作した時に target_canvas をスクロールさせる"""
        def _on_wheel(event):
            # Windows / macOS
            if event.delta:
                target_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            # Linux (Button-4 / Button-5)
            elif event.num == 4:
                target_canvas.yview_scroll(-3, "units")
            elif event.num == 5:
                target_canvas.yview_scroll(3, "units")
        widget.bind("<MouseWheel>", _on_wheel)
        widget.bind("<Button-4>", _on_wheel)
        widget.bind("<Button-5>", _on_wheel)

    # ───── APIキー管理（OS資格情報ストア使用） ─────

    def _check_keyring(self) -> bool:
        """keyringライブラリが使えるか確認"""
        try:
            import keyring
            # 実際にアクセスできるか簡易テスト
            keyring.get_credential(self._keyring_service, self._keyring_username)
            return True
        except ImportError:
            return False
        except Exception:
            # keyringはインストール済みだがバックエンドエラー等
            return False

    def _load_api_key(self) -> str:
        """保存済みAPIキーを読み込む（OS資格情報ストアから）"""
        if self._keyring_available:
            try:
                import keyring
                key = keyring.get_password(self._keyring_service, self._keyring_username)
                if key:
                    return key
            except Exception:
                pass
        return ""

    def _save_api_key(self, key: str):
        """APIキーをOS資格情報ストアに保存"""
        if self._keyring_available:
            try:
                import keyring
                keyring.set_password(self._keyring_service, self._keyring_username, key.strip())
                return True
            except Exception:
                pass
        return False

    def _delete_api_key(self):
        """保存済みAPIキーを削除"""
        if self._keyring_available:
            try:
                import keyring
                keyring.delete_password(self._keyring_service, self._keyring_username)
            except Exception:
                pass

    def _prompt_api_key(self):
        """APIキー入力ダイアログを表示"""
        parent = self.ai_window if self.ai_window else self.root
        dialog = tk.Toplevel(parent)
        dialog.title("🔑 APIキー設定")
        dialog.geometry("560x310")
        dialog.resizable(False, False)
        dialog.configure(bg="#f5f7fa")
        dialog.transient(parent)
        dialog.grab_set()
        
        tk.Label(dialog, text="🔑 Anthropic APIキーを入力してください",
                 font=("Meiryo UI", 12, "bold"), bg="#f5f7fa").pack(pady=(20, 5))
        
        tk.Label(dialog, text="https://console.anthropic.com/ から取得できます",
                 font=("Meiryo UI", 9), bg="#f5f7fa", fg="#718096").pack(pady=(0, 10))
        
        key_frame = tk.Frame(dialog, bg="#f5f7fa")
        key_frame.pack(fill=tk.X, padx=30, pady=5)
        
        key_var = tk.StringVar(value=self.api_key)
        key_entry = tk.Entry(key_frame, textvariable=key_var, show="•",
                             font=("Consolas", 11), width=48)
        key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 右クリックメニュー（ペースト等）
        entry_menu = tk.Menu(key_entry, tearoff=0)
        entry_menu.add_command(label="切り取り (Ctrl+X)",
                               command=lambda: key_entry.event_generate("<<Cut>>"))
        entry_menu.add_command(label="コピー (Ctrl+C)",
                               command=lambda: key_entry.event_generate("<<Copy>>"))
        entry_menu.add_command(label="貼り付け (Ctrl+V)",
                               command=lambda: key_entry.event_generate("<<Paste>>"))
        entry_menu.add_separator()
        entry_menu.add_command(label="全選択 (Ctrl+A)",
                               command=lambda: (key_entry.select_range(0, tk.END), key_entry.icursor(tk.END)))
        key_entry.bind("<Button-3>", lambda e: entry_menu.tk_popup(e.x_root, e.y_root))
        
        # 表示/非表示の切替
        show_var = tk.BooleanVar(value=False)
        def toggle_show():
            key_entry.config(show="" if show_var.get() else "•")
        tk.Checkbutton(key_frame, text="表示", variable=show_var,
                       command=toggle_show, bg="#f5f7fa",
                       font=("Meiryo UI", 9)).pack(side=tk.RIGHT, padx=5)
        
        # 保存チェック
        save_var = tk.BooleanVar(value=self._keyring_available)
        save_cb = tk.Checkbutton(dialog, text="次回以降のためにキーを保存する（OS資格情報ストア使用）",
                       variable=save_var, bg="#f5f7fa",
                       font=("Meiryo UI", 9))
        save_cb.pack(pady=5)
        
        # keyring未対応の場合の説明
        if self._keyring_available:
            storage_info = "🔒 Windows資格情報マネージャー / macOS Keychain / Linux Secret Service に暗号化保存されます"
            info_color = "#38a169"
        else:
            storage_info = ("⚠️ keyringライブラリ未導入のため保存できません（今回の起動中のみ有効）\n"
                           "　　pip install keyring でインストールすると安全に保存できます")
            info_color = "#e53e3e"
            save_cb.config(state=tk.DISABLED)
            save_var.set(False)
        
        tk.Label(dialog, text=storage_info, font=("Meiryo UI", 8),
                 bg="#f5f7fa", fg=info_color, wraplength=480, justify=tk.LEFT).pack(padx=30, pady=(0, 10))
        
        btn_frame = tk.Frame(dialog, bg="#f5f7fa")
        btn_frame.pack(pady=10)
        
        result = {"ok": False}
        
        def on_ok():
            k = key_var.get().strip()
            if not k:
                messagebox.showwarning("警告", "APIキーを入力してください", parent=dialog)
                return
            self.api_key = k
            if save_var.get():
                saved = self._save_api_key(k)
                if not saved:
                    messagebox.showwarning("警告",
                        "キーの保存に失敗しました。今回の起動中のみ有効です。",
                        parent=dialog)
            result["ok"] = True
            dialog.destroy()
        
        def on_cancel():
            dialog.destroy()
        
        tk.Button(btn_frame, text="✅ 設定", command=on_ok,
                  bg="#48bb78", fg="white", font=("Meiryo UI", 10, "bold"),
                  relief=tk.FLAT, padx=20, pady=6, cursor="hand2").pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="キャンセル", command=on_cancel,
                  bg="#a0aec0", fg="white", font=("Meiryo UI", 10),
                  relief=tk.FLAT, padx=15, pady=6, cursor="hand2").pack(side=tk.LEFT, padx=10)
        
        key_entry.focus_force()
        key_entry.bind("<Return>", lambda e: on_ok())
        
        dialog.wait_window()
        return result["ok"]

    def _open_ai_window(self):
        """AI支援チャットウィンドウを開く（Toplevelで独立ウィンドウ）"""
        # 既に開いている場合は前面に出す
        if self.ai_window is not None:
            try:
                self.ai_window.lift()
                self.ai_window.focus_force()
                if hasattr(self, 'ai_input') and self.ai_input.winfo_exists():
                    self.ai_input.focus_force()
                return
            except tk.TclError:
                self.ai_window = None
        
        # ----- 独立ウィンドウ作成 -----
        win = tk.Toplevel(self.root)
        win.title("🤖 Claude AI 勤務表支援")
        
        # ✨ 画面サイズに応じて自動調整
        try:
            # 画面サイズを取得
            self.root.update_idletasks()
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            
            # AI支援ウィンドウのサイズを計算
            ai_width = 400
            
            # 画面高さの85%を上限に（タスクバー等を考慮）
            max_height = int(screen_height * 0.85)
            # 最小高さ500px（ボタンが見える最小サイズ）
            min_height = 500
            # 理想の高さ700px
            ideal_height = 700
            
            # 画面に収まる高さを計算
            ai_height = min(ideal_height, max_height)
            ai_height = max(ai_height, min_height)
            
            # 画面の右端に配置
            ai_x = screen_width - ai_width - 10  # 右端から10px余白
            ai_y = 30  # 上部に少し余白
            
            # 画面からはみ出さないように調整
            if ai_y + ai_height > screen_height:
                ai_y = max(0, screen_height - ai_height - 40)  # タスクバー分
            
            win.geometry(f"{ai_width}x{ai_height}+{ai_x}+{ai_y}")
        except:
            # エラー時はデフォルトサイズ
            win.geometry("400x600")
        
        # ✨ 最小サイズを設定（ボタンが見える最小サイズ）
        win.minsize(350, 500)
        win.configure(bg="#f5f7fa")
        self.ai_window = win
        win.protocol("WM_DELETE_WINDOW", self._close_ai_window)
        
        # --- ヘッダー ---
        header = tk.Frame(win, bg="#4a5568", height=50)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)
        tk.Label(header, text="🤖 Claude AI 勤務表支援",
                 font=("Meiryo UI", 14, "bold"),
                 bg="#4a5568", fg="white").pack(side=tk.LEFT, padx=15, pady=10)
        tk.Button(header, text="🔄 リセット",
                  command=self._reset_ai_conversation,
                  bg="#e53e3e", fg="white", font=("Meiryo UI", 9),
                  relief=tk.FLAT, padx=10, pady=3).pack(side=tk.RIGHT, padx=15)
        tk.Button(header, text="🔑 APIキー",
                  command=self._prompt_api_key,
                  bg="#718096", fg="white", font=("Meiryo UI", 9),
                  relief=tk.FLAT, padx=10, pady=3).pack(side=tk.RIGHT, padx=0)
        
        # --- メインコンテナ ---
        main_container = tk.Frame(win, bg="#f5f7fa")
        main_container.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        
        # --- チャット履歴 ---
        chat_frame = tk.Frame(main_container, bg="white", relief=tk.RIDGE, bd=2)
        chat_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        chat_scroll = tk.Scrollbar(chat_frame)
        chat_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.ai_chat_display = tk.Text(chat_frame, wrap=tk.WORD,
                                       font=("Meiryo UI", 10),
                                       bg="white", fg="#2d3748",
                                       yscrollcommand=chat_scroll.set,
                                       state=tk.DISABLED, padx=12, pady=12)
        self.ai_chat_display.pack(fill=tk.BOTH, expand=True)
        chat_scroll.config(command=self.ai_chat_display.yview)
        
        self.ai_chat_display.tag_config("user", foreground="#2b6cb0", font=("Meiryo UI", 10, "bold"))
        self.ai_chat_display.tag_config("assistant", foreground="#38a169", font=("Meiryo UI", 10, "bold"))
        self.ai_chat_display.tag_config("system", foreground="#718096", font=("Meiryo UI", 9, "italic"))
        self.ai_chat_display.tag_config("proposal", background="#fef5e7", relief=tk.RAISED, borderwidth=1)
        
        # --- ✨ 自動作成・改善モードボタン ---
        mode_frame = tk.Frame(main_container, bg="#f5f7fa")
        mode_frame.pack(fill=tk.X, pady=(0, 6))
        tk.Button(mode_frame, text="🪄 自動作成（3段階）",
                  command=self._start_auto_generate,
                  bg="#d69e2e", fg="white", font=("Meiryo UI", 9, "bold"),
                  relief=tk.FLAT, padx=10, pady=4, cursor="hand2"
                  ).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(mode_frame, text="📈 改善提案（現状を分析）",
                  command=self._start_improvement,
                  bg="#38a169", fg="white", font=("Meiryo UI", 9, "bold"),
                  relief=tk.FLAT, padx=10, pady=4, cursor="hand2"
                  ).pack(side=tk.LEFT, padx=4)

        # --- 例文ボタン ---
        examples_frame = tk.Frame(main_container, bg="#f5f7fa")
        examples_frame.pack(fill=tk.X, pady=(0, 6))
        tk.Label(examples_frame, text="💡 例:", bg="#f5f7fa",
                 font=("Meiryo UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        for ex in ["休みを均等に配分して", "桜と小の当直を被らないように", "金のER勤務を増やして"]:
            tk.Button(examples_frame, text=ex,
                      command=lambda e=ex: self._insert_example(e),
                      bg="#e2e8f0", fg="#2d3748", font=("Meiryo UI", 8),
                      relief=tk.FLAT, padx=6, pady=2, cursor="hand2"
                      ).pack(side=tk.LEFT, padx=2)
        
        # --- 入力エリア ---
        input_frame = tk.Frame(main_container, bg="white", relief=tk.RIDGE, bd=2)
        input_frame.pack(fill=tk.X)
        
        self.ai_input = tk.Text(input_frame, height=3, wrap=tk.WORD,
                                font=("Meiryo UI", 11), bg="#fffff8", fg="#2d3748",
                                relief=tk.FLAT, padx=10, pady=8,
                                insertbackground="black", insertwidth=2)
        self.ai_input.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0), pady=4)
        self.ai_input.bind("<Control-Return>", lambda e: (self._send_ai_message(), "break")[-1])
        self.ai_input.bind("<Return>", self._on_ai_enter_key)
        
        btn_frame = tk.Frame(input_frame, bg="white")
        btn_frame.pack(side=tk.RIGHT, padx=8, pady=8)
        self.ai_send_btn = tk.Button(btn_frame, text="📤 送信\n(Enter)",
                                     command=self._send_ai_message,
                                     bg="#4299e1", fg="white",
                                     font=("Meiryo UI", 10, "bold"),
                                     relief=tk.FLAT, padx=12, pady=8, cursor="hand2")
        self.ai_send_btn.pack(fill=tk.BOTH, expand=True)
        
        # --- プレビュー/適用ボタン（初期非表示） ---
        self.ai_action_frame = tk.Frame(main_container, bg="#f5f7fa")
        
        self.ai_preview_btn = tk.Button(self.ai_action_frame, text="👁️ プレビュー",
                                        command=self._preview_ai_proposal,
                                        bg="#805ad5", fg="white",
                                        font=("Meiryo UI", 10, "bold"),
                                        relief=tk.FLAT, padx=15, pady=8, cursor="hand2")
        self.ai_preview_btn.pack(side=tk.LEFT, padx=4)
        
        self.ai_apply_btn = tk.Button(self.ai_action_frame, text="✅ 適用",
                                      command=self._apply_ai_proposal,
                                      bg="#48bb78", fg="white",
                                      font=("Meiryo UI", 10, "bold"),
                                      relief=tk.FLAT, padx=15, pady=8, cursor="hand2")
        self.ai_apply_btn.pack(side=tk.LEFT, padx=4)
        
        # ✨ 削除ボタンを追加
        self.ai_delete_btn = tk.Button(self.ai_action_frame, text="🗑️ 削除",
                                       command=self._delete_ai_proposal,
                                       bg="#e53e3e", fg="white",
                                       font=("Meiryo UI", 10, "bold"),
                                       relief=tk.FLAT, padx=15, pady=8, cursor="hand2")
        self.ai_delete_btn.pack(side=tk.LEFT, padx=4)
        
        self.ai_cancel_preview_btn = tk.Button(self.ai_action_frame, text="❌ 解除",
                                               command=self._cancel_preview,
                                               bg="#f56565", fg="white",
                                               font=("Meiryo UI", 10, "bold"),
                                               relief=tk.FLAT, padx=15, pady=8, cursor="hand2")
        
        # --- ローディング ---
        self.ai_loading_label = tk.Label(main_container, text="",
                                         bg="#f5f7fa", fg="#718096",
                                         font=("Meiryo UI", 10))
        
        # --- 初期メッセージ ---
        self._add_chat_message("system",
            "AIアシスタントが勤務表作成をお手伝いします。\n"
            "例：「休みを均等に配分して」「桜さんと小さんの当直を被らないように」など")
        
        if self.api_key:
            self._add_chat_message("system", "✅ APIキー設定済み — メッセージを送信できます。")
        else:
            if self._keyring_available:
                self._add_chat_message("system", "⚠️ APIキーが未設定です。右上の「🔑 APIキー」ボタンから設定してください。\n🔒 キーはOSの資格情報ストアに暗号化保存されます。")
            else:
                self._add_chat_message("system", "⚠️ APIキーが未設定です。右上の「🔑 APIキー」ボタンから設定してください。\n💡 pip install keyring で安全な保存が可能になります。")
        
        # フォーカスを入力欄に
        win.after(150, lambda: self.ai_input.focus_force())

    def _close_ai_window(self):
        """AI支援ウィンドウを閉じる"""
        if self.ai_window is not None:
            try:
                if self.ai_preview_active:
                    self._cancel_preview()
                self.ai_window.destroy()
            except tk.TclError:
                pass
            self.ai_window = None

    def _on_ai_enter_key(self, event):
        """Enter で送信、Shift+Enter で改行"""
        if event.state & 0x1:  # Shift が押されている
            return  # デフォルト動作（改行挿入）
        self._send_ai_message()
        return "break"

    def _insert_example(self, text):
        """例文を入力欄に挿入"""
        if not hasattr(self, 'ai_input') or not self.ai_input.winfo_exists():
            return
        self.ai_input.delete("1.0", tk.END)
        self.ai_input.insert("1.0", text)
        self.ai_input.focus_force()

    def _reset_ai_conversation(self):
        """AI会話をリセット"""
        if messagebox.askyesno("確認", "会話履歴をリセットしますか？"):
            self.ai_conversation_history.clear()
            self.ai_latest_proposal = None
            if hasattr(self, 'ai_chat_display') and self.ai_chat_display.winfo_exists():
                self.ai_chat_display.config(state=tk.NORMAL)
                self.ai_chat_display.delete("1.0", tk.END)
                self.ai_chat_display.config(state=tk.DISABLED)
                self._add_chat_message("system", "会話履歴がリセットされました。")
            self._hide_action_buttons()
            if self.ai_preview_active:
                self._cancel_preview()

    def _add_chat_message(self, role, content):
        """チャット履歴にメッセージを追加"""
        if not hasattr(self, 'ai_chat_display') or not self.ai_chat_display.winfo_exists():
            return
        self.ai_chat_display.config(state=tk.NORMAL)
        
        if role == "user":
            self.ai_chat_display.insert(tk.END, "あなた:\n", "user")
            self.ai_chat_display.insert(tk.END, content + "\n\n", "")
        elif role == "assistant":
            self.ai_chat_display.insert(tk.END, "Claude:\n", "assistant")
            self.ai_chat_display.insert(tk.END, content + "\n\n", "")
        elif role == "system":
            self.ai_chat_display.insert(tk.END, "💡 " + content + "\n\n", "system")
        elif role == "proposal":
            self.ai_chat_display.insert(tk.END, "📋 提案内容:\n", "assistant")
            self.ai_chat_display.insert(tk.END, content + "\n\n", "proposal")
        
        self.ai_chat_display.see(tk.END)
        self.ai_chat_display.config(state=tk.DISABLED)

    def _send_ai_message(self):
        """ユーザーメッセージを送信してAIレスポンスを取得"""
        if not hasattr(self, 'ai_input') or not self.ai_input.winfo_exists():
            return
        
        # APIキーチェック
        if not self.api_key:
            self._add_chat_message("system", "⚠️ APIキーが設定されていません。「🔑 APIキー」ボタンから設定してください。")
            ok = self._prompt_api_key()
            if not ok or not self.api_key:
                return
            self._add_chat_message("system", "✅ APIキーが設定されました。")
        
        user_message = self.ai_input.get("1.0", tk.END).strip()
        if not user_message:
            return
        
        # 入力欄をクリア
        self.ai_input.delete("1.0", tk.END)
        
        # ユーザーメッセージを表示
        self._add_chat_message("user", user_message)

        # ✨ 新しい依頼なので自動修正リトライ回数をリセット
        self._ai_retry_count = 0

        # 送信ボタンを無効化してローディング表示
        try:
            self.ai_send_btn.config(state=tk.DISABLED)
            self.ai_loading_label.config(text="🔄 Claudeが考えています...")
            self.ai_loading_label.pack(pady=10)
        except tk.TclError:
            pass
        
        # 別スレッドでAPI呼び出し
        threading.Thread(target=self._call_claude_api, args=(user_message,), daemon=True).start()

    def _build_system_prompt(self, extra_instruction: str = "") -> str:
        """カレンダー状態・メンバー情報・勤務分析を統合したシステムプロンプトを構築"""
        calendar_state = self._get_calendar_state()
        members_info = self._format_members_for_ai()
        team_rules_text = calendar_state['team_rules'] if calendar_state['team_rules'] else "特になし"
        analysis = self._analyze_schedule()
        analysis_text = self._format_analysis_text(analysis)
        max_col = self.BLOCK_W - 1

        prompt = f"""あなたは医療機関の勤務表作成支援AIです。

【絶対に守るべきルール（ハードルール）】
1. ロックされたセルは絶対に変更しない
2. 同じ人を同じ日に複数の勤務に割り当てない（当直と同日の明けは除く）
3. 「当直」に入った人は、翌日は必ず「明け」にする（他の勤務は不可）
4. 「明け」は前日に「当直」だった人だけに割り当てる
5. personはアクティブメンバーの表示名から選ぶ
6. 勤務回数は全員でできるだけ均等にする（下記の集計を必ず参照）

【全体の決まり事（チームルール）】
{team_rules_text}

【アクティブメンバー情報（個人リクエストは必ず尊重すること）】
{members_info}

【現在の勤務状況の分析（Pythonで機械集計した正確な値）】
{analysis_text}

現在の状況:
- 年月: {self.current_year}年{self.current_month}月
- 月の日数: {calendar.monthrange(self.current_year, self.current_month)[1]}日
- 勤務種別と列数: ER, A, B, 当直, 明け, 外勤, 出張, 休み（各{self.BLOCK_W}列、col=0〜{max_col}）

現在の勤務表データ:
{json.dumps(calendar_state['current_assignments'], ensure_ascii=False)}

ロックされているセル（変更不可）:
{json.dumps(calendar_state['locked_cells'], ensure_ascii=False)}

ユーザーの要望に基づいて勤務表の提案を行ってください。
偏りの是正には上記の分析データ（勤務回数集計・偏り指標）を必ず根拠として使ってください。

**重要**: 提案する場合は、必ず以下のJSON形式で出力してください:
- ```jsonブロックは不要です
- 説明は1-2文で簡潔に
- assignmentsには必要な変更のみを含める（全日程を含める必要はありません）

出力形式:
{{
  "explanation": "簡潔な説明（1-2文）",
  "assignments": [
    {{"day": 1, "label": "ER", "col": 0, "person": "桜"}},
    {{"day": 2, "label": "A", "col": 1, "person": "小"}}
  ]
}}

注意事項:
- 各勤務種別の列（col）は0〜{max_col}
- 日付（day）は1から月末日まで
- 提案がない場合はassignmentsを空配列にする
- **全日程を提案する場合は、回答が切れないよう注意してJSONを完結させてください**"""
        if extra_instruction:
            prompt += f"\n\n【今回の追加指示】\n{extra_instruction}"
        return prompt

    def _api_request(self, system_prompt: str, messages: List[Dict]) -> str:
        """Claude APIを呼び出してテキスト応答を返す（呼び出し元スレッドでブロック）"""
        import urllib.request

        data = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 16000,
            "system": system_prompt,
            "messages": messages
        }
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(data).encode('utf-8'),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01"
            }
        )
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))

        assistant_message = ""
        for content_block in result.get("content", []):
            if content_block.get("type") == "text":
                assistant_message += content_block.get("text", "")
        return assistant_message

    def _call_claude_api(self, user_message):
        """Claude APIを呼び出し（別スレッドで実行）"""
        import urllib.error
        try:
            system_prompt = self._build_system_prompt()

            # 会話履歴に追加
            self.ai_conversation_history.append({
                "role": "user",
                "content": user_message
            })

            assistant_message = self._api_request(system_prompt, self.ai_conversation_history)

            # 会話履歴に追加
            self.ai_conversation_history.append({
                "role": "assistant",
                "content": assistant_message
            })

            # メインスレッドでUI更新
            self.root.after(0, self._handle_ai_response, assistant_message)

        except urllib.error.HTTPError as e:
            if e.code == 401:
                error_msg = "❌ APIキーが無効です。「🔑 APIキー」ボタンから正しいキーを設定してください。"
                self.api_key = ""  # 無効なキーをクリア
                self._delete_api_key()  # 保存済みキーも削除
            elif e.code == 429:
                error_msg = "⏳ レート制限に達しました。少し待ってから再度お試しください。"
            elif e.code == 400:
                error_msg = "❌ リクエストエラー（400）。会話をリセットしてお試しください。"
            else:
                error_msg = f"❌ APIエラー（{e.code}）: {str(e)}"
            # 失敗した場合は会話履歴から最後のユーザーメッセージを除去
            if self.ai_conversation_history and self.ai_conversation_history[-1]["role"] == "user":
                self.ai_conversation_history.pop()
            self.root.after(0, self._handle_ai_error, error_msg)
        except Exception as e:
            error_msg = f"❌ 通信エラー: {str(e)}"
            if self.ai_conversation_history and self.ai_conversation_history[-1]["role"] == "user":
                self.ai_conversation_history.pop()
            self.root.after(0, self._handle_ai_error, error_msg)

    def _handle_ai_response(self, response_text):
        """AIレスポンスを処理（メインスレッドで実行）"""
        # ローディングを非表示
        if hasattr(self, 'ai_loading_label') and self.ai_loading_label.winfo_exists():
            self.ai_loading_label.pack_forget()
        if hasattr(self, 'ai_send_btn') and self.ai_send_btn.winfo_exists():
            self.ai_send_btn.config(state=tk.NORMAL)
        
        # JSONを抽出して解析
        proposal = self._extract_json_from_response(response_text)
        
        if proposal and proposal.get("assignments"):
            # 提案がある場合
            explanation = proposal.get("explanation", "")

            # 応答が途中で切れていた可能性をチェック
            if len(response_text) > 15000 or response_text.endswith("...") or not response_text.rstrip().endswith("}"):
                warning_msg = "\n\n⚠️ 注意: AIの応答が非常に長いため、一部のデータが省略されている可能性があります。"
                self._add_chat_message("assistant", explanation + warning_msg)
            else:
                self._add_chat_message("assistant", explanation)

            # ✨ 提案をPython側で検証し、違反があれば自動で修正を依頼（1回まで）
            violations = self._validate_proposal(proposal)
            if violations and getattr(self, "_ai_retry_count", 0) < 1:
                self._ai_retry_count = getattr(self, "_ai_retry_count", 0) + 1
                self._add_chat_message("system",
                    f"⚠️ 提案に{len(violations)}件のルール違反を検出。自動修正を依頼しています...\n"
                    + "\n".join(f"  ・{v}" for v in violations[:8]))
                fix_request = ("先ほどの提案に以下のルール違反があります。"
                               "違反を解消した提案を同じJSON形式で再出力してください:\n- "
                               + "\n- ".join(violations[:20]))
                try:
                    self.ai_send_btn.config(state=tk.DISABLED)
                    self.ai_loading_label.config(text="🔄 違反を自動修正中...")
                    self.ai_loading_label.pack(pady=10)
                except tk.TclError:
                    pass
                threading.Thread(target=self._call_claude_api, args=(fix_request,), daemon=True).start()
                return

            # 提案詳細を表示
            assignment_summary = f"📋 {len(proposal['assignments'])}件の割り当てを提案します"
            if violations:
                assignment_summary += (f"\n⚠️ {len(violations)}件の問題が残っています:\n"
                                       + "\n".join(f"  ・{v}" for v in violations[:8]))
            else:
                assignment_summary += "\n✅ ルール検証: 問題なし"
            self._add_chat_message("proposal", assignment_summary)

            # 提案を保存
            self.ai_latest_proposal = proposal
            self._show_action_buttons()
        else:
            # 提案がない場合は通常の応答
            self._add_chat_message("assistant", response_text)
            self._hide_action_buttons()

    def _handle_ai_error(self, error_msg):
        """エラーハンドリング（メインスレッドで実行）"""
        if hasattr(self, 'ai_loading_label') and self.ai_loading_label.winfo_exists():
            self.ai_loading_label.pack_forget()
        if hasattr(self, 'ai_send_btn') and self.ai_send_btn.winfo_exists():
            self.ai_send_btn.config(state=tk.NORMAL)
        self._add_chat_message("system", "❌ " + error_msg)

    def _extract_json_from_response(self, text):
        """レスポンステキストからJSON提案を抽出"""
        try:
            # ```json ブロックを探す
            if "```json" in text:
                start = text.find("```json") + 7
                end = text.find("```", start)
                if end == -1:  # 閉じ```がない場合は文末まで
                    json_str = text[start:].strip()
                else:
                    json_str = text[start:end].strip()
            elif "```" in text:
                start = text.find("```") + 3
                end = text.find("```", start)
                if end == -1:
                    json_str = text[start:].strip()
                else:
                    json_str = text[start:end].strip()
            else:
                # JSONっぽい部分を探す（改良版）
                start = text.find("{")
                if start == -1:
                    return None
                
                # 対応する閉じ括弧を探す（ネストに対応）
                brace_count = 0
                end = start
                for i in range(start, len(text)):
                    if text[i] == "{":
                        brace_count += 1
                    elif text[i] == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            end = i + 1
                            break
                
                if end <= start:
                    # 閉じ括弧が見つからない場合は文末まで
                    json_str = text[start:].strip()
                else:
                    json_str = text[start:end]
            
            # ✨ 不完全なJSONを補完する処理 ✨
            json_str = self._complete_incomplete_json(json_str)
            
            # JSON解析を試行
            parsed = json.loads(json_str)
            
            # 必須フィールドの確認
            if not isinstance(parsed, dict):
                return None
            
            # assignmentsフィールドが存在し、リストであることを確認
            if "assignments" in parsed and isinstance(parsed.get("assignments"), list):
                return parsed
            
            return None
            
        except json.JSONDecodeError as e:
            print(f"JSON解析エラー: {e}")
            print(f"解析を試みた文字列の先頭: {text[:200]}...")
            return None
        except Exception as e:
            print(f"予期しないエラー: {e}")
            return None
    
    def _complete_incomplete_json(self, json_str):
        """不完全なJSONを補完する"""
        # 末尾の不要なカンマを削除
        json_str = json_str.rstrip()
        
        # 末尾がカンマで終わっている場合は削除
        if json_str.endswith(','):
            json_str = json_str[:-1].rstrip()
        
        # 開き括弧と閉じ括弧の数をカウント
        open_braces = json_str.count('{')
        close_braces = json_str.count('}')
        open_brackets = json_str.count('[')
        close_brackets = json_str.count(']')
        
        # 不足している閉じ括弧を追加
        missing_brackets = open_brackets - close_brackets
        missing_braces = open_braces - close_braces
        
        # assignmentsの配列が閉じられていない場合
        if missing_brackets > 0:
            json_str += '\n' + ']' * missing_brackets
        
        # オブジェクトが閉じられていない場合
        if missing_braces > 0:
            json_str += '\n' + '}' * missing_braces
        
        return json_str

    def _get_calendar_state(self):
        """現在のカレンダー状態を取得"""
        # 人員リストを取得
        people = set()
        for value in self.cell_data.values():
            if value and value.strip():
                people.add(value)
        
        # 現在の割り当てを取得
        assignments = []
        for (day, label_idx, col), person in self.cell_data.items():
            if person and person.strip() and 1 <= label_idx <= 8:
                label = self.LABELS[label_idx]
                assignments.append({
                    "day": day,
                    "label": label,
                    "col": col,
                    "person": person
                })
        
        # ロックされたセル
        locked = []
        for (day, label_idx, col) in self.locked_cells:
            if 1 <= label_idx <= 8:
                label = self.LABELS[label_idx]
                person = self.cell_data.get((day, label_idx, col), "")
                locked.append({
                    "day": day,
                    "label": label,
                    "col": col,
                    "person": person
                })
        
        # ✨ アクティブメンバー情報を取得
        active_members = []
        for member in self.members_data:
            if member["active"]:
                active_members.append({
                    "name": member["name"],
                    "display_name": member["display_name"],
                    "skill_level": member["skill_level"],
                    "personal_request": member["personal_request"]
                })
        
        return {
            "people": sorted(people),
            "current_assignments": assignments,
            "locked_cells": locked,
            "team_rules": self.team_rules,  # ✨ 全体の決まり事
            "active_members": active_members  # ✨ アクティブメンバー情報
        }

    # ───── ✨ 勤務表分析エンジン（C案: Python側で機械集計） ─────

    WORK_LABELS = ("ER", "A", "B", "当直", "明け", "外勤", "出張", "休み")
    DUTY_LABELS = ("ER", "A", "B", "当直", "外勤")  # 負荷としてカウントする実勤務

    def _collect_day_label_map(self, extra_assignments: Optional[List[Dict]] = None):
        """cell_data（＋追加提案）から {person: {day: set(labels)}} を作る"""
        person_days: Dict[str, Dict[int, set]] = defaultdict(lambda: defaultdict(set))
        for (day, label_idx, col), person in self.cell_data.items():
            if person and person.strip() and 1 <= label_idx <= 8:
                person_days[person][day].add(self.LABELS[label_idx])
        if extra_assignments:
            for a in extra_assignments:
                if a.get("person"):
                    person_days[a["person"]][a["day"]].add(a["label"])
        return person_days

    def _analyze_schedule(self) -> Dict:
        """現在の勤務表を機械集計して偏り・違反を抽出"""
        last_day = calendar.monthrange(self.current_year, self.current_month)[1]
        active_names = [m["display_name"] for m in self.members_data if m.get("active", True)]

        counts: Dict[str, Counter] = {name: Counter() for name in active_names}
        weekend_counts: Counter = Counter()
        person_days = self._collect_day_label_map()

        for person, days in person_days.items():
            if person not in counts:
                counts[person] = Counter()
            for day, labels in days.items():
                for label in labels:
                    counts[person][label] += 1
                if any(l in self.DUTY_LABELS for l in labels):
                    try:
                        if date(self.current_year, self.current_month, day).weekday() >= 5:
                            weekend_counts[person] += 1
                    except ValueError:
                        pass

        # 連続勤務日数の最大値
        max_streaks: Dict[str, int] = {}
        for person, days in person_days.items():
            streak = best = 0
            for d in range(1, last_day + 1):
                if any(l in self.DUTY_LABELS for l in days.get(d, ())):
                    streak += 1
                    best = max(best, streak)
                else:
                    streak = 0
            max_streaks[person] = best

        violations = self._find_rule_violations(person_days, last_day, active_names)

        return {
            "counts": counts,
            "weekend_counts": weekend_counts,
            "max_streaks": max_streaks,
            "violations": violations,
            "last_day": last_day,
        }

    def _find_rule_violations(self, person_days, last_day, active_names) -> List[str]:
        """ハードルール違反を列挙"""
        violations = []
        for person, days in sorted(person_days.items()):
            for day in sorted(days):
                labels = days[day]
                # 同日複数勤務（当直+明け以外）
                dup = [l for l in labels if l in self.WORK_LABELS]
                if len(dup) > 1 and set(dup) != {"当直", "明け"}:
                    violations.append(f"{day}日: {person} が同日に複数勤務（{'/'.join(sorted(dup))}）")
                # 当直翌日は明け
                if "当直" in labels and day < last_day:
                    next_labels = days.get(day + 1, set())
                    others = [l for l in next_labels if l in self.DUTY_LABELS]
                    if others:
                        violations.append(f"{day}日: {person} が当直なのに翌{day+1}日に勤務（{'/'.join(others)}）が入っている")
                # 明けの前日は当直
                if "明け" in labels and day > 1:
                    if "当直" not in days.get(day - 1, set()):
                        violations.append(f"{day}日: {person} が明けだが前日{day-1}日に当直がない")
            if person not in active_names:
                violations.append(f"{person} はアクティブメンバーに存在しない")
        return violations

    def _format_analysis_text(self, analysis: Dict) -> str:
        """分析結果をAIプロンプト用テキストに整形"""
        lines = ["■ メンバー別勤務回数（種別ごと）:"]
        all_totals = []
        for person in sorted(analysis["counts"]):
            c = analysis["counts"][person]
            total = sum(c[l] for l in self.DUTY_LABELS)
            all_totals.append((person, total))
            detail = ", ".join(f"{l}:{c[l]}" for l in self.WORK_LABELS if c[l])
            wk = analysis["weekend_counts"].get(person, 0)
            streak = analysis["max_streaks"].get(person, 0)
            lines.append(f"  {person}: 実勤務計{total}回 [{detail or 'なし'}] 土日勤務{wk}回 最大連続{streak}日")

        if all_totals:
            totals = [t for _, t in all_totals]
            mx, mn = max(totals), min(totals)
            lines.append(f"■ 偏り指標: 実勤務回数 最多{mx}回/最少{mn}回（差{mx-mn}回）")
            if mx - mn >= 2:
                most = [p for p, t in all_totals if t == mx]
                least = [p for p, t in all_totals if t == mn]
                lines.append(f"  → 多い: {', '.join(most)} / 少ない: {', '.join(least)} — この差を縮める割り当てを優先すること")

        if analysis["violations"]:
            lines.append("■ 現在のルール違反（修正が必要）:")
            for v in analysis["violations"][:20]:
                lines.append(f"  ⚠ {v}")
        else:
            lines.append("■ 現在ルール違反はありません")
        return "\n".join(lines)

    def _validate_proposal(self, proposal: Dict) -> List[str]:
        """AI提案を現在の勤務表にマージした場合のハードルール違反を検出"""
        problems = []
        last_day = calendar.monthrange(self.current_year, self.current_month)[1]
        active_names = {m["display_name"] for m in self.members_data if m.get("active", True)}
        max_col = self.BLOCK_W - 1

        assignments = proposal.get("assignments", [])
        valid_assignments = []
        for a in assignments:
            day, label, col, person = a.get("day"), a.get("label"), a.get("col"), a.get("person")
            if not isinstance(day, int) or not (1 <= day <= last_day):
                problems.append(f"無効な日付: {a}")
                continue
            if label not in self.WORK_LABELS:
                problems.append(f"無効な勤務種別: {a}")
                continue
            if not isinstance(col, int) or not (0 <= col <= max_col):
                problems.append(f"列colは0〜{max_col}の範囲にすること: {a}")
                continue
            if person not in active_names:
                problems.append(f"{person} はアクティブメンバーではない（{day}日 {label}）")
                continue
            try:
                label_idx = self.LABELS.index(label)
                if (day, label_idx, col) in self.locked_cells:
                    problems.append(f"{day}日 {label} col{col} はロック済みセル（変更不可）")
                    continue
            except ValueError:
                continue
            valid_assignments.append(a)

        # 提案をマージした状態でルールチェック
        # （提案に含まれる人の既存セルはクリアされる仕様に合わせる）
        proposed_people = {a["person"] for a in valid_assignments}
        person_days: Dict[str, Dict[int, set]] = defaultdict(lambda: defaultdict(set))
        for (day, label_idx, col), person in self.cell_data.items():
            if not person or not person.strip() or not (1 <= label_idx <= 8):
                continue
            if person in proposed_people and (day, label_idx, col) not in self.locked_cells:
                continue  # 上書きされるセル
            person_days[person][day].add(self.LABELS[label_idx])
        for a in valid_assignments:
            person_days[a["person"]][a["day"]].add(a["label"])

        problems.extend(self._find_rule_violations(person_days, last_day, sorted(active_names)))
        return problems

    # ───── ✨ 段階的自動作成（B案）＆改善モード ─────

    AUTO_GEN_STAGES = [
        ("当直・明け", "今回は「当直」と「明け」だけを月全体に割り当ててください。"
         "当直の翌日は必ず同じ人を明けにすること。当直回数は全員で均等にし、"
         "土日の当直も特定の人に偏らないようにすること。他の勤務種別は提案しないこと。"),
        ("ER・A・B", "当直・明けは確定済みです（変更しないこと）。今回は「ER」「A」「B」だけを"
         "月全体に割り当ててください。当直・明けの日と重複させないこと。"
         "各人の勤務回数が均等になるようにすること。他の勤務種別は提案しないこと。"),
        ("外勤・出張・休み", "当直・明け・ER・A・Bは確定済みです（変更しないこと）。"
         "今回は「外勤」「出張」「休み」を割り当ててください。"
         "個人リクエストの休み希望を最優先で反映し、休み日数も均等にすること。"),
    ]

    def _start_auto_generate(self):
        """段階的自動作成を開始（当直→ER/A/B→外勤・休みの3段階）"""
        if not self.api_key:
            ok = self._prompt_api_key()
            if not ok or not self.api_key:
                return
        if not messagebox.askyesno("確認",
                "勤務表を3段階（当直・明け → ER/A/B → 外勤・出張・休み）で自動作成します。\n"
                "API呼び出しが3回行われます。よろしいですか？",
                parent=self.ai_window or self.root):
            return
        self._add_chat_message("system", "🪄 段階的自動作成を開始します（3段階）...")
        try:
            self.ai_send_btn.config(state=tk.DISABLED)
            self.ai_loading_label.config(text="🔄 段階1/3: 当直・明けを作成中...")
            self.ai_loading_label.pack(pady=10)
        except tk.TclError:
            pass
        threading.Thread(target=self._run_auto_generate, daemon=True).start()

    def _run_auto_generate(self):
        """3段階のAI呼び出しで勤務表全体を生成（別スレッド）"""
        import urllib.error
        combined: List[Dict] = []
        try:
            for i, (stage_name, stage_inst) in enumerate(self.AUTO_GEN_STAGES, 1):
                self.root.after(0, self._set_loading_text,
                                f"🔄 段階{i}/3: {stage_name}を作成中...")
                # ここまでの確定分をプロンプトに含める
                extra = stage_inst
                if combined:
                    extra += ("\n\n【ここまでの段階で確定した割り当て（変更禁止・重複禁止）】\n"
                              + json.dumps(combined, ensure_ascii=False))
                system_prompt = self._build_system_prompt(extra_instruction=extra)
                response = self._api_request(system_prompt, [
                    {"role": "user", "content": f"{stage_name}の割り当てをJSON形式で提案してください。"}
                ])
                proposal = self._extract_json_from_response(response)
                if not proposal or not proposal.get("assignments"):
                    self.root.after(0, self._handle_ai_error,
                                    f"段階{i}（{stage_name}）で有効な提案を取得できませんでした。")
                    return
                combined.extend(proposal["assignments"])
                self.root.after(0, self._add_chat_message, "system",
                                f"✅ 段階{i}/3 完了: {stage_name} {len(proposal['assignments'])}件")

            final = {"explanation": "3段階の自動作成による勤務表提案です。", "assignments": combined}
            self.root.after(0, self._finish_auto_generate, final)
        except urllib.error.HTTPError as e:
            self.root.after(0, self._handle_ai_error, f"APIエラー（{e.code}）: {str(e)}")
        except Exception as e:
            self.root.after(0, self._handle_ai_error, f"通信エラー: {str(e)}")

    def _set_loading_text(self, text):
        try:
            if self.ai_loading_label.winfo_exists():
                self.ai_loading_label.config(text=text)
        except tk.TclError:
            pass

    def _finish_auto_generate(self, proposal):
        """自動作成完了: 検証して提案として提示（メインスレッド）"""
        try:
            self.ai_loading_label.pack_forget()
            self.ai_send_btn.config(state=tk.NORMAL)
        except tk.TclError:
            pass
        violations = self._validate_proposal(proposal)
        self.ai_latest_proposal = proposal
        msg = f"📋 自動作成完了: {len(proposal['assignments'])}件の割り当てを提案します"
        if violations:
            msg += f"\n⚠️ 検証で{len(violations)}件の問題を検出:\n" + "\n".join(f"  ・{v}" for v in violations[:10])
            msg += "\nプレビューで確認のうえ、必要に応じて「この違反を修正して」と依頼してください。"
        else:
            msg += "\n✅ ルール検証: 問題なし"
        self._add_chat_message("proposal", msg)
        self._show_action_buttons()

    def _start_improvement(self):
        """改善モード: 現在の勤務表を分析し、AIに改善案を依頼"""
        if not self.cell_data:
            self._add_chat_message("system", "⚠️ 勤務表が空です。まず勤務表をある程度作成してください。")
            return
        if not self.api_key:
            ok = self._prompt_api_key()
            if not ok or not self.api_key:
                return
        analysis = self._analyze_schedule()
        analysis_text = self._format_analysis_text(analysis)
        self._add_chat_message("system", "📈 現在の勤務表を分析しました:\n" + analysis_text)
        request = (
            "現在の勤務表を分析した結果が上記システム情報にあります。"
            "次の優先順位で改善案を提案してください:\n"
            "1. ルール違反の修正（最優先）\n"
            "2. 勤務回数の偏りの是正（多い人から少ない人へ振り替え）\n"
            "3. 土日勤務・連続勤務の偏り是正\n"
            "4. 個人リクエストの反映漏れの修正\n"
            "変更は必要最小限にし、既に問題ない割り当ては動かさないでください。"
        )
        self._add_chat_message("user", "（改善モード）勤務表の改善案を提案して")
        try:
            self.ai_send_btn.config(state=tk.DISABLED)
            self.ai_loading_label.config(text="🔄 Claudeが改善案を検討しています...")
            self.ai_loading_label.pack(pady=10)
        except tk.TclError:
            pass
        self._ai_retry_count = 0
        threading.Thread(target=self._call_claude_api, args=(request,), daemon=True).start()

    def _show_action_buttons(self):
        """プレビュー/適用ボタンを表示"""
        if hasattr(self, 'ai_action_frame') and self.ai_action_frame.winfo_exists():
            self.ai_action_frame.pack(fill=tk.X, pady=8)

    def _hide_action_buttons(self):
        """プレビュー/適用ボタンを非表示"""
        if hasattr(self, 'ai_action_frame') and self.ai_action_frame.winfo_exists():
            self.ai_action_frame.pack_forget()

    def _preview_ai_proposal(self):
        """AI提案をプレビュー（提案に含まれる人のみ上書き）"""
        if not self.ai_latest_proposal:
            return
        
        # 現在のデータをバックアップ（cell_sequence と next_sequence も含める）
        self.ai_preview_data = {
            'cell_data': copy.deepcopy(self.cell_data),
            'cell_colors': copy.deepcopy(self.cell_colors),
            'cell_sequence': copy.deepcopy(self.cell_sequence),
            'next_sequence': self.next_sequence,
        }
        
        # ✨ Step 1: 提案に含まれる人を抽出
        proposed_people = set()
        for assignment in self.ai_latest_proposal.get("assignments", []):
            proposed_people.add(assignment["person"])
        
        # ✨ Step 2: 提案に含まれる人のセルだけをクリア
        cells_to_clear = []
        for cell_key, person in self.cell_data.items():
            if person in proposed_people:
                cells_to_clear.append(cell_key)
        
        # クリア実行
        for cell_key in cells_to_clear:
            if cell_key not in self.locked_cells:  # ロックセルは保護
                if cell_key in self.cell_data:
                    del self.cell_data[cell_key]
                if cell_key in self.cell_colors:
                    del self.cell_colors[cell_key]
        
        # ✨ Step 3: 提案を適用
        for assignment in self.ai_latest_proposal.get("assignments", []):
            day = assignment["day"]
            label = assignment["label"]
            col = assignment["col"]
            person = assignment["person"]
            
            # ラベルインデックスを取得
            try:
                label_idx = self.LABELS.index(label)
            except ValueError:
                continue
            
            # ロックされているかチェック
            cell_key = (day, label_idx, col)
            if cell_key in self.locked_cells:
                continue
            
            # データを設定
            self.cell_data[cell_key] = person
            color = self._get_or_assign_color(person)
            self.cell_colors[cell_key] = color
        
        self.ai_preview_active = True
        
        # カレンダーを再描画
        self._redraw_all_cells()
        
        # ボタンを切り替え
        try:
            self.ai_preview_btn.pack_forget()
            self.ai_apply_btn.pack_forget()
            self.ai_cancel_preview_btn.pack(side=tk.LEFT, padx=5)
        except tk.TclError:
            pass
        
        # 提案に含まれる人を通知
        people_list = "、".join(sorted(proposed_people))
        self._add_chat_message("system", f"💡 プレビュー中です。\n対象メンバー: {people_list}\n「適用する」で確定、「プレビュー解除」で元に戻します。")

    def _cancel_preview(self):
        """プレビューを解除"""
        if not self.ai_preview_active:
            return
        
        # データを復元（cell_sequence と next_sequence も元に戻す）
        self.cell_data = self.ai_preview_data['cell_data']
        self.cell_colors = self.ai_preview_data['cell_colors']
        self.cell_sequence = self.ai_preview_data['cell_sequence']
        self.next_sequence = self.ai_preview_data['next_sequence']
        self.ai_preview_data = {}
        self.ai_preview_active = False
        
        # カレンダーを再描画
        self._redraw_all_cells()
        
        # ボタンを元に戻す
        try:
            self.ai_cancel_preview_btn.pack_forget()
            self.ai_preview_btn.pack(side=tk.LEFT, padx=5)
            self.ai_apply_btn.pack(side=tk.LEFT, padx=5)
        except tk.TclError:
            pass
        
        self._add_chat_message("system", "プレビューを解除しました。")

    def _apply_ai_proposal(self):
        """AI提案を適用（提案に含まれる人のみ上書き）"""
        if not self.ai_latest_proposal:
            return
        
        # プレビュー中ならそのまま確定
        if self.ai_preview_active:
            # プレビュー前の状態（ai_preview_data）を undo スタックに積む
            # これにより「適用」後もアンドゥで元に戻せる
            if self.ai_preview_data:
                self.undo_stack.append(self.ai_preview_data)
                if len(self.undo_stack) > self.max_history:
                    self.undo_stack.pop(0)
                self.redo_stack.clear()
            self.ai_preview_data = {}
            self.ai_preview_active = False
            try:
                self.ai_cancel_preview_btn.pack_forget()
                self.ai_preview_btn.pack(side=tk.LEFT, padx=5)
                self.ai_apply_btn.pack(side=tk.LEFT, padx=5)
            except tk.TclError:
                pass
        else:
            # プレビューしていない場合は直接適用
            self._save_state()
            
            # ✨ Step 1: 提案に含まれる人を抽出
            proposed_people = set()
            for assignment in self.ai_latest_proposal.get("assignments", []):
                proposed_people.add(assignment["person"])
            
            # ✨ Step 2: 提案に含まれる人のセルだけをクリア
            cells_to_clear = []
            for cell_key, person in self.cell_data.items():
                if person in proposed_people:
                    cells_to_clear.append(cell_key)
            
            # クリア実行
            for cell_key in cells_to_clear:
                if cell_key not in self.locked_cells:  # ロックセルは保護
                    if cell_key in self.cell_data:
                        del self.cell_data[cell_key]
                    if cell_key in self.cell_colors:
                        del self.cell_colors[cell_key]
                    # cell_sequenceも削除
                    if cell_key in self.cell_sequence:
                        del self.cell_sequence[cell_key]
            
            # ✨ Step 3: 提案を適用
            for assignment in self.ai_latest_proposal.get("assignments", []):
                day = assignment["day"]
                label = assignment["label"]
                col = assignment["col"]
                person = assignment["person"]
                
                try:
                    label_idx = self.LABELS.index(label)
                except ValueError:
                    continue
                
                cell_key = (day, label_idx, col)
                if cell_key in self.locked_cells:
                    continue
                
                self.cell_data[cell_key] = person
                color = self._get_or_assign_color(person)
                self.cell_colors[cell_key] = color
                
                if cell_key not in self.cell_sequence:
                    self.cell_sequence[cell_key] = self.next_sequence
                    self.next_sequence += 1
            
            self._redraw_all_cells()
        
        self._add_chat_message("system", "✅ 提案を適用しました！")
        self._hide_action_buttons()
        self.ai_latest_proposal = None
        
        # メインタブに切り替え
        self.notebook.select(0)
        self.draw_statistics()

    def _delete_ai_proposal(self):
        """AI提案を削除"""
        if not self.ai_latest_proposal:
            return
        
        # プレビュー中なら解除
        if self.ai_preview_active:
            self._cancel_preview()
        
        # 提案を削除
        self.ai_latest_proposal = None
        self._hide_action_buttons()
        self._add_chat_message("system", "🗑️ 提案を削除しました。")

    def _on_tab_changed(self, event):
        current_tab = self.notebook.index(self.notebook.select())
        if current_tab == 1:
            # サブカレンダータブ
            self.draw_sub_calendar()
        elif current_tab == 2:
            # 個人別一覧タブ
            self.draw_personal_calendars()

    # ─────────── 特別項目管理ウィンドウ ───────────

    def _open_special_item_window(self, category: str):
        """外勤・委員会・コース・訓練の項目管理ウィンドウを開く"""
        # 既に開いていたら前面に出す
        win = self._special_item_windows.get(category)
        if win and tk.Toplevel.winfo_exists(win):
            win.lift()
            win.focus_force()
            return

        icons = {"外勤": "🚗", "委員会": "🏛", "コース": "📚", "訓練": "🎯"}
        icon = icons.get(category, "📋")

        win = tk.Toplevel(self.root)
        win.title(f"{icon} {category} 項目管理")
        win.geometry("420x480")
        win.resizable(True, True)
        win.configure(bg="#f5f7fa")
        win.transient(self.root)
        self._special_item_windows[category] = win

        # ─ ヘッダー ─
        header = tk.Frame(win, bg="#2d5a7b", pady=10)
        header.pack(fill=tk.X)
        tk.Label(header, text=f"{icon} {category} 項目一覧",
                 font=("Meiryo UI", 13, "bold"),
                 bg="#2d5a7b", fg="white").pack()
        tk.Label(header, text="右クリックメニューに表示されます",
                 font=("Meiryo UI", 9), bg="#2d5a7b", fg="#aac8e0").pack()

        # ─ リストボックス ─
        list_frame = tk.Frame(win, bg="#f5f7fa")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(12, 5))

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        listbox = tk.Listbox(list_frame, font=("Meiryo UI", 11),
                             yscrollcommand=scrollbar.set,
                             selectmode=tk.SINGLE,
                             bg="white", bd=1, relief=tk.SOLID,
                             activestyle="none",
                             selectbackground="#2d5a7b", selectforeground="white")
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)

        def refresh_list():
            listbox.delete(0, tk.END)
            for item in self.special_items[category]:
                listbox.insert(tk.END, f"  {item}")

        refresh_list()

        # ─ 入力エリア ─
        input_frame = tk.Frame(win, bg="#f5f7fa")
        input_frame.pack(fill=tk.X, padx=15, pady=5)

        tk.Label(input_frame, text="新しい項目名:", font=("Meiryo UI", 10),
                 bg="#f5f7fa").pack(anchor=tk.W)

        entry_frame = tk.Frame(input_frame, bg="#f5f7fa")
        entry_frame.pack(fill=tk.X, pady=3)

        entry = tk.Entry(entry_frame, font=("Meiryo UI", 11), bd=1, relief=tk.SOLID)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        def add_item():
            text = entry.get().strip()
            if not text:
                return
            if text in self.special_items[category]:
                messagebox.showwarning("重複", f"「{text}」は既に登録されています",
                                       parent=win)
                return
            self.special_items[category].append(text)
            refresh_list()
            entry.delete(0, tk.END)
            listbox.see(tk.END)

        tk.Button(entry_frame, text="追加", command=add_item,
                  bg="#2d5a7b", fg="white",
                  font=("Meiryo UI", 10, "bold"), width=7,
                  relief=tk.FLAT, cursor="hand2").pack(side=tk.LEFT)

        entry.bind("<Return>", lambda e: add_item())

        # ─ 操作ボタン ─
        btn_frame = tk.Frame(win, bg="#f5f7fa")
        btn_frame.pack(fill=tk.X, padx=15, pady=(5, 15))

        def delete_item():
            sel = listbox.curselection()
            if not sel:
                messagebox.showinfo("未選択", "削除する項目を選択してください", parent=win)
                return
            idx = sel[0]
            item_name = self.special_items[category][idx]
            if messagebox.askyesno("確認", f"「{item_name}」を削除しますか？", parent=win):
                self.special_items[category].pop(idx)
                refresh_list()

        def move_up():
            sel = listbox.curselection()
            if not sel or sel[0] == 0:
                return
            idx = sel[0]
            items = self.special_items[category]
            items[idx-1], items[idx] = items[idx], items[idx-1]
            refresh_list()
            listbox.selection_set(idx-1)

        def move_down():
            sel = listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            items = self.special_items[category]
            if idx >= len(items) - 1:
                return
            items[idx], items[idx+1] = items[idx+1], items[idx]
            refresh_list()
            listbox.selection_set(idx+1)

        tk.Button(btn_frame, text="🗑 削除", command=delete_item,
                  bg="#e76f51", fg="white", font=("Meiryo UI", 10),
                  width=9, relief=tk.FLAT, cursor="hand2").pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(btn_frame, text="▲ 上へ", command=move_up,
                  bg="#6c757d", fg="white", font=("Meiryo UI", 10),
                  width=8, relief=tk.FLAT, cursor="hand2").pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="▼ 下へ", command=move_down,
                  bg="#6c757d", fg="white", font=("Meiryo UI", 10),
                  width=8, relief=tk.FLAT, cursor="hand2").pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="✓ 閉じる", command=win.destroy,
                  bg="#2a9d8f", fg="white", font=("Meiryo UI", 10),
                  width=9, relief=tk.FLAT, cursor="hand2").pack(side=tk.RIGHT)

        win.focus_force()

    def switch_stats_mode(self, mode):
        self.stats_mode = mode
        
        if mode == "person":
            self.btn_person.config(relief=tk.SUNKEN, bg="#4a90e2", font=("Meiryo UI", 10, "bold"))
            self.btn_category.config(relief=tk.RAISED, bg="#7c8a9e", font=("Meiryo UI", 10))
        else:
            self.btn_category.config(relief=tk.SUNKEN, bg="#4a90e2", font=("Meiryo UI", 10, "bold"))
            self.btn_person.config(relief=tk.RAISED, bg="#7c8a9e", font=("Meiryo UI", 10))
        
        self.draw_statistics()

    def _toggle_sound(self):
        is_muted = self.sound_manager.toggle_mute()
        if is_muted:
            self.sound_btn.config(text="🔇 SE:OFF", bg="#9E9E9E")
        else:
            self.sound_btn.config(text="🔊 SE:ON", bg="#4CAF50")
            self.sound_manager.play("bright")

    def _on_close(self):
        self._close_ai_window()
        self.sound_manager.cleanup()
        self.root.destroy()

    def _mark_day_as_complete(self, day: int):
        """指定した日を完成状態にマークする"""
        if day in self.completed_days:
            return
        
        self.completed_days.add(day)
        self._draw_day_complete_marker(day)
        self.sound_manager.play("complete")
        self._animate_completion(day)
    
    def _unmark_day_as_complete(self, day: int):
        """指定した日の完成マークを解除する"""
        if day not in self.completed_days:
            return
        
        self.completed_days.discard(day)
        if day in self.day_complete_rects:
            self.canvas.delete(self.day_complete_rects[day])
            del self.day_complete_rects[day]
    
    def _draw_day_complete_marker(self, day: int):
        """日付セルに薄い黄色の背景を描画"""
        if day not in self._day_positions:
            return
        
        week, dow, col_x, row_y = self._day_positions[day]
        
        x1 = col_x
        y1 = row_y
        x2 = col_x + self.CELL_W
        y2 = row_y + self.CELL_H
        
        rect_id = self.canvas.create_rectangle(
            x1, y1, x2, y2,
            fill="#fffacd",
            outline="",
            tags="day_complete"
        )
        self.day_complete_rects[day] = rect_id
        
        self.canvas.tag_lower("day_complete")
        self.canvas.tag_lower("day_complete", "grid")
    
    def _redraw_day_complete_markers(self):
        """すべての完成マーカーを再描画"""
        for rect_id in self.day_complete_rects.values():
            self.canvas.delete(rect_id)
        self.day_complete_rects.clear()
        
        for day in list(self.completed_days):
            self._draw_day_complete_marker(day)
    
    def _animate_completion(self, day: int):
        info = self._day_positions.get(day)
        if not info:
            return
        
        week, dow, col_x, row_y = info
        
        x1 = col_x
        y1 = row_y
        x2 = col_x + self.BLOCK_W * self.CELL_W
        y2 = row_y + self.BLOCK_H * self.CELL_H
        
        animation_ids = []
        
        def phase1():
            border_id = self.canvas.create_rectangle(
                x1, y1, x2, y2,
                outline="#FFD700", width=6, tags="completion_anim"
            )
            animation_ids.append(border_id)
            self.root.after(100, phase2)
        
        def phase2():
            for _ in range(12):
                star_x = random.randint(int(x1 + 10), int(x2 - 10))
                star_y = random.randint(int(y1 + 10), int(y2 - 10))
                star_id = self.canvas.create_text(
                    star_x, star_y, text="✨", 
                    font=("Segoe UI Emoji", random.randint(12, 20)),
                    fill=random.choice(["#FFD700", "#FFA500", "#FFFF00", "#FF69B4"]),
                    tags="completion_anim"
                )
                animation_ids.append(star_id)
            self.root.after(150, phase3)
        
        def phase3():
            for item_id in animation_ids:
                if self.canvas.type(item_id) == "rectangle":
                    self.canvas.itemconfig(item_id, width=4, outline="#FFD700")
            self.root.after(150, phase4)
        
        def phase4():
            for _ in range(8):
                star_x = random.randint(int(x1 + 10), int(x2 - 10))
                star_y = random.randint(int(y1 + 10), int(y2 - 10))
                star_id = self.canvas.create_text(
                    star_x, star_y, text="⭐", 
                    font=("Segoe UI Emoji", random.randint(10, 18)),
                    fill=random.choice(["#FFD700", "#FFA500", "#FFFF00"]),
                    tags="completion_anim"
                )
                animation_ids.append(star_id)
            self.root.after(200, phase5)
        
        def phase5():
            for item_id in animation_ids:
                if self.canvas.type(item_id) == "rectangle":
                    self.canvas.itemconfig(item_id, width=7, outline="#FFA500")
            self.root.after(120, phase6)
        
        def phase6():
            for item_id in animation_ids:
                if self.canvas.type(item_id) == "rectangle":
                    self.canvas.itemconfig(item_id, width=5, outline="#FFD700")
            self.root.after(150, phase7)
        
        def phase7():
            for item_id in animation_ids:
                if self.canvas.type(item_id) == "rectangle":
                    self.canvas.itemconfig(item_id, width=3, outline="#FFE4B5")
            self.root.after(180, phase8)
        
        def phase8():
            self.canvas.delete("completion_anim")
        
        phase1()

    # ========== ✨ 日付メモ帳機能 ==========
    
    def _open_day_memo(self, day: int):
        """指定した日のメモ帳を開く"""
        # 既に開いている場合は前面に
        if day in self.memo_windows:
            try:
                self.memo_windows[day].lift()
                self.memo_windows[day].focus_force()
                return
            except tk.TclError:
                # ウィンドウが既に閉じられている
                del self.memo_windows[day]
        
        # ✨ 10枚まで制限
        if len(self.memo_windows) >= 10:
            messagebox.showwarning("制限", 
                "メモ帳は最大10枚までしか同時に開けません。\n"
                "他のメモ帳を閉じてから開いてください。")
            return
        
        # メモウィンドウを作成
        memo_win = tk.Toplevel(self.root)
        memo_win.title(f"📝 {day}日")
        
        # ✨ サイズをコンパクトに
        memo_width = 220
        memo_height = 140
        
        # ウィンドウのコンテンツを先に作成
        memo_win.configure(bg="#f8f9fa")
        
        # ✨ ヘッダー（コンパクト化）
        header = tk.Frame(memo_win, bg="#4a90e2", height=28)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(header, 
                text=f"📅 {self.current_month}/{day}",
                bg="#4a90e2", fg="white",
                font=("Meiryo UI", 9, "bold")).pack(side=tk.LEFT, padx=8, pady=4)
        
        # メモ入力エリア（コンパクト化）
        text_frame = tk.Frame(memo_win, bg="#f8f9fa")
        text_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        
        # テキストウィジェット（2行分の高さ）
        text_widget = tk.Text(text_frame, 
                             height=2,
                             font=("Meiryo UI", 9),
                             bg="white", fg="#2d3748",
                             relief=tk.SOLID, bd=1,
                             wrap=tk.WORD)
        text_widget.pack(fill=tk.BOTH, expand=True)
        
        # 既存のメモを読み込み
        if day in self.day_memos:
            text_widget.insert("1.0", self.day_memos[day])
        
        # 閉じるボタン（text_widget定義後に作成）
        close_btn = tk.Button(header, text="✕", 
                             command=lambda: self._close_day_memo(day, memo_win, text_widget),
                             bg="#e74c3c", fg="white",
                             font=("Meiryo UI", 8, "bold"),
                             relief=tk.FLAT, cursor="hand2",
                             padx=4, pady=0)
        close_btn.pack(side=tk.RIGHT, padx=5)
        
        # ウィンドウを更新してサイズを確定
        memo_win.update_idletasks()
        
        # ✨ カレンダーの日付の右側に配置
        self.root.update_idletasks()
        
        # デフォルト位置（メインウィンドウの右側）
        try:
            main_x = self.root.winfo_x()
            main_y = self.root.winfo_y()
            main_width = self.root.winfo_width()
            
            # デフォルト: メインウィンドウの右側
            memo_x = main_x + main_width + 10
            memo_y = main_y + 100 + (len(self.memo_windows) * 150)  # 重ならないように
            
            # 日付の位置情報を取得して上書き
            if day in self._day_positions:
                week, dow, col_x, row_y = self._day_positions[day]
                
                # キャンバスの絶対座標を取得
                try:
                    canvas_x = self.canvas.winfo_rootx()
                    canvas_y = self.canvas.winfo_rooty()
                    
                    # 座標が有効かチェック
                    if canvas_x > 0 and canvas_y > 0:
                        # 日付ブロックの右側に配置
                        block_width = int(self.BLOCK_W * self.CELL_W)
                        memo_x = canvas_x + int(col_x) + block_width + 10
                        memo_y = canvas_y + int(row_y)
                except:
                    pass  # デフォルト位置を使用
        except:
            # 完全なフォールバック: 画面中央
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            memo_x = (screen_width - memo_width) // 2
            memo_y = (screen_height - memo_height) // 2
        
        # 位置を設定
        memo_win.geometry(f"{memo_width}x{memo_height}+{memo_x}+{memo_y}")
        memo_win.resizable(False, False)  # サイズ固定
        
        # ✨ 常に前面に表示（位置設定後）
        memo_win.lift()
        memo_win.attributes('-topmost', True)
        
        # フォーカス
        text_widget.focus_force()
        
        # ウィンドウを登録
        self.memo_windows[day] = memo_win
        
        # ウィンドウが閉じられた時の処理
        memo_win.protocol("WM_DELETE_WINDOW", 
                         lambda: self._close_day_memo(day, memo_win, text_widget))
    
    def _close_day_memo(self, day: int, window: tk.Toplevel, text_widget: tk.Text):
        """メモ帳を閉じる（内容を保存）"""
        # テキスト内容を取得
        memo_text = text_widget.get("1.0", "end-1c").strip()
        
        # 保存
        if memo_text:
            self.day_memos[day] = memo_text
        else:
            # 空の場合は削除
            if day in self.day_memos:
                del self.day_memos[day]
        
        # ウィンドウを閉じる
        if day in self.memo_windows:
            del self.memo_windows[day]
        
        try:
            window.destroy()
        except:
            pass

    def create_calendar(self):
        try:
            self.current_year = int(self.year_var.get())
            self.current_month = int(self.month_var.get())
        except ValueError:
            messagebox.showerror("エラー", "正しい年月を入力してください")
            return

        self._finish_edit()
        self.canvas.delete("all")
        self._rect_ids.clear()
        self._text_ids.clear()
        self._cell_bounds.clear()
        self._day_positions.clear()
        self.day_complete_rects.clear()
        
        self.left_frame.update_idletasks()
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w < 100: canvas_w = 1000
        if canvas_h < 100: canvas_h = 800

        first_wd = calendar.weekday(self.current_year, self.current_month, 1)
        first_wd = (first_wd + 1) % 7
        if first_wd == 0: first_wd = 7
        last_day = calendar.monthrange(self.current_year, self.current_month)[1]
        
        if self.current_month == 1:
            prev_month_year = self.current_year - 1
            prev_month = 12
        else:
            prev_month_year = self.current_year
            prev_month = self.current_month - 1
        prev_month_last_day = calendar.monthrange(prev_month_year, prev_month)[1]
        
        total_cells = first_wd - 1 + last_day
        total_weeks = -(-total_cells // 7)

        ox = 10
        oy = 10
        scrollbar_buffer = 20

        available_w = canvas_w - (ox * 2) - (self.LABEL_COL_W * 2) - scrollbar_buffer
        total_cols = 7 * self.BLOCK_W
        new_cell_w = available_w / total_cols
        
        available_h = canvas_h - oy - self.TITLE_H - self.HEADER_H - scrollbar_buffer
        total_rows = total_weeks * self.BLOCK_H
        new_cell_h = available_h / total_rows

        self.CELL_W = max(20, new_cell_w)
        self.CELL_H = max(15, new_cell_h)

        self.canvas.create_text(ox, oy, anchor="nw",
                                text=f"{self.current_year}年 {self.current_month}月",
                                font=("Meiryo UI", 24, "bold"), fill="black")
        oy += self.TITLE_H

        hdr_x = ox + self.LABEL_COL_W
        for i, wd in enumerate(self.WEEKDAYS):
            x1 = hdr_x + i * self.BLOCK_W * self.CELL_W
            x2 = x1 + self.BLOCK_W * self.CELL_W
            self.canvas.create_rectangle(x1, oy, x2, oy + self.HEADER_H,
                                         fill="#dcdcdc", outline="gray")
            fg = "blue" if i == 5 else ("red" if i == 6 else "black")
            self.canvas.create_text((x1 + x2) / 2, oy + self.HEADER_H / 2,
                                    text=wd, font=("Meiryo UI", 12, "bold"), fill=fg)
        oy += self.HEADER_H

        current_day = 1
        prev_day_counter = first_wd - 2
        next_day_counter = 1
        right_x = ox + self.LABEL_COL_W + 7 * self.BLOCK_W * self.CELL_W + self.LABEL_COL_W

        for week in range(total_weeks):
            row_y = oy + week * self.BLOCK_H * self.CELL_H

            self._draw_label_column(ox, row_y)

            for dow in range(7):
                col_x = ox + self.LABEL_COL_W + dow * self.BLOCK_W * self.CELL_W

                if week == 0 and dow < first_wd - 1:
                    prev_day = prev_month_last_day - prev_day_counter
                    self._draw_adjacent_month_block(col_x, row_y, -prev_day, dow, week, is_prev_month=True)
                    prev_day_counter -= 1
                elif current_day <= last_day:
                    self._draw_day_block(col_x, row_y, current_day, dow, week)
                    current_day += 1
                else:
                    self._draw_adjacent_month_block(col_x, row_y, last_day + next_day_counter, dow, week, is_prev_month=False)
                    next_day_counter += 1
                
                if dow < 6:
                    line_x = col_x + self.BLOCK_W * self.CELL_W
                    line_y1 = row_y
                    line_y2 = row_y + self.BLOCK_H * self.CELL_H
                    self.canvas.create_line(line_x, line_y1, line_x, line_y2,
                                          width=3, fill="#444444", tags="week_separator")

            right_label_x = ox + self.LABEL_COL_W + 7 * self.BLOCK_W * self.CELL_W
            self._draw_label_column(right_label_x, row_y)

            week_bottom_y = row_y + self.BLOCK_H * self.CELL_H
            self.canvas.create_line(ox, week_bottom_y, right_x, week_bottom_y,
                                    width=3, fill="#444444", tags="grid_line")
            
            self.canvas.tag_raise("divider_line")

        total_h = oy + total_weeks * self.BLOCK_H * self.CELL_H + 20
        total_w = ox + self.LABEL_COL_W * 2 + 7 * self.BLOCK_W * self.CELL_W + 20
        self.canvas.configure(scrollregion=(0, 0, total_w, total_h))

        self._apply_data()
        self._draw_all_lines()
        
        self.canvas.tag_raise("divider_line")
        self.canvas.update_idletasks()
        self.canvas.tag_raise("divider_line")
        
        self._redraw_special_borders()
        self._redraw_lock_borders()
        self._redraw_day_complete_markers()
        
        self.draw_statistics()

    def draw_statistics(self):
        self.right_frame.update_idletasks()
        
        self.stats_canvas.delete("all")
        w = self.stats_canvas.winfo_width()
        if w < 50: w = 350
        
        valid_values = [v for v in self.cell_data.values() if v and v.strip()]
        if not valid_values:
            self.stats_canvas.create_text(w/2, 50, text="データなし", font=("Meiryo UI", 11))
            self.stats_canvas.configure(scrollregion=(0, 0, w, 100))
            return
        
        if self.stats_mode == "person":
            self._draw_person_statistics(w)
        else:
            self._draw_category_statistics(w)

    def _draw_person_statistics(self, canvas_width):
        w = canvas_width
        
        person_stats = defaultdict(lambda: defaultdict(int))
        
        for (day, label_idx, col_idx), value in self.cell_data.items():
            if not value or not value.strip():
                continue
            label = self.LABELS[label_idx] if label_idx < len(self.LABELS) else ""
            if label and label.strip():
                person_stats[value][label] += 1
        
        if not person_stats:
            self.stats_canvas.create_text(w/2, 50, text="データなし", font=("Meiryo UI", 11))
            self.stats_canvas.configure(scrollregion=(0, 0, w, 100))
            return
        
        sorted_persons = sorted(person_stats.keys(), 
                               key=lambda p: sum(person_stats[p].values()), 
                               reverse=True)
        
        y_pos = 15
        
        self.stats_canvas.create_text(w/2, y_pos, anchor="n",
                                      text="【詳細ビュー - 個人別内訳】",
                                      font=("Meiryo UI", 13, "bold", "underline"),
                                      fill="#2c3e50")
        y_pos += 30
        
        category_order = ["ER", "A", "B", "当直", "明け", "外勤", "出張", "休み"]

        # ✨ ツールチップ領域をリセット
        self._hp_tooltip_areas = []
        
        for person in sorted_persons:
            stats = person_stats[person]
            
            work_days = sum(count for cat, count in stats.items() if cat != "休み")
            holiday_days = stats.get("休み", 0)
            total_days = work_days + holiday_days

            # ✨ 疲労度計算
            hp_pct, fatigue_detail = self._calc_fatigue(person)

            # ── 名前バー（2行構成）──
            # 行1: 名前＋集計テキスト
            name_bg = self.stats_canvas.create_rectangle(
                10, y_pos - 2, w - 10, y_pos + 18,
                fill="#ecf0f1", outline="#bdc3c7")
            self.stats_canvas.create_text(
                15, y_pos + 8, anchor="w",
                text=f"■ {person}  総計: {total_days}日 （労働: {work_days}日、休み: {holiday_days}日）",
                font=("Meiryo UI", 10, "bold"))
            y_pos += 20

            # 行2: HPゲージ専用行
            gauge_row_bg = self.stats_canvas.create_rectangle(
                10, y_pos, w - 10, y_pos + 20,
                fill="#dde4ea", outline="#bdc3c7")
            gauge_w = w - 80
            gauge_x = 40
            gauge_y = y_pos + 10
            self._draw_hp_gauge(gauge_x, gauge_y, gauge_w, hp_pct)

            # ✨ ホバー領域をゲージ行に登録
            tooltip_text = self._build_hp_tooltip_text(person, hp_pct, fatigue_detail)
            self._hp_tooltip_areas.append((10, y_pos, w - 10, y_pos + 20, tooltip_text))

            y_pos += 26
            
            max_count = max([stats.get(cat, 0) for cat in category_order]) if stats else 1
            bar_max_width = w - 140
            
            for category in category_order:
                count = stats.get(category, 0)
                color = self._get_or_assign_color(category)
                
                self.stats_canvas.create_text(30, y_pos, anchor="w",
                                             text=category,
                                             font=("Meiryo UI", 9))
                
                if count > 0:
                    bar_width = (count / max(max_count, 1)) * bar_max_width
                    self.stats_canvas.create_rectangle(90, y_pos-8, 90 + bar_width, y_pos+8,
                                                      fill=color, outline=color, width=0)
                    self.stats_canvas.create_text(95 + bar_width, y_pos, anchor="w",
                                                 text=f"{count}日",
                                                 font=("Meiryo UI", 9, "bold"))
                else:
                    self.stats_canvas.create_text(90, y_pos, anchor="w",
                                                 text="─ 0日",
                                                 font=("Meiryo UI", 9),
                                                 fill="#95a5a6")
                
                y_pos += 20
            
            y_pos += 5
            self.stats_canvas.create_line(10, y_pos, w-10, y_pos, fill="#bdc3c7", width=1)
            y_pos += 15
        
        y_pos += 10
        self.stats_canvas.create_text(w/2, y_pos, anchor="n",
                                      text="【比較ビュー - 項目別人員比較】",
                                      font=("Meiryo UI", 13, "bold", "underline"),
                                      fill="#2c3e50")
        y_pos += 35
        
        person_col_width = 70
        start_x = 80
        
        for i, person in enumerate(sorted_persons):
            x_pos = start_x + i * person_col_width
            self.stats_canvas.create_text(x_pos + person_col_width/2, y_pos, anchor="n",
                                         text=person,
                                         font=("Meiryo UI", 9, "bold"))
        y_pos += 25
        
        for category in category_order:
            color = self._get_or_assign_color(category)
            
            self.stats_canvas.create_text(15, y_pos, anchor="w",
                                         text=category,
                                         font=("Meiryo UI", 9, "bold"))
            
            all_counts = [person_stats[p].get(category, 0) for p in sorted_persons]
            max_count = max(all_counts) if all_counts else 1
            
            for i, person in enumerate(sorted_persons):
                count = person_stats[person].get(category, 0)
                x_pos = start_x + i * person_col_width
                
                if count > 0:
                    bar_width = (count / max(max_count, 1)) * (person_col_width - 25)
                    self.stats_canvas.create_rectangle(x_pos, y_pos-7,
                                                      x_pos + bar_width, y_pos+7,
                                                      fill=color, outline="", width=0)
                    self.stats_canvas.create_text(x_pos + bar_width + 3, y_pos, anchor="w",
                                                 text=str(count),
                                                 font=("Meiryo UI", 8, "bold"))
                else:
                    self.stats_canvas.create_text(x_pos, y_pos, anchor="w",
                                                 text="─",
                                                 font=("Meiryo UI", 9),
                                                 fill="#95a5a6")
            
            y_pos += 22
        
        total_width = max(w, start_x + len(sorted_persons) * person_col_width + 50)
        self.stats_canvas.configure(scrollregion=(0, 0, total_width, y_pos + 20))

    # ─────────────── ✨ 疲労度インジケーター ───────────────

    def _calc_fatigue(self, person: str):
        """
        疲労スコアを計算して (hp_pct, detail_dict) を返す。
        hp_pct: 0〜100 （100=元気満タン、0=燃え尽き）
        """
        # 日別に勤務ラベルを収集
        person_days: Dict[int, set] = {}
        for (day, li, ci), name in self.cell_data.items():
            if name != person:
                continue
            label = self.LABELS[li] if li < len(self.LABELS) else ""
            if label and label.strip():
                person_days.setdefault(day, set()).add(label)

        tochoku   = sum(1 for ls in person_days.values() if "当直"   in ls)
        kyukin    = sum(1 for ls in person_days.values() if "休み"    in ls)
        gakin     = sum(1 for ls in person_days.values() if "外勤"    in ls)
        shutcho   = sum(1 for ls in person_days.values() if "出張"    in ls)

        # 連続勤務（休みがない連続日数）の最長を算出
        work_days = sorted(d for d, ls in person_days.items() if "休み" not in ls)
        max_consec = cur = 0
        prev = None
        for d in work_days:
            cur = cur + 1 if prev is not None and d == prev + 1 else 1
            max_consec = max(max_consec, cur)
            prev = d

        # スコア計算（疲労ポイント）
        score = 0
        score += tochoku * 15
        score += max(0, max_consec - 2) * 8   # 3日以上連続で加算
        score += gakin   * 5
        score += shutcho * 8
        score -= kyukin  * 10                  # 休みは回復
        score = max(0, score)

        # 100段階に正規化（最大想定スコア≈120）
        MAX_SCORE = 240
        fatigue_pct = min(100, int(score / MAX_SCORE * 100))
        hp_pct = 100 - fatigue_pct

        detail = {
            "当直回数":     tochoku,
            "休み回数":     kyukin,
            "外勤回数":     gakin,
            "出張回数":     shutcho,
            "連続勤務最長": max_consec,
            "疲労スコア":   score,
        }
        return hp_pct, detail

    def _draw_hp_gauge(self, x: float, cy: float, total_w: float, hp_pct: int) -> list:
        """
        HPゲージを描画して canvas アイテム ID のリストを返す。
        x: ゲージ左端X  cy: ゲージ中央Y  total_w: ゲージ全幅
        """
        ids = []
        # ── 色・アイコン決定 ──
        if hp_pct >= 80:
            bar_color, emoji = "#27ae60", "😊"
        elif hp_pct >= 60:
            bar_color, emoji = "#f1c40f", "😐"
        elif hp_pct >= 40:
            bar_color, emoji = "#e67e22", "😓"
        elif hp_pct >= 20:
            bar_color, emoji = "#e74c3c", "😫"
        else:
            bar_color, emoji = "#900000", "💀"

        bar_h = 12
        y1 = cy - bar_h // 2
        y2 = cy + bar_h // 2

        # 左側ラベル「疲労度」
        ids.append(self.stats_canvas.create_text(
            x - 2, cy, anchor="w",
            text="疲労度", font=("Meiryo UI", 8),
            fill="#555"))

        label_prefix_w = 34
        bar_w = total_w - label_prefix_w - 90   # 右余白90px（HP%テキスト＋絵文字丸分）

        bx = x + label_prefix_w
        # ゲージ背景
        ids.append(self.stats_canvas.create_rectangle(
            bx, y1, bx + bar_w, y2,
            fill="#c8ccd4", outline="#999", width=1))
        # ゲージ本体
        filled_w = max(1, int(bar_w * hp_pct / 100))
        ids.append(self.stats_canvas.create_rectangle(
            bx, y1, bx + filled_w, y2,
            fill=bar_color, outline="", width=0))
        # HP% テキスト（ゲージ右）
        ids.append(self.stats_canvas.create_text(
            bx + bar_w + 4, cy, anchor="w",
            text=f"HP {hp_pct}%",
            font=("Meiryo UI", 8, "bold"),
            fill=bar_color))
        # 絵文字（右端）
        emoji_cx = bx + bar_w + 62   # %テキストから十分に離す
        ids.append(self.stats_canvas.create_text(
            emoji_cx, cy,
            anchor="center", text=emoji, font=("Meiryo UI", 13)))
        return ids

    def _build_hp_tooltip_text(self, person: str, hp_pct: int, detail: dict) -> str:
        """ホバー時に表示するツールチップ文字列を生成"""
        if hp_pct >= 80:
            comment = "十分な余裕あり。良いバランスです！"
        elif hp_pct >= 60:
            comment = "やや負荷あり。休みを確保したいところ。"
        elif hp_pct >= 40:
            comment = "疲労が蓄積ぎみ。注意が必要です。"
        elif hp_pct >= 20:
            comment = "かなりの過負荷状態！要フォロー。"
        else:
            comment = "燃え尽き寸前…！至急休みを。"

        lines = [
            f"── {person} の疲労度詳細 ──",
            f"  HP: {hp_pct}%  {comment}",
            "",
            f"  当直回数     : {detail['当直回数']} 回  (+{detail['当直回数']*15}pt)",
            f"  外勤回数     : {detail['外勤回数']} 回  (+{detail['外勤回数']*5}pt)",
            f"  出張回数     : {detail['出張回数']} 回  (+{detail['出張回数']*8}pt)",
            f"  連続勤務最長 : {detail['連続勤務最長']} 日",
        ]
        if detail['連続勤務最長'] > 2:
            lines[-1] += f"  (+{max(0,detail['連続勤務最長']-2)*8}pt)"
        lines += [
            f"  休み回数     : {detail['休み回数']} 回  (-{detail['休み回数']*10}pt)",
            "",
            f"  疲労スコア合計: {detail['疲労スコア']} pt",
        ]
        return "\n".join(lines)

    def _on_stats_motion(self, event):
        """stats_canvas 上でマウスが動いたときのコールバック"""
        # スクロール量を考慮したキャンバス座標
        cx = self.stats_canvas.canvasx(event.x)
        cy = self.stats_canvas.canvasy(event.y)
        for (x1, y1, x2, y2, text) in self._hp_tooltip_areas:
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                self._show_hp_tooltip(event, text)
                return
        self._hide_hp_tooltip()

    def _show_hp_tooltip(self, event, text: str):
        """ツールチップウィンドウを表示"""
        if self._hp_tooltip_win is not None:
            # 既に同じテキストで表示中なら位置だけ更新
            try:
                self._hp_tooltip_win.geometry(
                    f"+{event.x_root + 12}+{event.y_root + 12}")
                return
            except Exception:
                self._hp_tooltip_win = None

        win = tk.Toplevel(self.root)
        win.wm_overrideredirect(True)   # タイトルバーなし
        win.wm_attributes("-topmost", True)
        win.geometry(f"+{event.x_root + 12}+{event.y_root + 12}")

        frame = tk.Frame(win, background="#fffbe6",
                         highlightbackground="#e0c050",
                         highlightthickness=1)
        frame.pack()
        lbl = tk.Label(frame, text=text,
                       background="#fffbe6",
                       font=("Meiryo UI", 9),
                       justify=tk.LEFT,
                       padx=8, pady=6)
        lbl.pack()
        self._hp_tooltip_win = win

    def _hide_hp_tooltip(self, event=None):
        """ツールチップウィンドウを非表示"""
        if self._hp_tooltip_win is not None:
            try:
                self._hp_tooltip_win.destroy()
            except Exception:
                pass
            self._hp_tooltip_win = None

    def _draw_category_statistics(self, canvas_width):
        w = canvas_width
        
        category_stats = defaultdict(lambda: defaultdict(int))
        
        for (day, label_idx, col_idx), value in self.cell_data.items():
            if not value or not value.strip():
                continue
            label = self.LABELS[label_idx] if label_idx < len(self.LABELS) else ""
            if label and label.strip():
                category_stats[label][value] += 1
        
        if not category_stats:
            self.stats_canvas.create_text(w/2, 50, text="データなし", font=("Meiryo UI", 11))
            self.stats_canvas.configure(scrollregion=(0, 0, w, 100))
            return
        
        priority_order = ["ER", "A", "B", "当直", "明け", "外勤", "出張", "休み"]
        sorted_categories = [cat for cat in priority_order if cat in category_stats]
        sorted_categories.extend([cat for cat in category_stats.keys() if cat not in priority_order])
        
        all_persons = set()
        for persons_dict in category_stats.values():
            all_persons.update(persons_dict.keys())
        sorted_persons = sorted(all_persons)
        
        y_pos = 15
        
        self.stats_canvas.create_text(w/2, y_pos, anchor="n",
                                      text="【詳細ビュー - 項目別内訳】",
                                      font=("Meiryo UI", 13, "bold", "underline"),
                                      fill="#2c3e50")
        y_pos += 30
        
        for category in sorted_categories:
            persons = category_stats[category]
            total = sum(persons.values())
            color = self._get_or_assign_color(category)
            
            name_bg = self.stats_canvas.create_rectangle(10, y_pos-2, w-10, y_pos+20,
                                                         fill="#ecf0f1", outline="#bdc3c7")
            self.stats_canvas.create_text(15, y_pos+9, anchor="w",
                                         text=f"■ {category}  総計: {total}日",
                                         font=("Meiryo UI", 10, "bold"))
            y_pos += 26
            
            max_count = max(persons.values()) if persons else 1
            bar_max_width = w - 140
            
            for person in sorted_persons:
                count = persons.get(person, 0)
                person_color = self._get_or_assign_color(person)
                
                self.stats_canvas.create_text(30, y_pos, anchor="w",
                                             text=person,
                                             font=("Meiryo UI", 9))
                
                if count > 0:
                    bar_width = (count / max(max_count, 1)) * bar_max_width
                    self.stats_canvas.create_rectangle(90, y_pos-8, 90 + bar_width, y_pos+8,
                                                      fill=person_color, outline="", width=0)
                    percentage = (count / total * 100) if total > 0 else 0
                    self.stats_canvas.create_text(95 + bar_width, y_pos, anchor="w",
                                                 text=f"{count}日 ({percentage:.1f}%)",
                                                 font=("Meiryo UI", 9, "bold"))
                else:
                    self.stats_canvas.create_text(90, y_pos, anchor="w",
                                                 text="─ 0日",
                                                 font=("Meiryo UI", 9),
                                                 fill="#95a5a6")
                
                y_pos += 20
            
            y_pos += 5
            self.stats_canvas.create_line(10, y_pos, w-10, y_pos, fill="#bdc3c7", width=1)
            y_pos += 15
        
        y_pos += 10
        self.stats_canvas.create_text(w/2, y_pos, anchor="n",
                                      text="【比較ビュー - 人別項目比較】",
                                      font=("Meiryo UI", 13, "bold", "underline"),
                                      fill="#2c3e50")
        y_pos += 35
        
        cat_col_width = 70
        start_x = 80
        
        for i, category in enumerate(sorted_categories):
            x_pos = start_x + i * cat_col_width
            self.stats_canvas.create_text(x_pos + cat_col_width/2, y_pos, anchor="n",
                                         text=category,
                                         font=("Meiryo UI", 9, "bold"))
        y_pos += 25
        
        for person in sorted_persons:
            person_color = self._get_or_assign_color(person)
            
            self.stats_canvas.create_text(15, y_pos, anchor="w",
                                         text=person,
                                         font=("Meiryo UI", 9, "bold"))
            
            all_counts = [category_stats[cat].get(person, 0) for cat in sorted_categories]
            max_count = max(all_counts) if all_counts else 1
            
            for i, category in enumerate(sorted_categories):
                count = category_stats[category].get(person, 0)
                x_pos = start_x + i * cat_col_width
                color = self._get_or_assign_color(category)
                
                if count > 0:
                    bar_width = (count / max(max_count, 1)) * (cat_col_width - 25)
                    self.stats_canvas.create_rectangle(x_pos, y_pos-7,
                                                      x_pos + bar_width, y_pos+7,
                                                      fill=color, outline="", width=0)
                    self.stats_canvas.create_text(x_pos + bar_width + 3, y_pos, anchor="w",
                                                 text=str(count),
                                                 font=("Meiryo UI", 8, "bold"))
                else:
                    self.stats_canvas.create_text(x_pos, y_pos, anchor="w",
                                                 text="─",
                                                 font=("Meiryo UI", 9),
                                                 fill="#95a5a6")
            
            y_pos += 22
        
        total_width = max(w, start_x + len(sorted_categories) * cat_col_width + 50)
        self.stats_canvas.configure(scrollregion=(0, 0, total_width, y_pos + 20))

    def draw_personal_calendars(self):
        self.personal_canvas.delete("all")
        
        all_persons = set()
        for value in self.cell_data.values():
            if value and value.strip():
                all_persons.add(value)
        
        if not all_persons:
            self.personal_canvas.create_text(400, 300, 
                                           text="データがありません",
                                           font=("Meiryo UI", 16))
            self.personal_canvas.configure(scrollregion=(0, 0, 800, 600))
            return
        
        sorted_persons = sorted(all_persons)
        
        cols = 3
        cal_width = 300
        cal_height = 280
        margin = 30
        start_x = margin
        start_y = margin
        
        first_wd = calendar.weekday(self.current_year, self.current_month, 1)
        first_wd = (first_wd + 1) % 7
        if first_wd == 0: first_wd = 7
        last_day = calendar.monthrange(self.current_year, self.current_month)[1]
        
        for person_idx, person in enumerate(sorted_persons):
            row = person_idx // cols
            col = person_idx % cols
            
            base_x = start_x + col * (cal_width + margin)
            base_y = start_y + row * (cal_height + margin)
            
            self.personal_canvas.create_text(
                base_x + cal_width / 2, base_y,
                text=f"{person} の勤務カレンダー",
                font=("Meiryo UI", 12, "bold")
            )
            
            cell_size = 35
            grid_start_x = base_x + 10
            grid_start_y = base_y + 30
            
            weekdays_short = ["月", "火", "水", "木", "金", "土", "日"]
            for wd_idx, wd in enumerate(weekdays_short):
                x = grid_start_x + wd_idx * cell_size
                y = grid_start_y
                self.personal_canvas.create_text(
                    x + cell_size / 2, y + cell_size / 2,
                    text=wd,
                    font=("Meiryo UI", 9, "bold")
                )
            
            current_day = 1
            for week in range(6):
                for dow in range(7):
                    x = grid_start_x + dow * cell_size
                    y = grid_start_y + (week + 1) * cell_size
                    
                    if week == 0 and dow < first_wd - 1:
                        continue
                    if current_day > last_day:
                        break
                    
                    day_activities = []
                    for label_idx in range(1, len(self.LABELS) - 1):
                        for col_idx in range(self.BLOCK_W):
                            ck = (current_day, label_idx, col_idx)
                            if ck in self.cell_data and self.cell_data[ck] == person:
                                label = self.LABELS[label_idx]
                                if label not in day_activities:
                                    day_activities.append(label)
                    
                    # ✨ 休みを目立たせる改善 ✨
                    if "休み" in day_activities:
                        cell_color = "#ff6b6b"  # 鮮やかな赤
                        text_color = "white"  # 白文字
                        border_color = "#cc0000"  # 濃い赤の枠線
                        border_width = 3  # 太い枠線
                        font_weight = "bold"  # 太字
                        show_yasumi_mark = True  # 「休」マークを表示
                    elif day_activities:
                        first_activity = day_activities[0]
                        cell_color = self._get_or_assign_color(first_activity)
                        text_color = "black"
                        border_color = "gray"
                        border_width = 1
                        font_weight = "normal"
                        show_yasumi_mark = False
                    else:
                        cell_color = "white"
                        text_color = "#cccccc"
                        border_color = "gray"
                        border_width = 1
                        font_weight = "normal"
                        show_yasumi_mark = False
                    
                    # セル背景を描画
                    self.personal_canvas.create_rectangle(
                        x, y, x + cell_size, y + cell_size,
                        fill=cell_color, outline=border_color, width=border_width
                    )
                    
                    # 日付番号を描画
                    if show_yasumi_mark:
                        # 休みの場合: 日付を左上、「休」を中央に
                        self.personal_canvas.create_text(
                            x + 5, y + 5,
                            text=str(current_day),
                            font=("Meiryo UI", 7, font_weight),
                            fill=text_color,
                            anchor="nw"
                        )
                        self.personal_canvas.create_text(
                            x + cell_size / 2, y + cell_size / 2 + 3,
                            text="休",
                            font=("Meiryo UI", 14, "bold"),
                            fill=text_color
                        )
                    else:
                        # 通常の場合: 日付を中央に
                        self.personal_canvas.create_text(
                            x + cell_size / 2, y + cell_size / 2,
                            text=str(current_day),
                            font=("Meiryo UI", 8, font_weight),
                            fill=text_color
                        )
                    
                    current_day += 1
            
            legend_y = grid_start_y + 7 * cell_size + 10
            person_summary = defaultdict(int)
            for (day, label_idx, col_idx), value in self.cell_data.items():
                if value == person:
                    label = self.LABELS[label_idx] if label_idx < len(self.LABELS) else ""
                    if label and label.strip():
                        person_summary[label] += 1
            
            legend_text = " | ".join([f"{k}:{v}" for k, v in sorted(person_summary.items())])
            self.personal_canvas.create_text(
                base_x + cal_width / 2, legend_y,
                text=legend_text,
                font=("Meiryo UI", 8),
                fill="#666666"
            )
        
        total_rows = (len(sorted_persons) + cols - 1) // cols
        total_height = start_y + total_rows * (cal_height + margin) + margin
        total_width = start_x + cols * (cal_width + margin)
        self.personal_canvas.configure(scrollregion=(0, 0, total_width, total_height))

    def _bg_color(self, label_idx: int, dow: int) -> str:
        if label_idx == 0 or label_idx == 9 or label_idx == 10:
            return "#f0f0f0"
        if dow == 5:
            return "#f0f0ff"
        if dow == 6:
            return "#fff0f0"
        return "white"
    
    def _lighten_color(self, color: str, factor: float = 0.6) -> str:
        color = color.lstrip('#')
        if len(color) != 6:
            return "#e0e0e0"
        
        try:
            r = int(color[0:2], 16)
            g = int(color[2:4], 16)
            b = int(color[4:6], 16)
            
            r = int(r * factor + 255 * (1 - factor))
            g = int(g * factor + 255 * (1 - factor))
            b = int(b * factor + 255 * (1 - factor))
            
            return f"#{r:02x}{g:02x}{b:02x}"
        except:
            return "#e0e0e0"

    def _draw_label_column(self, x, row_y):
        label_fg = {
            "当直": "#960000", "明け": "#c04040", "休み": "#000096",
            "ER": "#006400", "外勤": "#640064",
        }
        for i, lbl in enumerate(self.LABELS):
            y1 = row_y + i * self.CELL_H
            y2 = y1 + self.CELL_H
            bg = "#f0f0f0" if (i == 0 or i == 9 or i == 10) else "white"
            self.canvas.create_rectangle(x, y1, x + self.LABEL_COL_W, y2,
                                         fill=bg, outline="gray", tags="grid")
            if lbl:
                fg = label_fg.get(lbl, "black")
                self.canvas.create_text(x + self.LABEL_COL_W / 2, (y1 + y2) / 2,
                                       text=lbl, font=("Meiryo UI", 10, "bold"), fill=fg, tags="grid")
            
            if i == 5:
                self.canvas.create_line(x, y2, x + self.LABEL_COL_W, y2,
                                      fill="#666666", width=2, dash=(4, 4), tags="divider_line")

    def _draw_adjacent_month_block(self, col_x, row_y, day, dow, week, is_prev_month=True):
        """前月末日または翌月初日のブロックを描画（入力可能）"""
        self._day_positions[day] = (week, dow, col_x, row_y)
        
        for li in range(self.BLOCK_H):
            for ci in range(self.BLOCK_W):
                x1 = col_x + ci * self.CELL_W
                y1 = row_y + li * self.CELL_H
                x2 = x1 + self.CELL_W
                y2 = y1 + self.CELL_H
                
                base_bg = self._bg_color(li, dow)
                if base_bg == "white":
                    bg = "#f5f5f5"
                else:
                    bg = self._lighten_color(base_bg, 0.8)
                
                rid = self.canvas.create_rectangle(x1, y1, x2, y2, fill=bg, outline="gray", tags="grid")
                tid = self.canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2, text="",
                                              font=("Meiryo UI", 9), fill="#888888", tags="cell_text")
                
                if li == 0 and ci == 0:
                    if day < 0:
                        display_day = abs(day)
                    else:
                        last_day = calendar.monthrange(self.current_year, self.current_month)[1]
                        display_day = day - last_day
                    
                    self.canvas.create_text(x1 + 3, y1 + 3, anchor="nw", text=str(display_day),
                                           font=("Meiryo UI", 6),
                                           fill="#999999",
                                           tags="day_number")
                
                if li == 5 and ci == 0:
                    line_y = y2
                    block_left = col_x
                    block_right = col_x + self.BLOCK_W * self.CELL_W
                    self.canvas.create_line(block_left, line_y, block_right, line_y,
                                          fill="#666666", width=2, dash=(4, 4), tags="divider_line")
                
                ck = (day, li, ci)
                self._rect_ids[ck] = rid
                self._text_ids[ck] = tid
                self._cell_bounds[ck] = (x1, y1, x2, y2)

    def _draw_day_block(self, col_x, row_y, day, dow, week):
        self._day_positions[day] = (week, dow, col_x, row_y)
        for li in range(self.BLOCK_H):
            for ci in range(self.BLOCK_W):
                x1 = col_x + ci * self.CELL_W
                y1 = row_y + li * self.CELL_H
                x2 = x1 + self.CELL_W
                y2 = y1 + self.CELL_H
                bg = self._bg_color(li, dow)
                rid = self.canvas.create_rectangle(x1, y1, x2, y2, fill=bg, outline="gray", tags="grid")
                tid = self.canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2, text="",
                                              font=("Meiryo UI", 9), tags="cell_text")
                if li == 0 and ci == 0:
                    self.canvas.create_text(x1 + 3, y1 + 3, anchor="nw", text=str(day),
                                           font=("Meiryo UI", 6, "bold"),
                                           fill="blue" if dow == 5 else ("red" if dow == 6 else "black"),
                                           tags="day_number")
                
                if li == 5 and ci == 0:
                    line_y = y2
                    block_left = col_x
                    block_right = col_x + self.BLOCK_W * self.CELL_W
                    self.canvas.create_line(block_left, line_y, block_right, line_y,
                                          fill="#666666", width=2, dash=(4, 4), tags="divider_line")
                
                ck = (day, li, ci)
                self._rect_ids[ck] = rid
                self._text_ids[ck] = tid
                self._cell_bounds[ck] = (x1, y1, x2, y2)

    def _apply_data(self):
        for (day, li, ci), value in self.cell_data.items():
            rid = self._rect_ids.get((day, li, ci))
            tid = self._text_ids.get((day, li, ci))
            color = self.cell_colors.get((day, li, ci), "white")
            if rid:
                self.canvas.itemconfigure(rid, fill=color)
                self.canvas.tag_raise(rid)
            if tid:
                self.canvas.itemconfigure(tid, text=value)
        
        self.canvas.tag_raise("divider_line")
        self._raise_all_text()
        self._redraw_lock_borders()

    def _update_cell_display(self, cell_key):
        rid = self._rect_ids.get(cell_key)
        tid = self._text_ids.get(cell_key)
        
        if cell_key in self.cell_data:
            value = self.cell_data[cell_key]
            color = self.cell_colors[cell_key]
            if rid:
                self.canvas.itemconfigure(rid, fill=color)
                self.canvas.tag_raise(rid)
            if tid:
                self.canvas.itemconfigure(tid, text=value)
                self.canvas.tag_raise(tid)
        else:
            day, li, ci = cell_key
            info = self._day_positions.get(day)
            dow = info[1] if info else 0
            bg = self._bg_color(li, dow)
            if day <= 0 or day > 31:
                if bg == "white":
                    bg = "#f5f5f5"
                else:
                    bg = self._lighten_color(bg, 0.8)
            if rid:
                self.canvas.itemconfigure(rid, fill=bg)
                self.canvas.tag_lower(rid)
            if tid:
                self.canvas.itemconfigure(tid, text="")
                self.canvas.tag_raise(tid)

    def _draw_all_lines(self):
        self.canvas.delete("connection_line")
        
        cells_by_value = defaultdict(list)
        for ck, value in self.cell_data.items():
            cells_by_value[value].append(ck)
        
        for value, cells in cells_by_value.items():
            def zigzag_sort_key(cell):
                day, li, ci = cell
                return (day, ci, li)
            
            sorted_cells = sorted(cells, key=zigzag_sort_key)
            
            for i in range(len(sorted_cells) - 1):
                ck1 = sorted_cells[i]
                ck2 = sorted_cells[i + 1]

                day1, li1, _ = ck1
                day2, li2, _ = ck2

                # 灰色セル（上端・下端行）は結合線を引かない
                if li1 == 0 or li1 == 9 or li1 == 10 or li2 == 0 or li2 == 9 or li2 == 10:
                    continue

                info1 = self._day_positions.get(day1)
                info2 = self._day_positions.get(day2)
                
                if info1 is None or info2 is None:
                    continue
                
                week1 = info1[0]
                week2 = info2[0]
                
                if week1 != week2:
                    continue
                
                bounds1 = self._cell_bounds.get(ck1)
                bounds2 = self._cell_bounds.get(ck2)
                
                if bounds1 and bounds2:
                    x1_start, y1_start, x1_end, y1_end = bounds1
                    x2_start, y2_start, x2_end, y2_end = bounds2
                    
                    x1_c = (x1_start + x1_end) / 2
                    y1_c = (y1_start + y1_end) / 2
                    x2_c = (x2_start + x2_end) / 2
                    y2_c = (y2_start + y2_end) / 2
                    
                    if x2_c > x1_end:
                        x1 = x1_end
                        y1 = y1_c
                    elif x2_c < x1_start:
                        x1 = x1_start
                        y1 = y1_c
                    elif y2_c > y1_end:
                        x1 = x1_c
                        y1 = y1_end
                    elif y2_c < y1_start:
                        x1 = x1_c
                        y1 = y1_start
                    else:
                        x1 = x1_c
                        y1 = y1_c
                    
                    if x1_c > x2_end:
                        x2 = x2_end
                        y2 = y2_c
                    elif x1_c < x2_start:
                        x2 = x2_start
                        y2 = y2_c
                    elif y1_c > y2_end:
                        x2 = x2_c
                        y2 = y2_end
                    elif y1_c < y2_start:
                        x2 = x2_c
                        y2 = y2_start
                    else:
                        x2 = x2_c
                        y2 = y2_c
                    
                    line_color = self.cell_colors.get(ck1, "blue")
                    
                    self.canvas.create_line(x1, y1, x2, y2,
                                           fill=line_color, width=2, tags="connection_line")
        
        self.canvas.tag_raise("connection_line", "grid")
        
        for ck in self.cell_data.keys():
            rid = self._rect_ids.get(ck)
            if rid:
                self.canvas.tag_raise(rid)
        
        self.canvas.tag_raise("divider_line")
        self._raise_all_text()
        self._redraw_lock_borders()
    
    def _raise_all_text(self):
        for ck, tid in self._text_ids.items():
            if tid:
                self.canvas.tag_raise(tid)

    def _cell_at(self, cx, cy) -> Optional[CellKey]:
        for ck, (x1, y1, x2, y2) in self._cell_bounds.items():
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                return ck
        return None

    def _on_click(self, event):
        self._finish_edit()
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        ck = self._cell_at(cx, cy)
        if ck is not None and ck in self.cell_data:
            self._drag_source = ck
            self._drag_start_cx = cx
            self._drag_start_cy = cy
            self._dragging = False

    def _on_motion(self, event):
        if self._drag_source is None:
            return
        
        if self._drag_source in self.locked_cells:
            return
        
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        dx = abs(cx - self._drag_start_cx)
        dy = abs(cy - self._drag_start_cy)
        if not self._dragging and (dx > self.DRAG_THRESHOLD or dy > self.DRAG_THRESHOLD):
            self._dragging = True
            self._show_drag_ghost(self._drag_source, cx, cy)
        if self._dragging:
            self._update_drag_ghost(cx, cy)
            drop_ck = self._cell_at(cx, cy)
            self._update_drop_highlight(drop_ck)

    def _on_release(self, event):
        if not self._dragging:
            if self._drag_source is not None:
                self._toggle_selection(self._drag_source)
            self._drag_source = None
            return
        
        if self._drag_source in self.locked_cells:
            self._drag_source = None
            self._dragging = False
            self._clear_drag_visuals()
            return
        
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        drop_ck = self._cell_at(cx, cy)
        
        if drop_ck and drop_ck in self.locked_cells:
            self._drag_source = None
            self._dragging = False
            self._clear_drag_visuals()
            messagebox.showwarning("ロック中", "このセルはロックされているため移動できません")
            return
        
        if drop_ck and self._drag_source:
            self._save_state()
            
            self._remove_special_border(self._drag_source)
            self._remove_special_border(drop_ck)
            
            src_val = self.cell_data.get(self._drag_source, "")
            src_color = self.cell_colors.get(self._drag_source, "white")
            src_seq = self.cell_sequence.get(self._drag_source, None)
            src_er = self._drag_source in self.er_marks
            dst_val = self.cell_data.get(drop_ck, "")
            dst_color = self.cell_colors.get(drop_ck, "white")
            dst_seq = self.cell_sequence.get(drop_ck, None)
            dst_er = drop_ck in self.er_marks
            
            if dst_val:
                self.cell_data[self._drag_source] = dst_val
                self.cell_colors[self._drag_source] = dst_color
                if dst_seq is not None:
                    self.cell_sequence[self._drag_source] = dst_seq
                else:
                    self.cell_sequence.pop(self._drag_source, None)
                if dst_er:
                    self.er_marks.add(self._drag_source)
                else:
                    self.er_marks.discard(self._drag_source)
            else:
                self.cell_data.pop(self._drag_source, None)
                self.cell_colors.pop(self._drag_source, None)
                self.cell_sequence.pop(self._drag_source, None)
                self.er_marks.discard(self._drag_source)
            
            if src_val:
                self.cell_data[drop_ck] = src_val
                self.cell_colors[drop_ck] = src_color
                if src_seq is not None:
                    self.cell_sequence[drop_ck] = src_seq
                if src_er:
                    self.er_marks.add(drop_ck)
            else:
                self.cell_data.pop(drop_ck, None)
                self.cell_colors.pop(drop_ck, None)
                self.cell_sequence.pop(drop_ck, None)
                self.er_marks.discard(drop_ck)
            
            self._update_cell_display(self._drag_source)
            self._update_cell_display(drop_ck)
            self._draw_all_lines()
            
            _, drop_li, _ = drop_ck
            drop_label = self.LABELS[drop_li] if drop_li < len(self.LABELS) else ""
            if drop_label and drop_label.strip():
                self.sound_manager.play_for_label(drop_label)
            else:
                self.sound_manager.play("move")
            
            self.draw_statistics()
            self._clear_selection()
        self._drag_source = None
        self._dragging = False
        self._clear_drag_visuals()

    def _show_drag_ghost(self, ck, cx, cy):
        val = self.cell_data.get(ck, "")
        color = self.cell_colors.get(ck, "white")
        bounds = self._cell_bounds.get(ck)
        if not bounds:
            return
        x1, y1, x2, y2 = bounds
        w = x2 - x1
        h = y2 - y1
        self._drag_ghost_rect = self.canvas.create_rectangle(
            cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2,
            fill=color, outline="blue", width=2, stipple="gray50", tags="drag_ghost"
        )
        self._drag_ghost_text = self.canvas.create_text(
            cx, cy, text=val, font=("Meiryo UI", 9), tags="drag_ghost"
        )

    def _update_drag_ghost(self, cx, cy):
        if self._drag_ghost_rect:
            bounds = self._cell_bounds.get(self._drag_source, (0, 0, 60, 25))
            x1, y1, x2, y2 = bounds
            w = x2 - x1
            h = y2 - y1
            self.canvas.coords(self._drag_ghost_rect, cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        if self._drag_ghost_text:
            self.canvas.coords(self._drag_ghost_text, cx, cy)

    def _update_drop_highlight(self, drop_ck):
        if self._drag_highlight:
            self.canvas.delete(self._drag_highlight)
            self._drag_highlight = None
        if drop_ck and drop_ck != self._drag_source:
            bounds = self._cell_bounds.get(drop_ck)
            if bounds:
                x1, y1, x2, y2 = bounds
                self._drag_highlight = self.canvas.create_rectangle(
                    x1, y1, x2, y2, outline="red", width=3, tags="drag_highlight"
                )

    def _clear_drag_visuals(self):
        self.canvas.delete("drag_ghost")
        self.canvas.delete("drag_highlight")
        self._drag_ghost_rect = None
        self._drag_ghost_text = None
        self._drag_highlight = None
    
    def _toggle_selection(self, cell_key):
        if cell_key not in self.cell_data:
            if self.selected_value is not None:
                self._clear_selection()
            return

        # 灰色セル（上端・下端行）はハイライト対象外
        _, li, _ = cell_key
        if li == 0 or li == 9 or li == 10:
            return

        clicked_value = self.cell_data[cell_key]
        
        if self.selected_value == clicked_value:
            self._clear_selection()
        else:
            self.selected_value = clicked_value
            self._apply_selection_mask()
    
    def _apply_selection_mask(self):
        if self.selected_value is None:
            return
        
        for ck, value in self.cell_data.items():
            rid = self._rect_ids.get(ck)
            tid = self._text_ids.get(ck)
            
            if value != self.selected_value:
                original_color = self.cell_colors.get(ck, "white")
                masked_color = self._lighten_color(original_color, self.mask_opacity)
                if rid:
                    self.canvas.itemconfigure(rid, fill=masked_color)
                if tid:
                    self.canvas.itemconfigure(tid, fill="#cccccc")
        
        self._apply_line_mask()
    
    def _apply_line_mask(self):
        if self.selected_value is None:
            return
        
        self.canvas.delete("connection_line")
        self.canvas.delete("connection_line_selected")  # 選択された線も削除
        
        cells_by_value = defaultdict(list)
        for ck, value in self.cell_data.items():
            cells_by_value[value].append(ck)
        
        # 非選択のセルの線を先に描画
        for value, cells in cells_by_value.items():
            if value == self.selected_value:
                continue  # 選択されたセルは後で描画
            
            def zigzag_sort_key(cell):
                day, li, ci = cell
                return (day, ci, li)
            
            sorted_cells = sorted(cells, key=zigzag_sort_key)
            
            original_color = self.cell_colors.get(sorted_cells[0], "blue")
            line_color = self._lighten_color(original_color, self.mask_opacity)
            
            for i in range(len(sorted_cells) - 1):
                ck1 = sorted_cells[i]
                ck2 = sorted_cells[i + 1]

                day1, li1, _ = ck1
                day2, li2, _ = ck2

                # 灰色セル（上端・下端行）は結合線を引かない
                if li1 == 0 or li1 == 9 or li1 == 10 or li2 == 0 or li2 == 9 or li2 == 10:
                    continue

                info1 = self._day_positions.get(day1)
                info2 = self._day_positions.get(day2)
                
                if info1 is None or info2 is None:
                    continue
                
                week1 = info1[0]
                week2 = info2[0]
                
                if week1 != week2:
                    continue
                
                bounds1 = self._cell_bounds.get(ck1)
                bounds2 = self._cell_bounds.get(ck2)
                
                if bounds1 and bounds2:
                    x1_start, y1_start, x1_end, y1_end = bounds1
                    x2_start, y2_start, x2_end, y2_end = bounds2
                    
                    x1_c = (x1_start + x1_end) / 2
                    y1_c = (y1_start + y1_end) / 2
                    x2_c = (x2_start + x2_end) / 2
                    y2_c = (y2_start + y2_end) / 2
                    
                    if x2_c > x1_end:
                        x1 = x1_end
                        y1 = y1_c
                    elif x2_c < x1_start:
                        x1 = x1_start
                        y1 = y1_c
                    elif y2_c > y1_end:
                        x1 = x1_c
                        y1 = y1_end
                    elif y2_c < y1_start:
                        x1 = x1_c
                        y1 = y1_start
                    else:
                        x1 = x1_c
                        y1 = y1_c
                    
                    if x1_c > x2_end:
                        x2 = x2_end
                        y2 = y2_c
                    elif x1_c < x2_start:
                        x2 = x2_start
                        y2 = y2_c
                    elif y1_c > y2_end:
                        x2 = x2_c
                        y2 = y2_end
                    elif y1_c < y2_start:
                        x2 = x2_c
                        y2 = y2_start
                    else:
                        x2 = x2_c
                        y2 = y2_c
                    
                    self.canvas.create_line(x1, y1, x2, y2,
                                           fill=line_color, width=2, tags="connection_line")
        
        # 非選択セルの線をgridより前面に配置
        self.canvas.tag_raise("connection_line", "grid")
        
        # 非選択セルの矩形を前面に配置（選択されたセルの矩形は除く）
        for ck in self.cell_data.keys():
            if self.cell_data.get(ck) != self.selected_value:
                rid = self._rect_ids.get(ck)
                if rid:
                    self.canvas.tag_raise(rid)
        
        # 選択されたセルの線を描画（最前面）
        if self.selected_value in cells_by_value:
            cells = cells_by_value[self.selected_value]
            
            def zigzag_sort_key(cell):
                day, li, ci = cell
                return (day, ci, li)
            
            sorted_cells = sorted(cells, key=zigzag_sort_key)
            line_color = self.cell_colors.get(sorted_cells[0], "blue")
            
            for i in range(len(sorted_cells) - 1):
                ck1 = sorted_cells[i]
                ck2 = sorted_cells[i + 1]

                day1, li1, _ = ck1
                day2, li2, _ = ck2

                # 灰色セル（上端・下端行）は結合線を引かない
                if li1 == 0 or li1 == 9 or li1 == 10 or li2 == 0 or li2 == 9 or li2 == 10:
                    continue

                info1 = self._day_positions.get(day1)
                info2 = self._day_positions.get(day2)
                
                if info1 is None or info2 is None:
                    continue
                
                week1 = info1[0]
                week2 = info2[0]
                
                if week1 != week2:
                    continue
                
                bounds1 = self._cell_bounds.get(ck1)
                bounds2 = self._cell_bounds.get(ck2)
                
                if bounds1 and bounds2:
                    x1_start, y1_start, x1_end, y1_end = bounds1
                    x2_start, y2_start, x2_end, y2_end = bounds2
                    
                    x1_c = (x1_start + x1_end) / 2
                    y1_c = (y1_start + y1_end) / 2
                    x2_c = (x2_start + x2_end) / 2
                    y2_c = (y2_start + y2_end) / 2
                    
                    if x2_c > x1_end:
                        x1 = x1_end
                        y1 = y1_c
                    elif x2_c < x1_start:
                        x1 = x1_start
                        y1 = y1_c
                    elif y2_c > y1_end:
                        x1 = x1_c
                        y1 = y1_end
                    elif y2_c < y1_start:
                        x1 = x1_c
                        y1 = y1_start
                    else:
                        x1 = x1_c
                        y1 = y1_c
                    
                    if x1_c > x2_end:
                        x2 = x2_end
                        y2 = y2_c
                    elif x1_c < x2_start:
                        x2 = x2_start
                        y2 = y2_c
                    elif y1_c > y2_end:
                        x2 = x2_c
                        y2 = y2_end
                    elif y1_c < y2_start:
                        x2 = x2_c
                        y2 = y2_start
                    else:
                        x2 = x2_c
                        y2 = y2_c
                    
                    # 選択されたセルの線は太く、専用タグで描画
                    self.canvas.create_line(x1, y1, x2, y2,
                                           fill=line_color, width=3, tags="connection_line_selected")
            
            # 選択されたセルの矩形を最前面に配置
            for ck in cells:
                rid = self._rect_ids.get(ck)
                if rid:
                    self.canvas.tag_raise(rid)
        
        # 区切り線とテキストを最前面に
        self.canvas.tag_raise("divider_line")
        self.canvas.tag_raise("connection_line_selected")  # 選択された線を最前面に
        self._raise_all_text()
        self._redraw_lock_borders()
    
    def _clear_selection(self):
        self.selected_value = None
        
        # 選択された線のタグも削除
        self.canvas.delete("connection_line_selected")
        
        for ck, value in self.cell_data.items():
            rid = self._rect_ids.get(ck)
            tid = self._text_ids.get(ck)
            original_color = self.cell_colors.get(ck, "white")
            
            if rid:
                self.canvas.itemconfigure(rid, fill=original_color)
            if tid:
                self.canvas.itemconfigure(tid, fill="black")
        
        self._draw_all_lines()
    
    def _add_lock(self, cell_key):
        if cell_key not in self.locked_cells:
            self.locked_cells.add(cell_key)
            self._draw_lock_border(cell_key)
            messagebox.showinfo("ロック", "このセルをロックしました")
    
    def _remove_lock(self, cell_key):
        if cell_key in self.locked_cells:
            self.locked_cells.discard(cell_key)
            if cell_key in self.locked_cell_borders:
                border_id = self.locked_cell_borders[cell_key]
                self.canvas.delete(border_id)
                del self.locked_cell_borders[cell_key]
            messagebox.showinfo("ロック解除", "このセルのロックを解除しました")
    
    def _draw_lock_border(self, cell_key):
        bounds = self._cell_bounds.get(cell_key)
        if not bounds:
            return
        
        x1, y1, x2, y2 = bounds
        
        border_id = self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline="black",
            width=3,
            tags="lock_border"
        )
        
        self.locked_cell_borders[cell_key] = border_id
        
        self.canvas.tag_raise("lock_border")
        self._raise_all_text()
    
    def _redraw_lock_borders(self):
        for border_id in self.locked_cell_borders.values():
            self.canvas.delete(border_id)
        self.locked_cell_borders.clear()
        
        for cell_key in list(self.locked_cells):
            if cell_key not in self.cell_data:
                self.locked_cells.discard(cell_key)
                continue
            
            self._draw_lock_border(cell_key)
        
        self.canvas.tag_raise("lock_border")
        self.canvas.tag_raise("special_border")
        self._raise_all_text()
    
    def _show_gray_cell_menu(self, event, ck):
        """灰色セル（上端・下端行）の右クリックメニュー：カスケード方式"""
        ICONS = {"外勤": "🚗", "委員会": "🏛", "コース": "📚", "訓練": "🎯"}
        popup = tk.Menu(self.root, tearoff=0)

        # ─── ドクターカー（固定項目・最上段）───
        popup.add_command(
            label="🚑 ドクターカー",
            command=lambda c=ck: self._set_gray_cell_text(c, "D/C")
        )
        popup.add_separator()

        has_any_item = any(len(self.special_items[cat]) > 0
                           for cat in ["外勤", "委員会", "コース", "訓練"])

        for cat in ["外勤", "委員会", "コース", "訓練"]:
            icon = ICONS[cat]
            sub = tk.Menu(popup, tearoff=0)
            items = self.special_items[cat]

            if items:
                for item in items:
                    # クロージャのためにデフォルト引数でキャプチャ
                    sub.add_command(
                        label=item,
                        command=lambda c=ck, t=item: self._set_gray_cell_text(c, t)
                    )
                sub.add_separator()
                sub.add_command(
                    label="（クリア）",
                    command=lambda c=ck: self._set_gray_cell_text(c, "")
                )
            else:
                sub.add_command(
                    label=f"（{cat}の項目未登録）",
                    state=tk.DISABLED
                )
                sub.add_command(
                    label=f"→ {cat}を登録する...",
                    command=lambda c=cat: self._open_special_item_window(c)
                )

            popup.add_cascade(label=f"{icon} {cat}", menu=sub)

        # 現在のセルに値が入っていたらクリアオプションも
        current_val = self.cell_data.get(ck, "")
        if current_val.strip():
            popup.add_separator()
            popup.add_command(
                label="✖ このセルをクリア",
                command=lambda c=ck: self._set_gray_cell_text(c, "")
            )

        try:
            popup.tk_popup(event.x_root, event.y_root)
        finally:
            popup.grab_release()

    def _set_gray_cell_text(self, ck, text: str):
        """灰色セルにテキストをセットする"""
        self._save_state()
        if text:
            self.cell_data[ck] = text
            self.cell_colors[ck] = "#d8d8d8"
        else:
            self.cell_data.pop(ck, None)
            self.cell_colors.pop(ck, None)
        self._update_cell_display(ck)
        self.draw_statistics()

    def _open_all_special_windows(self):
        """全カテゴリの管理ウィンドウを開く（項目管理のショートカット）"""
        # 最初のカテゴリだけ開く（ユーザーが選べる）
        cats = ["外勤", "委員会", "コース", "訓練"]
        # まだ開いていない最初のカテゴリを開く
        for cat in cats:
            win = self._special_item_windows.get(cat)
            if not (win and tk.Toplevel.winfo_exists(win)):
                self._open_special_item_window(cat)
                return
        # 全部開いていたら最初のものを前面に
        self._open_special_item_window(cats[0])

    def _on_right_click(self, event):
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        ck = self._cell_at(cx, cy)

        if ck is None:
            return

        day, li, ci = ck
        # 灰色行（上端/下端）は特別メニュー
        if li == 0 or li == 9 or li == 10:
            self._show_gray_cell_menu(event, ck)
            return

        popup = tk.Menu(self.root, tearoff=0)

        # ── セルに値がある場合: ロック / 枠線 ──
        if ck in self.cell_data:
            if ck in self.locked_cells:
                popup.add_command(label="🔓 ロック解除",
                                  command=lambda: self._remove_lock(ck))
            else:
                popup.add_command(label="🔒 ロック",
                                  command=lambda: self._add_lock(ck))

            popup.add_separator()
            current_border = self.special_borders.get(ck, '')
            dc_check  = "✔ " if current_border in ('doctor_car', 'both') else "　"
            ang_check = "✔ " if current_border in ('angio_call', 'both') else "　"
            popup.add_command(label=f"{dc_check}ドクターカー",
                              command=lambda: self._toggle_special_border(ck, 'doctor_car'))
            popup.add_command(label=f"{ang_check}アンギオコール",
                              command=lambda: self._toggle_special_border(ck, 'angio_call'))
            popup.add_separator()
            popup.add_command(label="枠線を解除",
                              command=lambda: self._remove_special_border(ck))
            popup.add_separator()

        # ── メンバー選択サブメニュー（A / B / 非常勤） ──
        team_defs = [
            ("A",   "🔵 Aチーム",   "#1d4ed8"),
            ("B",   "🟢 Bチーム",   "#15803d"),
            ("非常勤", "⬜ 非常勤",  "#78716c"),
        ]
        for team_key, team_label, team_color in team_defs:
            team_members = [m for m in self.members_data
                            if m.get("active", True) and m.get("team", "A") == team_key]
            sub = tk.Menu(popup, tearoff=0)
            if team_members:
                for m in team_members:
                    dname = m["display_name"]
                    sub.add_command(
                        label=dname,
                        command=lambda k=ck, d=dname, c=m.get("color","#cccccc"):
                                self._set_cell_from_menu(k, d, c)
                    )
            else:
                sub.add_command(label="（メンバーなし）", state=tk.DISABLED)
            popup.add_cascade(label=team_label, menu=sub)

        # セルをクリアするオプション
        if ck in self.cell_data and self.cell_data[ck].strip():
            popup.add_separator()
            popup.add_command(label="✖ クリア",
                              command=lambda k=ck: self._clear_cell_from_menu(k))

        try:
            popup.tk_popup(event.x_root, event.y_root)
        finally:
            popup.grab_release()

    def _set_cell_from_menu(self, ck, member_name: str, color: str):
        """右クリックメニューからメンバーをセルに入力"""
        if ck in self.locked_cells:
            messagebox.showwarning("ロック中", "このセルはロックされています")
            return
        self._save_state()
        self.cell_data[ck]   = member_name
        self.cell_colors[ck] = color
        if ck not in self.cell_sequence:
            self.cell_sequence[ck] = self.next_sequence
            self.next_sequence += 1
        self._update_cell_display(ck)
        self._draw_all_lines()
        _, li, _ = ck
        lbl = self.LABELS[li] if li < len(self.LABELS) else ""
        if lbl and lbl.strip():
            self.sound_manager.play_for_label(lbl)
        self.draw_statistics()

    def _clear_cell_from_menu(self, ck):
        """右クリックメニューからセルをクリア"""
        if ck in self.locked_cells:
            messagebox.showwarning("ロック中", "このセルはロックされています")
            return
        self._save_state()
        self.cell_data.pop(ck, None)
        self.cell_colors.pop(ck, None)
        self.cell_sequence.pop(ck, None)
        self.er_marks.discard(ck)
        self._update_cell_display(ck)
        self._draw_all_lines()
        self.draw_statistics()
    
    def _draw_border_visual(self, cell_key, border_type):
        """枠線を描画してcanvasアイテムIDのリストを返す"""
        bounds = self._cell_bounds.get(cell_key)
        if not bounds:
            return []
        x1, y1, x2, y2 = bounds
        ids = []

        PINK = "#FF1493"   # ドクターカー
        BLUE = "#00BFFF"   # アンギオコール
        W = 4              # 線幅

        if border_type == 'doctor_car':
            ids.append(self.canvas.create_rectangle(
                x1, y1, x2, y2, outline=PINK, width=W, tags="special_border"))

        elif border_type == 'angio_call':
            ids.append(self.canvas.create_rectangle(
                x1, y1, x2, y2, outline=BLUE, width=W, tags="special_border"))

        elif border_type == 'both':
            # 上辺・左辺 → ピンク（ドクターカー）
            ids.append(self.canvas.create_line(
                x1, y1, x2, y1, fill=PINK, width=W, tags="special_border"))  # 上
            ids.append(self.canvas.create_line(
                x1, y1, x1, y2, fill=PINK, width=W, tags="special_border"))  # 左
            # 下辺・右辺 → 青（アンギオコール）
            ids.append(self.canvas.create_line(
                x1, y2, x2, y2, fill=BLUE, width=W, tags="special_border"))  # 下
            ids.append(self.canvas.create_line(
                x2, y1, x2, y2, fill=BLUE, width=W, tags="special_border"))  # 右

        return ids

    def _toggle_special_border(self, cell_key, border_type):
        """ドクターカー/アンギオコールをトグル。両方ONで'both'状態にする"""
        current = self.special_borders.get(cell_key, '')

        if current == '':
            new_type = border_type
        elif current == border_type:
            # 同じものをもう一度→解除
            self._remove_special_border(cell_key)
            return
        elif current == 'both':
            # 'both'から片方を外す
            if border_type == 'doctor_car':
                new_type = 'angio_call'
            else:
                new_type = 'doctor_car'
        else:
            # 別の種類が入っている→両方に
            new_type = 'both'

        self._remove_special_border(cell_key)
        ids = self._draw_border_visual(cell_key, new_type)
        self.special_borders[cell_key] = new_type
        self.special_border_ids[cell_key] = ids
        self.canvas.tag_raise("special_border")
        self._raise_all_text()

        if new_type == 'doctor_car':
            self.sound_manager.play("vroom")
        elif new_type == 'angio_call':
            self.sound_manager.play("sheen")
        elif new_type == 'both':
            self.sound_manager.play("vroom")

    def _add_special_border(self, cell_key, border_type):
        """後方互換用（旧コードから呼ばれる可能性があるため残す）"""
        self._remove_special_border(cell_key)
        ids = self._draw_border_visual(cell_key, border_type)
        self.special_borders[cell_key] = border_type
        self.special_border_ids[cell_key] = ids
        self.canvas.tag_raise("special_border")
        self._raise_all_text()
        if border_type == 'doctor_car':
            self.sound_manager.play("vroom")
        elif border_type == 'angio_call':
            self.sound_manager.play("sheen")

    def _remove_special_border(self, cell_key):
        if cell_key in self.special_border_ids:
            for item_id in self.special_border_ids[cell_key]:
                self.canvas.delete(item_id)
            del self.special_border_ids[cell_key]
        if cell_key in self.special_borders:
            del self.special_borders[cell_key]

    def _redraw_special_borders(self):
        for ids in self.special_border_ids.values():
            for item_id in ids:
                self.canvas.delete(item_id)
        self.special_border_ids.clear()

        for cell_key, border_type in list(self.special_borders.items()):
            if cell_key not in self.cell_data:
                del self.special_borders[cell_key]
                continue
            bounds = self._cell_bounds.get(cell_key)
            if not bounds:
                continue
            ids = self._draw_border_visual(cell_key, border_type)
            self.special_border_ids[cell_key] = ids

        self.canvas.tag_raise("special_border")
        self._raise_all_text()

    def _on_double_click(self, event):
        self._drag_source = None
        self._dragging = False
        self._clear_drag_visuals()
        self._clear_selection()
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        ck = self._cell_at(cx, cy)
        if ck is None: return
        self._finish_edit()
        self._start_edit(ck)

    def _start_edit(self, cell_key):
        self._save_state()
        
        bounds = self._cell_bounds.get(cell_key)
        if bounds is None: return
        x1, y1, x2, y2 = bounds
        current_val = self.cell_data.get(cell_key, "")
        color = self.cell_colors.get(cell_key, "white")
        self._edit_entry = tk.Entry(self.canvas, font=("Meiryo UI", 9),
                                    justify=tk.CENTER, bg=color)
        self._edit_entry.insert(0, current_val)
        self._edit_entry.select_range(0, tk.END)
        self._edit_entry.focus_set()
        self._edit_entry.bind("<Return>", lambda e: self._finish_edit())
        self._edit_entry.bind("<Escape>", lambda e: self._cancel_edit())
        self._edit_entry.bind("<Tab>", lambda e: self._tab_to_next(e))
        self._edit_window_id = self.canvas.create_window(
            (x1 + x2) / 2, (y1 + y2) / 2,
            window=self._edit_entry,
            width=x2 - x1 - 2, height=y2 - y1 - 2,
            tags="edit_entry"
        )
        self._edit_key = cell_key

    def _tab_to_next(self, event):
        if self._edit_key is None: return "break"
        day, li, ci = self._edit_key
        self._finish_edit()
        next_key = (day, li, ci + 1)
        if next_key not in self._cell_bounds: next_key = (day, li + 1, 0)
        if next_key in self._cell_bounds: self._start_edit(next_key)
        return "break"

    def _finish_edit(self):
        if self._edit_entry is None: return
        new_val = self._edit_entry.get().strip()
        ck = self._edit_key
        self.canvas.delete("edit_entry")
        self._edit_entry.destroy()
        self._edit_entry = None
        self._edit_key = None
        if ck is None: return
        old_val = self.cell_data.get(ck, "")
        if new_val == old_val: return
        rid = self._rect_ids.get(ck)
        tid = self._text_ids.get(ck)
        if not new_val:
            self.cell_data.pop(ck, None)
            self.cell_colors.pop(ck, None)
            self.cell_sequence.pop(ck, None)
            self.er_marks.discard(ck)
            if rid:
                day, li, ci = ck
                info = self._day_positions.get(day)
                dow = info[1] if info else 0
                bg = self._bg_color(li, dow)
                if day <= 0 or day > 31:
                    if bg == "white":
                        bg = "#f5f5f5"
                    else:
                        bg = self._lighten_color(bg, 0.8)
                self.canvas.itemconfigure(rid, fill=bg)
            if tid: self.canvas.itemconfigure(tid, text="")
        else:
            self.cell_data[ck] = new_val
            if ck not in self.cell_sequence:
                self.cell_sequence[ck] = self.next_sequence
                self.next_sequence += 1
            color = self._get_or_assign_color(new_val)
            self.cell_colors[ck] = color
            if rid: self.canvas.itemconfigure(rid, fill=color)
            if tid: self.canvas.itemconfigure(tid, text=new_val)
            
            day, li, ci = ck
            if day == 1 and li >= 1 and li <= 7:
                self._auto_replicate(new_val, color, li, ci)
        
        self._draw_all_lines()
        self.draw_statistics()
        self._clear_selection()

    def _auto_replicate(self, value, color, label_idx, col_idx):
        last_day = calendar.monthrange(self.current_year, self.current_month)[1]
        
        for target_day in range(2, last_day + 1):
            target_key = (target_day, label_idx, col_idx)
            
            if target_key in self.cell_data:
                continue
            
            self.cell_data[target_key] = value
            self.cell_colors[target_key] = color
            
            if target_key not in self.cell_sequence:
                self.cell_sequence[target_key] = self.next_sequence
                self.next_sequence += 1
            
            self._update_cell_display(target_key)

    def _cancel_edit(self):
        if self._edit_entry:
            self.canvas.delete("edit_entry")
            self._edit_entry.destroy()
            self._edit_entry = None
            self._edit_key = None
            # _start_edit が事前に _save_state() を呼んでいるため、
            # キャンセル時は積んだ状態を取り消してundo履歴を汚染しない
            if self.undo_stack:
                self.undo_stack.pop()

    def _get_or_assign_color(self, value):
        if value in self.value_colors: return self.value_colors[value]
        # パステルカラー生成:
        # 色相をハッシュで決定し、彩度低め・明度高めで生成
        import hashlib
        h = int(hashlib.md5(value.encode()).hexdigest()[:6], 16)
        hue = (h % 360) / 360.0
        # HSL → RGB (s=0.45, l=0.88)
        s, l = 0.45, 0.88
        if s == 0:
            rv = gv = bv = l
        else:
            def hue2rgb(p, q, t):
                if t < 0: t += 1
                if t > 1: t -= 1
                if t < 1/6: return p + (q - p) * 6 * t
                if t < 1/2: return q
                if t < 2/3: return p + (q - p) * (2/3 - t) * 6
                return p
            q = l + s - l * s
            p = 2 * l - q
            rv = hue2rgb(p, q, hue + 1/3)
            gv = hue2rgb(p, q, hue)
            bv = hue2rgb(p, q, hue - 1/3)
        r, g, b = int(rv*255), int(gv*255), int(bv*255)
        color = f"#{r:02x}{g:02x}{b:02x}"
        self.value_colors[value] = color
        return color

    def _save_state(self):
        state = {
            'cell_data': copy.deepcopy(self.cell_data),
            'cell_colors': copy.deepcopy(self.cell_colors),
            'cell_sequence': copy.deepcopy(self.cell_sequence),
            'er_marks': copy.deepcopy(self.er_marks),
            'value_colors': copy.deepcopy(self.value_colors),
            'next_sequence': self.next_sequence,
            'locked_cells': copy.deepcopy(self.locked_cells),
            'completed_days': copy.deepcopy(self.completed_days),
        }
        self.undo_stack.append(state)
        
        if len(self.undo_stack) > self.max_history:
            self.undo_stack.pop(0)
        
        self.redo_stack.clear()
    
    def undo(self):
        if not self.undo_stack:
            messagebox.showinfo("情報", "これ以上戻せません")
            return
        
        current_state = {
            'cell_data': copy.deepcopy(self.cell_data),
            'cell_colors': copy.deepcopy(self.cell_colors),
            'cell_sequence': copy.deepcopy(self.cell_sequence),
            'er_marks': copy.deepcopy(self.er_marks),
            'value_colors': copy.deepcopy(self.value_colors),
            'next_sequence': self.next_sequence,
            'locked_cells': copy.deepcopy(self.locked_cells),
            'completed_days': copy.deepcopy(self.completed_days),
        }
        self.redo_stack.append(current_state)
        
        previous_state = self.undo_stack.pop()
        self.cell_data = previous_state['cell_data']
        self.cell_colors = previous_state['cell_colors']
        self.cell_sequence = previous_state['cell_sequence']
        self.er_marks = previous_state['er_marks']
        self.value_colors = previous_state['value_colors']
        self.next_sequence = previous_state['next_sequence']
        self.locked_cells = previous_state.get('locked_cells', set())
        self.completed_days = previous_state.get('completed_days', set())
        
        self._redraw_all_cells()
        self.draw_statistics()
        self._clear_selection()
    
    def redo(self):
        if not self.redo_stack:
            messagebox.showinfo("情報", "これ以上進めません")
            return
        
        current_state = {
            'cell_data': copy.deepcopy(self.cell_data),
            'cell_colors': copy.deepcopy(self.cell_colors),
            'cell_sequence': copy.deepcopy(self.cell_sequence),
            'er_marks': copy.deepcopy(self.er_marks),
            'value_colors': copy.deepcopy(self.value_colors),
            'next_sequence': self.next_sequence,
            'locked_cells': copy.deepcopy(self.locked_cells),
            'completed_days': copy.deepcopy(self.completed_days),
        }
        self.undo_stack.append(current_state)
        
        next_state = self.redo_stack.pop()
        self.cell_data = next_state['cell_data']
        self.cell_colors = next_state['cell_colors']
        self.cell_sequence = next_state['cell_sequence']
        self.er_marks = next_state['er_marks']
        self.value_colors = next_state['value_colors']
        self.next_sequence = next_state['next_sequence']
        self.locked_cells = next_state.get('locked_cells', set())
        self.completed_days = next_state.get('completed_days', set())
        
        self._redraw_all_cells()
        self.draw_statistics()
        self._clear_selection()
    
    def _redraw_all_cells(self):
        for ck in self._rect_ids.keys():
            rid = self._rect_ids.get(ck)
            tid = self._text_ids.get(ck)
            day, li, ci = ck
            info = self._day_positions.get(day)
            if info:
                dow = info[1]
                bg = self._bg_color(li, dow)
                if day <= 0 or day > 31:
                    if bg == "white":
                        bg = "#f5f5f5"
                    else:
                        bg = self._lighten_color(bg, 0.8)
                if rid:
                    self.canvas.itemconfigure(rid, fill=bg)
                    self.canvas.tag_lower(rid)
                if tid:
                    self.canvas.itemconfigure(tid, text="")
        
        for ck, value in self.cell_data.items():
            rid = self._rect_ids.get(ck)
            tid = self._text_ids.get(ck)
            color = self.cell_colors.get(ck, "#ffffff")
            if rid:
                self.canvas.itemconfigure(rid, fill=color)
                self.canvas.tag_raise(rid)
            if tid:
                self.canvas.itemconfigure(tid, text=value)
        
        self._draw_all_lines()
        self._redraw_lock_borders()
        self._redraw_day_complete_markers()

    def clear_data(self):
        if messagebox.askyesno("確認", "すべてのデータをクリアしますか？"):
            self.cell_data.clear()
            self.cell_colors.clear()
            self.cell_sequence.clear()
            self.er_marks.clear()
            self.value_colors = {
                "ER": "#98fb98",
                "A": "#ffcc99",
                "B": "#add8e6",
                "当直": "#ffb6c1",
                "外勤": "#dda0dd",
                "出張": "#f0e68c",
                "休み": "#e0ffff",
                "秋": "#FFE4B2",
                "桜": "#FFD1DC",
                "小": "#D8D8E8",
                "金": "#C5EDD6",
                "坪": "#FFDCB5",
                "東": "#DDD0F5",
                "長": "#BDE3F8",
                "矢": "#FFF0B5",
                "宮": "#E0E0E0",
            }
            self.next_sequence = 1
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.special_borders.clear()
            self.special_border_ids.clear()
            self.locked_cells.clear()
            self.locked_cell_borders.clear()
            self.completed_days.clear()
            self.day_complete_rects.clear()
            self.create_calendar()
            self.draw_statistics()

    def save_data(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"calendar_{self.current_year}_{self.current_month}.json"
        )
        if not filename: return
        data = {
            "year": self.current_year,
            "month": self.current_month,
            "cell_data": {f"{d},{i},{j}": v for (d, i, j), v in self.cell_data.items()},
            "cell_colors": {f"{d},{i},{j}": v for (d, i, j), v in self.cell_colors.items()},
            "cell_sequence": {f"{d},{i},{j}": v for (d, i, j), v in self.cell_sequence.items()},
            "er_marks": [f"{d},{i},{j}" for d, i, j in self.er_marks],
            "value_colors": self.value_colors,
            "next_sequence": self.next_sequence,
            "special_borders": {f"{d},{i},{j}": v for (d, i, j), v in self.special_borders.items()},
            "locked_cells": [f"{d},{i},{j}" for d, i, j in self.locked_cells],
            "completed_days": list(self.completed_days),
            # ✨ メンバー管理情報を追加
            "team_rules": self.team_rules,
            "members_data": self.members_data,
            "next_member_id": self._next_member_id,
            # ✨ 日付メモを追加
            "day_memos": {str(k): v for k, v in self.day_memos.items()},
            "special_items": self.special_items,
            # ✨ サブカレンダーデータ
            "sub_cell_data": {f"{name}|||{d}|||{slot}": v for (name, d, slot), v in self.sub_cell_data.items()},
        }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("保存完了", f"データを保存しました:\n{filename}")

    def load_data(self):
        filename = filedialog.askopenfilename(filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not filename: return
        try:
            with open(filename, "r", encoding="utf-8") as f: data = json.load(f)
            self.current_year = data["year"]
            self.current_month = data["month"]
            self.year_var.set(str(self.current_year))
            self.month_var.set(str(self.current_month))
            self.cell_data = {tuple(map(int, k.split(","))): v for k, v in data["cell_data"].items()}
            self.cell_colors = {tuple(map(int, k.split(","))): v for k, v in data["cell_colors"].items()}
            self.cell_sequence = {tuple(map(int, k.split(","))): v for k, v in data["cell_sequence"].items()}
            self.er_marks = {tuple(map(int, k.split(","))) for k in data["er_marks"]}
            self.value_colors = data["value_colors"]
            self.next_sequence = data["next_sequence"]
            if "special_borders" in data:
                self.special_borders = {tuple(map(int, k.split(","))): v for k, v in data["special_borders"].items()}
            else:
                self.special_borders = {}
            if "locked_cells" in data:
                self.locked_cells = {tuple(map(int, k.split(","))) for k in data["locked_cells"]}
            else:
                self.locked_cells = set()
            if "completed_days" in data:
                self.completed_days = set(data["completed_days"])
            else:
                self.completed_days = set()
            # ✨ メンバー管理情報を読込
            if "team_rules" in data:
                self.team_rules = data["team_rules"]
            else:
                self.team_rules = ""
            if "members_data" in data:
                self.members_data = data["members_data"]
            else:
                self.members_data = []
                self._load_default_members()
            if "next_member_id" in data:
                self._next_member_id = data["next_member_id"]
            else:
                self._next_member_id = len(self.members_data) + 1
            # ✨ 日付メモを読込
            # ✨ 特別項目マスターデータを読込
            if "special_items" in data:
                for cat in ["外勤", "委員会", "コース", "訓練"]:
                    if cat in data["special_items"]:
                        self.special_items[cat] = data["special_items"][cat]
            if "day_memos" in data:
                self.day_memos = {int(k): v for k, v in data["day_memos"].items()}
            else:
                self.day_memos = {}
            # ✨ サブカレンダーデータを読込
            if "sub_cell_data" in data:
                self.sub_cell_data = {}
                for k, v in data["sub_cell_data"].items():
                    parts = k.split("|||")
                    if len(parts) == 3:
                        name, d, slot = parts[0], int(parts[1]), parts[2]
                        self.sub_cell_data[(name, d, slot)] = v
                    elif len(parts) == 2:
                        # 旧フォーマット互換: (name, day) → duty として移行
                        name, d = parts[0], int(parts[1])
                        self.sub_cell_data[(name, d, "duty")] = v
            else:
                self.sub_cell_data = {}
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.create_calendar()
            self.draw_statistics()
            messagebox.showinfo("読込完了", "データを読み込みました")
        except Exception as e: messagebox.showerror("エラー", f"データの読み込みに失敗しました:\n{e}")

    def export_to_excel(self):
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, Alignment, PatternFill
        except ImportError:
            messagebox.showerror("エラー", "openpyxlがインストールされていません。\npip install openpyxlを実行してください。")
            return
        filename = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
            initialfile=f"calendar_{self.current_year}_{self.current_month}.xlsx"
        )
        if not filename: return
        try:
            wb = Workbook()
            ws = wb.active
            ws.title = f"{self.current_year}年{self.current_month}月"
            ws.merge_cells("B1:AE1")
            ws["B1"] = f"{self.current_year}年 {self.current_month}月"
            ws["B1"].font = Font(name="Meiryo UI", size=24, bold=True)
            ws["B1"].alignment = Alignment(horizontal="left", vertical="center")
            ws.row_dimensions[1].height = 35
            for (day, li, ci), value in self.cell_data.items():
                info = self._day_positions.get(day)
                if info is None: continue
                week, dow, _, _ = info
                excel_row = 3 + week * self.BLOCK_H + li
                excel_col = 2 + dow * self.BLOCK_W + ci + 1
                cell = ws.cell(row=excel_row, column=excel_col, value=value)
                ck = (day, li, ci)
                if ck in self.cell_colors:
                    h = self.cell_colors[ck].replace("#", "")
                    cell.fill = PatternFill(start_color=h, end_color=h, fill_type="solid")
            wb.save(filename)
            messagebox.showinfo("エクスポート完了", f"Excelファイルを保存しました:\n{filename}")
        except Exception as e: messagebox.showerror("エラー", f"Excelファイルの保存に失敗しました:\n{e}")

    # ========== メンバー管理機能 ==========
    
    def _load_default_members(self):
        """デフォルトメンバーを読み込み（既存のvalue_colorsから）"""
        default_names = ["秋", "桜", "小", "金", "坪", "東", "長", "矢", "宮"]
        for name in default_names:
            if name in self.value_colors:
                self.members_data.append({
                    "id": str(self._next_member_id).zfill(3),
                    "name": name,
                    "display_name": name,
                    "active": True,
                    "skill_level": "専門医",
                    "personal_request": "",
                    "color": self.value_colors[name],
                    "team": "A"
                })
                self._next_member_id += 1
    
    def open_member_management(self):
        """メンバー管理ウィンドウを開く"""
        MemberManagementDialog(self)
    
    def _format_members_for_ai(self):
        """AIプロンプト用にメンバー情報をフォーマット（チーム別）"""
        active_members = [m for m in self.members_data if m["active"]]
        if not active_members:
            return "アクティブなメンバーはいません"
        lines = []
        for team in ("A", "B", "非常勤"):
            label = f"【{team}チーム】" if team in ("A", "B") else "【非常勤】"
            team_members = [m for m in active_members if m.get("team", "A") == team]
            if team_members:
                lines.append(label)
                for i, member in enumerate(team_members, 1):
                    lines.append(f"  {i}. {member['name']}（{member['skill_level']}）")
                    if member['personal_request']:
                        lines.append(f"     リクエスト: {member['personal_request']}")
        return "\n".join(lines)

    # ========== ✨ サブカレンダー機能 ==========

    # ═════════════════════════════════════════════
    #  サブカレンダー描画・編集 (v2 週折り返し版)
    # ═════════════════════════════════════════════

    # レイアウト定数
    SUB_NAME_W  = 55
    SUB_TOP_H   = 16    # 上段（勤務左 / フリー右）
    SUB_BOT_H   = 16    # 下段（特別4マス）
    SUB_HDR_H   = 22    # 週ヘッダー高さ
    SUB_WEEK_GAP = 6    # 週間スペース
    SUB_OX      = 8
    SUB_TITLE_H = 32

    DUTY_COLORS = {
        "ER": "#98fb98", "A": "#ffcc99", "B": "#add8e6",
        "当直": "#ffb6c1", "明け": "#ffc8a0", "外勤": "#dda0dd",
        "出張": "#f0e68c", "休み": "#e0ffff",
    }

    def draw_sub_calendar(self):
        """サブカレンダーをABチーム別・週折り返し形式で描画"""
        if not hasattr(self, 'sub_canvas'):
            return
        self._finish_sub_edit()
        self.sub_canvas.delete("all")
        self._sub_cell_bounds.clear()

        yr, mo = self.current_year, self.current_month
        last_day = calendar.monthrange(yr, mo)[1]

        # チーム別メンバー（登録順を維持）
        members_a = [m for m in self.members_data
                     if m.get("active", True) and m.get("team", "A") == "A"]
        members_b = [m for m in self.members_data
                     if m.get("active", True) and m.get("team", "A") == "B"]
        members_p = [m for m in self.members_data
                     if m.get("active", True) and m.get("team", "A") == "非常勤"]

        if not members_a and not members_b and not members_p:
            self.sub_canvas.create_text(300, 200, text="アクティブなメンバーがいません",
                                        font=("Meiryo UI", 12))
            self.sub_canvas.configure(scrollregion=(0, 0, 600, 400))
            return

        # 週配列（月曜始まり）
        first_wd = calendar.weekday(yr, mo, 1)
        weeks = []
        week = [None] * first_wd
        for d in range(1, last_day + 1):
            week.append(d)
            if len(week) == 7:
                weeks.append(week); week = []
        if week:
            while len(week) < 7: week.append(None)
            weeks.append(week)

        WD_LABELS = ["月", "火", "水", "木", "金", "土", "日"]

        # ── レイアウト定数 ──
        TLW = 18    # チームラベル列幅
        NW  = self.SUB_NAME_W
        CH  = self.SUB_TOP_H + self.SUB_BOT_H
        HH  = self.SUB_HDR_H
        SEP = 3     # A/B 間セパレータ高さ
        GAP = self.SUB_WEEK_GAP
        OX  = self.SUB_OX
        TITLE_H = self.SUB_TITLE_H

        # キャンバス幅から日幅を動的計算
        self.sub_canvas.update_idletasks()
        cw = self.sub_canvas.winfo_width()
        if cw < 300: cw = 960
        DW = max(64, (cw - OX * 2 - TLW - NW) / 7)

        na = len(members_a)
        nb = len(members_b)
        np_ = len(members_p)
        # 1週ブロック高さ: ヘッダー + Aメンバー + SEP + Bメンバー + SEP + 非常勤メンバー
        block_h = HH + na * CH + SEP + nb * CH + (SEP + np_ * CH if np_ > 0 else 0)

        oy = OX + TITLE_H

        # タイトル
        self.sub_canvas.create_text(
            OX, OX, anchor="nw",
            text=f"{yr}年 {mo}月  サブカレンダー",
            font=("Meiryo UI", 14, "bold"), fill="#2d3748"
        )

        for wi, week in enumerate(weeks):
            base_y = oy + wi * (block_h + GAP)

            # ─── 週ヘッダー行 ───
            # チームラベル列ヘッダー (空白, 濃色)
            self.sub_canvas.create_rectangle(
                OX, base_y, OX + TLW, base_y + HH,
                fill="#334155", outline="#334155"
            )
            # 名前列ヘッダー
            self.sub_canvas.create_rectangle(
                OX + TLW, base_y, OX + TLW + NW, base_y + HH,
                fill="#4a5568", outline="#4a5568"
            )
            self.sub_canvas.create_text(
                OX + TLW + NW / 2, base_y + HH / 2,
                text="名前", font=("Meiryo UI", 8, "bold"), fill="white"
            )
            # 曜日・日付ヘッダー
            for di, day in enumerate(week):
                x1 = OX + TLW + NW + di * DW
                x2 = x1 + DW
                if di == 5:
                    hfill, hfg = "#b8d0f8", "#1a4fa8"
                elif di == 6:
                    hfill, hfg = "#f8b8b8", "#a81a1a"
                else:
                    hfill, hfg = "#dcdcdc", "#222"
                self.sub_canvas.create_rectangle(
                    x1, base_y, x2, base_y + HH,
                    fill=hfill, outline="#999"
                )
                lbl = WD_LABELS[di] + (f"\n{day}" if day else "")
                self.sub_canvas.create_text(
                    (x1 + x2) / 2, base_y + HH / 2,
                    text=lbl, font=("Meiryo UI", 8, "bold"), fill=hfg
                )

            # ─── Aチームラベル (rowspan = na 行) ───
            a_top = base_y + HH
            a_bot = a_top + na * CH
            if na > 0:
                self.sub_canvas.create_rectangle(
                    OX, a_top, OX + TLW, a_bot,
                    fill="white", outline="#aaa"
                )
                # "A" 横書き
                self.sub_canvas.create_text(
                    OX + TLW / 2, a_top + a_bot / 2 - a_top / 2 - 8,
                    text="A", font=("Meiryo UI", 10, "bold"), fill="#1d4ed8"
                )
                # "チーム" 縦書き（1文字ずつ）
                for ci, ch in enumerate("チーム"):
                    self.sub_canvas.create_text(
                        OX + TLW / 2,
                        a_top + a_bot / 2 - a_top / 2 + 6 + ci * 11,
                        text=ch, font=("Meiryo UI", 8), fill="#475569"
                    )

            # ─── Aチームメンバー行 ───
            self._draw_sub_team_rows(
                week, members_a, a_top, OX, TLW, NW, DW, CH
            )

            # ─── A/B セパレータ ───
            sep_y = a_bot
            self.sub_canvas.create_rectangle(
                OX, sep_y, OX + TLW + NW + 7 * DW, sep_y + SEP,
                fill="#cbd5e1", outline=""
            )

            # ─── Bチームラベル (rowspan = nb 行) ───
            b_top = sep_y + SEP
            b_bot = b_top + nb * CH
            if nb > 0:
                self.sub_canvas.create_rectangle(
                    OX, b_top, OX + TLW, b_bot,
                    fill="white", outline="#aaa"
                )
                self.sub_canvas.create_text(
                    OX + TLW / 2, b_top + b_bot / 2 - b_top / 2 - 8,
                    text="B", font=("Meiryo UI", 10, "bold"), fill="#15803d"
                )
                for ci, ch in enumerate("チーム"):
                    self.sub_canvas.create_text(
                        OX + TLW / 2,
                        b_top + b_bot / 2 - b_top / 2 + 6 + ci * 11,
                        text=ch, font=("Meiryo UI", 8), fill="#475569"
                    )

            # ─── Bチームメンバー行 ───
            self._draw_sub_team_rows(
                week, members_b, b_top, OX, TLW, NW, DW, CH
            )

            # ─── 非常勤セクション（存在する場合のみ）───
            if np_ > 0:
                p_sep_y = b_bot
                self.sub_canvas.create_rectangle(
                    OX, p_sep_y, OX + TLW + NW + 7 * DW, p_sep_y + SEP,
                    fill="#d6d3d1", outline=""
                )
                p_top = p_sep_y + SEP
                p_bot = p_top + np_ * CH
                # 非常勤ラベル
                self.sub_canvas.create_rectangle(
                    OX, p_top, OX + TLW, p_bot,
                    fill="white", outline="#aaa"
                )
                self.sub_canvas.create_text(
                    OX + TLW / 2, p_top + np_ * CH / 2 - 8,
                    text="非", font=("Meiryo UI", 9, "bold"), fill="#78716c"
                )
                for ci2, ch2 in enumerate("常勤"):
                    self.sub_canvas.create_text(
                        OX + TLW / 2,
                        p_top + np_ * CH / 2 + 4 + ci2 * 11,
                        text=ch2, font=("Meiryo UI", 8), fill="#78716c"
                    )
                # 非常勤メンバー行
                self._draw_sub_team_rows(
                    week, members_p, p_top, OX, TLW, NW, DW, CH
                )

        total_h = oy + len(weeks) * (block_h + GAP) + 20
        total_w = OX + TLW + NW + 7 * DW + 20
        self.sub_canvas.configure(scrollregion=(0, 0, total_w, total_h))

    def _draw_sub_team_rows(self, week, members, top_y, OX, TLW, NW, DW, CH):
        """チームのメンバー行群を描画するヘルパー"""
        for mi, member in enumerate(members):
            mname  = member["display_name"]
            mcolor = member.get("color", "#cccccc")
            team   = member.get("team", "A")
            my = top_y + mi * CH

            # 名前セル
            nc = self._lighten_color(mcolor, 0.45)
            self.sub_canvas.create_rectangle(
                OX + TLW, my, OX + TLW + NW, my + CH,
                fill=nc, outline="#aaa"
            )
            self.sub_canvas.create_text(
                OX + TLW + NW / 2, my + CH / 2,
                text=mname, font=("Meiryo UI", 9, "bold"), fill="#1a202c"
            )

            for di, day in enumerate(week):
                x1 = OX + TLW + NW + di * DW
                x2 = x1 + DW

                if day is None:
                    self.sub_canvas.create_rectangle(
                        x1, my, x2, my + CH, fill="#efefef", outline="#ccc"
                    )
                    continue

                day_bg = "#e8f0ff" if di == 5 else ("#ffe8e8" if di == 6 else "white")

                # 上段左: 勤務
                duty    = self.sub_cell_data.get((mname, day, "duty"), "")
                duty_bg = self._lighten_color(
                    self.DUTY_COLORS.get(duty, day_bg), 0.65
                ) if duty else day_bg
                dty1, dty2 = my, my + self.SUB_TOP_H
                dx_mid  = x1 + DW / 2
                self.sub_canvas.create_rectangle(
                    x1, dty1, dx_mid, dty2,
                    fill=duty_bg, outline="#ccc", tags="sub_duty"
                )
                self.sub_canvas.create_text(
                    (x1 + dx_mid) / 2, (dty1 + dty2) / 2,
                    text=duty, font=("Meiryo UI", 8), fill="#1a202c"
                )
                self._sub_cell_bounds[(mname, day, "duty")] = (x1, dty1, dx_mid, dty2)

                # 上段右: フリーテキスト
                free = self.sub_cell_data.get((mname, day, "free"), "")
                self.sub_canvas.create_rectangle(
                    dx_mid, dty1, x2, dty2,
                    fill="#fffdf0", outline="#ccc", tags="sub_free"
                )
                self.sub_canvas.create_text(
                    (dx_mid + x2) / 2, (dty1 + dty2) / 2,
                    text=free, font=("Meiryo UI", 7), fill="#555"
                )
                self._sub_cell_bounds[(mname, day, "free")] = (dx_mid, dty1, x2, dty2)

                # 下段: 特別項目 2×2
                bot_y1  = my + self.SUB_TOP_H
                bot_y2  = my + CH
                bot_mid = (bot_y1 + bot_y2) / 2
                for sl, (bx1, by1, bx2, by2) in zip(
                    ["s0", "s1", "s2", "s3"],
                    [(x1, bot_y1, dx_mid, bot_mid),
                     (dx_mid, bot_y1, x2, bot_mid),
                     (x1, bot_mid, dx_mid, bot_y2),
                     (dx_mid, bot_mid, x2, bot_y2)]
                ):
                    sv  = self.sub_cell_data.get((mname, day, sl), "")
                    sbg = "#f0eaff" if sv else "#f8f5ff"
                    self.sub_canvas.create_rectangle(
                        bx1, by1, bx2, by2,
                        fill=sbg, outline="#d4c8ee", tags="sub_special"
                    )
                    self.sub_canvas.create_text(
                        (bx1 + bx2) / 2, (by1 + by2) / 2,
                        text=sv, font=("Meiryo UI", 7), fill="#4a2d8a"
                    )
                    self._sub_cell_bounds[(mname, day, sl)] = (bx1, by1, bx2, by2)

    # ─── セルクリックで編集エントリ表示 ───

    def _sub_cell_at(self, cx, cy):
        """クリック座標からセルキーを返す"""
        for ck, (x1, y1, x2, y2) in self._sub_cell_bounds.items():
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                return ck
        return None

    def _on_sub_canvas_click(self, event):
        """左クリック: duty/free セルをインライン編集"""
        self._finish_sub_edit()
        cx = self.sub_canvas.canvasx(event.x)
        cy = self.sub_canvas.canvasy(event.y)
        ck = self._sub_cell_at(cx, cy)
        if ck is None:
            return
        _, _, slot = ck
        if slot not in ("duty", "free"):
            return   # 特別セルは右クリック専用

        x1, y1, x2, y2 = self._sub_cell_bounds[ck]
        cur = self.sub_cell_data.get(ck, "")

        entry = tk.Entry(self.sub_canvas, font=("Meiryo UI", 8), justify=tk.CENTER,
                         relief=tk.FLAT, bd=0,
                         highlightthickness=1, highlightbackground="#4a90e2",
                         bg="#fffde7" if slot == "free" else "#e8ffe8")
        entry.insert(0, cur)
        win_id = self.sub_canvas.create_window(
            x1, y1, anchor="nw", window=entry,
            width=x2 - x1, height=y2 - y1,
            tags="sub_edit_entry"
        )
        self._sub_edit_entry = entry
        self._sub_edit_key   = ck
        self._sub_edit_win_id = win_id

        entry.select_range(0, tk.END)
        entry.focus_force()
        entry.bind("<Return>",   lambda e: self._finish_sub_edit())
        entry.bind("<Escape>",   lambda e: self._cancel_sub_edit())
        entry.bind("<FocusOut>", lambda e: self._finish_sub_edit())

    def _finish_sub_edit(self):
        """編集を確定して再描画"""
        if self._sub_edit_entry is None:
            return
        ck  = self._sub_edit_key
        val = self._sub_edit_entry.get().strip()
        try:
            self.sub_canvas.delete("sub_edit_entry")
            self._sub_edit_entry.destroy()
        except Exception:
            pass
        self._sub_edit_entry  = None
        self._sub_edit_key    = None
        self._sub_edit_win_id = None
        if ck is None:
            return
        if val:
            self.sub_cell_data[ck] = val
        else:
            self.sub_cell_data.pop(ck, None)
        self.draw_sub_calendar()

    def _cancel_sub_edit(self):
        """編集をキャンセル"""
        if self._sub_edit_entry is None:
            return
        try:
            self.sub_canvas.delete("sub_edit_entry")
            self._sub_edit_entry.destroy()
        except Exception:
            pass
        self._sub_edit_entry  = None
        self._sub_edit_key    = None
        self._sub_edit_win_id = None

    # ─── 右クリック: 特別項目コンテキストメニュー ───

    def _on_sub_canvas_right_click(self, event):
        """右クリック: duty セルは勤務選択、特別セル(s0-s3)はカテゴリ選択"""
        self._finish_sub_edit()
        cx = self.sub_canvas.canvasx(event.x)
        cy = self.sub_canvas.canvasy(event.y)
        ck = self._sub_cell_at(cx, cy)
        if ck is None:
            return
        _, _, slot = ck

        # ── 勤務セルの右クリック ──
        if slot == "duty":
            popup = tk.Menu(self.root, tearoff=0)
            duty_entries = [
                ("ER",   "#98fb98"),
                ("A",    "#ffcc99"),
                ("B",    "#add8e6"),
                ("当直", "#ffb6c1"),
                ("明け", "#ffc8a0"),
                ("外勤", "#dda0dd"),
                ("出張", "#f0e68c"),
                ("休み", "#e0ffff"),
            ]
            for label, _ in duty_entries:
                cur_duty = self.sub_cell_data.get(ck, "")
                check = "✔ " if cur_duty == label else "　"
                popup.add_command(
                    label=f"{check}{label}",
                    command=lambda v=label, k=ck: self._set_sub_duty(k, v)
                )
            cur = self.sub_cell_data.get(ck, "")
            if cur:
                popup.add_separator()
                popup.add_command(
                    label="✖ クリア",
                    command=lambda k=ck: self._set_sub_duty(k, "")
                )
            try:
                popup.tk_popup(event.x_root, event.y_root)
            finally:
                popup.grab_release()
            return

        # ── 特別セル(s0-s3)の右クリック ──
        if slot not in ("s0", "s1", "s2", "s3"):
            return

        popup = tk.Menu(self.root, tearoff=0)
        icons = {"外勤": "🚗", "委員会": "🏛", "コース": "📚", "訓練": "🎯"}
        for cat, items in self.special_items.items():
            sub = tk.Menu(popup, tearoff=0)
            if items:
                for item in items:
                    sub.add_command(
                        label=item,
                        command=lambda v=item, k=ck: self._set_sub_special(k, v)
                    )
            else:
                sub.add_command(label="（項目未登録）", state=tk.DISABLED)
            popup.add_cascade(label=f"{icons.get(cat,'')} {cat}", menu=sub)

        cur = self.sub_cell_data.get(ck, "")
        if cur:
            popup.add_separator()
            popup.add_command(
                label="✖ クリア",
                command=lambda k=ck: self._set_sub_special(k, "")
            )
        try:
            popup.tk_popup(event.x_root, event.y_root)
        finally:
            popup.grab_release()

    def _set_sub_duty(self, ck, value: str):
        """勤務セルの値をセット/クリアして再描画"""
        if value:
            self.sub_cell_data[ck] = value
        else:
            self.sub_cell_data.pop(ck, None)
        self.draw_sub_calendar()

    def _set_sub_special(self, ck, value: str):
        """特別セルの値をセット/クリアして再描画"""
        if value:
            self.sub_cell_data[ck] = value
        else:
            self.sub_cell_data.pop(ck, None)
        self.draw_sub_calendar()

    # ─── 同期ボタン処理 ───

    def _on_main_sync_btn(self):
        """メインの同期ボタン: サブ→メインに反映"""
        if not messagebox.askyesno(
                "確認",
                "サブカレンダーの勤務内容でメインカレンダーを上書きします。\nよろしいですか？"):
            return
        self._apply_sub_to_main()

    def _on_sub_sync_btn(self):
        """サブの同期ボタン: メイン→サブに反映"""
        self._apply_main_to_sub()
        messagebox.showinfo("同期完了", "メインカレンダーの内容をサブカレンダーに反映しました。")

    def _apply_main_to_sub(self):
        """メイン cell_data → sub_cell_data['duty'] を更新して再描画"""
        members  = [m for m in self.members_data if m.get("active", True)]
        last_day = calendar.monthrange(self.current_year, self.current_month)[1]
        for member in members:
            name = member["display_name"]
            for d in range(1, last_day + 1):
                duties = self._get_duties_from_main(name, d)
                key = (name, d, "duty")
                if duties:
                    self.sub_cell_data[key] = duties
                else:
                    self.sub_cell_data.pop(key, None)
        self.draw_sub_calendar()

    def _apply_sub_to_main(self):
        """sub_cell_data['duty'] → cell_data に書き戻してメインを再描画"""
        self._save_state()
        members  = [m for m in self.members_data if m.get("active", True)]
        last_day = calendar.monthrange(self.current_year, self.current_month)[1]

        for member in members:
            name  = member["display_name"]
            color = member.get("color", self._get_or_assign_color(name))

            keys_to_del = [
                ck for ck, v in self.cell_data.items()
                if v == name and 1 <= ck[0] <= last_day
            ]
            for k in keys_to_del:
                self.cell_data.pop(k, None)
                self.cell_colors.pop(k, None)
                self.cell_sequence.pop(k, None)

            for d in range(1, last_day + 1):
                duties_str = self.sub_cell_data.get((name, d, "duty"), "")
                if not duties_str:
                    continue
                for duty in [dt.strip() for dt in duties_str.split("/") if dt.strip()]:
                    label_idx = next(
                        (i for i, lbl in enumerate(self.LABELS) if lbl == duty), None
                    )
                    if label_idx is None:
                        continue
                    ck = (d, label_idx, 0)
                    for ci in range(self.BLOCK_W):
                        cand = (d, label_idx, ci)
                        if cand not in self.cell_data or self.cell_data[cand] == name:
                            ck = cand; break
                    self.cell_data[ck]   = name
                    self.cell_colors[ck] = color
                    if ck not in self.cell_sequence:
                        self.cell_sequence[ck] = self.next_sequence
                        self.next_sequence += 1

        self._redraw_all_cells()
        self.draw_statistics()
        messagebox.showinfo("同期完了", "サブカレンダーの内容をメインカレンダーに反映しました。")

    def _get_duties_from_main(self, member_name: str, day: int) -> str:
        """メインカレンダーから指定メンバー・日の勤務を '/' 区切りで返す"""
        duties: List[str] = []
        for label_idx in range(1, len(self.LABELS)):
            label = self.LABELS[label_idx]
            if not label or not label.strip():
                continue
            for col_idx in range(self.BLOCK_W):
                if self.cell_data.get((day, label_idx, col_idx)) == member_name:
                    if label not in duties:
                        duties.append(label)
                    break
        return "/".join(duties)




# ========== メンバー管理ダイアログ（AB チーム対応版） ==========

class MemberManagementDialog:
    """メンバー管理ダイアログ: AチームとBチームを左右に並べ D&D で移動できる"""

    TEAM_A_BG   = "#dbeafe"
    TEAM_B_BG   = "#dcfce7"
    TEAM_P_BG   = "#f5f5f4"   # 非常勤 (stone-100)
    TEAM_A_HDR  = "#1d4ed8"
    TEAM_B_HDR  = "#15803d"
    TEAM_P_HDR  = "#78716c"   # 非常勤 (stone-500)
    TEAM_A_DARK = "#1e3a8a"
    TEAM_B_DARK = "#14532d"
    TEAM_P_DARK = "#44403c"

    def __init__(self, parent_app):
        self.app = parent_app
        self.dialog = tk.Toplevel(parent_app.root)
        self.dialog.title("👥 メンバー管理（A / B / 非常勤）")
        self.dialog.geometry("1300x820")
        self.dialog.minsize(800, 600)
        self.dialog.transient(parent_app.root)

        # ドラッグ状態
        self._drag_member  = None        # ドラッグ中のメンバー dict
        self._drag_ghost   = None        # Toplevel ゴーストウィンドウ
        self._drag_label   = None        # ゴースト内ラベル

        self._setup_ui()
        self._refresh_all()

    # ─────────────────────────────────────
    # UI 構築
    # ─────────────────────────────────────
    def _setup_ui(self):
        self.dialog.configure(bg="#f1f5f9")

        # ── トップバー ──
        top = tk.Frame(self.dialog, bg="#f1f5f9")
        top.pack(fill=tk.X, padx=12, pady=(10, 6))

        btn_s = {"font": ("Meiryo UI", 10), "relief": tk.FLAT,
                 "cursor": "hand2", "padx": 14, "pady": 7}
        tk.Button(top, text="➕ Aチームに追加",
                  command=lambda: self._add_member("A"),
                  bg=self.TEAM_A_HDR, fg="white", **btn_s).pack(side=tk.LEFT, padx=4)
        tk.Button(top, text="➕ Bチームに追加",
                  command=lambda: self._add_member("B"),
                  bg=self.TEAM_B_HDR, fg="white", **btn_s).pack(side=tk.LEFT, padx=4)
        tk.Button(top, text="➕ 非常勤に追加",
                  command=lambda: self._add_member("非常勤"),
                  bg=self.TEAM_P_HDR, fg="white", **btn_s).pack(side=tk.LEFT, padx=4)
        tk.Button(top, text="💾 保存", command=self._save_members,
                  bg="#475569", fg="white", **btn_s).pack(side=tk.LEFT, padx=4)
        tk.Button(top, text="📤 CSV出力", command=self._export_csv,
                  bg="#f59e0b", fg="white", **btn_s).pack(side=tk.LEFT, padx=4)
        tk.Button(top, text="📥 CSV取込", command=self._import_csv,
                  bg="#8b5cf6", fg="white", **btn_s).pack(side=tk.LEFT, padx=4)

        self.status_label = tk.Label(top, text="", bg="#f1f5f9",
                                     font=("Meiryo UI", 9), fg="#64748b")
        self.status_label.pack(side=tk.RIGHT, padx=8)

        # ── 全体の決まり事 ──
        rules_outer = tk.Frame(self.dialog, bg="#eef2ff", relief=tk.FLAT, bd=0)
        rules_outer.pack(fill=tk.X, padx=12, pady=(0, 6))

        rules_hdr = tk.Frame(rules_outer, bg="#eef2ff")
        rules_hdr.pack(fill=tk.X)
        tk.Label(rules_hdr, text="📋 全体の決まり事", bg="#eef2ff",
                 font=("Meiryo UI", 10, "bold"), fg="#4338ca").pack(side=tk.LEFT, padx=8, pady=4)
        self._rules_expanded = True
        self._toggle_btn = tk.Button(rules_hdr, text="▼", bg="#eef2ff", fg="#4338ca",
                                     relief=tk.FLAT, font=("Meiryo UI", 11, "bold"),
                                     cursor="hand2", command=self._toggle_rules)
        self._toggle_btn.pack(side=tk.RIGHT, padx=8)

        self._rules_body = tk.Frame(rules_outer, bg="#eef2ff")
        self._rules_body.pack(fill=tk.X, padx=8, pady=(0, 6))
        self.rules_text = tk.Text(self._rules_body, height=4, wrap=tk.WORD,
                                  font=("Meiryo UI", 10), bg="#fefce8",
                                  relief=tk.FLAT, padx=8, pady=6)
        self.rules_text.pack(fill=tk.X)
        self.rules_text.insert("1.0", self.app.team_rules)

        # ── 2カラム（A / B） ──
        hint = tk.Label(self.dialog,
                        text="※ カードをドラッグして反対チームにドロップすると移動できます",
                        bg="#f1f5f9", font=("Meiryo UI", 9), fg="#94a3b8")
        hint.pack(pady=(0, 4))

        cols_frame = tk.Frame(self.dialog, bg="#f1f5f9")
        cols_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 4))
        cols_frame.columnconfigure(0, weight=1, uniform="col")
        cols_frame.columnconfigure(1, weight=1, uniform="col")
        cols_frame.columnconfigure(2, weight=1, uniform="col")
        cols_frame.rowconfigure(0, weight=1)

        self._panel_a = self._build_team_panel(cols_frame, "A",    0)
        self._panel_b = self._build_team_panel(cols_frame, "B",    1)
        self._panel_p = self._build_team_panel(cols_frame, "非常勤", 2)

        # ── 閉じる ──
        bot = tk.Frame(self.dialog, bg="#f1f5f9")
        bot.pack(fill=tk.X, padx=12, pady=8)
        tk.Button(bot, text="閉じる", command=self._close,
                  bg="#64748b", fg="white", font=("Meiryo UI", 11),
                  relief=tk.FLAT, padx=28, pady=8, cursor="hand2").pack(side=tk.RIGHT)

    def _build_team_panel(self, parent, team: str, col: int):
        """チームパネル（ヘッダー＋スクロールリスト）を構築して canvas を返す"""
        if team == "A":
            hdr_bg, hdr_fg = self.TEAM_A_BG, self.TEAM_A_HDR
            icon, label = "🔵", "Aチーム"
            pad = (0, 4)
        elif team == "B":
            hdr_bg, hdr_fg = self.TEAM_B_BG, self.TEAM_B_HDR
            icon, label = "🟢", "Bチーム"
            pad = (4, 4)
        else:
            hdr_bg, hdr_fg = self.TEAM_P_BG, self.TEAM_P_HDR
            icon, label = "⬜", "非常勤"
            pad = (4, 0)

        outer = tk.Frame(parent, bg=hdr_bg, relief=tk.FLAT, bd=0)
        outer.grid(row=0, column=col, sticky="nsew", padx=pad)

        hdr = tk.Frame(outer, bg=hdr_fg, height=36)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(hdr, text=f"{icon} {label}",
                 bg=hdr_fg, fg="white",
                 font=("Meiryo UI", 13, "bold")).pack(side=tk.LEFT, padx=12, pady=6)

        # カウントラベル
        cnt_lbl = tk.Label(hdr, text="0人", bg=hdr_fg, fg="white",
                           font=("Meiryo UI", 10))
        cnt_lbl.pack(side=tk.RIGHT, padx=12)

        # スクロールエリア
        sc_frame = tk.Frame(outer, bg=hdr_bg)
        sc_frame.pack(fill=tk.BOTH, expand=True)

        vsb = tk.Scrollbar(sc_frame, orient=tk.VERTICAL)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        canvas = tk.Canvas(sc_frame, bg=hdr_bg, highlightthickness=0,
                           yscrollcommand=vsb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.config(command=canvas.yview)

        inner = tk.Frame(canvas, bg=hdr_bg)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        inner.bind("<Configure>",
                   lambda e, c=canvas: c.configure(scrollregion=c.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e, c=canvas, wid=win_id: c.itemconfig(wid, width=e.width))
        canvas.bind("<MouseWheel>",
                    lambda e, c=canvas: c.yview_scroll(int(-1*(e.delta/120)), "units"))

        # ドロップゾーン検出用にタグを付けておく
        canvas.team = team          # type: ignore
        canvas.inner_frame = inner  # type: ignore
        canvas.count_label = cnt_lbl  # type: ignore

        return canvas

    # ─────────────────────────────────────
    # リスト再描画
    # ─────────────────────────────────────
    def _refresh_all(self):
        """A / B / 非常勤 リストを再描画"""
        for team, canvas in (("A", self._panel_a), ("B", self._panel_b), ("非常勤", self._panel_p)):
            inner = canvas.inner_frame
            for w in inner.winfo_children():
                w.destroy()
            members = [m for m in self.app.members_data
                       if m.get("team", "A") == team]
            for m in members:
                self._create_card(inner, m, team)
            canvas.count_label.config(text=f"{len(members)}人")

        total  = len(self.app.members_data)
        active = sum(1 for m in self.app.members_data if m["active"])
        na = len([m for m in self.app.members_data if m.get("team","A")=="A"])
        nb = len([m for m in self.app.members_data if m.get("team","A")=="B"])
        np_ = len([m for m in self.app.members_data if m.get("team","A")=="非常勤"])
        self.status_label.config(
            text=f"A:{na}人  B:{nb}人  非常勤:{np_}人  （アクティブ計 {active}/{total}人）"
        )

    def _create_card(self, parent: tk.Frame, member: dict, team: str):
        """メンバーカードを生成してドラッグイベントを設定"""
        if team == "A":
            team_light, team_hdr = self.TEAM_A_BG, self.TEAM_A_HDR
        elif team == "B":
            team_light, team_hdr = self.TEAM_B_BG, self.TEAM_B_HDR
        else:
            team_light, team_hdr = self.TEAM_P_BG, self.TEAM_P_HDR

        card = tk.Frame(parent, bg="white", relief=tk.RAISED, bd=1,
                        cursor="fleur")
        card.pack(fill=tk.X, padx=8, pady=4)

        # ── カードヘッダー ──
        hdr_bg = "#f8fafc" if member["active"] else "#fee2e2"
        hdr = tk.Frame(card, bg=hdr_bg, height=36)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)

        # カラー丸
        circ = tk.Canvas(hdr, width=20, height=20, bg=hdr_bg, highlightthickness=0)
        circ.pack(side=tk.LEFT, padx=(8, 6))
        mc = member.get("color", "#cccccc")
        if not member["active"]:
            mc = self._lighten(mc)
        circ.create_oval(2, 2, 18, 18, fill=mc, outline="")

        # 名前・スキル
        nf = tk.Frame(hdr, bg=hdr_bg)
        nf.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        nm_text = f"{member['name']}  ({member['display_name']})"
        if not member["active"]:
            nm_text += "  [非アクティブ]"
        tk.Label(nf, text=nm_text, bg=hdr_bg,
                 font=("Meiryo UI", 10, "bold"), fg="#111827").pack(side=tk.LEFT)
        tk.Label(nf, text=f" | {member['skill_level']}", bg=hdr_bg,
                 font=("Meiryo UI", 9), fg="#6b7280").pack(side=tk.LEFT)

        # 統計
        stats = self._get_stats(member["display_name"])
        if stats:
            tk.Label(nf, text=" | " + " ".join(f"{k}:{v}" for k,v in stats.items()),
                     bg=hdr_bg, font=("Meiryo UI", 8), fg="#9ca3af").pack(side=tk.LEFT)

        # ボタン群
        bf = tk.Frame(hdr, bg=hdr_bg)
        bf.pack(side=tk.RIGHT, padx=6)
        bs = {"font": ("Meiryo UI", 8), "relief": tk.FLAT,
               "cursor": "hand2", "padx": 6, "pady": 3}
        tk.Button(bf, text="編集",
                  command=lambda m=member: self._edit_member(m),
                  bg="#3b82f6", fg="white", **bs).pack(side=tk.LEFT, padx=2)
        if member["active"]:
            tk.Button(bf, text="OFF",
                      command=lambda m=member: self._toggle_active(m),
                      bg="#f59e0b", fg="white", **bs).pack(side=tk.LEFT, padx=2)
        else:
            tk.Button(bf, text="ON",
                      command=lambda m=member: self._toggle_active(m),
                      bg="#10b981", fg="white", **bs).pack(side=tk.LEFT, padx=2)
        tk.Button(bf, text="削除",
                  command=lambda m=member: self._delete_member(m),
                  bg="#ef4444", fg="white", **bs).pack(side=tk.LEFT, padx=2)

        # リクエスト
        if member.get("personal_request"):
            rf = tk.Frame(card, bg="white")
            rf.pack(fill=tk.X, padx=10, pady=6)
            tk.Label(rf, text="💬", bg="white",
                     font=("Meiryo UI", 9)).pack(side=tk.LEFT)
            tk.Label(rf, text=member["personal_request"],
                     bg="#eef2ff", fg="#312e81",
                     font=("Meiryo UI", 9), justify=tk.LEFT,
                     wraplength=340, padx=8, pady=3).pack(fill=tk.X)

        # ── ドラッグイベントをカード全体に登録 ──
        for w in self._all_widgets(card):
            if isinstance(w, tk.Button):
                continue   # ボタン自身はクリック優先
            w.bind("<ButtonPress-1>",   lambda e, m=member: self._drag_start(e, m))
            w.bind("<B1-Motion>",        self._drag_motion)
            w.bind("<ButtonRelease-1>",  self._drag_release)

    # ─────────────────────────────────────
    # ドラッグ & ドロップ
    # ─────────────────────────────────────
    def _all_widgets(self, widget):
        """ウィジェットとすべての子を再帰的に列挙"""
        yield widget
        for child in widget.winfo_children():
            yield from self._all_widgets(child)

    def _drag_start(self, event, member: dict):
        self._drag_member = member
        self._create_ghost(member, event.x_root, event.y_root)

    def _drag_motion(self, event):
        if self._drag_ghost and self._drag_ghost.winfo_exists():
            self._drag_ghost.geometry(f"+{event.x_root+12}+{event.y_root+6}")

    def _drag_release(self, event):
        if self._drag_member is None:
            return
        # どちらのパネルの上でリリースされたか判定
        target_team = self._detect_drop_target(event.x_root, event.y_root)
        current_team = self._drag_member.get("team", "A")

        self._destroy_ghost()

        if target_team and target_team != current_team:
            self._drag_member["team"] = target_team
            self._refresh_all()

        self._drag_member = None

    def _detect_drop_target(self, rx: int, ry: int) -> Optional[str]:
        """画面座標からドロップ先チームを判定。どちらでもなければ None"""
        for team, canvas in (("A", self._panel_a), ("B", self._panel_b), ("非常勤", self._panel_p)):
            try:
                cx = canvas.winfo_rootx()
                cy = canvas.winfo_rooty()
                cw = canvas.winfo_width()
                ch = canvas.winfo_height()
                if cx <= rx <= cx + cw and cy <= ry <= cy + ch:
                    return team
            except Exception:
                pass
        return None

    def _create_ghost(self, member: dict, rx: int, ry: int):
        """ドラッグ中に名前を示すゴーストウィンドウを作成"""
        self._destroy_ghost()
        ghost = tk.Toplevel(self.dialog)
        ghost.overrideredirect(True)
        ghost.attributes("-topmost", True)
        ghost.attributes("-alpha", 0.82)
        ghost.geometry(f"+{rx+12}+{ry+6}")
        lbl = tk.Label(ghost,
                       text=f"  {member.get('display_name',member['name'])}  ",
                       bg="#1e40af", fg="white",
                       font=("Meiryo UI", 11, "bold"),
                       padx=10, pady=5, relief=tk.FLAT)
        lbl.pack()
        self._drag_ghost = ghost
        self._drag_label = lbl

    def _destroy_ghost(self):
        if self._drag_ghost:
            try:
                self._drag_ghost.destroy()
            except Exception:
                pass
            self._drag_ghost = None
            self._drag_label = None

    # ─────────────────────────────────────
    # メンバー操作
    # ─────────────────────────────────────
    def _add_member(self, team: str = "A"):
        MemberEditDialog(self, None, default_team=team)

    def _edit_member(self, member):
        MemberEditDialog(self, member)

    def _toggle_active(self, member):
        member["active"] = not member["active"]
        self._refresh_all()

    def _delete_member(self, member):
        if messagebox.askyesno("確認", f"{member['name']} を削除しますか？",
                               parent=self.dialog):
            self.app.members_data.remove(member)
            self._refresh_all()

    def _toggle_rules(self):
        if self._rules_expanded:
            self._rules_body.pack_forget()
            self._toggle_btn.config(text="▶")
        else:
            self._rules_body.pack(fill=tk.X, padx=8, pady=(0, 6))
            self._toggle_btn.config(text="▼")
        self._rules_expanded = not self._rules_expanded

    def _get_stats(self, display_name: str):
        stats = defaultdict(int)
        for (_, li, _), v in self.app.cell_data.items():
            if v == display_name:
                lbl = self.app.LABELS[li] if li < len(self.app.LABELS) else ""
                if lbl and lbl.strip():
                    stats[lbl] += 1
        return dict(stats) if stats else None

    @staticmethod
    def _lighten(color: str, factor: float = 0.55) -> str:
        color = color.lstrip("#")
        if len(color) != 6:
            return "#cccccc"
        r, g, b = (int(color[i:i+2], 16) for i in (0, 2, 4))
        r = int(r + (255 - r) * factor)
        g = int(g + (255 - g) * factor)
        b = int(b + (255 - b) * factor)
        return f"#{r:02x}{g:02x}{b:02x}"

    # ─────────────────────────────────────
    # 保存 / CSV
    # ─────────────────────────────────────
    def _save_members(self):
        self.app.team_rules = self.rules_text.get("1.0", tk.END).strip()
        self.app.save_data()
        messagebox.showinfo("保存完了", "メンバー情報を保存しました", parent=self.dialog)

    def _export_csv(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="members.csv",
            parent=self.dialog
        )
        if not filename:
            return
        try:
            import csv
            with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(["名前","表示名","スキルレベル","アクティブ","個人リクエスト","色","チーム"])
                for m in self.app.members_data:
                    writer.writerow([
                        m["name"], m["display_name"], m["skill_level"],
                        "はい" if m["active"] else "いいえ",
                        m["personal_request"], m["color"],
                        m.get("team", "A")
                    ])
            messagebox.showinfo("出力完了", f"CSVを保存しました:\n{filename}", parent=self.dialog)
        except Exception as e:
            messagebox.showerror("エラー", f"CSV出力に失敗しました:\n{e}", parent=self.dialog)

    def _import_csv(self):
        filename = filedialog.askopenfilename(
            filetypes=[("CSV files", "*.csv")], parent=self.dialog)
        if not filename:
            return
        try:
            import csv
            with open(filename, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                new_members = []
                for row in reader:
                    new_members.append({
                        "id": str(self.app._next_member_id).zfill(3),
                        "name": row["名前"],
                        "display_name": row["表示名"],
                        "skill_level": row["スキルレベル"],
                        "active": row["アクティブ"] == "はい",
                        "personal_request": row["個人リクエスト"],
                        "color": row["色"],
                        "team": row.get("チーム", "A"),
                    })
                    self.app._next_member_id += 1
            if messagebox.askyesno("確認", f"{len(new_members)}人を追加しますか？",
                                   parent=self.dialog):
                self.app.members_data.extend(new_members)
                self._refresh_all()
        except Exception as e:
            messagebox.showerror("エラー", f"CSV取込に失敗しました:\n{e}", parent=self.dialog)

    def _close(self):
        self.app.team_rules = self.rules_text.get("1.0", tk.END).strip()
        self._destroy_ghost()
        self.dialog.destroy()

    # 旧コードとの互換用（MemberEditDialog から呼ばれる）
    def _refresh_member_list(self):
        self._refresh_all()

    def _lighten_member_color(self, color: str) -> str:
        return self._lighten(color)


# ========== メンバー編集ダイアログ ==========

class MemberEditDialog:
    """メンバー編集/追加ダイアログ"""
    
    def __init__(self, parent_dialog, member=None, default_team: str = "A"):
        self.parent = parent_dialog
        self.app = parent_dialog.app
        self.member = member
        self.is_new = member is None
        self._default_team = default_team
        
        self.dialog = tk.Toplevel(parent_dialog.dialog)
        self.dialog.title("メンバー追加" if self.is_new else f"{member['name']} の編集")
        self.dialog.geometry("500x640")
        self.dialog.transient(parent_dialog.dialog)
        self.dialog.grab_set()
        
        self._setup_ui()
    
    def _setup_ui(self):
        """UI構築"""
        main_frame = tk.Frame(self.dialog, bg="white", padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 名前
        tk.Label(main_frame, text="名前（フルネーム）:", bg="white",
                font=("Meiryo UI", 10, "bold")).pack(anchor="w", pady=(0, 5))
        self.name_entry = tk.Entry(main_frame, font=("Meiryo UI", 11), width=30)
        self.name_entry.pack(fill=tk.X, pady=(0, 15))
        
        # セル表示名
        tk.Label(main_frame, text="セル表示文字:", bg="white",
                font=("Meiryo UI", 10, "bold")).pack(anchor="w", pady=(0, 5))
        self.display_entry = tk.Entry(main_frame, font=("Meiryo UI", 11), width=30)
        self.display_entry.pack(fill=tk.X, pady=(0, 15))
        
        # スキルレベル
        tk.Label(main_frame, text="スキルレベル:", bg="white",
                font=("Meiryo UI", 10, "bold")).pack(anchor="w", pady=(0, 5))
        self.skill_var = tk.StringVar(value="専門医")
        skill_frame = tk.Frame(main_frame, bg="white")
        skill_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Combobox(skill_frame, textvariable=self.skill_var, font=("Meiryo UI", 10),
                     values=["研修医", "専門医", "部長", "その他"], state="readonly", width=28).pack(side=tk.LEFT)
        
        # 色選択
        tk.Label(main_frame, text="カレンダー色:", bg="white",
                font=("Meiryo UI", 10, "bold")).pack(anchor="w", pady=(0, 5))
        
        color_frame = tk.Frame(main_frame, bg="white")
        color_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.color_var = tk.StringVar(value="#FFE4B2")
        self.color_preview = tk.Label(color_frame, text="   ", bg=self.color_var.get(),
                                      width=3, relief=tk.RAISED)
        self.color_preview.pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Button(color_frame, text="色を選択", command=self._choose_color,
                 font=("Meiryo UI", 9), cursor="hand2").pack(side=tk.LEFT)
        
        # 個人リクエスト
        tk.Label(main_frame, text="💬 個人リクエスト（自由記述）:", bg="white",
                font=("Meiryo UI", 10, "bold")).pack(anchor="w", pady=(0, 5))
        tk.Label(main_frame, text="例: 土日の当直は避けてほしい、月末に連休希望", bg="white",
                font=("Meiryo UI", 8), fg="#6b7280").pack(anchor="w", pady=(0, 5))
        
        request_frame = tk.Frame(main_frame, bg="white")
        request_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        request_scroll = tk.Scrollbar(request_frame)
        request_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.request_text = tk.Text(request_frame, height=10, wrap=tk.WORD,
                                    font=("Meiryo UI", 10), yscrollcommand=request_scroll.set)
        self.request_text.pack(fill=tk.BOTH, expand=True)
        request_scroll.config(command=self.request_text.yview)
        
        # チーム選択
        tk.Label(main_frame, text="チーム:", bg="white",
                font=("Meiryo UI", 10, "bold")).pack(anchor="w", pady=(0, 5))
        team_frame = tk.Frame(main_frame, bg="white")
        team_frame.pack(fill=tk.X, pady=(0, 15))
        self.team_var = tk.StringVar(value=self._default_team)
        tk.Radiobutton(team_frame, text="🔵 Aチーム", variable=self.team_var,
                       value="A", bg="white", font=("Meiryo UI", 10),
                       fg="#1d4ed8", activebackground="white",
                       selectcolor="#dbeafe").pack(side=tk.LEFT, padx=(0, 16))
        tk.Radiobutton(team_frame, text="🟢 Bチーム", variable=self.team_var,
                       value="B", bg="white", font=("Meiryo UI", 10),
                       fg="#15803d", activebackground="white",
                       selectcolor="#dcfce7").pack(side=tk.LEFT, padx=(0, 16))
        tk.Radiobutton(team_frame, text="⬜ 非常勤", variable=self.team_var,
                       value="非常勤", bg="white", font=("Meiryo UI", 10),
                       fg="#78716c", activebackground="white",
                       selectcolor="#f5f5f4").pack(side=tk.LEFT)

        # 既存メンバーの場合は値を設定
        if not self.is_new:
            self.name_entry.insert(0, self.member["name"])
            self.display_entry.insert(0, self.member["display_name"])
            self.skill_var.set(self.member["skill_level"])
            self.color_var.set(self.member["color"])
            self.color_preview.config(bg=self.member["color"])
            self.request_text.insert("1.0", self.member["personal_request"])
            self.team_var.set(self.member.get("team", "A"))
        
        # ボタン
        btn_frame = tk.Frame(main_frame, bg="white")
        btn_frame.pack(fill=tk.X, pady=(15, 0))
        
        tk.Button(btn_frame, text="キャンセル", command=self.dialog.destroy,
                 bg="#6b7280", fg="white", font=("Meiryo UI", 10),
                 relief=tk.FLAT, padx=20, pady=8, cursor="hand2").pack(side=tk.RIGHT, padx=(5, 0))
        
        tk.Button(btn_frame, text="保存", command=self._save,
                 bg="#10b981", fg="white", font=("Meiryo UI", 10, "bold"),
                 relief=tk.FLAT, padx=30, pady=8, cursor="hand2").pack(side=tk.RIGHT)
    
    def _choose_color(self):
        """色選択ダイアログ"""
        from tkinter import colorchooser
        color = colorchooser.askcolor(initialcolor=self.color_var.get())[1]
        if color:
            self.color_var.set(color)
            self.color_preview.config(bg=color)
    
    def _save(self):
        """保存"""
        name = self.name_entry.get().strip()
        display = self.display_entry.get().strip()
        
        if not name or not display:
            messagebox.showwarning("警告", "名前とセル表示文字を入力してください")
            return
        
        if self.is_new:
            # 新規追加
            new_member = {
                "id": str(self.app._next_member_id).zfill(3),
                "name": name,
                "display_name": display,
                "active": True,
                "skill_level": self.skill_var.get(),
                "personal_request": self.request_text.get("1.0", tk.END).strip(),
                "color": self.color_var.get(),
                "team": self.team_var.get(),
            }
            self.app.members_data.append(new_member)
            self.app._next_member_id += 1
            
            # 色辞書にも追加＆セルに反映
            self.app._apply_member_color_to_cells(display, self.color_var.get())
        else:
            # 既存編集 — 表示名変更があれば old_display_name を渡す
            old_display = self.member["display_name"]
            self.member["name"] = name
            self.member["display_name"] = display
            self.member["skill_level"] = self.skill_var.get()
            self.member["personal_request"] = self.request_text.get("1.0", tk.END).strip()
            self.member["color"] = self.color_var.get()
            self.member["team"] = self.team_var.get()
            
            # 色辞書更新＆セルに反映（表示名が変わっていれば旧名も渡す）
            self.app._apply_member_color_to_cells(
                display, self.color_var.get(),
                old_display_name=old_display if old_display != display else None
            )
        
        self.parent._refresh_member_list()
        self.dialog.destroy()



def main():
    root = tk.Tk()
    app = CalendarApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
