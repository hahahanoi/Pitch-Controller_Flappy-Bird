# Fourier Bird: Pitch Control

A small Pygame arcade game controlled by microphone pitch. The game opens an 800 × 600 window and uses a microphone to read audio at 44.1 kHz, mono. It does not need a camera or a dedicated graphics card.

## Requirements

- Windows, macOS, or Linux
- Python 3.11 recommended (the project was checked with Python 3.11)
- A working microphone and permission for Python to use it
- An audio input device/driver that supports 44.1 kHz mono capture
- Internet access for the first-time installation of Python packages

The game uses `pygame`, `pyaudio`, and `numpy`, listed in `requirements.txt`. PyAudio also needs PortAudio support from the operating system. On Windows, pip normally installs its wheel. On macOS and Linux, install PortAudio before installing the Python requirements.

## Windows setup and launch

Install Python 3.11 from [python.org](https://www.python.org/downloads/) and select **Add python.exe to PATH** during setup. Open PowerShell in this project folder and run:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

After setup, double-click `Start Game.bat` to launch the game. You can also start it from PowerShell:

```powershell
.\.venv\Scripts\python.exe main_game.py
```

## macOS setup and launch

Install Python 3.11 or newer. If you use Homebrew, install the PortAudio library first:

```sh
brew install portaudio
```

In Terminal, change to this project folder, then run:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main_game.py
```

If macOS asks for microphone access, allow it for the terminal or Python application you use to launch the game.

## Linux setup and launch

On Debian or Ubuntu, install Python, venv support, and PortAudio headers:

```sh
sudo apt update
sudo apt install python3 python3-venv python3-pip portaudio19-dev
```

In a terminal opened in this project folder, run:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main_game.py
```

Other Linux distributions may use different package names for PortAudio and Python.

## Playing

- The voice-control start prompt asks for a steady pitch around 150 Hz. Hold it until the progress bar completes, then follow the prompts to sing your lowest and highest comfortable notes for calibration.
- You can also press a key or click to start without voice calibration. During play, **Up** or **W** moves the bird up; **Down** or **S** moves it down. Holding the left mouse button also moves it up.
- The game still opens the microphone when it starts, even if you plan to use keyboard controls.
- Press a key or click after game over to return to the menu.

## Troubleshooting

- **Microphone/audio startup error:** Check that the microphone is connected, selected as an input device, and allowed for desktop applications. Close other apps that may have exclusive access to it. The game currently requires microphone initialization even when using keyboard controls.
- **`No module named ...`:** Activate/use the project `.venv` Python and install requirements again with `python -m pip install -r requirements.txt`.
- **PyAudio installation fails on macOS/Linux:** Install the operating-system PortAudio package, then repeat the pip install command.
- **No sound:** Music and effects are optional; the game can run without them.

## Project files

- `main_game.py` — game source
- `requirements.txt` — Python dependencies
- `Start Game.bat` — one-click launcher for Windows after setup
- `spaceship.png`, `bgm.mp3`, `crash.wav`, `impact.wav`, `LogoITB.png` — included graphics and audio assets

The game can fall back to built-in pipe/background graphics when optional texture files are absent. A `highscore.txt` file is created in the project folder when a high score is saved.
