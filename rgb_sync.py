import os, math, time, threading, stat
from pathlib import Path
from PySide6.QtCore import QObject, Signal

class RGBSync(QObject):
 report=Signal(str)
 def __init__(self,parent=None):
  super().__init__(parent)
  self.state=(False,False,True,True,True,False,{})
  self.stop=threading.Event()
  threading.Thread(target=self.run,daemon=True).start()
 def update(self,enabled,locked,keyboard,ram,mouse,scanning=True,profile=None):
  self.state=(enabled,locked,keyboard,ram,mouse,scanning,profile or {})
 def run(self):
  client=None;devices=[];previous=None;mix=0.;retry=0.;mouse_retry=0.;mouse_path=None;last_mouse=None;last_sdk=None;last_status='';base=(244.,120.,215.)
  def report(msg):
   nonlocal last_status
   if msg!=last_status:self.report.emit(msg);last_status=msg
  def disconnect():
   nonlocal client,devices,last_sdk
   if client:
    try:client.disconnect()
    except Exception:pass
   client=None;devices=[];last_sdk=None
  while not self.stop.wait(.10):
   enabled,locked,keyboard,ram,mouse,scanning,profile=self.state
   now=time.monotonic()
   if not enabled:
    if previous is not None:
     disconnect();previous=None;last_mouse=None;mix=0.;report('RGB sync off')
    continue
   selection=(keyboard,ram,mouse)
   if selection!=previous:
    disconnect();last_mouse=None;retry=0.;mouse_retry=0.;previous=selection
   locked=locked and profile.get('mode','auto')=='auto'
   mix+=((1. if locked else 0.)-mix)*.35
   if abs(mix-(1. if locked else 0.))<.01:mix=1. if locked else 0.
   pulse=(1+math.sin(now*math.tau/2.4))/2
   strength=.40+.60*pulse
   target_base=profile.get('manual',(244,120,215)) if profile.get('mode')=='manual' else profile.get('scanning',(179,108,255)) if scanning else profile.get('idle',(244,120,215))
   base=tuple(a+(b-a)*.35 if abs(b-a)>=.5 else float(b) for a,b in zip(base,target_base))
   rgb=tuple(round((a*(1-mix)+b*mix*strength)*profile.get('brightness',100)/100) for a,b in zip(base,profile.get('combat',(240,24,134))))
   errors=[]
   if (keyboard or ram or mouse) and client is None and now>=retry:
    retry=now+8
    try:
     from openrgb import OpenRGBClient
     client=OpenRGBClient('127.0.0.1',6743)
     for d in client.devices:
      if (keyboard and int(d.type)==5) or (ram and int(d.type)==1) or (mouse and int(d.type)==6):
       devices.append(d) # OpenLinkHub exposes only Direct mode; already selected
    except Exception as e:
     disconnect();errors.append('SDK: '+str(e))
   if client and rgb!=last_sdk:
    try:
     from openrgb.utils import RGBColor
     for d in devices:d.set_colors([RGBColor(*rgb) for _ in d.leds],fast=True)
     last_sdk=rgb
    except Exception as e:
     disconnect();retry=now+8;errors.append('SDK: '+str(e))
   if False: # Linux ckb FIFO not available on Windows
    try:
     if mouse_path is None or not mouse_path.exists():
      mouse_path=None
      for p in Path('/dev/input').glob('ckb*/model'):
       if 'harpoon' in p.read_text().lower():mouse_path=p.parent/'cmd';break
     if mouse_path is None:raise RuntimeError('Harpoon not found')
     if not stat.S_ISFIFO(mouse_path.stat().st_mode):raise RuntimeError('Not a ckb command FIFO')
     fd=os.open(mouse_path,os.O_WRONLY|os.O_NONBLOCK)
     try:os.write(fd,('rgb %02x%02x%02x\n'%rgb).encode())
     finally:os.close(fd)
     last_mouse=rgb
    except Exception as e:mouse_retry=now+3;errors.append('Mouse: '+str(e))
   if errors:report(' | '.join(errors))
   elif (keyboard or ram) and client is None:report('Waiting for OpenRGB SDK')
   else:report(f'OpenRGB: {len(devices)} selected devices')
  disconnect()
