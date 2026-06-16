import asyncio
import os
import cv2
import numpy as np
import base64
import time
import threading

class AsyncVisionAgent:
    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.cap = None
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.face_cascade = cv2.CascadeClassifier(cascade_path)
        self.is_streaming = True
        self.is_enabled = True
        self.state_callback = None
        self.camera_view = None
        self._camera_lock = asyncio.Lock()
        
        # Background capture thread fields
        self.latest_frame = None
        self.latest_is_mock = True
        self.active_camera_index = camera_index
        self.frame_lock = threading.Lock()
        self.thread_running = True
        self.last_open_attempt = 0.0
        self.cap_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.cap_thread.start()

    def _open_camera(self):
        """Attempts to open the hardware camera. Returns True if successful."""
        try:
            if self.cap is None or not self.cap.isOpened():
                backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
                self.cap = cv2.VideoCapture(self.camera_index, backend)
                if self.cap is not None and self.cap.isOpened():
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            return self.cap is not None and self.cap.isOpened()
        except Exception as e:
            print(f"Error opening camera: {e}")
            return False

    def _capture_loop(self):
        """Dedicated background thread loop to read frames from the camera."""
        while self.thread_running and self.is_streaming:
            # Handle camera index change
            if self.active_camera_index != self.camera_index:
                if self.cap is not None:
                    try:
                        self.cap.release()
                    except Exception:
                        pass
                    self.cap = None
                self.active_camera_index = self.camera_index

            opened = False
            if self.cap is not None:
                try:
                    opened = self.cap.isOpened()
                except Exception:
                    opened = False

            if not opened:
                current_time = time.time()
                if current_time - self.last_open_attempt >= 3.0:
                    self.last_open_attempt = current_time
                    save_fd = None
                    null_fd = None
                    try:
                        try:
                            import sys
                            err_fd = sys.stderr.fileno()
                            save_fd = os.dup(err_fd)
                            null_fd = os.open(os.devnull, os.O_WRONLY)
                            os.dup2(null_fd, err_fd)
                        except Exception:
                            pass
                        
                        backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
                        self.cap = cv2.VideoCapture(self.camera_index, backend)
                        if self.cap is not None and self.cap.isOpened():
                            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    except Exception:
                        self.cap = None
                    finally:
                        if save_fd is not None:
                            try:
                                import sys
                                err_fd = sys.stderr.fileno()
                                os.dup2(save_fd, err_fd)
                                os.close(save_fd)
                            except Exception:
                                pass
                        if null_fd is not None:
                            try:
                                os.close(null_fd)
                            except Exception:
                                pass

            # Read frame if opened
            frame = None
            is_mock = False
            
            if self.cap is not None:
                try:
                    if self.cap.isOpened():
                        ret, raw_frame = self.cap.read()
                        if ret and raw_frame is not None:
                            frame = raw_frame.copy()
                            is_mock = False
                except Exception:
                    pass

            # If opening or reading failed, generate mock frame
            if frame is None:
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                frame[:, :] = (30, 20, 20)
                cv2.line(frame, (320, 0), (320, 480), (50, 50, 50), 1)
                cv2.line(frame, (0, 240), (640, 240), (50, 50, 50), 1)
                cv2.putText(frame, "CAMERA SIMULATION MODE", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 180, 255), 2)
                cv2.putText(frame, f"Time: {time.strftime('%H:%M:%S')}", (20, 70),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
                is_mock = True

            with self.frame_lock:
                self.latest_frame = frame
                self.latest_is_mock = is_mock

            # Compress and encode to Base64 (70% JPEG quality)
            try:
                _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                base64_string = base64.b64encode(buffer).decode('utf-8')
                
                # Push to Flet UI widget if wrapper is registered
                if self.camera_view is not None:
                    try:
                        self.camera_view.widget.src_base64 = base64_string
                        self.camera_view.update()
                    except Exception:
                        pass
            except Exception as e:
                print(f"Error compressing/encoding frame in loop: {e}")

            time.sleep(0.033)

        # Release resources when streaming is stopped/disabled
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

    def _grab_frame(self):
        """Grabs the latest frame from the background capture loop cache."""
        with self.frame_lock:
            if self.latest_frame is not None:
                return self.latest_frame.copy(), self.latest_is_mock
        
        mock_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_frame[:, :] = (30, 20, 20)
        return mock_frame, True

    async def get_raw_frame(self):
        """Asynchronously retrieves a single frame (camera or mock)."""
        return self._grab_frame()

    async def set_enabled(self, enabled: bool):
        """Enables or disables camera polling."""
        self.is_enabled = enabled
        self.is_streaming = enabled
        
        if enabled:
            # Start background capture thread if not running
            with self.frame_lock:
                if not self.thread_running or self.cap_thread is None or not self.cap_thread.is_alive():
                    self.thread_running = True
                    self.cap_thread = threading.Thread(target=self._capture_loop, daemon=True)
                    self.cap_thread.start()
        else:
            # Stop capture thread and wait for it to join
            self.thread_running = False
            if self.cap_thread is not None:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self.cap_thread.join)
                self.cap_thread = None

        if self.state_callback:
            if asyncio.iscoroutinefunction(self.state_callback):
                await self.state_callback(enabled)
            else:
                self.state_callback(enabled)

    async def update_camera_index(self, index: int):
        """Changes camera hardware source index dynamically."""
        self.camera_index = index

    async def close(self):
        """Releases the camera without blocking the event loop."""
        await self.set_enabled(False)


    async def detect_faces(self) -> tuple[dict, str]:
        """
        Asynchronously captures a frame, detects faces using Haar Cascade,
        annotates the frame, and returns a results dictionary and base64-encoded frame.
        """
        loop = asyncio.get_running_loop()
        
        def _process():
            frame, is_mock = self._grab_frame()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            faces = []
            if is_mock:
                center_x, center_y = 320, 240
                w, h = 120, 120
                faces = [(center_x - w//2, center_y - h//2, w, h)]
                cv2.circle(frame, (center_x, center_y), 60, (0, 255, 255), 2)
                cv2.circle(frame, (center_x - 20, center_y - 20), 5, (0, 255, 255), -1)
                cv2.circle(frame, (center_x + 20, center_y - 20), 5, (0, 255, 255), -1)
                cv2.ellipse(frame, (center_x, center_y + 15), (25, 15), 0, 0, 180, (0, 255, 255), 2)
                cv2.putText(frame, "SIMULATED FACE", (center_x - 60, center_y - 80),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            else:
                faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

            face_list = []
            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(frame, "Face", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                face_list.append({
                    "x": int(x),
                    "y": int(y),
                    "w": int(w),
                    "h": int(h)
                })

            count = len(face_list)
            cv2.putText(frame, f"Faces Detected: {count}", (20, 450),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            b64_str = base64.b64encode(buffer).decode('utf-8')
            
            result = {
                "face_count": count,
                "faces": face_list,
                "is_mocked_camera": is_mock
            }
            return result, b64_str

        async with self._camera_lock:
            return await loop.run_in_executor(None, _process)

    async def detect_colors(self) -> tuple[dict, str]:
        """
        Asynchronously captures a frame, analyses the center HSV values,
        identifies the dominant color, and returns the result and base64 frame.
        """
        loop = asyncio.get_running_loop()

        def _process():
            frame, is_mock = self._grab_frame()
            h_height, h_width = frame.shape[:2]
            
            cx, cy = h_width // 2, h_height // 2
            size = 100
            x1, y1 = cx - size // 2, cy - size // 2
            x2, y2 = cx + size // 2, cy + size // 2

            if is_mock:
                t = int(time.time()) % 4
                mock_color_bgr = (0, 0, 0)
                mock_color_name = "unknown"
                if t == 0:
                    mock_color_bgr = (0, 0, 255)
                    mock_color_name = "Red"
                elif t == 1:
                    mock_color_bgr = (0, 255, 0)
                    mock_color_name = "Green"
                elif t == 2:
                    mock_color_bgr = (255, 0, 0)
                    mock_color_name = "Blue"
                else:
                    mock_color_bgr = (0, 255, 255)
                    mock_color_name = "Yellow"

                cv2.rectangle(frame, (x1, y1), (x2, y2), mock_color_bgr, -1)
                cv2.putText(frame, f"SIMULATED {mock_color_name.upper()} CARD", (x1 - 20, y1 - 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            roi = frame[y1:y2, x1:x2]
            hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            
            avg_hsv = np.mean(hsv_roi, axis=(0, 1))
            h, s, v = avg_hsv[0], avg_hsv[1], avg_hsv[2]

            color_name = "Unknown"
            color_bgr = (200, 200, 200)

            if v < 40:
                color_name = "Black"
                color_bgr = (0, 0, 0)
            elif s < 40 and v > 180:
                color_name = "White"
                color_bgr = (255, 255, 255)
            elif s < 40 and v >= 40:
                color_name = "Gray"
                color_bgr = (128, 128, 128)
            else:
                if (h < 10 or h >= 170) and s >= 40:
                    color_name = "Red"
                    color_bgr = (0, 0, 255)
                elif 10 <= h < 34 and s >= 40:
                    color_name = "Yellow"
                    color_bgr = (0, 255, 255)
                elif 34 <= h < 85 and s >= 40:
                    color_name = "Green"
                    color_bgr = (0, 255, 0)
                elif 85 <= h < 140 and s >= 40:
                    color_name = "Blue"
                    color_bgr = (255, 0, 0)

            cv2.rectangle(frame, (x1, y1), (x2, y2), color_bgr, 2)
            cv2.circle(frame, (cx, cy), 4, (0, 0, 255), -1)
            cv2.putText(frame, f"Color: {color_name}", (x1, y2 + 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color_bgr, 2)
            cv2.putText(frame, f"H:{int(h)} S:{int(s)} V:{int(v)}", (x1, y2 + 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

            _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            b64_str = base64.b64encode(buffer).decode('utf-8')
            
            result = {
                "detected_color": color_name,
                "hsv_values": {"h": round(h, 2), "s": round(s, 2), "v": round(v, 2)},
                "is_mocked_camera": is_mock
            }
            return result, b64_str

        async with self._camera_lock:
            return await loop.run_in_executor(None, _process)

    @staticmethod
    def _detect_cameras():
        import os
        import sys
        
        save_fd = None
        null_fd = None
        try:
            err_fd = sys.stderr.fileno()
            save_fd = os.dup(err_fd)
            null_fd = os.open(os.devnull, os.O_WRONLY)
            os.dup2(null_fd, err_fd)
        except Exception:
            pass

        available = []
        try:
            backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
            for i in range(5):
                try:
                    cap = cv2.VideoCapture(i, backend)
                    if cap is not None and cap.isOpened():
                        cap.release()
                        available.append(i)
                except Exception:
                    pass
        finally:
            if save_fd is not None:
                try:
                    err_fd = sys.stderr.fileno()
                    os.dup2(save_fd, err_fd)
                    os.close(save_fd)
                except Exception:
                    pass
            if null_fd is not None:
                try:
                    os.close(null_fd)
                except Exception:
                    pass

        if not available:
            available = [0]
        return available

    async def get_available_cameras(self) -> list[int]:
        """Asynchronously queries the hardware for available camera indexes."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._detect_cameras)
