import math, tarfile, subprocess, os, sys, json, time, re, base64, hashlib, secrets, threading, urllib.request, urllib.parse, urllib.error, http.server, webbrowser
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtWidgets import *
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QGuiApplication, QLinearGradient
ROOT=Path.home()/'.config/sakura-game-sync'; ROOT.mkdir(parents=True,exist_ok=True)
DEFAULT=[['Trailmakers','585420','trailmakers.exe','0WJzQWmJyamJTDxct2Tzw8'],['ULTRAKILL','1229490','ultrakill.exe','1bGOkRB37GOYMpr7DGDXxM'],['Minecraft','','net.minecraft.client.main.main|net.fabricmc.loader.impl.launch.knot.knotclient|org.quiltmc.loader.impl.launch.knot.knotclient|net.minecraft.launchwrapper.launch|forgeclient','3zI3N0QdvDVWLQQdsPhUdI'],['Rocket League','252950','rocketleague.exe','6cY3qz1WExXcwKOPfjceO7'],['Desktop','','','6HDaqxkKSPxjhditVm7vx7']]
def load(name, default):
 try:return json.loads((ROOT/name).read_text())
 except (OSError,ValueError):return default
def save(name,obj):
 p=ROOT/name; t=p.with_suffix('.tmp'); fd=os.open(t,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as f:json.dump(obj,f,indent=2)
 os.replace(t,p)
def uri(s):
 s=s.strip(); m=re.fullmatch(r'(?:spotify:playlist:|https://open.spotify.com/playlist/)?([A-Za-z0-9]{22})(?:\?.*)?',s)
 if not m:raise ValueError('Use a Spotify playlist link, URI or ID.')
 return 'spotify:playlist:'+m[1]
def scan(rows):
 found=set()
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   if p.stat().st_uid!=os.getuid():continue
   cmd=(p/'cmdline').read_bytes().decode(errors='replace').lower().split('\0'); env=(p/'environ').read_bytes().split(b'\0')
   ids={x.split(b'=',1)[1].decode(errors='ignore') for x in env if x.startswith((b'SteamAppId=',b'SteamGameId='))}
   for name,appid,patterns,_ in rows:
    if name=='Desktop':continue
    if (appid and appid in ids) or any(x and any(x.lower() in a for a in cmd) for x in patterns.split('|')):found.add(name)
  except (OSError,ValueError):pass
 return found
class Spotify:
 def __init__(self):self.token=load('token.json',{}); self.client=''
 def exchange(self,data):
  req=urllib.request.Request('https://accounts.spotify.com/api/token',data=urllib.parse.urlencode(data).encode())
  with urllib.request.urlopen(req,timeout=12) as r:
   try:t=json.load(r)
   except ValueError as e:raise RuntimeError(f'Spotify token endpoint returned invalid JSON (HTTP {r.status}).') from e
  self.token={**self.token,**t,'expires_at':time.time()+t['expires_in']};save('token.json',self.token)
 def login(self,client):
  self.client=client; verifier=secrets.token_urlsafe(64); state=secrets.token_urlsafe(24); challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='); redirect='http://127.0.0.1:8700/callback'; result={}
  class Handler(http.server.BaseHTTPRequestHandler):
   def do_GET(self):
    q=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
    if urllib.parse.urlsplit(self.path).path!='/callback' or q.get('state',[''])[0]!=state:self.send_error(400);return
    result.update(q);self.send_response(200);self.end_headers();self.wfile.write(b'Return to Sakura Game Sync.')
   def log_message(self,*args):pass
  with http.server.HTTPServer(('127.0.0.1',8700),Handler) as server:
   server.timeout=1
   webbrowser.open('https://accounts.spotify.com/authorize?'+urllib.parse.urlencode(dict(client_id=client,response_type='code',redirect_uri=redirect,code_challenge_method='S256',code_challenge=challenge,state=state,scope='user-read-playback-state user-modify-playback-state user-read-currently-playing')))
   deadline=time.monotonic()+180
   while not result and time.monotonic()<deadline:server.handle_request()
  if 'code' not in result:raise RuntimeError('Spotify sign-in cancelled or timed out.')
  self.token={};self.exchange(dict(client_id=client,grant_type='authorization_code',code=result['code'][0],redirect_uri=redirect,code_verifier=verifier))
 def call(self,path,method='GET',body=None):
  if not self.client or not self.token.get('refresh_token'):raise RuntimeError('Connect Spotify in Settings first.')
  if time.time()>self.token.get('expires_at',0)-60:self.exchange(dict(client_id=self.client,grant_type='refresh_token',refresh_token=self.token['refresh_token']))
  req=urllib.request.Request('https://api.spotify.com/v1/me/player'+path,method=method,headers={'Authorization':'Bearer '+self.token['access_token'],'Content-Type':'application/json'},data=json.dumps(body).encode() if body is not None else None)
  try:
   with urllib.request.urlopen(req,timeout=10) as r:
    b=r.read()
    if not b.strip() or r.status==204:return {}
    try:return json.loads(b)
    except ValueError as e:raise RuntimeError(f'Spotify returned non-JSON HTTP {r.status} for {method} {path or "/"}: '+b.decode(errors='replace')[:160]) from e
  except urllib.error.HTTPError as e:raise RuntimeError(f'Spotify HTTP {e.code}: '+e.read().decode(errors='replace')[:250]) from e
 def play(self,playlist,device,shuffle):
  devices=self.call('/devices').get('devices',[]); d=next((d for d in devices if d['name']==device),None) if device else next((d for d in devices if d.get('is_active')),None)
  if not d:raise RuntimeError('Open Spotify on the desired device, then refresh devices.')
  q=urllib.parse.urlencode({'device_id':d['id']}); desired=uri(playlist)
  current=self.call('')
  if (current.get('context') or {}).get('uri')==desired and (current.get('device') or {}).get('id')==d['id'] and current.get('is_playing'):return
  self.call('/play?'+q,'PUT',{'context_uri':desired})
  try:self.call('/shuffle?'+q+'&state='+str(shuffle).lower(),'PUT')
  except RuntimeError:pass
class Bridge(QObject):
 done=Signal(object,object)
class CombatHue(QWidget):
 def __init__(self):
  super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowTransparentForInput|Qt.WindowType.WindowDoesNotAcceptFocus)
  self.setWindowTitle('Sakura Combat Hue')
  self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
  self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
  self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
  self.mix=0.;self.pulse=0.;self.target_screen=None
 def paintEvent(self,event):
  p=QPainter(self)
  w,h=self.width(),self.height()
  depth=max(1,int(min(w,h)*.16))
  color=QColor(int(45+210*self.mix),int(220-175*self.mix),int(200-155*self.mix))
  alpha=int(65+self.mix*(35+55*self.pulse))
  for x1,y1,x2,y2,x,y,rw,rh in [(0,0,depth,0,0,0,depth,h),(w,0,w-depth,0,w-depth,0,depth,h),(0,0,0,depth,0,0,w,depth),(0,h,0,h-depth,0,h-depth,w,depth)]:
   g=QLinearGradient(x1,y1,x2,y2)
   c=QColor(color);c.setAlpha(alpha);g.setColorAt(0,c)
   c=QColor(color);c.setAlpha(int(alpha*.25));g.setColorAt(.45,c)
   c=QColor(color);c.setAlpha(0);g.setColorAt(1,c)
   p.fillRect(x,y,rw,rh,g)
  p.end()
 def display_on(self,screen):
  if self.target_screen!=screen or not self.isVisible():
   self.target_screen=screen
   self.winId()
   self.windowHandle().setScreen(screen)
   self.setGeometry(screen.geometry())
   self.showFullScreen()
   self.raise_()
