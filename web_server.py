import PySpin

from flask import Flask, Response, render_template

from PIL import Image
import io
import time
from threading import Thread, Lock

class Recorder():
    def __init__(self, cams):
        self.app = Flask(__name__)
        self.app.config['SERVER_NAME'] = "localhost:8888"

        self.cams = cams
        self.num_cams = len(cams)
        self.run_cam = [False] * self.num_cams
        self.recording = [False] * self.num_cams
        self.recording_threads = [None] * self.num_cams
        self.frame_count = [0] * self.num_cams
        self.frames = [None] * self.num_cams
        self.frame_locks = [Lock()] * self.num_cams

        self.app.route("/feed", subdomain="<cam_idx>")(self.cam_feed)
        self.app.route("/record")(self.record_all)

    def record_all(self):
        return Response()

    def cam_feed(self, cam_idx):
        return Response(
            self.generate_cam_feed(int(cam_idx)),
            mimetype = "multipart/x-mixed-replace; boundary=frame"
        )

    def generate_cam_feed(self, cam_idx):
        if not self.run_cam[cam_idx]:
            t = Thread(target=self.run_cam_func, args=(cam_idx,))
            t.start()
            self.recording_threads[cam_idx] = t
            self.run_cam[cam_idx] = True
        # print(cam_idx)

        # try:
        fc = self.frame_count[cam_idx]
        while True:
            time.sleep(0.1)
            if self.frame_count[cam_idx] > fc:
                self.frame_locks[cam_idx].acquire()
                fc = self.frame_count[cam_idx]
                chunk = b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + self.frames[cam_idx] + b'\r\n'
                self.frame_locks[cam_idx].release()
                yield chunk

    def run_cam_func(self, cam_idx):
        print(f"{cam_idx} recording")
        cam = self.cams[int(cam_idx)]
        cam.Init()
        cam.BeginAcquisition()
        proc = PySpin.ImageProcessor()
        while self.run_cam[cam_idx]:
            img = cam.GetNextImage(1000)
            # print(f"{cam_idx} got frame")
            img = proc.Convert(img, PySpin.PixelFormat_RGB8)
            # print(f"{cam_idx} converted frame")
            pil_img = Image.fromarray(img.GetNDArray())
            # print(f"{cam_idx} get img array")

            img_bytes_io = io.BytesIO()
            pil_img.save(img_bytes_io, format='jpeg')
            # print(f"{cam_idx} converted to jpg")
            self.frame_locks[cam_idx].acquire()
            self.frames[cam_idx] = img_bytes_io.getvalue()
            self.frame_locks[cam_idx].release()
            self.frame_count[cam_idx] += 1

            # if self.recording[cam_idx]:
                # img.Save()

            # print('got frame')
        cam.EndAcquisition()
        cam.DeInit()
        print(f"{cam_idx} stopped")

    def start(self):
        self.app.run(host='localhost', port=8888, debug=False, threaded=True, use_reloader=False)
        # t = Thread(target=lambda: self.app.run(host='localhost', port=8888, debug=False, threaded=True, use_reloader=False))
        # t.start()

    def stop(self):
        print("Stopping...")
        for i, t in enumerate(self.recording_threads):
            self.run_cam[i] = False
            if t:
                t.join()

if __name__ == '__main__':
    try:
        system = PySpin.System.GetInstance()
        cams = system.GetCameras()

        num_cams = len(cams)
        if num_cams == 0:
            print("No cameras found...")
            cams.Clear()
            system.ReleaseInstance()
            exit(0)

        print(f"Found {len(cams)} cameras...")

        rec = Recorder(cams)
        rec.start()

    except Exception as e:
        print(e)
        rec.stop()
        cams.Clear()
        system.ReleaseInstance()
    except KeyboardInterrupt:
        print("interrupt")
        rec.stop()
        cams.Clear()
        system.ReleaseInstance()