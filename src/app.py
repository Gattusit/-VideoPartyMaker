import json
import re
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QPushButton, QLabel, QSpinBox,
    QFileDialog, QMessageBox, QComboBox, QProgressBar, QInputDialog
)

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".caf", ".flac"}


def numeric_key(path: Path):
    # Gestisce 1, 02, 2, 10 in modo naturale.
    nums = re.findall(r"\d+", path.stem)
    if nums:
        return (0, int(nums[-1]), path.name.lower())
    return (1, path.name.lower())


def smart_sort(paths):
    paths = [Path(p) for p in paths]
    numbered = [p for p in paths if re.search(r"\d+", p.stem)]
    if paths and len(numbered) >= len(paths) * 0.7:
        return sorted(paths, key=numeric_key)
    return paths


def ffmpeg_exists():
    return shutil.which("ffmpeg") is not None


class RenderThread(QThread):
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, images, audio, duration, profile, output):
        super().__init__()
        self.images = images
        self.audio = audio
        self.duration = duration
        self.profile = profile
        self.output = output

    def run(self):
        try:
            if not ffmpeg_exists():
                raise RuntimeError(
                    "FFmpeg non trovato nel PATH. Installalo e riapri l'app."
                )

            widths = {
                "4K": (3840, 2160),
                "Full HD 1080p": (1920, 1080),
                "HD 720p": (1280, 720),
                "WhatsApp": (1920, 1080),
            }
            width, height = widths[self.profile]

            work = Path(self.output).parent
            concat = work / "_vpm_images.txt"

            with concat.open("w", encoding="utf-8") as f:
                for image in self.images:
                    p = Path(image).resolve()
                    # concat demuxer: escape apostrophi.
                    s = str(p).replace("'", "'\\''")
                    f.write(f"file '{s}'\n")
                    f.write(f"duration {self.duration}\n")
                p = Path(self.images[-1]).resolve()
                s = str(p).replace("'", "'\\''")
                f.write(f"file '{s}'\n")

            vf = (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
                "format=yuv420p"
            )

            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat)
            ]

            if self.audio:
                cmd += ["-i", self.audio]

            cmd += [
                "-vf", vf,
                "-r", "25",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "20",
                "-movflags", "+faststart",
            ]

            if self.audio:
                cmd += [
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                ]

            cmd += [self.output]

            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            try:
                concat.unlink()
            except OSError:
                pass

            self.finished_ok.emit(self.output)

        except Exception as e:
            self.failed.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Party Maker")
        self.resize(1250, 780)

        self.images = []
        self.audio = None
        self.render_thread = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        title = QLabel("🎬 Video Party Maker")
        title.setStyleSheet("font-size: 26px; font-weight: bold;")
        root.addWidget(title)

        top = QHBoxLayout()
        self.add_btn = QPushButton("➕ Aggiungi foto")
        self.audio_btn = QPushButton("🎵 Aggiungi audio")
        self.voice_btn = QPushButton("🎙 Registra voce")
        self.save_btn = QPushButton("💾 Salva progetto")
        self.export_btn = QPushButton("🚀 Esporta MP4")

        for b in (self.add_btn, self.audio_btn, self.voice_btn,
                  self.save_btn, self.export_btn):
            top.addWidget(b)

        root.addLayout(top)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Durata foto:"))
        self.duration = QSpinBox()
        self.duration.setRange(1, 60)
        self.duration.setValue(4)
        self.duration.setSuffix(" s")
        controls.addWidget(self.duration)

        controls.addWidget(QLabel("Qualità:"))
        self.profile = QComboBox()
        self.profile.addItems(["Full HD 1080p", "4K", "HD 720p", "WhatsApp"])
        controls.addWidget(self.profile)
        controls.addStretch()

        self.audio_label = QLabel("Audio: nessuno")
        controls.addWidget(self.audio_label)
        root.addLayout(controls)

        self.list = QListWidget()
        self.list.setAcceptDrops(True)
        self.list.setDragDropMode(QListWidget.DropOnly)
        self.list.setIconSize(self.list.iconSize())
        self.list.setStyleSheet(
            "QListWidget { font-size: 16px; padding: 10px; }"
        )
        root.addWidget(self.list, 1)

        self.status = QLabel("Trascina qui le foto per iniziare.")
        root.addWidget(self.status)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        root.addWidget(self.progress)

        self.add_btn.clicked.connect(self.add_images)
        self.audio_btn.clicked.connect(self.add_audio)
        self.voice_btn.clicked.connect(self.record_voice)
        self.save_btn.clicked.connect(self.save_project)
        self.export_btn.clicked.connect(self.export_video)

        self.list.dropEvent = self.dropEvent
        self.list.dragEnterEvent = self.dragEnterEvent
        self.list.dragMoveEvent = self.dragMoveEvent

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [
            u.toLocalFile()
            for u in event.mimeData().urls()
            if u.isLocalFile()
        ]
        self.add_paths(paths)
        event.acceptProposedAction()

    def add_images(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Seleziona foto",
            "",
            "Immagini (*.jpg *.jpeg *.png *.webp *.bmp)"
        )
        self.add_paths(files)

    def add_paths(self, paths):
        images = [
            Path(p) for p in paths
            if Path(p).suffix.lower() in IMAGE_EXT
        ]
        self.images.extend(str(p) for p in images)
        self.images = [str(p) for p in smart_sort(self.images)]
        self.refresh_list()

    def refresh_list(self):
        self.list.clear()
        for i, p in enumerate(self.images, 1):
            item = QListWidgetItem(f"{i:03d}   {Path(p).name}")
            self.list.addItem(item)
        self.status.setText(f"{len(self.images)} foto in timeline.")

    def add_audio(self):
        file, _ = QFileDialog.getOpenFileName(
            self,
            "Seleziona audio",
            "",
            "Audio (*.mp3 *.wav *.m4a *.aac *.caf *.flac)"
        )
        if file:
            self.audio = file
            self.audio_label.setText(f"Audio: {Path(file).name}")

    def record_voice(self):
        try:
            import sounddevice as sd
            import numpy as np
        except Exception:
            QMessageBox.warning(
                self, "Registrazione",
                "Modulo audio non disponibile. Esegui: pip install sounddevice numpy"
            )
            return

        seconds, ok = QInputDialog.getInt(
            self, "Registrazione voce",
            "Durata registrazione (secondi):", 10, 1, 300
        )
        if not ok:
            return

        output, _ = QFileDialog.getSaveFileName(
            self, "Salva registrazione", "voice.wav",
            "WAV (*.wav)"
        )
        if not output:
            return

        try:
            sample_rate = 48000
            recording = sd.rec(
                int(seconds * sample_rate),
                samplerate=sample_rate,
                channels=2,
                dtype="float32"
            )
            sd.wait()

            import wave
            data = np.clip(recording, -1, 1)
            data = (data * 32767).astype(np.int16)

            with wave.open(output, "wb") as wf:
                wf.setnchannels(2)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(data.tobytes())

            self.audio = output
            self.audio_label.setText(f"Audio: {Path(output).name}")
        except Exception as e:
            QMessageBox.critical(self, "Errore registrazione", str(e))

    def save_project(self):
        file, _ = QFileDialog.getSaveFileName(
            self, "Salva progetto", "project.json",
            "Video Party Project (*.json)"
        )
        if not file:
            return

        data = {
            "version": 1,
            "images": self.images,
            "audio": self.audio,
            "photo_duration": self.duration.value(),
            "profile": self.profile.currentText()
        }

        Path(file).write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        QMessageBox.information(self, "Salvato", "Progetto salvato.")

    def export_video(self):
        if not self.images:
            QMessageBox.warning(
                self, "Esportazione",
                "Aggiungi almeno una foto."
            )
            return

        if not ffmpeg_exists():
            QMessageBox.critical(
                self, "FFmpeg mancante",
                "FFmpeg non è installato o non è nel PATH."
            )
            return

        output, _ = QFileDialog.getSaveFileName(
            self, "Esporta video", "video_party.mp4",
            "Video MP4 (*.mp4)"
        )
        if not output:
            return

        self.export_btn.setEnabled(False)
        self.progress.show()
        self.status.setText("Rendering in corso...")

        self.render_thread = RenderThread(
            self.images,
            self.audio,
            self.duration.value(),
            self.profile.currentText(),
            output
        )
        self.render_thread.finished_ok.connect(self.render_ok)
        self.render_thread.failed.connect(self.render_failed)
        self.render_thread.start()

    def render_ok(self, output):
        self.progress.hide()
        self.export_btn.setEnabled(True)
        self.status.setText("Rendering completato.")
        QMessageBox.information(
            self, "Completato",
            f"Video creato:\n{output}"
        )

    def render_failed(self, error):
        self.progress.hide()
        self.export_btn.setEnabled(True)
        self.status.setText("Errore durante il rendering.")
        QMessageBox.critical(self, "Errore FFmpeg", error)


def main():
    app = QApplication([])
    app.setApplicationName("Video Party Maker")
    window = MainWindow()
    window.show()
    app.exec()
