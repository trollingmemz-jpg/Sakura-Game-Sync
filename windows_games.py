"""Discover installed Steam games and detect running games without scanning game files."""
import os,re,time,threading
from pathlib import Path
import psutil
def value(text,key):
 m=re.search(r'"'+re.escape(key)+r'"\s*"([^"]*)"',text,re.I)
 return m[1] if m else ''
def steam_games():
 import winreg
 roots=set()
 for hive,key in [(winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam'),(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\WOW6432Node\Valve\Steam'),(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Valve\Steam')]:
  try:
   with winreg.OpenKey(hive,key) as k:
    for name in ('SteamPath','InstallPath'):
     try:roots.add(Path(winreg.QueryValueEx(k,name)[0]))
     except OSError:pass
  except OSError:pass
 roots.add(Path(os.environ.get('ProgramFiles(x86)',r'C:\Program Files (x86)'))/'Steam')
 libraries=set(roots)
 for root in roots:
  try:
   data=(root/'steamapps'/'libraryfolders.vdf').read_text(encoding='utf-8',errors='replace')
   for path in re.findall(r'"path"\s*"([^"]+)"',data):libraries.add(Path(path.replace('\\\\','\\')))
  except OSError:pass
 games={}
 for root in libraries:
  for manifest in (root/'steamapps').glob('appmanifest_*.acf'):
   try:
    data=manifest.read_text(encoding='utf-8',errors='replace')
    appid=value(data,'appid');name=value(data,'name');folder=value(data,'installdir')
    if not appid.isdigit() or not name or not folder:continue
    base=(root/'steamapps'/'common').resolve();path=(base/folder).resolve()
    if path.is_relative_to(base) and path.is_dir():games[appid]=(name,str(path).casefold())
   except (OSError,ValueError):pass
 return games
class Detector:
 def __init__(self):
  self.games={};self.result=set();self.rows=[];self.stop=threading.Event();self.refresh=threading.Event();self.refresh.set()
  threading.Thread(target=self.run,daemon=True).start()
 def run(self):
  next_refresh=0
  while not self.stop.is_set():
   if self.refresh.is_set() or time.monotonic()>=next_refresh:
    self.refresh.clear()
    try:self.games=steam_games()
    except Exception:pass
    next_refresh=time.monotonic()+120
   try:self.result=self.scan(self.rows)
   except Exception:pass
   self.stop.wait(2)
 def scan(self,rows):
  games=self.games;found=set()
  mapped={r[1]:r[0] for r in rows if r[1]}
  patterns=[(r[0],tuple(x.casefold() for x in r[2].split('|') if x)) for r in rows if r[0]!='Desktop']
  folders=tuple((path.rstrip('\\/')+os.sep,mapped.get(appid,name)) for appid,(name,path) in games.items())
  for p in psutil.process_iter(['name','exe']):
   try:
    name=(p.info.get('name') or '').casefold();exe=(p.info.get('exe') or '').casefold()
    if not name:continue
    for folder,game in folders:
     if exe.startswith(folder):
      if not any(x in name for x in ('crash','uninstall','setup','redist','reporter')):found.add(game)
      break
    cmd=''
    if name.startswith(('java','python','dotnet')):cmd=' '.join(p.cmdline()).casefold()
    for game,terms in patterns:
     if any(term in name or term in exe or term in cmd for term in terms):found.add(game)
   except (psutil.Error,OSError):pass
  return found
