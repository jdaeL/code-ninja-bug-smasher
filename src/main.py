"""
main.py
-------
Punto de entrada de Code Ninja: Bug Smasher.
Une el Módulo A (hand_tracking.py) con el Módulo B (game_logic.py).

Flujo por frame:
  1. Capturar frame de cámara → voltear horizontalmente
  2. HandTracker.process_frame()  → HandData (x, y del índice)
  3. GameState.update()           → física, spawn, penalizaciones
  4. _check_collisions()          → matemática euclidiana
  5. Renderer.draw_frame()        → dibujar todo
  6. HandTracker.draw_cursor()    → cursor encima de todo

Controles:
  SPACE → iniciar / reiniciar
  q     → salir
"""

import cv2
import math
import sys
import os

# Permitir imports relativos ejecutando desde la raíz del proyecto
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from hand_tracking import HandTracker, HandData
from game_logic import (
    GameState, GameStatus, Renderer, Bug,
    FRAME_W, FRAME_H, BUG_RADIUS,
)


# ── Constantes de integración ─────────────────────────────────────────────────

COLLISION_TOLERANCE = 1.15   # factor de tolerancia sobre el radio (más generoso)
CAMERA_INDEX        = 0      # índice de la cámara (cambiar a 1 si hay dos)
TARGET_FPS          = 30     # FPS objetivo (waitKey en ms)


# ── Colisiones ────────────────────────────────────────────────────────────────

def check_collisions(
    hand_data: HandData,
    state: GameState,
) -> None:
    """
    Evalúa colisión bidimensional entre la punta del dedo índice
    y cada Bug activo usando distancia euclidiana:

        d = sqrt((x_cursor - x_bug)² + (y_cursor - y_bug)²)

    Si d ≤ radio_efectivo  →  colisión registrada.

    Se itera sobre una copia de la lista para poder modificarla
    durante la iteración sin comportamiento indefinido.
    """
    if not hand_data.hand_detected or hand_data.index_tip is None:
        return

    cx, cy = hand_data.index_tip
    radio_efectivo = BUG_RADIUS * COLLISION_TOLERANCE

    for bug in list(state.bugs):
        if bug.hit:
            continue

        # ── Fórmula de distancia euclidiana ──────────────────────────────────
        dx = cx - bug.x
        dy = cy - bug.y
        distancia = math.sqrt(dx * dx + dy * dy)
        # ─────────────────────────────────────────────────────────────────────

        if distancia <= radio_efectivo:
            state.register_hit(bug)


# ── Overlay de debug de colisión (opcional) ───────────────────────────────────

def draw_debug_collision(
    frame,
    hand_data: HandData,
    show: bool = False,
) -> None:
    """
    Muestra el radio de colisión alrededor del cursor.
    Útil para calibración. Activar con la tecla 'd' en runtime.
    """
    if not show or not hand_data.hand_detected or hand_data.index_tip is None:
        return
    cx, cy = hand_data.index_tip
    radio = int(BUG_RADIUS * COLLISION_TOLERANCE)
    cv2.circle(frame, (cx, cy), radio, (0, 255, 255), 1, cv2.LINE_AA)


# ── Bucle principal ───────────────────────────────────────────────────────────

def main() -> None:
    # ── Inicialización de cámara ──────────────────────────────────────────────
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print(f"[ERROR] No se pudo abrir la cámara (índice {CAMERA_INDEX}).")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
    cap.set(cv2.CAP_PROP_FPS,          TARGET_FPS)

    # ── Inicialización de módulos ─────────────────────────────────────────────
    tracker  = HandTracker(max_hands=1, detection_confidence=0.7)
    state    = GameState()          # comienza en WAITING
    renderer = Renderer()

    debug_collision = False         # toggle con tecla 'd'
    ms_per_frame    = max(1, 1000 // TARGET_FPS)

    print("[INFO] Code Ninja: Bug Smasher iniciado.")
    print("       SPACE → iniciar/reiniciar  |  d → debug colisión  |  q → salir")

    # ── Bucle de juego ────────────────────────────────────────────────────────
    while True:
        ret, frame = cap.read()
        if not ret:
            print("[WARN] Frame perdido, reintentando...")
            continue

        # 1. Espejo horizontal (más intuitivo para el jugador)
        frame = cv2.flip(frame, 1)

        # 2. Visión computacional → coordenadas del dedo
        hand_data = tracker.process_frame(frame)

        # 3. Lógica de juego (solo en PLAYING)
        state.update()

        # 4. Detección de colisiones
        if state.is_playing:
            check_collisions(hand_data, state)

        # 5. Renderizado completo
        frame = renderer.draw_frame(frame, state)

        # 6. Cursor encima de todo lo demás
        tracker.draw_landmarks(frame)
        tracker.draw_cursor(frame)

        # 7. Overlay de debug (opcional)
        draw_debug_collision(frame, hand_data, show=debug_collision)

        # 8. Indicador de debug activo
        if debug_collision:
            cv2.putText(
                frame, "[DEBUG COLISION ON]", (10, FRAME_H - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA,
            )

        cv2.imshow("Code Ninja: Bug Smasher", frame)

        # ── Entrada de teclado ────────────────────────────────────────────────
        key = cv2.waitKey(ms_per_frame) & 0xFF

        if key == ord("q"):
            print("[INFO] Saliendo...")
            break

        elif key == ord(" "):
            # SPACE: iniciar desde WAITING o reiniciar desde GAME_OVER
            if state.status in (GameStatus.WAITING, GameStatus.GAME_OVER):
                state.start()
                print(f"[INFO] Partida iniciada. ¡Aplasta los bugs!")

        elif key == ord("d"):
            # Toggle modo debug de colisión
            debug_collision = not debug_collision
            estado = "ON" if debug_collision else "OFF"
            print(f"[DEBUG] Visualización de colisión: {estado}")

    # ── Liberación de recursos ────────────────────────────────────────────────
    tracker.release()
    cap.release()
    cv2.destroyAllWindows()
    print("[INFO] Recursos liberados. Fin del juego.")


if __name__ == "__main__":
    main()