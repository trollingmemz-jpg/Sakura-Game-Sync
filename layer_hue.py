import os,sys,json,math,time
os.environ['GDK_BACKEND']='x11'
import gi
gi.require_version('Gtk','3.0')
gi.require_version('GdkX11','3.0')
from gi.repository import Gtk,Gdk,GdkX11,GLib
from Xlib import X,display,error
import cairo
path=sys.argv[1]
parent=os.getppid()
connection=display.Display()
root=connection.screen().root
active_atom=connection.intern_atom('_NET_ACTIVE_WINDOW')
clients_atom=connection.intern_atom('_NET_CLIENT_LIST')
win=Gtk.Window(type=Gtk.WindowType.POPUP)
win.set_title('Sakura Combat Hue')
win.set_accept_focus(False);win.set_focus_on_map(False);win.set_app_paintable(True)
visual=win.get_screen().get_rgba_visual()
if visual is None:raise RuntimeError('No transparent XWayland visual')
win.set_visual(visual)
state={};mix=0.;bounds=None;target=None
def find_game():
 clients=root.get_full_property(clients_atom,X.AnyPropertyType)
 candidates=[]
 for wid in clients.value if clients else ():
  try:
   w=connection.create_resource_object('window',int(wid))
   if 'steam_app_585420' not in (w.get_wm_class() or ()) or w.get_attributes().map_state!=X.IsViewable:continue
   g=w.get_geometry()
   if g.width>=640 and g.height>=360:candidates.append((g.width*g.height,w))
  except error.XError:continue
 return max(candidates,key=lambda x:x[0])[1] if candidates else None
def draw(widget,cr):
 global mix
 w,h=widget.get_allocated_width(),widget.get_allocated_height()
 cr.set_operator(cairo.OPERATOR_SOURCE);cr.set_source_rgba(0,0,0,0);cr.paint();cr.set_operator(cairo.OPERATOR_OVER)
 if not state.get('focused'):return True
 mix+=((1. if state.get('locked') else 0.)-mix)*.14
 pulse=(1+math.sin(time.monotonic()*math.tau/2.4))/2
 r,g,b=(45+210*mix)/255,(220-175*mix)/255,(200-155*mix)/255
 a=(65+mix*(35+55*pulse))/255
 d=max(1,int(min(w,h)*.16))
 for x1,y1,x2,y2,x,y,rw,rh in [(0,0,d,0,0,0,d,h),(w,0,w-d,0,w-d,0,d,h),(0,0,0,d,0,0,w,d),(0,h,0,h-d,0,h-d,w,d)]:
  gradient=cairo.LinearGradient(x1,y1,x2,y2)
  for pos,opacity in [(0,a),(.45,a*.25),(1,0)]:gradient.add_color_stop_rgba(pos,r,g,b,opacity)
  cr.set_source(gradient);cr.rectangle(x,y,rw,rh);cr.fill()
 x=max(0,w-320);y=24
 cr.set_source_rgba(.04,.08,.10,.84);cr.rectangle(x,y,300,76);cr.fill_preserve()
 cr.set_source_rgba(r,g,b,.95);cr.set_line_width(2);cr.stroke()
 cr.select_font_face('Sans',cairo.FONT_SLANT_NORMAL,cairo.FONT_WEIGHT_BOLD);cr.set_font_size(13)
 cr.move_to(x+12,y+27);cr.show_text('SAKURA / '+state.get('status','SCANNING'))
 cr.set_font_size(12);cr.move_to(x+12,y+51);cr.show_text('Evidence '+str(state.get('evidence',0))+'/3 | '+state.get('music',''))
 return True
win.connect('draw',draw)
def tick():
 global state,bounds,target
 if os.getppid()!=parent:Gtk.main_quit();return False
 try:
  with open(path) as f:state=json.load(f)
  if time.time()-state['time']>3 or not state['visible']:win.hide();return True
  if target is None:target=find_game()
  if target is None:win.hide();return True
  active=root.get_full_property(active_atom,X.AnyPropertyType)
  state['focused']=bool(active and len(active.value) and int(active.value[0])==target.id and target.get_attributes().map_state==X.IsViewable)
  g=target.get_geometry();p=root.translate_coords(target,0,0);scale=win.get_scale_factor()
  new=tuple(round(v/scale) for v in (p.x,p.y,g.width,g.height))
  if new!=bounds:
   win.move(*new[:2]);win.resize(*new[2:]);bounds=new
  if not win.get_visible():
   win.realize();native=win.get_window();native.input_shape_combine_region(cairo.Region(),0,0);native.set_pass_through(True);win.show()
  win.queue_draw()
 except error.XError:target=None;bounds=None;win.hide()
 except (OSError,ValueError,KeyError):win.hide()
 return True
GLib.timeout_add(40,tick)
Gtk.main()
