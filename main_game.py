import pygame
import pyaudio
import numpy as np
import random
import os
import math
from statistics import median

current_mag = 0
# --- 1. Audio Configuration ---
CHUNK = 2048
RATE = 44100
p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True, frames_per_buffer=CHUNK)

# --- 2. Pygame Setup ---
pygame.init()
pygame.mixer.init()
WIDTH, HEIGHT = 800, 600
window = pygame.display.set_mode((WIDTH, HEIGHT))          # jendela asli yang tampil ke layar
screen = pygame.Surface((WIDTH, HEIGHT))                    # buffer gambar offscreen (untuk screen-shake)
pygame.display.set_caption("Fourier Bird: Pitch Control")
clock = pygame.time.Clock()

# --- Musik & Efek Suara (opsional, tidak wajib ada filenya) ---
try:
    pygame.mixer.music.load("bgm.mp3")
    pygame.mixer.music.set_volume(0.5)
    pygame.mixer.music.play(-1)  # loop selamanya
    has_music = True
except (pygame.error, FileNotFoundError):
    has_music = False

try:
    crash_sound = pygame.mixer.Sound("crash.wav")
    crash_sound.set_volume(1.0)
    has_crash_sound = True
except (pygame.error, FileNotFoundError):
    has_crash_sound = False

# Lapisan suara kedua (opsional) — misalnya "boom" berat di bawah suara crash yang tajam
try:
    impact_sound = pygame.mixer.Sound("impact.wav")
    impact_sound.set_volume(1.0)
    has_impact_sound = True
except (pygame.error, FileNotFoundError):
    has_impact_sound = False

wakeup_target = 150       # Nada target (Hz)
wakeup_tolerance = 50     # Toleransi +/- 50 Hz
wakeup_progress = 0       # Progress menahan nada

# Colors
BLACK = (10, 10, 15)
NEON_BLUE = (0, 255, 255)
NEON_PINK = (255, 20, 147)
NEON_GREEN = (57, 255, 20)

# --- Game Variables & High Score ---
HIGH_SCORE_FILE = "highscore.txt"


def load_high_score():
    if os.path.exists(HIGH_SCORE_FILE):
        with open(HIGH_SCORE_FILE, "r") as f:
            try:
                return int(f.read())
            except ValueError:
                return 0
    return 0


def save_high_score(score):
    with open(HIGH_SCORE_FILE, "w") as f:
        f.write(str(score))


high_score = load_high_score()

bird_x = 150
bird_y = HEIGHT // 2
image_size = 60
bird_radius = image_size // 2   # 40 — hitbox matches sprite size
target_freq_min = 150
target_freq_max = 800

# --- Kalibrasi rentang suara per pemain ---
calib_low = None
calib_high = None
calib_samples = []
calib_timer = 0
CALIB_HOLD_TARGET = 100   # skala sama dengan wakeup_progress
CALIB_MARGIN = 20         # Hz, sedikit ruang ekstra di atas/bawah rentang yang dinyanyikan
CALIB_MIN_RANGE = 60      # Hz, jarak minimum low-high agar rentang tidak terlalu sempit

# --- Load Custom Graphics ---
player_img = pygame.image.load("spaceship.png").convert_alpha()
player_img = pygame.transform.scale(player_img, (image_size, image_size))


def get_average_color(surface, fallback=(0, 255, 255)):
    """Warna rata-rata piksel yang tidak transparan pada sprite, dipakai supaya
    efek seperti ledakan partikel otomatis senada dengan sprite apa pun yang dipakai."""
    try:
        arr = pygame.surfarray.array3d(surface)
        alpha = pygame.surfarray.array_alpha(surface)
        mask = alpha > 10
        if not mask.any():
            return fallback
        r = int(arr[:, :, 0][mask].mean())
        g = int(arr[:, :, 1][mask].mean())
        b = int(arr[:, :, 2][mask].mean())
        return (r, g, b)
    except Exception:
        return fallback


SHIP_COLOR = get_average_color(player_img)

pipe_width = 80
pipe_gap = 200
pipe_speed = 4
PIPE_SPACING = 300   # jarak horizontal antar pipa — atur ini untuk mengubah kesulitan
pipes = []


