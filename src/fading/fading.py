import os
import cv2
import re
import numpy as np
from typing import Tuple, List
from datamodel import SubfolderFadeData, FadeParams
from scipy.interpolate import CubicSpline

class ImageHelper:
  """
  Image-related utility methods (reading, brightness, etc.).
  """

  @staticmethod
  def calculate_brightness(filepath: str, gamma_val: float = 2.0) -> int:
    img = cv2.imread(filepath)
    if img is None:
      return 0
    br = round(np.mean(img))
    eff = (br / 255.0)**gamma_val * 255
    return int(eff)

class FadingLogic:
  """
  Implements fade building and crossfading logic. 
  """

  @staticmethod
  def crossfade_subfolders_onto_writer(
    ui_obj,
    writer: cv2.VideoWriter,
    steps: int,
    progress_bar,
    diag,
    out_folder: str,
    file_tag: str,
    export_images: bool,
    use_spline: bool = True
  ):
    """
    Builds a global crossfade from multiple subfolders. Spline is always "Cubic".
    Export_images is removed from the UI, but we keep a parameter 
    to avoid changing references. We pass 'False' from UI.
    """
    n_sub = len(ui_obj.subfolder_names)
    if n_sub < 2:
      return

    keyframes_data = []
    for i, sf in enumerate(ui_obj.subfolder_names):
      ui_obj._create_subfolder_image_cards(i, auto_calc=False)
      if ui_obj.brightness_slider.get() > 0:
        ui_obj._reset_image_checkboxes()
        thr = ui_obj.brightness_slider.get()
        for d in ui_obj.image_data:
          if d.brightness_value < thr:
            d.check_var.set(False)
      ui_obj._perform_fade_calculation()

      fadeData = ui_obj.subfolder_fade_info.get(sf, None)
      if fadeData is None:
        fadeData = SubfolderFadeData(
          final_image=ui_obj.final_image.copy(),
          boundary_positions=[],
          filenames_at_boundaries=[],
          average_colors=[],
          transitions=[]
        )
      keyframes_data.append(fadeData)

    if len(keyframes_data) < 2:
      return

    keyframe_times = np.linspace(0, 1, len(keyframes_data))
    n_boundaries = len(keyframes_data[0].boundary_positions)

    boundary_splines = None
    if use_spline and n_boundaries > 0:
      boundary_splines = []
      for j in range(n_boundaries):
        positions = [keyframes_data[i].boundary_positions[j] for i in range(len(keyframes_data))]
        spline = CubicSpline(keyframe_times, positions)
        boundary_splines.append(spline)

    total_frames = steps * (len(keyframes_data) - 1)
    h, w, _ = keyframes_data[0].final_image.shape

    for f in range(total_frames + 1):
      t_global = f / total_frames

      if boundary_splines:
        global_boundaries = [int(round(float(spline(t_global)))) for spline in boundary_splines]
      else:
        pos = t_global * (len(keyframes_data) - 1)
        i2 = int(np.floor(pos))
        local_t = pos - i2
        if i2 >= len(keyframes_data) - 1:
          i2 = len(keyframes_data) - 2
          local_t = 1.0
        global_boundaries = []
        for j in range(n_boundaries):
          xA = keyframes_data[i2].boundary_positions[j]
          xB = keyframes_data[i2+1].boundary_positions[j]
          val_j = (1.0 - local_t)*xA + local_t*xB
          global_boundaries.append(int(round(val_j)))

      pos = t_global * (len(keyframes_data) - 1)
      i2 = int(np.floor(pos))
      local_t = pos - i2
      if i2 >= len(keyframes_data) - 1:
        i2 = len(keyframes_data) - 2
        local_t = 1.0
      global_avg_colors = []
      for j in range(n_boundaries):
        colA = keyframes_data[i2].average_colors[j]
        colB = keyframes_data[i2+1].average_colors[j]
        c_mix = np.clip((1.0 - local_t)*colA + local_t*colB, 0,255).astype(np.uint8)
        global_avg_colors.append(c_mix)

      if n_boundaries>0:
        if global_boundaries[0]!=0:
          global_boundaries.insert(0,0)
          global_avg_colors.insert(0, global_avg_colors[0])
        if global_boundaries[-1]!=w:
          global_boundaries.append(w)
          global_avg_colors.append(global_avg_colors[-1])
        # ensure strictly increasing
        for idx2 in range(1,len(global_boundaries)):
          if global_boundaries[idx2]<=global_boundaries[idx2-1]:
            global_boundaries[idx2] = global_boundaries[idx2-1]+1
            if global_boundaries[idx2]>w:
              global_boundaries[idx2] = w

      frame= np.zeros((h,w,3), dtype=np.uint8)
      if len(global_boundaries)>1:
        for j in range(len(global_boundaries)-1):
          x0= global_boundaries[j]
          x1= global_boundaries[j+1]
          seg_w= x1-x0
          if seg_w<1:
            seg_w=1
            x1= min(x0+1, w)
          leftC= global_avg_colors[j].reshape(h,1,3)
          rightC= global_avg_colors[j+1].reshape(h,1,3)
          x_indices= np.linspace(0.0,1.0, seg_w).reshape(1, seg_w,1)
          grad= (1.0- x_indices)* leftC + x_indices* rightC
          if frame[:, x0:x1].shape[1] == grad.shape[1]:
            frame[:, x0:x1] = grad.astype(np.uint8)

      if writer:
        writer.write(frame)
      # export_images is always False now
      progress_bar['value'] = f
      diag.update_idletasks()

  @staticmethod
  def parse_utc_offset(filepath: str) -> float:
    base = os.path.basename(filepath)
    match = re.match(r"^(UTC[+-]\d+(?:\.\d+)?).*", base, re.IGNORECASE)
    if match:
      sub = re.match(r"UTC([+-]\d+(?:\.\d+)?)", match.group(1), re.IGNORECASE)
      if sub:
        try:
          return float(sub.group(1))
        except ValueError:
          pass
    return 9999

  @staticmethod
  def fallback_for_offset(i: int, offset: float, subfolder_names: list, subfolder_data: dict) -> Tuple[str, bool]:
    """
    Returns a fallback image path for a missing offset by looking at neighbors
    or creating a black dummy if none is found.
    """
    if i == 0:
      for k in range(1,len(subfolder_names)):
        om= subfolder_data[subfolder_names[k]]
        if offset in om:
          return om[offset][0], True
      return FadingLogic.create_black_dummy_image(offset), True

    if i == len(subfolder_names)-1:
      for k in range(len(subfolder_names)-2, -1, -1):
        om= subfolder_data[subfolder_names[k]]
        if offset in om:
          return om[offset][0], True
      return FadingLogic.create_black_dummy_image(offset), True

    for k in range(i+1,len(subfolder_names)):
      om= subfolder_data[subfolder_names[k]]
      if offset in om:
        return om[offset][0], True
    for k in range(i-1,-1,-1):
      om= subfolder_data[subfolder_names[k]]
      if offset in om:
        return om[offset][0], True

    return FadingLogic.create_black_dummy_image(offset), True

  @staticmethod
  def get_next_output_subfolder() -> str:
    base = "output"
    if not os.path.exists(base):
      os.makedirs(base)
    i=1
    while True:
      path= os.path.join(base, f"{i:03d}")
      if not os.path.exists(path):
        os.makedirs(path)
        return path
      i+=1

  @staticmethod
  def create_black_dummy_image(offset: float) -> str:
    if not os.path.exists("temp"):
      os.makedirs("temp")
    sign = "+" if offset>=0 else ""
    fname = f"UTC{sign}{offset}_dummy.png"
    path = os.path.join("temp", fname)
    dummy= np.zeros((10,10,3), dtype=np.uint8)
    cv2.imwrite(path, dummy)
    return path

  @staticmethod
  def calculate_horizontal_average(image: np.ndarray) -> np.ndarray:
    return np.mean(image, axis=1).astype(np.uint8)

  @staticmethod
  def build_crossfade_sequence(imgA: np.ndarray, imgB: np.ndarray, steps: int) -> List[np.ndarray]:
    frames= []
    hA,wA,_= imgA.shape
    hB,wB,_= imgB.shape
    if (hA!=hB) or (wA!=wB):
      imgB= cv2.resize(imgB, (wA,hA))
    frames.append(imgA.copy())
    for i in range(1,steps+1):
      alpha= i/(steps+1)
      blend= cv2.addWeighted(imgA, 1.0-alpha, imgB, alpha, 0)
      frames.append(blend)
    frames.append(imgB.copy())
    return frames

  @staticmethod
  def export_mpeg_video(frames: list, filename: str, fps: int=25):
    """
    Exports frames to an MP4. (Unused now, but left for reference.)
    """
    if not frames:
      return
    height, width, _= frames[0].shape
    fourcc= cv2.VideoWriter_fourcc(*'mp4v')
    out= cv2.VideoWriter(filename, fourcc, float(fps), (width, height), True)
    if not out.isOpened():
      return
    for f in frames:
      out.write(f)
    out.release()

  @staticmethod
  def build_fade_core(
      active_paths: List[str],
      brightness_list: List[int],
      proxy_list: List[bool],
      fade_params: FadeParams
    ):
    """
    Single horizontal fade with post-distribution approach.
    """
    if len(active_paths)<2:
      return None

    width_total = fade_params.width
    height_total= fade_params.height
    influence_val= fade_params.influence
    damping_percent= fade_params.damping_percent

    final_result= np.zeros((height_total, width_total,3), dtype=np.uint8)
    bounds= []
    filenames= []
    average_colors= []
    n= len(active_paths)

    # load row-average colors
    loaded_colors= []
    for idx, path in enumerate(active_paths):
      img= cv2.imread(path)
      if img is None:
        dummy= np.zeros((10,10,3), dtype=np.uint8)
        ratio= height_total/10.0
        new_w= max(1,int(10*ratio))
        resized= cv2.resize(dummy,(new_w, height_total))
        avg= FadingLogic.calculate_horizontal_average(resized)
      else:
        ratio= float(height_total)/ float(img.shape[0])
        new_w= max(1,int(img.shape[1]* ratio))
        resized= cv2.resize(img, (new_w, height_total))
        avg= FadingLogic.calculate_horizontal_average(resized)
      loaded_colors.append(avg)

    transitions= []
    original= []
    for i in range(n-1):
      ab= (brightness_list[i]+ brightness_list[i+1])/2.0
      if influence_val==0:
        wgt=1.0
      else:
        safe_bright= max(1, ab)
        wgt= (safe_bright**influence_val)
        if wgt<1e-6:
          wgt=0
      transitions.append(wgt)
      original.append(1.0)

    total_w= sum(transitions)
    if total_w<=0:
      return None

    sum_orig= sum(original)
    seg_widths_float= []
    for i in range(n-1):
      w_i= transitions[i]
      frac_influenced= w_i / total_w
      frac_original= original[i]/ sum_orig

      influenced_width_px= width_total * frac_influenced
      original_width_px= width_total * frac_original
      diff= influenced_width_px- original_width_px
      max_shift= original_width_px*(damping_percent/100.0)

      if abs(diff)> max_shift:
        if diff>0:
          influenced_width_px= original_width_px+ max_shift
        else:
          influenced_width_px= original_width_px- max_shift

      seg_widths_float.append(influenced_width_px)

    # post-distribute
    seg_widths_int= FadingLogic.distribute_segment_widths(seg_widths_float, width_total)

    # paint segments
    x_start=0
    for i in range(n-1):
      segw= seg_widths_int[i]
      fname= os.path.basename(active_paths[i])
      is_proxy= proxy_list[i]

      if segw<=0:
        bounds.append(x_start)
        filenames.append((fname,is_proxy))
        continue

      leftC= loaded_colors[i]
      rightC= loaded_colors[i+1]
      if segw<1:
        segw=1
      x_end= x_start+ segw
      if x_end> width_total:
        x_end= width_total
      seg_w= x_end- x_start
      if seg_w<1:
        bounds.append(x_start)
        filenames.append((fname,is_proxy))
        continue

      x_indices= np.linspace(0.0,1.0, seg_w, dtype=np.float32).reshape(1,seg_w,1)
      leftC_resh= leftC.reshape(height_total,1,3)
      rightC_resh= rightC.reshape(height_total,1,3)
      grad= (1.0- x_indices)* leftC_resh + x_indices* rightC_resh
      grad= grad.astype(np.uint8)

      final_result[:, x_start:x_end]= grad

      bounds.append(x_start)
      filenames.append((fname,is_proxy))
      x_start= x_end

    last_name= os.path.basename(active_paths[-1])
    last_proxy= proxy_list[-1]
    bounds.append(width_total-1)
    filenames.append((last_name, last_proxy))

    return (final_result, bounds, filenames, loaded_colors)

  @staticmethod
  def distribute_segment_widths(w_list: List[float], width_total: int) -> List[int]:
    """
    Takes raw float-based segment widths and ensures they sum to width_total.
    This is approach 3: distributing leftover or scaling down proportionally.

    Returns a list of int widths that sum exactly to width_total.
    """
    sum_w= sum(w_list)
    if sum_w<=0:
      # fallback: everything zero => last segment gets entire width
      out= [0]*(len(w_list)-1)
      out.append(width_total)
      return out

    if abs(sum_w- width_total)< 1e-5:
      w_scaled= w_list[:]
    elif sum_w> width_total:
      # scale down
      factor= width_total/ sum_w
      w_scaled= [wi*factor for wi in w_list]
    else:
      # sum_w < width_total => distribute leftover
      leftover= width_total- sum_w
      w_scaled= [wi + (wi/sum_w)* leftover for wi in w_list]

    # round
    w_int= [int(round(x)) for x in w_scaled]
    diff= width_total- sum(w_int)
    if diff>0:
      idx=0
      while diff>0 and idx< len(w_int):
        w_int[idx]+=1
        diff-=1
        idx+=1
        if idx>= len(w_int):
          idx=0
    elif diff<0:
      diff= abs(diff)
      idx=0
      while diff>0 and idx< len(w_int):
        if w_int[idx]>0:
          w_int[idx]-=1
          diff-=1
        idx+=1
        if idx>= len(w_int):
          idx=0

    return w_int
