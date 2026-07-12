"""
game_logic.py
-------------
Módulo B — Frontend y Escenario Virtual
Clases:
  · Bug         → entidad enemiga con física de caída
  · BugSpawner  → generación aleatoria con dificultad progresiva
  · GameState   → puntaje, vidas y estado global del juego
  · Renderer    → dibuja todo sobre el frame (bugs, HUD, pantallas)

En la Ilación 5, Renderer sustituirá los círculos por imágenes PNG
con canal alfa. El resto de clases NO necesitará modificarse.
"""

import cv2
import numpy as np
import random
import math
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum, auto


# ── Constantes globales del juego ────────────────────────────────────────────

FRAME_W        = 640
FRAME_H        = 480
INITIAL_LIVES  = 3
BUG_RADIUS     = 32          # radio de colisión y dibujado
BASE_SPEED_MIN = 2.5         # píxeles/frame mínimo inicial
BASE_SPEED_MAX = 4.5         # píxeles/frame máximo inicial
SPEED_SCALE    = 0.08        # incremento de velocidad por punto
MAX_BUGS       = 7           # máximo de bugs simultáneos en pantalla
SPAWN_INTERVAL = 1.4         # segundos entre spawns (base)
MIN_SPAWN_INT  = 0.45        # intervalo mínimo (dificultad máxima)

# Paleta visual (BGR)
COLOR_BUG_BODY   = (30,  200,  30)   # verde insecto
COLOR_BUG_EYE    = (255, 255, 255)   # blanco
COLOR_BUG_PUPIL  = (0,    0,    0)   # negro
COLOR_BUG_BORDER = (10,  120,  10)   # borde oscuro
COLOR_HUD_BG     = (20,   20,   20)  # fondo HUD
COLOR_SCORE      = (80,  220, 255)   # amarillo-cian puntaje
COLOR_LIVES      = (60,  100, 255)   # rojo vidas
COLOR_COMBO      = (0,   200, 255)   # amarillo combo
COLOR_GAMEOVER   = (30,   30, 200)   # rojo game over
COLOR_FLASH      = (60,  255, 160)   # verde hit flash


class GameStatus(Enum):
    PLAYING   = auto()
    GAME_OVER = auto()
    WAITING   = auto()   # pantalla de inicio


# ── Dataclass: efecto visual de impacto ─────────────────────────────────────

@dataclass
class HitEffect:
    """Partícula de feedback visual al aplastar un bug."""
    x: int
    y: int
    text: str
    color: Tuple[int, int, int]
    birth_time: float
    duration: float = 0.6      # segundos que dura el efecto


# ── Clase Bug ────────────────────────────────────────────────────────────────

class Bug:
    """
    Entidad enemiga. Cae desde la parte superior con velocidad
    configurable. Maneja su propia posición y estado.
    """

    def __init__(self, x: int, speed: float) -> None:
        self.x: int        = x
        self.y: int        = -BUG_RADIUS          # empieza fuera del frame
        self.speed: float  = speed
        self.radius: int   = BUG_RADIUS
        self.alive: bool   = True
        self.hit: bool     = False                 # marcado para destruir
        # Variación visual individual (wobble horizontal)
        self._wobble_amp   = random.uniform(0.4, 1.2)
        self._wobble_freq  = random.uniform(0.05, 0.12)
        self._wobble_phase = random.uniform(0, math.pi * 2)
        self._frame_count  = 0

    def update(self) -> None:
        """Actualiza posición en cada frame."""
        self._frame_count += 1
        self.y += self.speed
        # Movimiento sinusoidal horizontal suave
        self.x += int(
            self._wobble_amp
            * math.sin(self._wobble_freq * self._frame_count + self._wobble_phase)
        )
        # Mantener dentro del ancho
        self.x = max(self.radius, min(self.x, FRAME_W - self.radius))

    def is_off_screen(self) -> bool:
        """Retorna True si el bug superó el borde inferior."""
        return self.y - self.radius > FRAME_H

    def get_center(self) -> Tuple[int, int]:
        return (self.x, self.y)


# ── Clase BugSpawner ─────────────────────────────────────────────────────────

