import os, sys, uuid
from gi.repository import Gio, GLib
import gi
gi.require_version('Gst','1.0')
from gi.repository import Gst
Gst.init(None)
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
dest='org.freedesktop.portal.Desktop'
path='/org/freedesktop/portal/desktop'
iface=dest.replace('Desktop','ScreenCast')
iface='org.freedesktop.portal.ScreenCast'
def call(method,args):
 return bus.call_sync(dest,path,iface,method,args,None,Gio.DBusCallFlags.NONE,-1,None)
def request(method,signature,values,options):
 token='sakura_'+uuid.uuid4().hex
 options['handle_token']=GLib.Variant('s',token)
 sender=bus.get_unique_name()[1:].replace('.','_')
 req='/org/freedesktop/portal/desktop/request/'+sender+'/'+token
 loop=GLib.MainLoop()
 result=[]
 def response(*args):
  result.extend(args[5].unpack())
  loop.quit()
 sub=bus.signal_subscribe(dest,'org.freedesktop.portal.Request','Response',req,None,Gio.DBusSignalFlags.NONE,response)
 try:
  call(method,GLib.Variant(signature,tuple(values)+(options,)))
  if not result:loop.run()
  if result[0]!=0:raise RuntimeError(method+' cancelled or denied')
  return result[1]
 finally:bus.signal_unsubscribe(sub)
session=None
pipeline=None
try:
 session=request('CreateSession','(a{sv})',[],{'session_handle_token':GLib.Variant('s','sakura_'+uuid.uuid4().hex)})['session_handle']
 request('SelectSources','(oa{sv})',[session],{'types':GLib.Variant('u',2),'multiple':GLib.Variant('b',False),'cursor_mode':GLib.Variant('u',1)})
 streams=request('Start','(osa{sv})',[session,''],{})['streams']
 if len(streams)!=1:raise RuntimeError('Select exactly one Trailmakers window')
 node,props=streams[0]
 if props.get('source_type',2)!=2:raise RuntimeError('Only window sharing is allowed')
 reply,fds=bus.call_with_unix_fd_list_sync(dest,path,iface,'OpenPipeWireRemote',GLib.Variant('(oa{sv})',(session,{})),None,Gio.DBusCallFlags.NONE,-1,None,None)
 fd=fds.get(reply.unpack()[0])
 pipeline=Gst.parse_launch(f'pipewiresrc fd={fd} path={node} ! videoconvert ! videoscale ! videorate ! video/x-raw,format=RGB,width=960,height=540,framerate=2/1 ! appsink name=out max-buffers=1 drop=true sync=false')
 sink=pipeline.get_by_name('out')
 pipeline.set_state(Gst.State.PLAYING)
 while True:
  sample=sink.emit('try-pull-sample',Gst.SECOND)
  if sample:
   buf=sample.get_buffer()
   data=buf.extract_dup(0,buf.get_size())
   if len(data)!=960*540*3:raise RuntimeError('Unexpected frame stride')
   sys.stdout.buffer.write(data);sys.stdout.buffer.flush()
  else:
   msg=pipeline.get_bus().pop_filtered(Gst.MessageType.ERROR|Gst.MessageType.EOS)
   if msg:
    if msg.type==Gst.MessageType.ERROR:raise RuntimeError(str(msg.parse_error()))
    break
finally:
 if pipeline:pipeline.set_state(Gst.State.NULL)
 if session:
  try:bus.call_sync(dest,session,'org.freedesktop.portal.Session','Close',None,None,Gio.DBusCallFlags.NONE,1000,None)
  except Exception:pass
