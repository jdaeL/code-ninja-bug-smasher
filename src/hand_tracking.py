"""
hand_tracking.py
----------------
Módulo A — Backend de Visión Computacional
Clase HandTracker: detecta la mano del usuario via MediaPipe y extrae
las coordenadas (x, y) del dedo índice (landmark 8) escaladas a píxeles.
"""

import cv2
import mediapipe as mp
import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple


# ── Constantes de landmarks MediaPipe Hands ──────────────────────────────────
INDEX_FINGER_TIP = 8   # Punta del dedo índice
PALM_CENTER      = 9   # Aproximación al centro de la palma


@dataclass
class HandData:
    """Estructura de datos limpia que devuelve HandTracker por frame."""
    index_tip: Optional[Tuple[int, int]]   # (x, y) punta índice en píxeles
    palm_center: Optional[Tuple[int, int]] # (x, y) centro palma en píxeles
    hand_detected: bool                    # True si se detectó al menos 1 mano


class HandTracker:
    """
    Encapsula MediaPipe Hands para detectar la mano del usuario y
    retornar coordenadas de interacción escaladas a la resolución del frame.

    Parámetros
    ----------
    max_hands : int
        Número máximo de manos a detectar (default 1 para menor carga).
    detection_confidence : float
        Confianza mínima para la detección inicial (0.0 – 1.0).
    tracking_confidence : float
        Confianza mínima para el tracking continuo (0.0 – 1.0).
    """

    def __init__(
        self,
        max_hands: int = 1,
        detection_confidence: float = 0.7,
        tracking_confidence: float = 0.6,
    ) -> None:
        self._mp_hands = mp.solutions.hands
        self._mp_draw  = mp.solutions.drawing_utils
        self._mp_styles = mp.solutions.drawing_styles

        self.hands = self._mp_hands.Hands(
            static_image_mode=False,          # modo video (tracking continuo)
            max_num_hands=max_hands,
            min_detection_confidence=detection_confidence,
            min_tracking_confidence=tracking_confidence,
        )
        self._last_hand_data = HandData(None, None, False)

    # ── API pública ──────────────────────────────────────────────────────────

    def process_frame(self, frame_bgr: np.ndarray) -> HandData:
        """
        Procesa un frame BGR de OpenCV y devuelve un HandData con las
        coordenadas del dedo índice y centro de palma en píxeles.

        El frame NO es modificado; usa draw_landmarks() para visualización.
        """
        h, w = frame_bgr.shape[:2]

        # MediaPipe requiere RGB; la conversión es in-place segura con copy
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        frame_rgb.flags.writeable = False          # optimización: evita copia
        results = self.hands.process(frame_rgb)
        frame_rgb.flags.writeable = True

        if not results.multi_hand_landmarks:
            self._last_hand_data = HandData(None, None, False)
            return self._last_hand_data

        # Tomamos la primera mano detectada
        hand_landmarks = results.multi_hand_landmarks[0]

        index_tip   = self._landmark_to_px(hand_landmarks, INDEX_FINGER_TIP, w, h)
        palm_center = self._landmark_to_px(hand_landmarks, PALM_CENTER,      w, h)

        self._last_hand_data = HandData(
            index_tip=index_tip,
            palm_center=palm_center,
            hand_detected=True,
        )
        # Guardamos los raw results para draw_landmarks
        self._last_results = results
        return self._last_hand_data

    def draw_landmarks(self, frame_bgr: np.ndarray) -> np.ndarray:
        """
        Dibuja los 21 landmarks y conexiones de la mano sobre el frame.
        Modifica y retorna el frame (útil para debug / demo).
        Debe llamarse DESPUÉS de process_frame().
        """
        if not hasattr(self, "_last_results") or \
           not self._last_results.multi_hand_landmarks:
            return frame_bgr

        for hand_lm in self._last_results.multi_hand_landmarks:
            self._mp_draw.draw_landmarks(
                frame_bgr,
                hand_lm,
                self._mp_hands.HAND_CONNECTIONS,
                self._mp_styles.get_default_hand_landmarks_style(),
                self._mp_styles.get_default_hand_connections_style(),
            )
        return frame_bgr

    def draw_cursor(self, frame_bgr: np.ndarray, radius: int = 18) -> np.ndarray:
        """
        Dibuja un cursor visual en la punta del dedo índice.
        Color verde sólido con borde blanco para máxima visibilidad.
        """
        data = self._last_hand_data
        if not data.hand_detected or data.index_tip is None:
            return frame_bgr

        x, y = data.index_tip
        cv2.circle(frame_bgr, (x, y), radius + 3, (255, 255, 255), -1)  # borde blanco
        cv2.circle(frame_bgr, (x, y), radius,     (0, 220, 80),   -1)   # relleno verde
        cv2.circle(frame_bgr, (x, y), radius,     (0, 160, 40),    2)   # contorno oscuro
        return frame_bgr

    def release(self) -> None:
        """Libera los recursos de MediaPipe. Llamar al cerrar la aplicación."""
        self.hands.close()

    # ── Helpers privados ─────────────────────────────────────────────────────

    @staticmethod
    def _landmark_to_px(
        hand_landmarks,
        landmark_id: int,
        frame_w: int,
        frame_h: int,
    ) -> Tuple[int, int]:
        """
        Convierte coordenadas normalizadas [0,1] de un landmark
        a coordenadas en píxeles del frame.
        """
        lm = hand_landmarks.landmark[landmark_id]
        x = int(lm.x * frame_w)
        y = int(lm.y * frame_h)
        # Clamp para no salir del frame
        x = max(0, min(x, frame_w - 1))
        y = max(0, min(y, frame_h - 1))
        return (x, y)


# ── Función main: test standalone de la cámara ───────────────────────────────

def main() -> None:
    """
    Test rápido del módulo: abre la cámara, detecta la mano y
    muestra en pantalla las coordenadas del dedo índice en tiempo real.
    Presiona 'q' para salir.
    """
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] No se pudo abrir la cámara.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    tracker = HandTracker(max_hands=1, detection_confidence=0.7)
    print("[INFO] Cámara iniciada. Presiona 'q' para salir.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] No se pudo leer el frame.")
            break

        # Espejo horizontal — más natural para el usuario
        frame = cv2.flip(frame, 1)

        # ── Procesamiento ────────────────────────────────────────────────────
        hand_data = tracker.process_frame(frame)
        tracker.draw_landmarks(frame)
        tracker.draw_cursor(frame)

        # ── HUD de debug ─────────────────────────────────────────────────────
        if hand_data.hand_detected and hand_data.index_tip:
            x, y = hand_data.index_tip
            status_text  = f"Indice: ({x}, {y})"
            status_color = (0, 255, 80)
        else:
            status_text  = "Mano no detectada"
            status_color = (0, 80, 255)

        cv2.putText(
            frame, status_text, (10, 35),
            cv2.FONT_HERSHEY_SIMPLEX, 0.9, status_color, 2, cv2.LINE_AA,
        )
        cv2.putText(
            frame, "Presiona 'q' para salir", (10, 470),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1, cv2.LINE_AA,
        )

        cv2.imshow("HandTracker — Test de Camara", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    tracker.release()
    cap.release()
    cv2.destroyAllWindows()
    print("[INFO] Cámara liberada. Fin del test.")


if __name__ == "__main__":
    main()