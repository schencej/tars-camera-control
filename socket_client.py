import socketio
import asyncio
import subprocess
import re
from threading import Thread
import PySpin
import io
from PIL import Image

res = subprocess.run(['ipconfig'], stdout=subprocess.PIPE)
ip_addr = re.findall(
    "192.168.1.2\d+",
    res.stdout.decode('utf8'),
)[0]

sio = socketio.AsyncClient()

frames = []
run_cams = True

async def main():
    print("Connecting to control server...")
    while True:
        try:
            await sio.connect("http://192.168.1.104:8080")
            print("Connected")
            break
        except socketio.exceptions.ConnectionError:
            await asyncio.sleep(1)
            print("Retrying...")

    await sio.wait()
    await sio.disconnect()

@sio.on('connect')
async def handle_connect():
    print('connected')
    sio.start_background_task(send_status)
    await sio.emit('ip_addr', ip_addr)

@sio.on('reconnect')
async def handle_reconnect():
    print('reconnected')
    await sio.emit('ip_addr', ip_addr)

@sio.on('frame')
async def handle_frame(ip, frame_idx):
    if ip == ip_addr:
        await sio.emit('frame', (frame_idx, frames[frame_idx]))

@sio.on('frames')
async def handle_frames(ip):
    if ip == ip_addr:
        for idx, frame in enumerate(frames):
            asyncio.ensure_future(sio.emit('frame', (idx, frame)))

async def send_status():
    while True:
        await sio.emit('status', [True] * 8)
        await sio.sleep(0.5)

def run_cameras():
    global frames
    system = PySpin.System.GetInstance()
    cams = system.GetCameras()
    frames = [None] * len(cams)
    threads = []
    for i, cam in enumerate(cams):
        t = Thread(target=run_camera, args=(cam, i))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    cams.Clear()
    system.ReleaseInstance()

def run_camera(cam, cam_idx):
    print(f"cam {cam_idx} recording")
    cam.Init()
    cam.BeginAcquisition()
    proc = PySpin.ImageProcessor()
    while run_cams:
        img = cam.GetNextImage(1000)
        img = proc.Convert(img, PySpin.PixelFormat_RGB8)
        pil_img = Image.fromarray(img.GetNDArray())

        img_bytes_io = io.BytesIO()
        pil_img.save(img_bytes_io, format='jpeg')
        frames[cam_idx] = img_bytes_io.getvalue()

    cam.EndAcquisition()
    cam.DeInit()
    print(f"{cam_idx} stopped")

if __name__ == '__main__':
    t = None
    try:
        t = Thread(target=run_cameras)
        t.start()
        asyncio.run(main())
    except KeyboardInterrupt:
        run_cams = False
        t.join()