def get_gap_y_bounds(current_score):
    """
    Sistem stage: pipa awal hanya muncul di bagian bawah layar (freq rendah,
    lebih mudah dijangkau), lalu makin melebar ke atas seiring skor naik.
    """
    full_lo = 100
    full_hi = HEIGHT - pipe_gap - 100

    if current_score < 2:
        lo = max(full_lo, full_hi - 150)   # hanya area bawah
    elif current_score < 12:
        lo = max(full_lo, full_hi - 320)   # melebar ke tengah
    else:
        lo = full_lo                        # rentang penuh

    return lo, full_hi


def spawn_pipe(x):
    lo, hi = get_gap_y_bounds(score)
    if hi < lo:
        hi = lo
    gap_y = random.randint(lo, hi)
    return {"x": x, "gap_y": gap_y, "scored": False}


def reset_pipes():
    global pipes
    pipes = [spawn_pipe(WIDTH + i * PIPE_SPACING) for i in range(3)]


def reset_run():
    """Single source of truth for starting/restarting a run."""
    global score, bird_y, target_y
    score = 0
    bird_y = HEIGHT // 2
    target_y = HEIGHT // 2
    freq_history.clear()
    bird_trail.clear()
    reset_pipes()


state = "MENU"
score = 0
freq_history = []
target_y = HEIGHT // 2

# --- Load Pipe Textures (optional) ---
try:
    pipe_body_img = pygame.image.load("pipe_body.png").convert_alpha()
    pipe_cap_img = pygame.image.load("pipe_cap.png").convert_alpha()
    pipe_body_img = pygame.transform.scale(pipe_body_img, (pipe_width, 40))
    pipe_cap_img = pygame.transform.scale(pipe_cap_img, (pipe_width + 14, 30))
    has_pipe_texture = True
except FileNotFoundError:
    has_pipe_texture = False

# --- Load Background (optional) ---
try:
    bg_img = pygame.image.load("background.png").convert()
    bg_img = pygame.transform.scale(bg_img, (WIDTH, HEIGHT))
    has_bg = True
except FileNotFoundError:
    has_bg = False


def get_peak_frequency():
    global current_mag
    try:
        data = stream.read(CHUNK, exception_on_overflow=False)
        audio_data = np.frombuffer(data, dtype=np.int16)
        fft_result = np.fft.rfft(audio_data * np.hanning(CHUNK))
        frequencies = np.fft.rfftfreq(CHUNK, d=1.0 / RATE)
        magnitudes = np.abs(fft_result)

        peak_index = np.argmax(magnitudes)
        current_mag = magnitudes[peak_index]

        if current_mag > 300000:  # <-- NOISE GATE, tune di sini
            return frequencies[peak_index]
    except Exception as e:
        print(f"Audio error: {e}")
    return None


def draw_pipe(surface, x, y_top, y_bottom, width, cap_h=30):
    if has_pipe_texture:
        tile_h = pipe_body_img.get_height()
        y = y_top - cap_h
        while y > -tile_h:
            surface.blit(pipe_body_img, (x, y))
            y -= tile_h
        surface.blit(pipe_cap_img, (x - 7, y_top - cap_h))

        y = y_bottom + cap_h
        while y < HEIGHT:
            surface.blit(pipe_body_img, (x, y))
            y += tile_h
        surface.blit(pipe_cap_img, (x - 7, y_bottom))
    else:
        # --- Gaya Geometry Dash: blok tajam + duri (spike) menghadap ke celah ---
        body_top = pygame.Rect(x, 0, width, max(0, y_top - cap_h))
        body_bottom = pygame.Rect(x, y_bottom + cap_h, width, HEIGHT - y_bottom - cap_h)

        # glow lembut di belakang blok
        glow_surf = pygame.Surface((width + 16, HEIGHT), pygame.SRCALPHA)
        pygame.draw.rect(glow_surf, (*NEON_PINK, 50), (0, 0, width + 16, body_top.height))
        pygame.draw.rect(glow_surf, (*NEON_PINK, 50), (0, body_bottom.top, width + 16, body_bottom.height))
        surface.blit(glow_surf, (x - 8, 0))

        # badan blok, sudut tajam (tanpa border_radius)
        pygame.draw.rect(surface, NEON_PINK, body_top)
        pygame.draw.rect(surface, NEON_PINK, body_bottom)
        pygame.draw.rect(surface, (255, 180, 220), body_top, width=2)
        pygame.draw.rect(surface, (255, 180, 220), body_bottom, width=2)

        # duri (spike) menghadap ke celah — ciri khas Geometry Dash
        top_spike = [(x, y_top - cap_h), (x + width, y_top - cap_h), (x + width / 2, y_top)]
        bottom_spike = [(x, y_bottom + cap_h), (x + width, y_bottom + cap_h), (x + width / 2, y_bottom)]
        pygame.draw.polygon(surface, NEON_PINK, top_spike)
        pygame.draw.polygon(surface, NEON_PINK, bottom_spike)
        pygame.draw.polygon(surface, (255, 180, 220), top_spike, width=2)
        pygame.draw.polygon(surface, (255, 180, 220), bottom_spike, width=2)