class BugSpawner:
    """
    Genera nuevos bugs de forma controlada.
    El intervalo de spawn y la velocidad escalan con el puntaje,
    aumentando la dificultad de forma progresiva.
    """

    def __init__(self) -> None:
        self._last_spawn: float = time.time()

    def _current_interval(self, score: int) -> float:
        """Intervalo decrece con el puntaje (más bugs = más difícil)."""
        interval = SPAWN_INTERVAL - score * 0.025
        return max(interval, MIN_SPAWN_INT)

    def _current_speed(self, score: int) -> float:
        """Velocidad de caída aumenta con el puntaje."""
        speed_min = BASE_SPEED_MIN + score * SPEED_SCALE
        speed_max = BASE_SPEED_MAX + score * SPEED_SCALE
        return random.uniform(speed_min, speed_max)

    def try_spawn(self, bugs: List[Bug], score: int) -> Optional[Bug]:
        """
        Intenta generar un nuevo bug. Retorna el Bug creado o None
        si aún no es momento de generar uno.
        """
        now = time.time()
        if len(bugs) >= MAX_BUGS:
            return None
        if now - self._last_spawn < self._current_interval(score):
            return None

        self._last_spawn = now
        margin = BUG_RADIUS + 10
        x = random.randint(margin, FRAME_W - margin)
        return Bug(x=x, speed=self._current_speed(score))

    def reset(self) -> None:
        self._last_spawn = time.time()


# ── Clase GameState ───────────────────────────────────────────────────────────

