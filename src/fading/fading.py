import cv2
import numpy as np
import os
import re
import time
import tkinter as tk
from tkinter import filedialog, ttk
from PIL import Image, ImageTk, ImageDraw, ImageFont

# Filter / Reset

BG_COLOR = "#dcdcdc"
TEXT_BG_COLOR = (220, 220, 220, 255)
PROXY_COLOR = (255, 0, 0, 255)  # red text for proxy images
TEXT_COLOR = (0, 0, 0)
TEXT_FONT_SIZE = 12

MODE_NONE = 0
MODE_FILES = 1
MODE_SINGLE_DIR = 2
MODE_SUBFOLDERS = 3
current_mode = MODE_NONE

# Each entry in image_data: (filepath, BoolVar, brightness, offset, is_proxy)
image_data = []

subfolder_names = []
subfolder_data = {}  # { subfolderName : { offset -> (filepath, is_proxy) } }
subfolder_combo_idx = 0

final_image = None
boundary_positions = []
filenames_at_boundaries = []

# Crossfade for entire subfolders
crossfade_frames = []
crossfade_index = 0
crossfade_active = False

def parse_utc_offset(filepath):
  base = os.path.basename(filepath)
  match = re.match(r"^(UTC[+-]\d+(?:\.\d+)?).*", base, re.IGNORECASE)
  if match:
    num_match = re.match(r"UTC([+-]\d+(?:\.\d+)?).*", match.group(1), re.IGNORECASE)
    if num_match:
      try:
        return float(num_match.group(1))
      except ValueError:
        pass
  return 9999

def extract_utc_prefix(filepath):
  base = os.path.basename(filepath)
  match = re.match(r"^(UTC[+-]\d+(?:\.\d+)?).*", base, re.IGNORECASE)
  if match:
    return match.group(1)
  return base

def calculate_horizontal_average(image):
  return np.mean(image, axis=1).astype(np.uint8)

def get_image_brightness(image):
  gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
  return int(gray.mean())

def generate_fading_gradient(colors_left, colors_right, width):
  h = colors_left.shape[0]
  grad = np.zeros((h, width, 3), dtype=np.uint8)
  for y in range(h):
    for x in range(width):
      alpha = x / max(width - 1, 1)
      grad[y, x] = (1 - alpha) * colors_left[y] + alpha * colors_right[y]
  return grad

def get_next_output_subfolder():
  base = "output"
  if not os.path.exists(base):
    os.makedirs(base)
  i = 1
  while True:
    path = os.path.join(base, f"{i:03d}")
    if not os.path.exists(path):
      os.makedirs(path)
      return path
    i += 1

def create_black_dummy_image(offset):
  if not os.path.exists("temp"):
    os.makedirs("temp")
  sign = "+" if offset >= 0 else ""
  fname = f"UTC{sign}{offset}_dummy.png"
  path = os.path.join("temp", fname)
  dummy = np.zeros((10, 10, 3), dtype=np.uint8)
  cv2.imwrite(path, dummy)
  return path

def fallback_for_offset(i, offset):
  if i == 0:
    for k in range(1, len(subfolder_names)):
      om = subfolder_data[subfolder_names[k]]
      if offset in om:
        return om[offset][0], True
    return create_black_dummy_image(offset), True
  if i == len(subfolder_names) - 1:
    for k in range(len(subfolder_names) - 2, -1, -1):
      om = subfolder_data[subfolder_names[k]]
      if offset in om:
        return om[offset][0], True
    return create_black_dummy_image(offset), True
  for k in range(i+1, len(subfolder_names)):
    om = subfolder_data[subfolder_names[k]]
    if offset in om:
      return om[offset][0], True
  for k in range(i-1, -1, -1):
    om = subfolder_data[subfolder_names[k]]
    if offset in om:
      return om[offset][0], True
  return create_black_dummy_image(offset), True