bird_trail = []
TRAIL_LENGTH = 25


def draw_bird_trail(surface, trail, sprite):
    """
    trail: list of (x, y, tilt_angle).
    Menjejak dengan salinan sprite kapal itu sendiri (diskalakan & diputar sesuai
    kemiringan saat itu) yang memudar dan mengecil — otomatis cocok dengan
    bentuk sprite apa pun, bukan cuma lingkaran generik.
    """
    n = len(trail)
    if n < 2:
        return
    trail_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    base_w, base_h = sprite.get_width(), sprite.get_height()
    for i, (tx, ty, tangle) in enumerate(trail):
        progress = i / n
        alpha = int(150 * progress)
        scale = 0.35 + 0.5 * progress
        w = max(2, int(base_w * scale))
        h = max(2, int(base_h * scale))
        ghost = pygame.transform.smoothscale(sprite, (w, h))
        ghost = pygame.transform.rotate(ghost, tangle)
        ghost.set_alpha(alpha)
        rect = ghost.get_rect(center=(int(tx), int(ty)))
        trail_surf.blit(ghost, rect)
    surface.blit(trail_surf, (0, 0))


# --- Efek ledakan partikel + screen-shake saat tabrakan (gaya Geometry Dash) ---
particles = []
screen_shake_timer = 0

# --- Efek "tirai" menutup sebelum layar GAME OVER ---
frozen_frame = None
curtain_timer = 0
CURTAIN_DURATION = 30  # ~0.5 detik pada 60 FPS

# --- Latar belakang bergerak (parallax) ---
bg_scroll_x = 0.0       # latar belakang jauh, bergerak lambat (efek parallax/kedalaman)

