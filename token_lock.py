"""Cross-platform advisory lock for shared Spotify credentials."""
from contextlib import contextmanager
import os
@contextmanager
def token_lock(path):
 with open(path,'a+b') as f:
  if os.name=='nt':
   import msvcrt
   f.seek(0,2)
   if f.tell()==0:f.write(b'0');f.flush()
   f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_LOCK,1)
   try:yield
   finally:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
  else:
   import fcntl
   fcntl.flock(f,fcntl.LOCK_EX)
   try:yield
   finally:fcntl.flock(f,fcntl.LOCK_UN)
