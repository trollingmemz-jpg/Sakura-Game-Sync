"""Experimental local mech matching using user-selected blueprint references."""
import time, threading, os, subprocess, shutil, sys
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QImage
class Vision(QObject):
 report=Signal(str)
 detected=Signal(float)
 def __init__(self,parent=None):
  super().__init__(parent);self.refs=[];self.busy=False;self.last=0;self.generation=0;self.proc=None
  self.portal_frame.connect(self.frame,Qt.ConnectionType.QueuedConnection)
 portal_frame=Signal(object)
 def load(self,files):
  import cv2,numpy as np
  orb=cv2.ORB_create(nfeatures=1000);refs=[]
  for p in files:
   im=cv2.imread(str(p),cv2.IMREAD_UNCHANGED)
   if im is None:continue
   gray=cv2.cvtColor(im[:,:,:3],cv2.COLOR_BGR2GRAY) if im.ndim==3 else im
   mask=im[:,:,3] if im.ndim==3 and im.shape[2]==4 else None
   for flip in (False,True):
    g=cv2.flip(gray,1) if flip else gray;m=cv2.flip(mask,1) if flip and mask is not None else mask
    k,d=orb.detectAndCompute(g,m)
    if d is not None and len(d)>=12:refs.append((np.float32([x.pt for x in k]),d))
  self.refs=refs;self.report.emit(f'{len(refs)} reference feature sets indexed')
 def start(self):
  if not self.refs:raise RuntimeError('Import mech references first.')
  self.stop()
  gen=self.generation
  def reader():
   try:
    import ctypes,ctypes.wintypes as wt,psutil,cv2,numpy as np
    from PIL import ImageGrab
    user=ctypes.windll.user32
    while gen==self.generation:
     hwnd=user.GetForegroundWindow();pid=wt.DWORD()
     user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
     try:match='trailmakers' in psutil.Process(pid.value).name().lower()
     except (psutil.Error,OSError):match=False
     if match and user.IsWindowVisible(hwnd) and not user.IsIconic(hwnd):
      rc=wt.RECT();origin=wt.POINT(0,0)
      if user.GetClientRect(hwnd,ctypes.byref(rc)) and user.ClientToScreen(hwnd,ctypes.byref(origin)):
       w=rc.right-rc.left;h=rc.bottom-rc.top
       if w>0 and h>0:
        # Foreground client-area capture only; do not capture when another app is focused.
        im=ImageGrab.grab(bbox=(origin.x,origin.y,origin.x+w,origin.y+h),all_screens=True)
        if user.GetForegroundWindow()==hwnd and gen==self.generation:
         data=cv2.resize(np.asarray(im.convert('RGB')),(960,540)).tobytes();self.portal_frame.emit((gen,data))
     time.sleep(.5)
   except Exception as e:self.report.emit('Windows capture: '+str(e))
  threading.Thread(target=reader,daemon=True).start()
 def stop(self):
  self.generation+=1
  if self.proc:
   self.proc.terminate();self.proc=None
 def frame(self,payload):
  gen,data=payload
  if gen!=self.generation or self.busy or time.monotonic()-self.last<0.5:return
  im=QImage(data,960,540,2880,QImage.Format.Format_RGB888).copy()
  if im.isNull():return
  if im.width()>960:im=im.scaledToWidth(960)
  im=im.convertToFormat(QImage.Format.Format_RGB888);data=bytes(im.constBits());w,h,stride=im.width(),im.height(),im.bytesPerLine();refs=self.refs;gen=self.generation;self.last=time.monotonic();self.busy=True
  def work():
   try:
    import cv2,numpy as np
    rgb=np.frombuffer(data,np.uint8).reshape(h,stride)[:,:w*3].reshape(h,w,3)
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    exclusion=np.full(gray.shape,255,np.uint8)
    exclusion[int(h*.78):,:int(w*.28)]=0
    k,d=cv2.ORB_create(nfeatures=1500).detectAndCompute(gray,exclusion);best=0
    if d is not None and len(d)>=2:
     pts=np.float32([x.pt for x in k]);matcher=cv2.BFMatcher(cv2.NORM_HAMMING)
     for rp,rd in refs:
      matches=[a for pair in matcher.knnMatch(rd,d,k=2) if len(pair)==2 for a,b in [pair] if a.distance<.75*b.distance]
      if len(matches)<8:continue
      H,mask=cv2.findHomography(np.float32([rp[a.queryIdx] for a in matches]),np.float32([pts[a.trainIdx] for a in matches]),cv2.RANSAC,4)
      if H is not None and mask is not None and mask.mean()>=.45:best=max(best,int(mask.sum()))
    if gen==self.generation:self.detected.emit(float(best))
   except Exception as e:self.report.emit(str(e))
   finally:self.busy=False
  threading.Thread(target=work,daemon=True).start()