def set_mode(m):
  global current_mode
  current_mode = m
  if m == MODE_SUBFOLDERS:
    subfolder_combo.config(state="readonly")
  else:
    subfolder_combo.config(state="disabled")
    prev_btn.config(state="disabled")
    next_btn.config(state="disabled")

def update_navigation():
  if current_mode == MODE_SUBFOLDERS and len(subfolder_names) > 1:
    subfolder_combo.config(state="readonly")
    prev_btn.config(state="normal")
    next_btn.config(state="normal")
  else:
    subfolder_combo.config(state="disabled")
    prev_btn.config(state="disabled")
    next_btn.config(state="disabled")

  if crossfade_active:
    cf_prev_btn.config(state="normal")
    cf_next_btn.config(state="normal")
  else:
    cf_prev_btn.config(state="disabled")
    cf_next_btn.config(state="disabled")

  c = len(image_data)
  if current_mode == MODE_SUBFOLDERS and subfolder_names:
    if subfolder_combo_idx < len(subfolder_names):
      sf = subfolder_names[subfolder_combo_idx]
      status_label.config(text=f"Subfolder '{sf}': {c} images.")
    else:
      status_label.config(text=f"{c} images in subfolder idx {subfolder_combo_idx}")
  else:
    status_label.config(text=f"{c} images loaded.")

def clear_final_image():
  global final_image, boundary_positions, filenames_at_boundaries
  final_image = None
  boundary_positions = []
  filenames_at_boundaries = []
  redraw()