class Window(QMainWindow):
 def __init__(self):
  super().__init__();self.setWindowTitle('Sakura • Game Sync');self.resize(980,660);self.cfg=load('settings.json',{});self.rows=load('games.json',DEFAULT);self.sp=Spotify();self.sp.client=self.cfg.get('client','');self.busy=False;self.active=None;self.candidate=None;self.count=0;self.bridge=Bridge();self.bridge.done.connect(self.complete);self.callback=None;self.quitting=False
  central=QWidget();self.setCentralWidget(central);layout=QVBoxLayout(central);layout.setContentsMargins(28,24,28,24);layout.setSpacing(14)
  title=QLabel('SAKURA  /  GAME SYNC');title.setObjectName('heading');layout.addWidget(title);self.status=QLabel('Ready • waiting for game detection');layout.addWidget(self.status)
  bar=QHBoxLayout();self.enabled=QCheckBox('Automatic switching');self.enabled.setChecked(self.cfg.get('enabled',False));self.shuffle=QCheckBox('Shuffle');self.shuffle.setChecked(self.cfg.get('shuffle',True));self.fallback=QCheckBox('Desktop playlist on game exit');self.fallback.setChecked(self.cfg.get('fallback',True));bar.addWidget(self.enabled);bar.addWidget(self.shuffle);bar.addWidget(self.fallback);bar.addStretch();layout.addLayout(bar)
  self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['Game','Steam app ID','Process match ( | separates alternatives )','Spotify playlist']);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents);self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);layout.addWidget(self.table,1)
  for row in self.rows:self.add(row)
  bar=QHBoxLayout()
  for label,fn in [('Add game',lambda:self.add(['New game','','',''])),('Remove selected',self.remove),('Save mappings',self.persist),('Play selected',self.manual),('Retry detection',self.retry)]:
   b=QPushButton(label);b.clicked.connect(fn);bar.addWidget(b)
  layout.addLayout(bar); settings=QGroupBox('Spotify connection');f=QFormLayout(settings);self.client=QLineEdit(self.sp.client);self.client.setPlaceholderText('Spotify developer application client ID');f.addRow('Client ID',self.client);self.device=QComboBox();self.device.setEditable(True);self.device.addItem(self.cfg.get('device',''));f.addRow('Playback device (blank = active)',self.device);b=QPushButton('Connect Spotify');b.clicked.connect(self.login);r=QPushButton('Refresh devices');r.clicked.connect(self.devices);f.addRow(b,r);layout.addWidget(settings)
  self.vision=None;self.last_mech=0;self.last_frame=0;self.combat_retry=0;self.last_switch=0;self.retry_after=0;self.hits=0;self.capture_requested=False;self.combat_latched=False;self.combat_sent=False;self.clear_since=None;self.hit_since=None;self.evidence=[]
  group=QGroupBox('Adaptive combat — experimental');form=QFormLayout(group)
  self.adaptive=QCheckBox('Enable mech soundtrack');self.adaptive.setChecked(self.cfg.get('adaptive',False));form.addRow(self.adaptive)
  self.combat=QLineEdit(self.cfg.get('combat',''));form.addRow('Combat playlist URL',self.combat)
  self.threshold=QSpinBox();self.threshold.setRange(8,100);self.threshold.setValue(self.cfg.get('threshold',12));form.addRow('Matching threshold',self.threshold)
  self.vision_status=QLabel('Import mech references, then start capture');self.vision_status.setWordWrap(True);form.addRow(self.vision_status)
  for label,fn in [('Install vision dependencies',self.install_vision),('Import blueprint archive',self.import_archive),('Import mech images',self.import_images),('Start capture',self.start_vision),('Stop capture',self.stop_vision)]:
   b=QPushButton(label);b.clicked.connect(fn);form.addRow(b)
  self.hud_enabled=QCheckBox('Show combat overlay');self.hud_enabled.setChecked(self.cfg.get('hud_enabled',True));form.addRow(self.hud_enabled)
  self.hud_screen=QComboBox()
  for screen in QGuiApplication.screens():self.hud_screen.addItem(screen.name())
  ix=self.hud_screen.findText(self.cfg.get('hud_screen',''))
  if ix>=0:self.hud_screen.setCurrentIndex(ix)
  form.addRow('Trailmakers monitor',self.hud_screen)
  self.hud=QLabel(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowTransparentForInput|Qt.WindowType.WindowDoesNotAcceptFocus)
  self.hud.setWindowTitle('Sakura Combat Overlay');self.hud.setObjectName('SakuraCombatOverlay');self.hud.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating);self.hud.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
  self.hue=CombatHue();self.hud.setFixedSize(300,76);self.hud.setAlignment(Qt.AlignmentFlag.AlignCenter)
  self.hud_enabled.toggled.connect(self.refresh_hud);self.hud_screen.currentIndexChanged.connect(self.refresh_hud)
  self.hud_timer=QTimer(self);self.hud_timer.timeout.connect(self.refresh_hud);self.hud_timer.start(40)
  layout.addWidget(group)
  self.log=QLabel('');self.log.setWordWrap(True);layout.addWidget(self.log);update=QPushButton('Check for updates');update.clicked.connect(self.update_app);layout.addWidget(update);self.setStyleSheet('QWidget{background:#161820;color:#e9e7ef;font-size:13px} QLabel#heading{font-size:25px;font-weight:700;color:#f1a6c4} QTableWidget,QLineEdit,QComboBox{background:#222531;border:1px solid #373949;border-radius:5px;padding:5px} QPushButton{background:#343143;border:1px solid #514459;border-radius:6px;padding:9px} QPushButton:hover{background:#55405a} QHeaderView::section{background:#2b2c38;padding:7px;border:0} QGroupBox{border:1px solid #373949;border-radius:8px;margin-top:10px;padding:12px} QGroupBox::title{subcontrol-origin:margin;left:10px;color:#f1a6c4}')
  pix=QPixmap(48,48);pix.fill(Qt.GlobalColor.transparent);p=QPainter(pix);p.setBrush(QColor('#ee9cbe'));p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(5,5,38,38);p.end();self.tray=QSystemTrayIcon(QIcon(pix),self);menu=QMenu();menu.addAction('Show Sakura',self.showNormal);menu.addAction('Check for updates',self.update_app);menu.addAction('Quit',self.quit);self.tray.setContextMenu(menu);self.tray.activated.connect(lambda reason:self.showNormal() if reason==QSystemTrayIcon.ActivationReason.Trigger else None);self.tray.show()
  self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(3000)
 def update_app(self):
  if self.busy:return
  if not self.persist():return
  root=Path(__file__).resolve().parent
  def git(*args):
   return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.STDOUT,text=True,timeout=60).strip()
  def check():
   if git('status','--porcelain','--untracked-files=no'):raise RuntimeError('Local tracked changes must be committed before updating.')
   git('fetch','origin','main')
   return (git('rev-parse','HEAD'),git('rev-parse','origin/main'))
  def ready(result):
   old,new=result
   if old==new:self.log.setText('Sakura is up to date.');return
   if QMessageBox.question(self,'Sakura update','Install available update and restart?')!=QMessageBox.StandardButton.Yes:return
   def apply():
    git('branch','-f','sakura-backup',old)
    git('merge','--ff-only',new)
    return old
   def restart(_):
    self.quitting=True
    if self.vision:self.vision.stop()
    self.hue.hide();self.hud.hide()
    lock.unlock()
    os.execv(sys.executable,[sys.executable,str(root/'app.py')])
   self.job(apply,restart)
  self.job(check,ready)
 def install_vision(self):
  self.job(lambda:subprocess.check_output([sys.executable,'-m','pip','install','opencv-python-headless'],stderr=subprocess.STDOUT,text=True,timeout=300),lambda _:self.vision_status.setText('Dependencies installed. Ready to import.'))
 def reference_dir(self):
  p=ROOT/'references';p.mkdir(exist_ok=True);return p
 def stage(self,name,data):
  if len(data)>20*1024*1024:return
  suffix=Path(name).suffix.lower()
  if suffix not in ('.png','.jpg','.jpeg','.webp'):return
  (self.reference_dir()/(hashlib.sha256(data).hexdigest()+suffix)).write_bytes(data)
 def import_archive(self):
  if self.busy:return
  path,_=QFileDialog.getOpenFileName(self,'Blueprint archive',str(Path.home()),'Archives (*.tar.gz *.tgz *.tar)')
  if not path:return
  def work():
   total=used=0
   with tarfile.open(path,'r:*') as t:
    for m in t:
     if not m.isfile() or Path(m.name).suffix.lower()!='.png':continue
     total+=1
     if not any('mech' in p.lower() for p in Path(m.name).parts[:-1]) or m.size>20*1024*1024:continue
     f=t.extractfile(m)
     if f:self.stage(m.name,f.read());used+=1
   return total,used
  def done(r):
   self.vision_status.setText(f'Found {r[0]} blueprints; staged {r[1]} mech-folder candidates. Start capture to index.')
  self.stop_vision();self.job(work,done)
 def import_images(self):
  if self.busy:return
  files,_=QFileDialog.getOpenFileNames(self,'Select cropped mech references',str(Path.home()),'Images (*.png *.jpg *.jpeg *.webp)')
  if not files:return
  self.stop_vision()
  try:
   for p in files:self.stage(p,Path(p).read_bytes())
   self.vision_status.setText('References saved. Start capture to index.')
  except OSError as e:self.vision_status.setText(str(e))
 def refresh_hud(self,*args):
  if not self.hud_enabled.isChecked() or not self.capture_requested:
   self.hud.hide();self.hue.hide();return
  screen=next((x for x in QGuiApplication.screens() if x.name()==self.hud_screen.currentText()),None)
  if screen is None:self.hud.hide();return
  locked=self.combat_latched and time.monotonic()-self.last_mech<20
  stale=not self.last_frame or time.monotonic()-self.last_frame>5
  n=min(3,sum(time.monotonic()-t<=8 for t in self.evidence))
  state='CAPTURE WAITING' if stale else ('COMBAT LOCKED' if locked else ('RESTORING MUSIC' if self.active=='Mech combat' else ('CONFIRMING MECH' if n else 'SCANNING')))
  pulse=(1+math.sin(time.monotonic()*math.tau/2.4))/2
  self.hue.mix+=((1. if locked else 0.)-self.hue.mix)*.14
  self.hue.pulse=pulse;self.hue.display_on(screen);self.hue.update()
  color=f'#ff{int(65+55*pulse):02x}{int(65+55*pulse):02x}' if locked else '#55d6c6'
  bg=f'rgba({int(48+40*pulse)},18,24,215)' if locked else 'rgba(15,42,43,205)'
  self.hud.setStyleSheet('QLabel{background:'+bg+';border:2px solid '+color+';border-radius:8px;color:'+color+';font-size:13px;font-weight:600;}')
  self.hud.setText('SAKURA  /  '+state+'\nEvidence '+str(n)+'/3  |  '+('Combat playlist' if self.active=='Mech combat' else 'Normal soundtrack'))
  self.hud.winId()
  if self.hud.windowHandle().screen()!=screen:self.hud.windowHandle().setScreen(screen)
  g=screen.availableGeometry();self.hud.move(g.x()+g.width()-self.hud.width()-20,g.y()+24)
  if not self.hud.isVisible():self.hud.show()
 def start_vision(self):
  if self.busy or not self.persist():return
  try:
   uri(self.combat.text())
   if 'Trailmakers' not in scan(self.rows):raise RuntimeError('Open Trailmakers first.')
   import cv2
   from adaptive import Vision
   if self.vision is None:
    self.vision=Vision(self);self.vision.report.connect(self.vision_status.setText);self.vision.detected.connect(self.on_mech)
   self.vision.load(list(self.reference_dir().glob('*')))
   screen=next((x for x in QGuiApplication.screens() if x.name()==self.hud_screen.currentText()),None)
   if screen is not None:self.vision.capture.setScreen(screen)
   self.last_mech=0;self.last_frame=0;self.hits=0;self.clear_since=None;self.hit_since=None;self.evidence=[];self.capture_requested=True;self.vision.start()
  except Exception as e:self.capture_requested=False;self.vision_status.setText(str(e))
 def stop_vision(self):
  self.evidence=[];self.capture_requested=False;self.last_mech=0;self.last_frame=0;self.hits=0;self.combat_latched=False;self.combat_sent=False;self.clear_since=None
  if self.vision:self.vision.stop()
  self.hud.hide();self.hue.hide()
 def on_mech(self,score):
  if not self.capture_requested:return
  now=time.monotonic()
  self.last_frame=now
  threshold=self.threshold.value()
  self.evidence=[t for t in self.evidence if now-t<=8]
  if score>=threshold:
   self.evidence.append(now)
  if len(self.evidence)>=3:
   if not self.combat_latched:
    self.combat_latched=True;self.clear_since=None
   if score>=threshold:self.last_mech=now
  if self.combat_latched and now-self.last_mech>=20:
   self.combat_latched=False;self.combat_sent=False;self.evidence=[];self.clear_since=None
  status=f'COMBAT LOCKED | release in {max(0,int(20-(now-self.last_mech)))}s' if self.combat_latched else ('Confirming mech' if self.evidence else 'Scanning')
  self.vision_status.setText(f'Matching features: {int(score)} | {status} | Evidence: {min(3,len(self.evidence))}/3')
  if self.combat_latched and not self.combat_sent and self.enabled.isChecked() and self.adaptive.isChecked() and not self.busy:self.tick()
 def add(self,row):
  i=self.table.rowCount();self.table.insertRow(i)
  for j,x in enumerate(row):self.table.setItem(i,j,QTableWidgetItem(x))
 def remove(self):
  for i in sorted({x.row() for x in self.table.selectedIndexes()},reverse=True):self.table.removeRow(i)
 def persist(self):
  rows=[[self.table.item(i,j).text().strip() if self.table.item(i,j) else '' for j in range(4)] for i in range(self.table.rowCount())]
  try:
   if len({r[0] for r in rows})!=len(rows) or any(not r[0] for r in rows):raise ValueError('Game names must be unique and nonempty.')
   for r in rows:uri(r[3])
  except ValueError as e:self.log.setText(str(e));return False
  self.rows=rows;self.cfg=dict(client=self.client.text().strip(),device=self.device.currentText().strip(),enabled=self.enabled.isChecked(),shuffle=self.shuffle.isChecked(),fallback=self.fallback.isChecked());self.cfg.update(adaptive=self.adaptive.isChecked(),combat=self.combat.text().strip(),threshold=self.threshold.value(),hud_enabled=self.hud_enabled.isChecked(),hud_screen=self.hud_screen.currentText());save('games.json',rows);save('settings.json',self.cfg);self.sp.client=self.cfg['client'];self.log.setText('Settings saved.');return True
 def job(self,fn,callback=None):
  if self.busy:return
  self.busy=True;self.callback=callback
  def run():
   try:self.bridge.done.emit(fn(),None)
   except Exception as e:self.bridge.done.emit(None,str(e))
  threading.Thread(target=run,daemon=True).start()
 def complete(self,result,error):
  self.busy=False; cb=self.callback;self.callback=None
  if error:self.log.setText(error)
  else:
   self.log.setText('Spotify request completed.')
   if cb:cb(result)
 def login(self):
  if self.busy or not self.persist():return
  self.log.setText('Complete the one-time Spotify authorisation in your browser.');self.job(lambda:self.sp.login(self.sp.client))
 def devices(self):
  if self.busy or not self.persist():return
  def update(result):
   old=self.device.currentText();self.device.clear();self.device.addItem('');self.device.addItems([d['name'] for d in result.get('devices',[])]);self.device.setCurrentText(old)
  self.job(lambda:self.sp.call('/devices'),update)
 def play(self,row):
  device=self.device.currentText().strip();shuffle=self.shuffle.isChecked();self.job(lambda:self.sp.play(row[3],device,shuffle))
 def manual(self):
  i=self.table.currentRow()
  if i>=0 and not self.busy and self.persist():self.play(self.rows[i])
 def retry(self):self.active=None;self.count=0;self.combat_sent=False;self.tick()
 def tick(self):
  now=time.monotonic()
  if self.combat_latched and now-self.last_mech>=20:
   self.combat_latched=False;self.combat_sent=False;self.evidence=[];self.clear_since=None
  if self.busy:return
  found=scan(self.rows)
  target=self.active if self.active in found else next((r[0] for r in self.rows if r[0] in found),'Desktop')
  self.status.setText('Detected: '+(', '.join(sorted(found)) or 'Desktop')+'  •  '+('Automatic switching on' if self.enabled.isChecked() else 'Manual mode'))
  if 'Trailmakers' not in found:
   if self.capture_requested:self.stop_vision()
   self.combat_latched=False;self.combat_sent=False;self.clear_since=None
  if not self.enabled.isChecked():self.active=None;self.candidate=None;self.count=0;return
  combat='Trailmakers' in found and self.adaptive.isChecked() and self.capture_requested
  if self.combat_latched and now-self.last_mech>=20:
   self.combat_latched=False;self.combat_sent=False;self.evidence=[];self.clear_since=None
  if combat and not self.combat_latched:target='Trailmakers'
  if combat and self.combat_latched:
   target='Mech combat'
   if self.combat_sent:return
  if target==self.active:self.candidate=None;self.count=0;return
  if target!=self.candidate:self.candidate=target;self.count=1
  else:self.count+=1
  if target!='Mech combat' and self.count<2:return
  if now<self.retry_after:return
  if target=='Desktop' and (self.active is None or not self.fallback.isChecked()):self.active=target;return
  row=next((r for r in self.rows if r[0]==target),None)
  playlist=self.combat.text().strip() if target=='Mech combat' else (row[3] if row else '')
  if not playlist:return
  try:uri(playlist)
  except ValueError as e:self.log.setText(str(e));self.retry_after=now+30;return
  device=self.device.currentText().strip();shuffle=self.shuffle.isChecked()
  self.retry_after=now+10
  def done(_):
   self.active=target;self.last_switch=time.monotonic();self.retry_after=0
  if target=='Mech combat':self.combat_sent=True
  self.job(lambda:self.sp.play(playlist,device,shuffle),done)
 def closeEvent(self,e):
  if self.quitting or not QSystemTrayIcon.isSystemTrayAvailable():e.accept()
  else:self.hide();e.ignore()
 def quit(self):self.stop_vision();self.quitting=True;QApplication.quit()
if __name__=='__main__':
 from PySide6.QtCore import QLockFile
 app=QApplication(sys.argv);lock=QLockFile(str(ROOT/'instance.lock'));lock.setStaleLockTime(0)
 if not lock.tryLock(0):sys.exit(0)
 app.setQuitOnLastWindowClosed(False);w=Window();w.show() if '--background' not in sys.argv else None;sys.exit(app.exec())
