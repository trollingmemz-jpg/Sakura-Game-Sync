import os,sys,json,math,time
import gi
gi.require_version('Gtk','3.0')
gi.require_version('GtkLayerShell','0.1')
from gi.repository import Gtk,Gdk,GLib,GtkLayerShell as Layer
import cairo
if not Layer.is_supported():raise RuntimeError('Compositor does not support layer shell')
path=sys.argv[1]
parent=os.getppid()
win=Gtk.Window()
win.set_decorated(False);win.set_app_paintable(True);win.set_accept_focus(False)
visual=win.get_screen().get_rgba_visual()
if visual:win.set_visual(visual)
Layer.init_for_window(win)
Layer.set_layer(win,Layer.Layer.OVERLAY)
Layer.set_exclusive_zone(win,-1)
Layer.set_keyboard_mode(win,Layer.KeyboardMode.NONE)
for edge in (Layer.Edge.TOP,Layer.Edge.BOTTOM,Layer.Edge.LEFT,Layer.Edge.RIGHT):Layer.set_anchor(win,edge,True)
def empty(*args):
 win.input_shape_combine_region(cairo.Region())
win.connect('realize',empty)
state={};mix=0.;monitor=None
def draw(widget,cr):
 global mix
 w,h=widget.get_allocated_width(),widget.get_allocated_height()
 cr.set_operator(cairo.OPERATOR_SOURCE);cr.set_source_rgba(0,0,0,0);cr.paint();cr.set_operator(cairo.OPERATOR_OVER)
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
 global state,monitor
 if os.getppid()!=parent:Gtk.main_quit();return False
 try:
  with open(path) as f:state=json.load(f)
  if time.time()-state['time']>3 or not state['visible']:win.hide();return True
  coords=state['geometry']
  display=Gdk.Display.get_default()
  target=display.get_monitor_at_point(coords[0]+coords[2]//2,coords[1]+coords[3]//2)
  if target!=monitor:
   win.hide();Layer.set_monitor(win,target);monitor=target
  if not win.get_visible():win.show_all();empty()
  win.queue_draw()
 except (OSError,ValueError,KeyError):win.hide()
 return True
GLib.timeout_add(40,tick)
Gtk.main()