def redraw(*_):
  if final_image is None:
    display_canvas.delete("all")
    return
  cw = display_canvas.winfo_width()
  ch = display_canvas.winfo_height()
  if cw < 10 or ch < 10:
    return
  display_canvas.delete("all")
  display_canvas.txt_refs = []

  oh, ow, _ = final_image.shape
  scale = cw / ow
  disp_h = int(oh * scale)
  if disp_h > ch:
    scale = ch / oh
    disp_h = ch

  disp_w = int(ow * scale)
  scaled = cv2.resize(final_image, (disp_w, disp_h))
  disp_rgb = cv2.cvtColor(scaled, cv2.COLOR_BGR2RGB)
  pil_img = Image.fromarray(disp_rgb)
  photo_img = ImageTk.PhotoImage(pil_img)
  display_canvas.create_image(0, 0, anchor="nw", image=photo_img)
  display_canvas.image = photo_img

  try:
    font = ImageFont.truetype("arial.ttf", TEXT_FONT_SIZE)
  except:
    font = ImageFont.load_default()

  for idx, (x_off, (fname, is_proxy)) in enumerate(zip(boundary_positions, filenames_at_boundaries)):
    x_scaled = int(x_off * scale)
    if idx == len(boundary_positions) - 1:
      x_scaled = max(0, x_scaled - 40)
    color = (255, 0, 0) if is_proxy else (0, 0, 0)
    tmp = Image.new("RGBA", (1, 1), TEXT_BG_COLOR)
    d = ImageDraw.Draw(tmp)
    bbox = d.textbbox((0, 0), fname, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    box_w = tw + 20
    box_h = th + 20
    timg = Image.new("RGBA", (box_w, box_h), TEXT_BG_COLOR)
    dd = ImageDraw.Draw(timg)
    dd.text((10, 10), fname, font=font, fill=color)
    rot = timg.rotate(90, expand=True)
    rph = ImageTk.PhotoImage(rot)
    y_bottom = ch
    display_canvas.create_image(x_scaled, y_bottom, anchor="sw", image=rph)
    display_canvas.txt_refs.append(rph)

def on_cf_prev():
  global crossfade_index
  crossfade_index -= 1
  if crossfade_index < 0:
    crossfade_index = 0
  show_crossfade_frame()

def on_cf_next():
  global crossfade_index
  crossfade_index += 1
  if crossfade_index >= len(crossfade_frames):
    crossfade_index = len(crossfade_frames) - 1
  show_crossfade_frame()

def show_crossfade_frame():
  global final_image
  if not crossfade_active or not crossfade_frames:
    return
  if crossfade_index < 0 or crossfade_index >= len(crossfade_frames):
    return
  final_image = crossfade_frames[crossfade_index]
  boundary_positions.clear()
  filenames_at_boundaries.clear()
  status_label.config(text=f"Crossfade frame {crossfade_index}/{len(crossfade_frames)-1}")
  redraw()
  update_navigation()

def prev_subfolder():
  global crossfade_active
  if crossfade_active:
    # do nothing or we can just turn it off
    crossfade_active=False
    crossfade_frames.clear()
  idx = subfolder_combo_idx - 1
  if idx < 0:
    return
  subfolder_combo.current(idx)
  load_subfolder_images(idx, auto_calc=True)

def next_subfolder():
  global crossfade_active
  if crossfade_active:
    crossfade_active=False
    crossfade_frames.clear()
  idx = subfolder_combo_idx + 1
  if idx >= len(subfolder_names):
    return
  subfolder_combo.current(idx)
  load_subfolder_images(idx, auto_calc=True)

def on_subfolder_change(evt=None):
  sel = subfolder_combo.get()
  if sel in subfolder_names:
    idx = subfolder_names.index(sel)
    load_subfolder_images(idx, auto_calc=True)

def open_files():
  files = filedialog.askopenfilenames(
    title="Select Images",
    filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif")]
  )
  if not files:
    return
  set_mode(MODE_FILES)
  sorted_files = sorted(files, key=parse_utc_offset)
  parse_image_data_into_checkboxes(sorted_files)
  update_navigation()

def open_single_directory():
  folder = filedialog.askdirectory(title="Select Directory")
  if not folder:
    return
  set_mode(MODE_SINGLE_DIR)
  arr = []
  for it in os.listdir(folder):
    if it.lower().endswith("_fading.png"):
      arr.append(os.path.join(folder, it))
  arr = sorted(arr, key=parse_utc_offset)
  parse_image_data_into_checkboxes(arr)
  update_navigation()

def open_subfolders_directory():
  global subfolder_names, subfolder_data
  folder = filedialog.askdirectory(title="Select Directory (with Subfolders)")
  if not folder:
    return
  set_mode(MODE_SUBFOLDERS)
  subfolder_names.clear()
  subfolder_data.clear()

  subs = []
  for item in os.listdir(folder):
    p = os.path.join(folder, item)
    if os.path.isdir(p):
      subs.append(item)
  subs.sort()

  all_offsets = set()
  for sf in subs:
    sp = os.path.join(folder, sf)
    fl = []
    for it in os.listdir(sp):
      if it.lower().endswith("_fading.png"):
        fl.append(os.path.join(sp, it))
    fl = sorted(fl, key=parse_utc_offset)
    if not fl:
      continue
    offmap = {}
    for fpath in fl:
      off = parse_utc_offset(fpath)
      offmap[off] = (fpath, False)
      all_offsets.add(off)
    subfolder_names.append(sf)
    subfolder_data[sf] = offmap

  if not subfolder_names or not all_offsets:
    status_label.config(text="No suitable subfolders found.")
    return

  all_offsets = sorted(list(all_offsets))
  for i, sf in enumerate(subfolder_names):
    om = subfolder_data[sf]
    new_map = {}
    for off in all_offsets:
      if off in om:
        new_map[off] = om[off]
      else:
        path, _ = fallback_for_offset(i, off)
        new_map[off] = (path, True)
    subfolder_data[sf] = new_map

  subfolder_combo['values'] = subfolder_names
  subfolder_combo.current(0)
  load_subfolder_images(0, auto_calc=False)
  update_navigation()

def parse_image_data_into_checkboxes(files_list):
  for widget in checkbox_frame.winfo_children():
    widget.destroy()
  image_data.clear()

  for c in range(len(files_list)):
    checkbox_frame.grid_columnconfigure(c, weight=1)

  for c, fpath in enumerate(files_list):
    off = parse_utc_offset(fpath)
    img = cv2.imread(fpath)
    br = get_image_brightness(img) if img is not None else 0
    var = tk.BooleanVar(value=True)

    cont = tk.Frame(checkbox_frame, bg=BG_COLOR)
    cont.grid(row=0, column=c, sticky="nsew", padx=5)

    prefix = extract_utc_prefix(fpath)
    lbl1 = tk.Label(cont, text=prefix, bg=BG_COLOR)
    lbl1.pack(side="top", pady=1)

    lbl2 = tk.Label(cont, text=f"({br})", bg=BG_COLOR)
    lbl2.pack(side="top", pady=1)

    chk = tk.Checkbutton(cont, variable=var, bg=BG_COLOR)
    chk.pack(side="top")

    image_data.append((fpath, var, br, off, False))

  status_label.config(text=f"{len(image_data)} images loaded.")

def load_subfolder_images(idx, auto_calc=False):
  global subfolder_combo_idx, crossfade_active
  crossfade_active = False
  crossfade_frames.clear()
  subfolder_combo_idx = idx
  for widget in checkbox_frame.winfo_children():
    widget.destroy()
  image_data.clear()

  if idx>0:
    prev_btn.config(state="normal")
  else:
    prev_btn.config(state="disabled")
  if idx<len(subfolder_names)-1:
    next_btn.config(state="normal")
  else:
    next_btn.config(state="disabled")

  sf = subfolder_names[idx]
  om = subfolder_data[sf]
  offsets_sorted = sorted(om.keys())

  for c in range(len(offsets_sorted)):
    checkbox_frame.grid_columnconfigure(c, weight=1)

  for c, off in enumerate(offsets_sorted):
    (fpath, ispx) = om[off]
    img = cv2.imread(fpath)
    br = get_image_brightness(img) if img is not None else 0
    var = tk.BooleanVar(value=True)

    cont = tk.Frame(checkbox_frame, bg=BG_COLOR)
    cont.grid(row=0, column=c, sticky="nsew", padx=5)

    prefix = extract_utc_prefix(fpath)
    lbl1 = tk.Label(cont, text=prefix, bg=BG_COLOR)
    lbl1.pack(side="top", pady=1)

    lbl2 = tk.Label(cont, text=f"({br})", bg=BG_COLOR)
    lbl2.pack(side="top", pady=1)

    chk = tk.Checkbutton(cont, variable=var, bg=BG_COLOR)
    chk.pack(side="top")

    image_data.append((fpath, var, br, off, ispx))

  update_navigation()
  if auto_calc:
    if brightness_slider.get() > 0:
      filter_button()
    else:
      do_build_fading_core()

def reset_checkboxes():
  for (fp,var,br,off,px) in image_data:
    var.set(True)
  status_label.config(text="All checkboxes enabled.")

def filter_button():
  reset_checkboxes()
  thr = brightness_slider.get()
  for (fp,var,br,off,px) in image_data:
    if br < thr:
      var.set(False)
  status_label.config(text=f"Filtered < {thr}, building fade.")
  do_build_fading_core()

def build_fading():
  global crossfade_active
  crossfade_active=False
  crossfade_frames.clear()
  if current_mode == MODE_SUBFOLDERS and subfolder_names:
    if brightness_slider.get()>0:
      filter_button()
    else:
      do_build_fading_core()
  else:
    do_build_fading_core()
  update_navigation()

def do_build_fading_core():
  global final_image,boundary_positions,filenames_at_boundaries
  active_files=[]
  bright_list=[]
  px_list=[]
  for (fp,var,br,off,px) in image_data:
    if var.get():
      active_files.append(fp)
      bright_list.append(br)
      px_list.append(px)

  if len(active_files)<2:
    status_label.config(text="Not enough checked images.")
    clear_final_image()
    return

  try:
    w=int(width_entry.get())
    h=int(height_entry.get())
  except ValueError:
    status_label.config(text="Width/Height error.")
    return

  final=np.zeros((h,w,3),dtype=np.uint8)
  bounds=[]
  fnames=[]
  t0=time.time()
  cols=[]
  for i,fpath in enumerate(active_files):
    img=cv2.imread(fpath)
    if img is None:
      dummy=np.zeros((10,10,3),dtype=np.uint8)
      ratio=h/10
      new_w=max(1,int(10*ratio))
      resized=cv2.resize(dummy,(new_w,h))
      avg=calculate_horizontal_average(resized)
      cols.append(avg)
    else:
      ratio=h/img.shape[0]
      new_w=max(1,int(img.shape[1]*ratio))
      resized=cv2.resize(img,(new_w,h))
      avg=calculate_horizontal_average(resized)
      cols.append(avg)
  influence=float(influence_slider.get())
  transitions=[]
  n=len(cols)
  for i in range(n-1):
    ab=(bright_list[i]+bright_list[i+1])/2.
    if influence==0:
      wgt=1.0
    else:
      sb=max(1,ab)
      wgt=sb**influence
      if wgt<1e-6:
        wgt=0
    transitions.append(wgt)
  tot_w=sum(transitions)
  if tot_w<=0:
    status_label.config(text="All transitions zero => no fade.")
    clear_final_image()
    return
  x_start=0
  for i in range(n-1):
    w_i=transitions[i]
    fname=os.path.basename(active_files[i])
    is_proxy=px_list[i]
    if w_i<=0:
      bounds.append(x_start)
      fnames.append((fname,is_proxy))
      continue
    frac=w_i/tot_w
    seg_w=int(round(w*frac))
    x_end=x_start+seg_w
    if i==(n-2):
      x_end=w
    if x_end>w:
      x_end=w
    if x_end<=x_start:
      bounds.append(x_start)
      fnames.append((fname,is_proxy))
      continue
    grad=generate_fading_gradient(cols[i],cols[i+1],x_end-x_start)
    final[:,x_start:x_end]=grad
    bounds.append(x_start)
    fnames.append((fname,is_proxy))
    x_start=x_end
  last_fname=os.path.basename(active_files[-1])
  last_is_proxy=px_list[-1]
  bounds.append(w-1)
  fnames.append((last_fname,last_is_proxy))

  global final_image,boundary_positions,filenames_at_boundaries
  final_image=final
  boundary_positions=bounds
  filenames_at_boundaries=fnames
  e=round(time.time()-t0,2)
  status_label.config(text=f"Processing complete in {e}s. Used {len(active_files)} images.")
  redraw()

def build_crossfade_sequence(imgA,imgB,steps):
  frames=[]
  hA,wA,_=imgA.shape
  hB,wB,_=imgB.shape
  if hA!=hB or wA!=wB:
    imgB=cv2.resize(imgB,(wA,hA))
  # first => A => _000
  frames.append(imgA.copy())
  for i in range(1, steps+1):
    alpha=i/(steps+1)
    blend=cv2.addWeighted(imgA,1-alpha,imgB,alpha,0)
    frames.append(blend)
  frames.append(imgB.copy())
  return frames

def export_mpeg_video(frames,name):
  if not frames:
    return
  h,w,_=frames[0].shape
  fourcc=cv2.VideoWriter_fourcc(*'mp4v')
  out=cv2.VideoWriter(name,fourcc,25.0,(w,h),True)
  if not out.isOpened():
    return
  for f in frames:
    out.write(f)
  out.release()

def build_global_subfolder_crossfade():
  # produce frames across all subfolders + crossfades
  all_frames=[]
  # we have two booleans => export_images_var => export_video_var
  # but first let's just build the frames
  n_sub=len(subfolder_names)
  if n_sub<1:
    return []
  # get final image of subfolder 0
  for i in range(n_sub):
    # build fade i
    load_subfolder_images(i, auto_calc=False)
    if brightness_slider.get()>0:
      filter_button()
    else:
      do_build_fading_core()
    if final_image is None:
      continue
    imgA=final_image.copy()
    # add entire subfolder fade as frames?
    if i==0:
      # store subfolder 0 fade as start
      all_frames.append(imgA)
    else:
      # crossfade from last frame in all_frames => new fade
      # last in all_frames => old fade
      prevA=all_frames[-1]  # might or might not be subfolder fade
      steps=intermediate_count.get()
      seq=build_crossfade_sequence(prevA,imgA,steps)
      # seq[0] => old => we already have it
      for idx in range(1,len(seq)):
        all_frames.append(seq[idx])
  return all_frames

def do_build_global_crossfade_view():
  global crossfade_frames,crossfade_active,crossfade_index
  crossfade_frames.clear()
  crossfade_index=0
  crossfade_active=False
  if current_mode!=MODE_SUBFOLDERS or len(subfolder_names)<2:
    status_label.config(text="Crossfade needs multiple subfolders.")
    return
  frames=build_global_subfolder_crossfade()
  if not frames:
    status_label.config(text="No frames built.")
    return
  crossfade_frames.extend(frames)
  crossfade_active=True
  show_crossfade_frame()
  update_navigation()

def on_build_crossfade():
  do_build_global_crossfade_view()

def export_fading():
  outf=get_next_output_subfolder()
  # check booleans => export_images_var => export_video_var
  do_build_fading_core()
  # if subfolder + multiple => we do a single crossfade or single fades
  frames=[]
  if current_mode==MODE_SUBFOLDERS and len(subfolder_names)>1:
    # build crossfade across all subfolders
    frames=build_global_subfolder_crossfade()
    if not frames:
      status_label.config(text=f"Export: no frames built.")
      return
    # if user wants export images
    if export_images_var.get():
      # save frames as _000.png, _001.png, ...
      for i,frm in enumerate(frames):
        cv2.imwrite(os.path.join(outf,f"{i:03d}.png"),frm)
    # if user wants export video
    if export_video_var.get():
      videoname=os.path.join(outf,"all_subfolders_crossfade.mp4")
      export_mpeg_video(frames,videoname)
    status_label.config(text=f"Export done => {outf}")
  else:
    # single fade
    if final_image is None:
      status_label.config(text="No fade to export.")
      return
    single_name=os.path.join(outf,"single_horizontalfading.png")
    if export_images_var.get():
      cv2.imwrite(single_name,final_image)
    if export_video_var.get():
      # single frame => create small 1s video
      frames=[final_image]*25
      videoname=os.path.join(outf,"single_horizontalfading.mp4")
      export_mpeg_video(frames,videoname)
    status_label.config(text=f"Export done => {outf}")

root=tk.Tk()
root.title("Horizontal Fading")
root.configure(bg=BG_COLOR)
root.geometry("1400x750")

top_frame=tk.Frame(root,bg=BG_COLOR)
top_frame.pack(side="top",fill="x",pady=5)

btn_files=tk.Button(top_frame,text="Select Images",command=open_files,bg=BG_COLOR)
btn_files.pack(side="left",padx=5)

btn_single_dir=tk.Button(top_frame,text="Select Directory",command=open_single_directory,bg=BG_COLOR)
btn_single_dir.pack(side="left",padx=5)

btn_subfolders=tk.Button(top_frame,text="Select Dir with Subfolders",command=open_subfolders_directory,bg=BG_COLOR)
btn_subfolders.pack(side="left",padx=5)

prev_btn=tk.Button(top_frame,text="<<",bg=BG_COLOR,command=prev_subfolder)
prev_btn.pack(side="left",padx=5)

subfolder_combo=ttk.Combobox(top_frame,state="disabled")
subfolder_combo.pack(side="left",padx=5)
subfolder_combo.bind("<<ComboboxSelected>>", on_subfolder_change)

next_btn=tk.Button(top_frame,text=">>",bg=BG_COLOR,command=next_subfolder)
next_btn.pack(side="left",padx=5)

tk.Label(top_frame,text="Width:",bg=BG_COLOR).pack(side="left",padx=5)
width_entry=tk.Entry(top_frame,width=6)
width_entry.insert(0,"3840")
width_entry.pack(side="left",padx=5)

tk.Label(top_frame,text="Height:",bg=BG_COLOR).pack(side="left",padx=5)
height_entry=tk.Entry(top_frame,width=6)
height_entry.insert(0,"1080")
height_entry.pack(side="left",padx=5)

calc_btn=tk.Button(top_frame,text="Calculate",command=build_fading,bg=BG_COLOR)
calc_btn.pack(side="left",padx=5)

cf_btn=tk.Button(top_frame,text="Build Crossfade",command=on_build_crossfade,bg=BG_COLOR)
cf_btn.pack(side="left",padx=5)

export_btn=tk.Button(top_frame,text="Export",command=export_fading,bg=BG_COLOR)
export_btn.pack(side="left",padx=5)

tk.Label(top_frame,text="Brightness Filter:",bg=BG_COLOR).pack(side="left",padx=5)
brightness_slider=tk.Scale(top_frame,from_=0,to=255,orient='horizontal',bg=BG_COLOR)
brightness_slider.set(0)
brightness_slider.pack(side="left",padx=5)

filt_btn=tk.Button(top_frame,text="Filter",command=filter_button,bg=BG_COLOR)
filt_btn.pack(side="left",padx=5)

reset_btn=tk.Button(top_frame,text="Reset",command=reset_checkboxes,bg=BG_COLOR)
reset_btn.pack(side="left",padx=5)

tk.Label(top_frame,text="Influence (-10..+10):",bg=BG_COLOR).pack(side="left",padx=5)
influence_slider=tk.Scale(top_frame,from_=-10,to=10,resolution=1,orient='horizontal',bg=BG_COLOR)
influence_slider.set(0)
influence_slider.pack(side="left",padx=5)

# 2 checkboxes => export images, export video
export_images_var=tk.BooleanVar(value=True)
export_video_var=tk.BooleanVar(value=False)

img_chk=tk.Checkbutton(top_frame,text="Export Images",variable=export_images_var,bg=BG_COLOR)
img_chk.pack(side="left",padx=5)

vid_chk=tk.Checkbutton(top_frame,text="Export Video",variable=export_video_var,bg=BG_COLOR)
vid_chk.pack(side="left",padx=5)

int_label=tk.Label(top_frame,text="Steps:",bg=BG_COLOR)
int_label.pack(side="left",padx=2)
intermediate_count=tk.IntVar(value=3)
steps_entry=tk.Entry(top_frame,textvariable=intermediate_count,width=4)
steps_entry.pack(side="left",padx=2)

cf_prev_btn=tk.Button(top_frame,text="CF <<",bg=BG_COLOR,command=on_cf_prev,state="disabled")
cf_prev_btn.pack(side="left",padx=5)

cf_next_btn=tk.Button(top_frame,text="CF >>",bg=BG_COLOR,command=on_cf_next,state="disabled")
cf_next_btn.pack(side="left",padx=5)

status_label=tk.Label(root,text="",fg="blue",bg=BG_COLOR)
status_label.pack(side="top",fill="x")

checkbox_frame=tk.Frame(root,bg=BG_COLOR)
checkbox_frame.pack(side="top",fill="x",pady=5)

display_canvas=tk.Canvas(root,bg=BG_COLOR)
display_canvas.pack(side="top",fill="both",expand=True)
display_canvas.bind("<Configure>",redraw)

root.mainloop()
