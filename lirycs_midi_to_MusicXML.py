import sys
import mido
import pyphen
from music21 import stream, note, duration
from PyQt6.QtWidgets import QApplication, QMainWindow, QGraphicsView, QGraphicsScene, QPushButton, QVBoxLayout, QWidget, QFileDialog, QLineEdit, QGraphicsItem
from PyQt6.QtCore import Qt, QRectF, QTimer
from PyQt6.QtGui import QColor, QPen, QFont, QBrush
import numpy as np
import pygame.mixer
import wave
import os

class PianoRoll(QGraphicsView):
    def __init__(self, notes, synced_data, tempo=120, ticks_per_beat=480):
        super().__init__()
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.notes = notes
        self.synced_data = synced_data
        self.tempo = tempo
        self.ticks_per_beat = ticks_per_beat
        self.playback_line = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_playback)
        self.current_time = 0
        self.is_playing = False
        self.temp_wav_file = "temp_audio.wav"
        self.draw_piano_roll()

    def draw_piano_roll(self):
        self.scene.clear()
        for note in self.notes:
            pitch = (127 - note['pitch']) * 5
            start = note['start'] * 100
            duration = note['duration'] * 100
            color = QColor.fromHsv(note['pitch'] % 128, 255, 200)
            rect = self.scene.addRect(QRectF(start, pitch, duration, 5), brush=QBrush(color))
            rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            rect.setData(0, note)

        for item in self.synced_data:
            start = item['start'] * 100
            matching_notes = [(127 - n['pitch']) * 5 for n in self.notes if n['start'] <= item['start'] < n['start'] + n['duration']]
            pitch = min(matching_notes) if matching_notes else 600
            text = self.scene.addText(item['word'], QFont("Arial", 8))
            text.setPos(start, pitch + 10)
            text.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            text.setData(0, item)

        self.playback_line = self.scene.addLine(0, 0, 0, 600, QPen(QColor(255, 0, 0)))

    def update_playback(self):
        seconds_per_beat = 60 / self.tempo
        seconds_per_tick = seconds_per_beat / self.ticks_per_beat
        self.current_time += seconds_per_tick * 10
        self.playback_line.setLine(self.current_time * 100, 0, self.current_time * 100, 600)
        if self.current_time > max(note['start'] + note['duration'] for note in self.notes):
            self.stop()

    def play_audio(self):
        try:
            self.play_midi()
        except Exception as e:
            print(f"Błąd odtwarzania dźwięku: {e}")

    def play_midi(self):
        sample_rate = 44100
        try:
            max_duration = max(note['start'] + note['duration'] for note in self.notes)
            audio_data = np.zeros(int(max_duration * sample_rate), dtype=np.int16)
            
            for n in self.notes:
                frequency = 440.0 * (2.0 ** ((n['pitch'] - 69) / 12.0))
                t = np.linspace(0, n['duration'], int(n['duration'] * sample_rate), False)
                note_wave = 0.5 * np.sin(2 * np.pi * frequency * t) * 32767
                start_sample = int(n['start'] * sample_rate)
                end_sample = start_sample + len(note_wave)
                audio_data[start_sample:end_sample] += note_wave[:len(audio_data[start_sample:end_sample])].astype(np.int16)

            audio_data = np.clip(audio_data, -32768, 32767).astype(np.int16)
            
            with wave.open(self.temp_wav_file, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_data.tobytes())

            pygame.mixer.init()
            pygame.mixer.music.load(self.temp_wav_file)
            pygame.mixer.music.play()
            self.current_time = 0
            self.timer.start(30)
            self.is_playing = True
        except Exception as e:
            print(f"Błąd pygame.mixer: {e}")

    def pause(self):
        if self.is_playing:
            pygame.mixer.music.pause()
            self.timer.stop()
            self.is_playing = False
        else:
            pygame.mixer.music.unpause()
            self.timer.start(30)
            self.is_playing = True

    def stop(self):
        self.timer.stop()
        pygame.mixer.music.stop()
        self.current_time = 0
        self.playback_line.setLine(0, 0, 0, 600)
        self.is_playing = False
        if os.path.exists(self.temp_wav_file):
            os.remove(self.temp_wav_file)

    def update_synced_data(self):
        for item in self.scene.items():
            if item.type() == 3:  # QGraphicsTextItem
                data = item.data(0)
                data['start'] = item.pos().x() / 100
                item.setData(0, data)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vocal Generator")
        self.setGeometry(100, 100, 800, 600)
        self.notes = []
        self.synced_data = []
        self.tempo = 120
        self.ticks_per_beat = 480

        widget = QWidget()
        self.setCentralWidget(widget)
        layout = QVBoxLayout(widget)

        self.text_input = QLineEdit(self)
        self.text_input.setPlaceholderText("Wpisz tekst piosenki...")
        layout.addWidget(self.text_input)

        self.piano_roll = PianoRoll(self.notes, self.synced_data, self.tempo, self.ticks_per_beat)
        layout.addWidget(self.piano_roll)

        self.load_btn = QPushButton("Wczytaj MIDI")
        self.sync_btn = QPushButton("Synchronizuj tekst")
        self.play_btn = QPushButton("Play")
        self.pause_btn = QPushButton("Pause")
        self.stop_btn = QPushButton("Stop")
        self.export_btn = QPushButton("Eksportuj MusicXML")

        self.load_btn.clicked.connect(self.load_midi)
        self.sync_btn.clicked.connect(self.sync_text)
        self.play_btn.clicked.connect(self.piano_roll.play_audio)
        self.pause_btn.clicked.connect(self.piano_roll.pause)
        self.stop_btn.clicked.connect(self.piano_roll.stop)
        self.export_btn.clicked.connect(self.export_musicxml)

        layout.addWidget(self.load_btn)
        layout.addWidget(self.sync_btn)
        layout.addWidget(self.play_btn)
        layout.addWidget(self.pause_btn)
        layout.addWidget(self.stop_btn)
        layout.addWidget(self.export_btn)

    def load_midi(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Wczytaj plik MIDI", "", "MIDI Files (*.mid)")
        if file_path:
            self.notes, self.tempo, self.ticks_per_beat = parse_midi(file_path)
            self.sync_text()

    def sync_text(self):
        if not self.notes or not self.text_input.text():
            print("Brak MIDI lub tekstu!")
            return
        text = self.text_input.text()
        self.synced_data = sync_text_to_midi_advanced(self.notes, text)
        self.piano_roll.notes = self.notes
        self.piano_roll.synced_data = self.synced_data
        self.piano_roll.tempo = self.tempo
        self.piano_roll.ticks_per_beat = self.ticks_per_beat
        self.piano_roll.draw_piano_roll()

    def export_musicxml(self):
        self.piano_roll.update_synced_data()
        if self.synced_data:
            try:
                create_musicxml(self.synced_data, 'output.xml')
                print("Zapisano output.xml – użyj Sinsy do generacji wokalu.")
            except Exception as e:
                print(f"Błąd eksportu MusicXML: {e}")
        else:
            print("Brak danych do eksportu!")

def parse_midi(file_path):
    midi = mido.MidiFile(file_path)
    notes = []
    current_time = 0
    tempo = 120
    ticks_per_beat = midi.ticks_per_beat
    min_duration = 1/64  # Minimalna długość w beatach

    for track in midi.tracks:
        for msg in track:
            if msg.type == 'set_tempo':
                tempo = mido.tempo2bpm(msg.tempo)
            elif msg.type in ['note_on', 'note_off']:
                delta_time = max(msg.time / ticks_per_beat, min_duration)
                current_time += delta_time
                if msg.type == 'note_on' and msg.velocity > 0:
                    notes.append({'pitch': msg.note, 'start': current_time, 'duration': 0})
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    for note in reversed(notes):
                        if note['pitch'] == msg.note and note['duration'] == 0:
                            note['duration'] = max(current_time - note['start'], min_duration)
                            break
    normalized_notes = normalize_durations(notes)
    return normalized_notes, tempo, ticks_per_beat

def normalize_durations(notes):
    # Normalizuj trwanie nut do wartości wyrażalnych w MusicXML
    valid_durations = [1, 1/2, 1/4, 1/8, 1/16, 1/32, 1/64, 1/128, 1/256]  # Standardowe wartości MusicXML
    for note in notes:
        dur = note['duration']
        # Znajdź najbliższą wyrażalną wartość
        note['duration'] = min(valid_durations, key=lambda x: abs(x - dur))
        if note['duration'] < 1/256:  # Minimum MusicXML
            note['duration'] = 1/256
    return notes

def sync_text_to_midi_advanced(notes, text):
    words = text.split()
    if not words or not notes:
        return []

    total_midi_duration = max(note['start'] + note['duration'] for note in notes)
    word_interval = total_midi_duration / len(words)

    synced = []
    note_index = 0
    for i, word in enumerate(words):
        word_start = i * word_interval
        while note_index < len(notes) - 1 and notes[note_index]['start'] + notes[note_index]['duration'] < word_start:
            note_index += 1
        note = notes[note_index]
        synced.append({
            'pitch': note['pitch'],
            'start': word_start,
            'duration': note['duration'],  # Użyj znormalizowanego trwania
            'word': word
        })

    return synced

def create_musicxml(synced_data, output_file):
    s = stream.Stream()
    min_duration = 1/64
    for item in synced_data:
        dur = max(item['duration'], min_duration)
        n = note.Note(midi=item['pitch'], quarterLength=dur * 4)
        n.lyric = item['word']
        # Normalizuj trwanie do wartości MusicXML
        valid_durations = [4, 2, 1, 0.5, 0.25, 0.125, 0.0625, 0.03125, 0.015625]  # quarterLength: 1 = ćwierćnuta
        n.duration.quarterLength = min(valid_durations, key=lambda x: abs(x - n.duration.quarterLength))
        if n.duration.quarterLength < 0.015625:  # 1/256 nuty
            n.duration.quarterLength = 0.015625
        s.append(n)
    s.write('musicxml', fp=output_file)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
