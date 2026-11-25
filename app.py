import os, sys, json, time, re, base64, hashlib, secrets, threading, urllib.request, urllib.parse, urllib.error, http.server, webbrowser
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtWidgets import *
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
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
  with urllib.request.urlopen(req,timeout=12) as r: t=json.load(r)
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
    b=r.read();return json.loads(b) if b else {}
  except urllib.error.HTTPError as e:raise RuntimeError(f'Spotify HTTP {e.code}: '+e.read().decode(errors='replace')[:250]) from e
 def play(self,playlist,device,shuffle):
  devices=self.call('/devices').get('devices',[]); d=next((d for d in devices if d['name']==device),None) if device else next((d for d in devices if d.get('is_active')),None)
  if not d:raise RuntimeError('Open Spotify on the desired device, then refresh devices.')
  q=urllib.parse.urlencode({'device_id':d['id']}); self.call('/play?'+q,'PUT',{'context_uri':uri(playlist)}); self.call('/shuffle?'+q+'&state='+str(shuffle).lower(),'PUT')
class Bridge(QObject):
 done=Signal(object,object)
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
  self.log=QLabel('');self.log.setWordWrap(True);layout.addWidget(self.log);self.setStyleSheet('QWidget{background:#161820;color:#e9e7ef;font-size:13px} QLabel#heading{font-size:25px;font-weight:700;color:#f1a6c4} QTableWidget,QLineEdit,QComboBox{background:#222531;border:1px solid #373949;border-radius:5px;padding:5px} QPushButton{background:#343143;border:1px solid #514459;border-radius:6px;padding:9px} QPushButton:hover{background:#55405a} QHeaderView::section{background:#2b2c38;padding:7px;border:0} QGroupBox{border:1px solid #373949;border-radius:8px;margin-top:10px;padding:12px} QGroupBox::title{subcontrol-origin:margin;left:10px;color:#f1a6c4}')
  pix=QPixmap(48,48);pix.fill(Qt.GlobalColor.transparent);p=QPainter(pix);p.setBrush(QColor('#ee9cbe'));p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(5,5,38,38);p.end();self.tray=QSystemTrayIcon(QIcon(pix),self);menu=QMenu();menu.addAction('Show Sakura',self.showNormal);menu.addAction('Quit',self.quit);self.tray.setContextMenu(menu);self.tray.activated.connect(lambda reason:self.showNormal() if reason==QSystemTrayIcon.ActivationReason.Trigger else None);self.tray.show()
  self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(3000)
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
  self.rows=rows;self.cfg=dict(client=self.client.text().strip(),device=self.device.currentText().strip(),enabled=self.enabled.isChecked(),shuffle=self.shuffle.isChecked(),fallback=self.fallback.isChecked());save('games.json',rows);save('settings.json',self.cfg);self.sp.client=self.cfg['client'];self.log.setText('Settings saved.');return True
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
 def retry(self):self.active=None;self.count=0;self.tick()
 def tick(self):
  if self.busy:return
  found=scan(self.rows);target=self.active if self.active in found else next((r[0] for r in self.rows if r[0] in found),'Desktop');self.status.setText('Detected: '+(', '.join(sorted(found)) or 'Desktop')+'  •  '+('Automatic switching on' if self.enabled.isChecked() else 'Manual mode'))
  if not self.enabled.isChecked():self.active=None;return
  if target!=self.candidate:self.candidate=target;self.count=1;return
  self.count+=1
  if self.count<2 or target==self.active:return
  previous=self.active;self.active=target
  if target=='Desktop' and (previous is None or not self.fallback.isChecked()):return
  row=next((r for r in self.rows if r[0]==target),None)
  if row:self.play(row)
 def closeEvent(self,e):
  if self.quitting or not QSystemTrayIcon.isSystemTrayAvailable():e.accept()
  else:self.hide();e.ignore()
 def quit(self):self.quitting=True;QApplication.quit()
if __name__=='__main__':
 app=QApplication(sys.argv);app.setQuitOnLastWindowClosed(False);w=Window();w.show() if '--background' not in sys.argv else None;sys.exit(app.exec())