# --- Latar retro synthwave prosedural (dipakai kalau background.png tidak ada) ---
RETRO_SKY = (15, 5, 30)
RETRO_HORIZON_Y = int(HEIGHT * 0.55)
RETRO_SUN_RADIUS = 90
RETRO_SUN_CENTER = (WIDTH // 2, RETRO_HORIZON_Y - 20)


def _build_retro_sun():
    """Matahari bergaris khas retrowave, dirender sekali dan di-cache (biar hemat performa)."""
    sun_surf = pygame.Surface((RETRO_SUN_RADIUS * 2, RETRO_SUN_RADIUS * 2), pygame.SRCALPHA)
    for i in range(RETRO_SUN_RADIUS, 0, -3):
        t = i / RETRO_SUN_RADIUS
        color = (
            int(255 * t + NEON_PINK[0] * (1 - t)),
            int(90 * t + NEON_PINK[1] * (1 - t)),
            int(60 * t + NEON_PINK[2] * (1 - t)),
        )
        pygame.draw.circle(sun_surf, color, (RETRO_SUN_RADIUS, RETRO_SUN_RADIUS), i)
    # garis-garis horizontal yang memotong matahari, ciri khas gaya ini
    for stripe_y in range(RETRO_SUN_RADIUS + 10, RETRO_SUN_RADIUS * 2, 9):
        pygame.draw.rect(sun_surf, RETRO_SKY, (0, stripe_y, RETRO_SUN_RADIUS * 2, 4))
    return sun_surf


RETRO_SUN_SURF = _build_retro_sun()


def draw_retro_background(surface, scroll):
    surface.fill(RETRO_SKY)
    surface.blit(RETRO_SUN_SURF, (RETRO_SUN_CENTER[0] - RETRO_SUN_RADIUS, RETRO_SUN_CENTER[1] - RETRO_SUN_RADIUS))
    pygame.draw.line(surface, NEON_PINK, (0, RETRO_HORIZON_Y), (WIDTH, RETRO_HORIZON_Y), 2)

    # Garis grid diagonal menuju satu titik hilang (perspektif)
    vanish_x = WIDTH // 2
    for i in range(-10, 11):
        x_top = vanish_x + i * 20
        x_bottom = vanish_x + i * 160
        pygame.draw.line(surface, NEON_BLUE, (x_top, RETRO_HORIZON_Y), (x_bottom, HEIGHT), 1)

    # Garis grid horizontal yang bergerak (scroll), makin rapat mendekati horizon
    grid_spacing = 28
    offset = int(scroll * 0.5) % grid_spacing
    y = HEIGHT - offset
    while y > RETRO_HORIZON_Y:
        pygame.draw.line(surface, NEON_BLUE, (0, y), (WIDTH, y), 1)
        y -= grid_spacing


# --- Denyut visual mengikuti tempo musik (bukan analisis audio real-time) ---
MUSIC_BPM = 128  # sesuaikan dengan tempo lagu bgm.mp3 kamu


def get_beat_pulse():
    """Nilai 0..1 yang 'berdenyut' cepat naik lalu meluruh, sinkron ke MUSIC_BPM."""
    if not has_music:
        return 0.0
    pos_ms = pygame.mixer.music.get_pos()
    if pos_ms < 0:
        return 0.0
    beat_ms = 60000.0 / MUSIC_BPM
    phase = (pos_ms % beat_ms) / beat_ms  # 0..1 di dalam satu ketukan
    return max(0.0, 1.0 - phase * 3.0)


def spawn_particle_burst(x, y, color, count=30):
    for _ in range(count):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(2, 8)
        particles.append({
            "x": x, "y": y,
            "vx": math.cos(angle) * speed,
            "vy": math.sin(angle) * speed,
            "life": random.randint(20, 40),
            "color": color,
        })


def update_and_draw_particles(surface):
    global particles
    alive = []
    for prt in particles:
        prt["x"] += prt["vx"]
        prt["y"] += prt["vy"]
        prt["vy"] += 0.15  # sedikit gravitasi
        prt["life"] -= 1
        if prt["life"] > 0:
            alive.append(prt)
            fade = max(0.0, min(1.0, prt["life"] / 40))
            alpha = int(255 * fade)
            size = max(1, int(4 * fade))
            particle_surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
            pygame.draw.rect(particle_surf, (*prt["color"], alpha), (0, 0, size * 2, size * 2))
            surface.blit(particle_surf, (int(prt["x"] - size), int(prt["y"] - size)))
    particles = alive


# --- 3. Main Game Loop ---
running = True
while running:
    if state in ("PLAYING", "CURTAIN"):
        if has_bg:
            bg_x = -(int(bg_scroll_x) % WIDTH)
            screen.blit(bg_img, (bg_x, 0))
            screen.blit(bg_img, (bg_x + WIDTH, 0))
        else:
            draw_retro_background(screen, bg_scroll_x)
    else:
        screen.fill(BLACK)  # layar menu/kalibrasi/game-over polos, biar teks jelas terbaca

    current_freq = get_peak_frequency()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.KEYDOWN:
            if state == "MENU":
                state = "PLAYING"
                reset_run()
            elif state == "GAME_OVER":
                state = "MENU"
                wakeup_progress = 0
                if has_music:
                    pygame.mixer.music.set_volume(0.5)  # kembalikan volume musik

        if event.type == pygame.MOUSEBUTTONDOWN:
            if state == "MENU":
                state = "PLAYING"
                reset_run()
            elif state == "GAME_OVER":
                state = "MENU"
                wakeup_progress = 0
                if has_music:
                    pygame.mixer.music.set_volume(0.5)  # kembalikan volume musik

    # ==========================================
    # STATE 1: MENU AWAL
    # ==========================================
    if state == "MENU":
        font_title = pygame.font.SysFont("Arial", 60, bold=True)
        font_sub = pygame.font.SysFont("Arial", 30)
        font_inst = pygame.font.SysFont("Arial", 24)

        title_txt = font_title.render("FOURIER BIRD", True, NEON_BLUE)
        screen.blit(title_txt, (WIDTH // 2 - title_txt.get_width() // 2, HEIGHT // 3 - 50))

        if current_freq:
            if (wakeup_target - wakeup_tolerance) <= current_freq <= (wakeup_target + wakeup_tolerance):
                wakeup_progress += 2
                feedback_txt = font_sub.render("TAHAN...", True, NEON_GREEN)
            else:
                wakeup_progress = max(0, wakeup_progress - 1)
                if current_freq < wakeup_target:
                    feedback_txt = font_sub.render("Nada terlalu rendah! Naikkan ⬆️", True, (255, 150, 0))
                else:
                    feedback_txt = font_sub.render("Nada terlalu tinggi! Turunkan ⬇️", True, (255, 150, 0))
        else:
            wakeup_progress = max(0, wakeup_progress - 1)
            feedback_txt = font_sub.render(f"Nyanyikan nada {wakeup_target} Hz untuk Mulai!", True, NEON_PINK)

        screen.blit(feedback_txt, (WIDTH // 2 - feedback_txt.get_width() // 2, HEIGHT // 2))

        bar_width = 200
        pygame.draw.rect(screen, (50, 50, 50), (WIDTH // 2 - bar_width // 2, HEIGHT // 2 + 50, bar_width, 20))
        pygame.draw.rect(screen, NEON_GREEN,
                          (WIDTH // 2 - bar_width // 2, HEIGHT // 2 + 50, min(bar_width, wakeup_progress * 2), 20))

        if wakeup_progress >= 100:
            state = "CALIB_LOW"
            calib_samples = []
            calib_timer = 0
            wakeup_progress = 0

        inst_1 = font_inst.render("🎤 Kendalikan ketinggian dengan nada suaramu", True, (200, 200, 200))
        inst_2 = font_inst.render(
            f"🎯 Target: {wakeup_target} Hz | Sekarang: {int(current_freq) if current_freq else 0} Hz", True,
            NEON_BLUE)
        screen.blit(inst_1, (WIDTH // 2 - inst_1.get_width() // 2, HEIGHT - 120))
        screen.blit(inst_2, (WIDTH // 2 - inst_2.get_width() // 2, HEIGHT - 80))

    # ==========================================
    # STATE 1.5: KALIBRASI RENTANG SUARA (per pemain)
    # ==========================================
    elif state == "CALIB_LOW" or state == "CALIB_HIGH":
        font_title = pygame.font.SysFont("Arial", 40, bold=True)
        font_sub = pygame.font.SysFont("Arial", 26)

        title_txt = font_title.render("KALIBRASI SUARA", True, NEON_BLUE)
        screen.blit(title_txt, (WIDTH // 2 - title_txt.get_width() // 2, HEIGHT // 4))

        if state == "CALIB_LOW":
            prompt = "Nyanyikan nada TERENDAH yang nyaman untukmu..."
        else:
            prompt = "Sekarang nyanyikan nada TERTINGGI yang nyaman..."
        prompt_txt = font_sub.render(prompt, True, NEON_PINK)
        screen.blit(prompt_txt, (WIDTH // 2 - prompt_txt.get_width() // 2, HEIGHT // 2 - 40))

        if current_freq:
            calib_samples.append(current_freq)
            calib_timer += 2
            reading_txt = font_sub.render(f"{int(current_freq)} Hz", True, NEON_GREEN)
        else:
            calib_timer = max(0, calib_timer - 1)
            reading_txt = font_sub.render("...", True, (150, 150, 150))
        screen.blit(reading_txt, (WIDTH // 2 - reading_txt.get_width() // 2, HEIGHT // 2))

        bar_width = 200
        pygame.draw.rect(screen, (50, 50, 50), (WIDTH // 2 - bar_width // 2, HEIGHT // 2 + 50, bar_width, 20))
        pygame.draw.rect(screen, NEON_GREEN,
                          (WIDTH // 2 - bar_width // 2, HEIGHT // 2 + 50, min(bar_width, calib_timer * 2), 20))

        if calib_timer >= CALIB_HOLD_TARGET and calib_samples:
            if state == "CALIB_LOW":
                calib_low = median(calib_samples)
                calib_samples = []
                calib_timer = 0
                state = "CALIB_HIGH"
            else:
                calib_high = median(calib_samples)
                calib_samples = []
                calib_timer = 0

                if calib_high - calib_low < CALIB_MIN_RANGE:
                    # Rentang terlalu sempit (kemungkinan nada datar) -> pakai default aman
                    target_freq_min = 150
                    target_freq_max = 800
                else:
                    target_freq_min = max(80, calib_low - CALIB_MARGIN)
                    target_freq_max = min(1200, calib_high + CALIB_MARGIN)

                state = "PLAYING"
                reset_run()

    # ==========================================
    # STATE 2: BERMAIN
    # ==========================================
    elif state == "PLAYING":
        keys = pygame.key.get_pressed()
        mouse_pressed = pygame.mouse.get_pressed()[0]
        keyboard_active = False

        if keys[pygame.K_UP] or keys[pygame.K_w] or mouse_pressed:
            target_y = max(50, target_y - 15)
            keyboard_active = True
        elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
            target_y = min(HEIGHT - 50, target_y + 15)
            keyboard_active = True

        if not keyboard_active:
            if current_freq:
                freq_history.append(current_freq)
                if len(freq_history) > 5:
                    freq_history.pop(0)
                smoothed_freq = sum(freq_history) / len(freq_history)
                target_y = np.interp(smoothed_freq, [target_freq_min, target_freq_max], [HEIGHT - 50, 50])
            else:
                bird_trail.clear()
                target_y += 10

        # --- Fisika dulu, baru gambar (urutan diperbaiki) ---
        velocity = (target_y - bird_y) * 0.15   # dipakai juga untuk memiringkan kapal
        bird_y += velocity
        tilt_angle = max(-35, min(35, -velocity * 4))   # balik tandanya jika arahnya terlihat terbalik

        bird_trail.append((bird_x, bird_y, tilt_angle))
        if len(bird_trail) > TRAIL_LENGTH:
            bird_trail.pop(0)

        draw_bird_trail(screen, bird_trail, player_img)

        # Miringkan sprite sesuai kecepatan vertikal (gaya "ship mode" Geometry Dash)
        tilted_img = pygame.transform.rotate(player_img, tilt_angle)
        tilted_rect = tilted_img.get_rect(center=(int(bird_x), int(bird_y)))
        screen.blit(tilted_img, tilted_rect)

        # Update Pipa
        for pipe in pipes:
            pipe["x"] -= pipe_speed
        bg_scroll_x += pipe_speed * 0.3  # latar bergerak lebih lambat dari pipa (efek parallax)

        while pipes[0]["x"] < -pipe_width:
            pipes.pop(0)
            pipes.append(spawn_pipe(pipes[-1]["x"] + PIPE_SPACING))

        for pipe in pipes:
            if not pipe["scored"] and pipe["x"] + pipe_width < bird_x:
                score += 1
                pipe["scored"] = True

        bird_rect = pygame.Rect(bird_x - bird_radius, bird_y - bird_radius, bird_radius * 2, bird_radius * 2)

        collided = False
        for pipe in pipes:
            top_pipe = pygame.Rect(pipe["x"], 0, pipe_width, pipe["gap_y"])
            bottom_pipe = pygame.Rect(pipe["x"], pipe["gap_y"] + pipe_gap, pipe_width,
                                       HEIGHT - pipe["gap_y"] - pipe_gap)
            if bird_rect.colliderect(top_pipe) or bird_rect.colliderect(bottom_pipe):
                collided = True
            draw_pipe(screen, pipe["x"], pipe["gap_y"], pipe["gap_y"] + pipe_gap, pipe_width)

        if collided or bird_y > HEIGHT or bird_y < 0:
            if score > high_score:
                high_score = score
                save_high_score(high_score)
            spawn_particle_burst(bird_x, bird_y, SHIP_COLOR, count=35)
            screen_shake_timer = 20
            if has_crash_sound:
                crash_sound.play()
            if has_impact_sound:
                impact_sound.play()  # lapisan kedua untuk efek yang lebih 'grand'
            if has_music:
                pygame.mixer.music.set_volume(0.0)  # bisukan musik sepenuhnya agar crash terdengar jelas
            state = "CURTAIN"
            curtain_timer = 0

        # --- Progress bar gaya Geometry Dash di bagian atas layar ---
        PROGRESS_MILESTONE = 10  # skor yang dibutuhkan agar bar terisi penuh sekali putaran
        progress_frac = (score % PROGRESS_MILESTONE) / PROGRESS_MILESTONE
        pygame.draw.rect(screen, (40, 40, 40), (0, 0, WIDTH, 8))
        pygame.draw.rect(screen, NEON_GREEN, (0, 0, int(WIDTH * progress_frac), 8))

        # HUD
        font = pygame.font.SysFont("Arial", 28)
        screen.blit(font.render(f"Skor: {score}", True, (255, 255, 255)), (20, 28))
        screen.blit(font.render(f"Skor Tertinggi: {high_score}", True, (255, 215, 0)), (WIDTH - 260, 28))

        if keyboard_active:
            screen.blit(font.render("Input: SENTUH / KEYBOARD", True, (255, 255, 0)), (20, 60))
        elif current_freq:
            screen.blit(font.render(f"Input: {int(current_freq)} Hz", True, NEON_BLUE), (20, 60))
        else:
            screen.blit(font.render("Input: (diam)", True, (150, 150, 150)), (20, 60))

        # --- DEBUG OVERLAY (tekan 'D') — sekarang di luar blok input, selalu bisa muncul ---
        if keys[pygame.K_d]:
            debug_txt = font.render(f"Vol: {int(current_mag)} | Gate: 300000", True, (255, 100, 100))
            screen.blit(debug_txt, (20, HEIGHT - 40))

        # Simpan frame terakhir persis sebelum tirai mulai menutup
        if state == "CURTAIN":
            frozen_frame = screen.copy()

    # ==========================================
    # STATE 2.5: TIRAI MENUTUP SEBELUM GAME OVER
    # ==========================================
    elif state == "CURTAIN":
        if frozen_frame is not None:
            screen.blit(frozen_frame, (0, 0))

        curtain_timer += 1
        progress = min(1.0, curtain_timer / CURTAIN_DURATION)
        panel_h = int((HEIGHT / 2) * progress)
        pygame.draw.rect(screen, BLACK, (0, 0, WIDTH, panel_h))
        pygame.draw.rect(screen, BLACK, (0, HEIGHT - panel_h, WIDTH, panel_h))

        if curtain_timer >= CURTAIN_DURATION:
            state = "GAME_OVER"

    # ==========================================
    # STATE 3: GAME OVER
    # ==========================================
    elif state == "GAME_OVER":
        font_large = pygame.font.SysFont("Arial", 60, bold=True)
        font_small = pygame.font.SysFont("Arial", 30)

        over_txt = font_large.render("JATUH!", True, (255, 50, 50))
        score_txt = font_small.render(f"Skor Akhir: {score}", True, (255, 255, 255))

        if score == high_score and score > 0:
            record_txt = font_small.render("REKOR BARU!", True, (255, 215, 0))
            screen.blit(record_txt, (WIDTH // 2 - record_txt.get_width() // 2, HEIGHT // 2 - 40))

        restart_txt = font_small.render("Tekan TOMBOL APA SAJA untuk kembali ke Menu", True, (200, 200, 200))

        screen.blit(over_txt, (WIDTH // 2 - over_txt.get_width() // 2, HEIGHT // 3 - 30))
        screen.blit(score_txt, (WIDTH // 2 - score_txt.get_width() // 2, HEIGHT // 2 + 10))
        screen.blit(restart_txt, (WIDTH // 2 - restart_txt.get_width() // 2, HEIGHT // 2 + 70))

    # --- Partikel & screen-shake selalu diproses, termasuk saat GAME_OVER ---
    update_and_draw_particles(screen)

    shake_offset = (0, 0)
    if screen_shake_timer > 0:
        shake_offset = (random.randint(-8, 8), random.randint(-8, 8))
        screen_shake_timer -= 1

    window.fill(BLACK)
    window.blit(screen, shake_offset)
    pygame.display.flip()
    clock.tick(60)

# --- Cleanup ---
stream.stop_stream()
stream.close()
p.terminate()
pygame.quit()