class GameState:
    """
    Única fuente de verdad del estado del juego.
    Gestiona puntaje, vidas, combo y transiciones de estado.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.score: int          = 0
        self.lives: int          = INITIAL_LIVES
        self.combo: int          = 0
        self.max_combo: int      = 0
        self.status: GameStatus  = GameStatus.WAITING
        self.bugs: List[Bug]     = []
        self.effects: List[HitEffect] = []
        self._spawner            = BugSpawner()

    def start(self) -> None:
        self.reset()
        self.status = GameStatus.PLAYING
        self._spawner.reset()

    def update(self) -> None:
        """Tick principal: spawn, movimiento y detección de bugs perdidos."""
        if self.status != GameStatus.PLAYING:
            return

        # Intentar spawnar un nuevo bug
        new_bug = self._spawner.try_spawn(self.bugs, self.score)
        if new_bug:
            self.bugs.append(new_bug)

        # Actualizar bugs y remover los marcados o fuera de pantalla
        survivors = []
        for bug in self.bugs:
            bug.update()
            if bug.hit:
                continue                     # destruido por colisión
            if bug.is_off_screen():
                self._on_bug_escaped()       # penalización
                continue
            survivors.append(bug)
        self.bugs = survivors

        # Limpiar efectos expirados
        now = time.time()
        self.effects = [
            e for e in self.effects
            if now - e.birth_time < e.duration
        ]

    def register_hit(self, bug: Bug) -> None:
        """Registra la destrucción de un bug y actualiza el puntaje."""
        bug.hit = True
        self.combo   += 1
        self.max_combo = max(self.max_combo, self.combo)

        # Puntos base + bonus de combo
        points = 1 + (self.combo // 3)
        self.score += points

        # Efecto visual de impacto
        label = f"+{points}" if self.combo < 3 else f"+{points} x{self.combo}!"
        color = COLOR_COMBO if self.combo >= 3 else COLOR_FLASH
        self.effects.append(HitEffect(
            x=bug.x, y=bug.y,
            text=label,
            color=color,
            birth_time=time.time(),
        ))

    def _on_bug_escaped(self) -> None:
        """Penaliza al jugador cuando un bug llega al borde inferior."""
        self.lives -= 1
        self.combo  = 0           # rompe el combo
        if self.lives <= 0:
            self.status = GameStatus.GAME_OVER

    @property
    def is_playing(self) -> bool:
        return self.status == GameStatus.PLAYING

    @property
    def is_game_over(self) -> bool:
        return self.status == GameStatus.GAME_OVER


# ── Clase Renderer ────────────────────────────────────────────────────────────

class Renderer:
    """
    Dibuja todos los elementos visuales sobre el frame de la cámara.
    En Ilación 5 se sustituirán los primitivos geométricos por PNGs con alfa.
    La interfaz pública (draw_frame) NO cambiará.
    """

    def draw_frame(self, frame: np.ndarray, state: GameState) -> np.ndarray:
        """Punto de entrada único. Dibuja todo y retorna el frame final."""
        if state.status == GameStatus.WAITING:
            return self._draw_start_screen(frame)
        if state.status == GameStatus.GAME_OVER:
            return self._draw_game_over(frame, state)

        # Estado PLAYING
        self._draw_bugs(frame, state.bugs)
        self._draw_effects(frame, state.effects)
        self._draw_hud(frame, state)
        return frame

    # ── Bugs ─────────────────────────────────────────────────────────────────

    def _draw_bugs(self, frame: np.ndarray, bugs: List[Bug]) -> None:
        for bug in bugs:
            self._draw_single_bug(frame, bug)

    def _draw_single_bug(self, frame: np.ndarray, bug: Bug) -> None:
        """
        Dibuja un bug como ícono de insecto estilizado con OpenCV.
        Ilación 5 reemplazará esta función por overlay de PNG.
        """
        cx, cy = bug.x, bug.y
        r      = bug.radius

        # Cuerpo principal (elipse verde)
        cv2.ellipse(frame, (cx, cy), (r - 6, r), 0, 0, 360,
                    COLOR_BUG_BODY, -1)
        cv2.ellipse(frame, (cx, cy), (r - 6, r), 0, 0, 360,
                    COLOR_BUG_BORDER, 2)

        # Cabeza
        head_r = r // 2
        cv2.circle(frame, (cx, cy - r + head_r // 2), head_r,
                   COLOR_BUG_BODY, -1)
        cv2.circle(frame, (cx, cy - r + head_r // 2), head_r,
                   COLOR_BUG_BORDER, 2)

        # Ojos
        eye_off = head_r // 2
        for ex in [cx - eye_off, cx + eye_off]:
            ey = cy - r + head_r // 2
            cv2.circle(frame, (ex, ey), 5, COLOR_BUG_EYE,   -1)
            cv2.circle(frame, (ex, ey), 2, COLOR_BUG_PUPIL,  -1)

        # Antenas
        ant_base = (cx, cy - r - head_r // 4)
        cv2.line(frame, ant_base, (cx - r // 2, cy - r - r // 2),
                 COLOR_BUG_BORDER, 2)
        cv2.line(frame, ant_base, (cx + r // 2, cy - r - r // 2),
                 COLOR_BUG_BORDER, 2)

        # Patas (3 a cada lado)
        for i, frac in enumerate([0.2, 0.5, 0.8]):
            py = int(cy - r + frac * 2 * r)
            cv2.line(frame, (cx - r + 6, py),
                     (cx - r - 14, py + random.randint(-4, 4)),
                     COLOR_BUG_BORDER, 2)
            cv2.line(frame, (cx + r - 6, py),
                     (cx + r + 14, py + random.randint(-4, 4)),
                     COLOR_BUG_BORDER, 2)

        # Línea dorsal
        cv2.line(frame, (cx, cy - r + head_r), (cx, cy + r),
                 COLOR_BUG_BORDER, 2)

    # ── Efectos visuales ─────────────────────────────────────────────────────

    def _draw_effects(
        self, frame: np.ndarray, effects: List[HitEffect]
    ) -> None:
        now = time.time()
        for eff in effects:
            age    = now - eff.birth_time
            alpha  = max(0.0, 1.0 - age / eff.duration)
            # El texto sube mientras desvanece
            y_off  = int(age * 60)
            pos    = (eff.x - 20, eff.y - 20 - y_off)
            # Sombra
            cv2.putText(frame, eff.text,
                        (pos[0] + 2, pos[1] + 2),
                        cv2.FONT_HERSHEY_DUPLEX, 0.85,
                        (0, 0, 0), 3, cv2.LINE_AA)
            # Texto principal (se oscurece al desvanecerse con alpha)
            color = tuple(int(c * alpha) for c in eff.color)
            cv2.putText(frame, eff.text, pos,
                        cv2.FONT_HERSHEY_DUPLEX, 0.85,
                        color, 2, cv2.LINE_AA)

    # ── HUD ──────────────────────────────────────────────────────────────────

    def _draw_hud(self, frame: np.ndarray, state: GameState) -> None:
        """Dibuja la barra superior con puntaje, vidas y combo activo."""
        # Fondo semitransparente para el HUD
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (FRAME_W, 52), COLOR_HUD_BG, -1)
        cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

        # Puntaje
        cv2.putText(frame, f"SCORE: {state.score:04d}",
                    (12, 36), cv2.FONT_HERSHEY_DUPLEX,
                    0.9, COLOR_SCORE, 2, cv2.LINE_AA)

        # Vidas como corazones (texto)
        hearts = "♥ " * state.lives + "♡ " * (INITIAL_LIVES - state.lives)
        cv2.putText(frame, hearts.strip(),
                    (FRAME_W // 2 - 55, 36),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.85, COLOR_LIVES, 2, cv2.LINE_AA)

        # Combo activo
        if state.combo >= 3:
            cv2.putText(frame, f"COMBO x{state.combo}!",
                        (FRAME_W - 180, 36),
                        cv2.FONT_HERSHEY_DUPLEX,
                        0.75, COLOR_COMBO, 2, cv2.LINE_AA)

    # ── Pantalla de inicio ───────────────────────────────────────────────────

    def _draw_start_screen(self, frame: np.ndarray) -> np.ndarray:
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (FRAME_W, FRAME_H), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

        texts = [
            ("CODE NINJA",        (FRAME_W//2, 160), 1.8,  COLOR_SCORE,   3),
            ("BUG SMASHER",       (FRAME_W//2, 215), 1.4,  COLOR_FLASH,   2),
            ("Muestra tu mano",   (FRAME_W//2, 300), 0.75, (220,220,220), 1),
            ("y presiona  SPACE", (FRAME_W//2, 335), 0.75, (220,220,220), 1),
            ("para iniciar",      (FRAME_W//2, 370), 0.75, (220,220,220), 1),
        ]
        for (text, pos, scale, color, thick) in texts:
            # Centrar horizontalmente
            (tw, th), _ = cv2.getTextSize(
                text, cv2.FONT_HERSHEY_DUPLEX, scale, thick)
            x = pos[0] - tw // 2
            cv2.putText(frame, text, (x, pos[1]),
                        cv2.FONT_HERSHEY_DUPLEX, scale,
                        color, thick, cv2.LINE_AA)
        return frame

    # ── Pantalla de Game Over ────────────────────────────────────────────────

    def _draw_game_over(
        self, frame: np.ndarray, state: GameState
    ) -> np.ndarray:
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (FRAME_W, FRAME_H), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

        texts = [
            ("GAME  OVER",               (FRAME_W//2, 170), 1.8,  COLOR_GAMEOVER, 3),
            (f"SCORE FINAL: {state.score:04d}", (FRAME_W//2, 240), 1.0, COLOR_SCORE,    2),
            (f"COMBO MAX:   x{state.max_combo}", (FRAME_W//2, 285), 0.9, COLOR_COMBO,   2),
            ("Presiona SPACE",            (FRAME_W//2, 360), 0.75, (220,220,220), 1),
            ("para volver a jugar",       (FRAME_W//2, 395), 0.75, (220,220,220), 1),
        ]
        for (text, pos, scale, color, thick) in texts:
            (tw, _), _ = cv2.getTextSize(
                text, cv2.FONT_HERSHEY_DUPLEX, scale, thick)
            x = pos[0] - tw // 2
            cv2.putText(frame, text, (x, pos[1]),
                        cv2.FONT_HERSHEY_DUPLEX, scale,
                        color, thick, cv2.LINE_AA)
        return frame


# ── Test standalone del módulo ────────────────────────────────────────────────

def main() -> None:
    """
    Prueba aislada del módulo gráfico sobre un fondo negro.
    NO requiere cámara. Presiona SPACE para iniciar / reiniciar,
    'q' para salir.
    """
    state    = GameState()
    renderer = Renderer()

    print("[INFO] Test gráfico iniciado.")
    print("       SPACE → iniciar/reiniciar  |  q → salir")

    while True:
        # Frame base negro (en el juego real vendrá de la cámara)
        frame = np.zeros((FRAME_H, FRAME_W, 3), dtype=np.uint8)

        state.update()
        frame = renderer.draw_frame(frame, state)

        cv2.imshow("game_logic.py — Test Grafico", frame)

        key = cv2.waitKey(16) & 0xFF   # ~60 FPS
        if key == ord("q"):
            break
        if key == ord(" "):
            state.start()

    cv2.destroyAllWindows()
    print("[INFO] Test gráfico finalizado.")


if __name__ == "__main__":
    main()