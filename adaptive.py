"""Experimental local mech matching using user-selected blueprint references."""
import time, threading
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from PySide6.QtMultimedia import QWindowCapture,QMediaCaptureSession,QVideoSink
class Vision(QObject):
 report=Signal(str)
 detected=Signal(float)
 def __init__(self,parent=None):
  super().__init__(parent);self.capture=QWindowCapture(self);self.session=QMediaCaptureSession(self);self.sink=QVideoSink(self);self.session.setWindowCapture(self.capture);self.session.setVideoSink(self.sink);self.sink.videoFrameChanged.connect(self.frame);self.capture.errorOccurred.connect(lambda *a:self.report.emit(str(a[-1])));self.refs=[];self.busy=False;self.last=0;self.generation=0
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
  windows=[w for w in QWindowCapture.capturableWindows() if w.isValid() and w.description().strip().lower()=='trailmakers']
  if not windows:raise RuntimeError('Trailmakers window capture unavailable on this Qt/Wayland backend. Desktop capture disabled for safety.')
  self.capture.setWindow(windows[0])
  self.generation+=1;self.capture.setActive(True)
 def stop(self):
  self.generation+=1;self.capture.setActive(False)
 def frame(self,f):
  if not self.capture.isActive() or self.busy or time.monotonic()-self.last<0.5:return
  from PySide6.QtGui import QImage
  im=f.toImage()
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
