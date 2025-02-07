import os
import cv2
import re
import numpy as np
from typing import Tuple, List
from datamodel import FadeParams
import concurrent.futures
import subprocess
from datetime import datetime
import time

class ImageHelper:
  @staticmethod
  def calculate_brightness(filepath: str, gamma_val: float=2.0) -> int:
    img= cv2.imread(filepath)
    if img is None:
      return 0
    br= round(np.mean(img))
    eff= (br/255.0)**gamma_val*255
    return int(eff)

class FadingLogic:
  """
  Single fade logic + global subfolder approach with frames in batch => partial videos in "output/chunk" => final in "output".
  Also includes optional chunk deletion and logs for chunk building time.
  """

  @staticmethod
  def parse_utc_offset(filepath: str)-> float:
    base= os.path.basename(filepath)
    m= re.match(r"^(UTC[+-]\d+(?:\.\d+)?).*", base, re.IGNORECASE)
    if m:
      s2= re.match(r"UTC([+-]\d+(?:\.\d+)?).*", m.group(1), re.IGNORECASE)
      if s2:
        try:
          return float(s2.group(1))
        except:
          pass
    return 9999

  @staticmethod
  def fallback_for_offset(i: int, offset: float, subfolder_names: list, subfolder_data: dict)-> Tuple[str,bool]:
    if i==0:
      for k in range(1,len(subfolder_names)):
        om= subfolder_data[subfolder_names[k]]
        if offset in om:
          return om[offset][0], True
      return FadingLogic.create_black_dummy_image(offset), True
    if i== len(subfolder_names)-1:
      for k in range(len(subfolder_names)-2, -1, -1):
        om= subfolder_data[subfolder_names[k]]
        if offset in om:
          return om[offset][0], True
      return FadingLogic.create_black_dummy_image(offset), True

    for k in range(i+1, len(subfolder_names)):
      om= subfolder_data[subfolder_names[k]]
      if offset in om:
        return om[offset][0], True
    for k in range(i-1, -1, -1):
      om= subfolder_data[subfolder_names[k]]
      if offset in om:
        return om[offset][0], True
    return FadingLogic.create_black_dummy_image(offset), True

  @staticmethod
  def create_black_dummy_image(offset: float)-> str:
    if not os.path.exists("temp"):
      os.makedirs("temp")
    sign= "+" if offset>=0 else ""
    fname= f"UTC{sign}{offset}_dummy.png"
    path= os.path.join("temp", fname)
    dummy= np.zeros((10,10,3), dtype=np.uint8)
    cv2.imwrite(path, dummy)
    return path

  @staticmethod
  def calculate_horizontal_average(image: np.ndarray)-> np.ndarray:
    return np.mean(image, axis=1).astype(np.uint8)

  @staticmethod
  def build_fade_core(
    active_paths: List[str],
    brightness_list: List[int],
    proxy_list: List[bool],
    fade_params: FadeParams
  ):
    """
    Single horizontal fade => (final_image, boundaries, filenames, average_colors).
    Possibly yields minor dimension mismatch => non-fatal logs.
    """
    if len(active_paths)<2:
      return None
    w_total= fade_params.width
    h_total= fade_params.height
    influence_val= fade_params.influence
    damping_val= fade_params.damping_percent

    final_img= np.zeros((h_total,w_total,3), dtype=np.uint8)
    boundaries=[]
    fnames=[]
    n= len(active_paths)
    loaded_colors= []

    for i,path in enumerate(active_paths):
      img= cv2.imread(path)
      if img is None:
        dummy= np.zeros((10,10,3), dtype=np.uint8)
        ratio= float(h_total)/10.0
        new_w= max(1,int(10* ratio))
        rz= cv2.resize(dummy,(new_w,h_total))
        avg= FadingLogic.calculate_horizontal_average(rz)
      else:
        ratio= float(h_total)/ float(img.shape[0])
        new_w= max(1,int(img.shape[1]* ratio))
        rz= cv2.resize(img,(new_w,h_total))
        avg= FadingLogic.calculate_horizontal_average(rz)
      loaded_colors.append(avg)

    transitions=[]
    original=[]
    for i in range(n-1):
      ab= (brightness_list[i]+ brightness_list[i+1])*0.5
      if influence_val==0:
        wgt=1.0
      else:
        sb= max(1, ab)
        wgt= (sb** influence_val)
        if wgt<1e-6:
          wgt=0
      transitions.append(wgt)
      original.append(1.0)

    sum_w= sum(transitions)
    if sum_w<=0:
      return None
    sum_o= sum(original)

    segw_float=[]
    for i in range(n-1):
      w_i= transitions[i]
      frac_inf= w_i/ sum_w
      frac_ori= original[i]/ sum_o
      infl_w= w_total* frac_inf
      orig_w= w_total* frac_ori
      diff= infl_w- orig_w
      max_sh= orig_w*(damping_val/100.0)
      if abs(diff)> max_sh:
        if diff>0:
          infl_w= orig_w+ max_sh
        else:
          infl_w= orig_w- max_sh
      segw_float.append(infl_w)

    seg_int= FadingLogic.distribute_segment_widths(segw_float, w_total)
    x_start=0
    for i in range(n-1):
      sw_= seg_int[i]
      fname= os.path.basename(active_paths[i])
      px_= proxy_list[i]
      if sw_<=0:
        boundaries.append(x_start)
        fnames.append((fname, px_))
        continue
      leftC= loaded_colors[i]
      rightC= loaded_colors[i+1]
      x_end= x_start+ sw_
      if x_end> w_total:
        x_end= w_total
      seg_w= x_end- x_start
      if seg_w<1:
        boundaries.append(x_start)
        fnames.append((fname, px_))
        continue
      xi= np.linspace(0.0,1.0, seg_w).reshape(1,seg_w,1)
      lc= leftC.reshape(h_total,1,3)
      rc= rightC.reshape(h_total,1,3)
      gd= (1.0- xi)* lc + xi* rc
      gd= gd.astype(np.uint8)
      try:
        final_img[:, x_start:x_start+ seg_w]= gd
      except ValueError as e:
        print(f"[DEBUG] dimension mismatch segment i={i}, error={str(e)}")
      boundaries.append(x_start)
      fnames.append((fname, px_))
      x_start+= seg_w

    lastn= os.path.basename(active_paths[-1])
    lastpx= proxy_list[-1]
    boundaries.append(w_total-1)
    fnames.append((lastn, lastpx))
    return (final_img, boundaries, fnames, loaded_colors)

  @staticmethod
  def distribute_segment_widths(w_list: List[float], width_total: int)-> List[int]:
    sm= sum(w_list)
    if sm<=0:
      out= [0]*(len(w_list)-1)
      out.append(width_total)
      return out
    if abs(sm- width_total)<1e-5:
      w_scaled= w_list[:]
    elif sm> width_total:
      factor= width_total/ sm
      w_scaled= [wi* factor for wi in w_list]
    else:
      leftover= width_total- sm
      w_scaled= [wi + (wi/sm)* leftover for wi in w_list]
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

  @staticmethod
  def build_global_subfolder_spline(subfolder_names: List[str], subfolder_fade_info: dict, steps: int):
    """
    Creates a cubic spline across subfolders => total_frames= steps*(m-1).
    """
    m= len(subfolder_names)
    if m<2:
      return None
    fadeDatas= []
    for sf in subfolder_names:
      fd= subfolder_fade_info.get(sf,None)
      if not fd:
        return None
      fadeDatas.append(fd)
    h,w,_= fadeDatas[0].final_image.shape
    bpos_count= len(fadeDatas[0].boundary_positions)
    if bpos_count<1:
      return None

    keyframe_times= np.linspace(0,1,m)
    boundary_splines_data= []
    for j in range(bpos_count):
      arr_j= []
      for fd in fadeDatas:
        if j< len(fd.boundary_positions):
          arr_j.append(fd.boundary_positions[j])
        else:
          arr_j.append(fd.boundary_positions[-1])
      boundary_splines_data.append(arr_j)

    color_splines_data= []
    for j in range(bpos_count):
      c_list= []
      for fd in fadeDatas:
        if j< len(fd.average_colors):
          c_list.append(fd.average_colors[j])
        else:
          c_list.append(fd.average_colors[-1])
      color_splines_data.append(c_list)

    total_frames= steps*(m-1)
    return (keyframe_times, boundary_splines_data, color_splines_data, w, h, total_frames)

  @staticmethod
  def build_one_frame_global(
    frame_idx: int,
    t_global: float,
    keyframe_times: np.ndarray,
    boundary_splines_data: List[List[float]],
    color_splines_data: List[List[np.ndarray]],
    w: int,
    h: int
  ):
    """
    Worker function for building a single frame from global spline.
    Logs dimension mismatch with [DEBUG], but keeps going.
    """
    from scipy.interpolate import CubicSpline
    n_boundaries= len(boundary_splines_data)
    global_boundaries= []
    for j in range(n_boundaries):
      arr_j= boundary_splines_data[j]
      spl_j= CubicSpline(keyframe_times, arr_j)
      val= float(spl_j(t_global))
      global_boundaries.append(int(round(val)))

    m= len(keyframe_times)
    pos= t_global*(m-1)
    i2= int(np.floor(pos))
    local_t= pos- i2
    if i2>= m-1:
      i2= m-2
      local_t=1.0

    global_avg_colors= []
    for j in range(n_boundaries):
      c_list= color_splines_data[j]
      cA= c_list[i2]
      cB= c_list[i2+1]
      c_mix= np.clip((1.0-local_t)* cA + local_t* cB,0,255).astype(np.uint8)
      global_avg_colors.append(c_mix)

    if n_boundaries>0:
      if global_boundaries[0]!=0:
        global_boundaries.insert(0,0)
        global_avg_colors.insert(0, global_avg_colors[0])
      if global_boundaries[-1]!= w:
        global_boundaries.append(w)
        global_avg_colors.append(global_avg_colors[-1])
      for ix in range(1,len(global_boundaries)):
        if global_boundaries[ix]<= global_boundaries[ix-1]:
          global_boundaries[ix]= global_boundaries[ix-1]+1
          if global_boundaries[ix]> w:
            global_boundaries[ix]= w

    frame= np.zeros((h,w,3), dtype=np.uint8)
    if len(global_boundaries)>1:
      for j in range(len(global_boundaries)-1):
        x0= global_boundaries[j]
        x1= global_boundaries[j+1]
        seg_w= x1- x0
        if seg_w<1:
          seg_w=1
          x1= min(x0+1,w)
        leftC= global_avg_colors[j].reshape(h,1,3)
        rightC= global_avg_colors[j+1].reshape(h,1,3)
        xi= np.linspace(0.0,1.0, seg_w).reshape(1, seg_w,1)
        gd= (1.0- xi)* leftC + xi* rightC
        gd= gd.astype(np.uint8)
        try:
          frame[:, x0:x1]= gd
        except ValueError as e:
          print(f"[DEBUG] Worker error frame {frame_idx}: {e}")
    return (frame_idx, frame, None)

  @staticmethod
  def crossfade_subfolders_onto_writer(
    keyframe_times: np.ndarray,
    boundary_splines_data: List[List[float]],
    color_splines_data: List[List[np.ndarray]],
    w: int,
    h: int,
    total_frames: int,
    fps_val: int,
    frames_per_batch: int,
    worker_count: int,
    ffmpeg_path: str,
    out_folder: str,
    file_tag: str,
    progress_bar,
    diag,
    delete_chunks: bool = True
  ):
    """
    Renders frames => partial .mp4 in 'output/chunk' => merges => final in 'output'.
    Logs chunk start time & chunk duration. On success merges & optionally deletes chunks.
    """
    import math

    chunk_folder= os.path.join(out_folder,"chunk")
    if not os.path.exists(chunk_folder):
      os.makedirs(chunk_folder)

    if progress_bar:
      progress_bar["maximum"] = total_frames+1
      progress_bar["value"] = 0

    tasks= []
    for f_idx in range(total_frames+1):
      t= f_idx/ total_frames
      tasks.append((f_idx,t))

    chunk_paths= []
    start_i=0
    chunk_idx=1
    chunk_total= math.ceil((total_frames+1)/ frames_per_batch)

    while start_i<= total_frames:
      end_i= min(start_i+ frames_per_batch, total_frames+1)
      chunk_name= f"{file_tag}_chunk_{chunk_idx:03d}.mp4"
      chunk_path= os.path.join(chunk_folder, chunk_name)
      chunk_paths.append(chunk_path)

      # logs
      chunk_start_time= time.time()
      print(f"[DEBUG] building chunk {chunk_idx}/{chunk_total}, frames {start_i}..{end_i-1} at {datetime.now().strftime('%H:%M:%S')}")

      subset= tasks[start_i:end_i]
      fourcc= cv2.VideoWriter_fourcc(*'mp4v')
      writer= cv2.VideoWriter(chunk_path, fourcc, float(fps_val), (w,h), True)

      with concurrent.futures.ProcessPoolExecutor(max_workers=worker_count) as executor:
        fut_map= {}
        for (fid,tg) in subset:
          fut= executor.submit(
            FadingLogic.build_one_frame_global,
            fid, tg,
            keyframe_times,
            boundary_splines_data,
            color_splines_data,
            w,h
          )
          fut_map[fut]= fid

        for fut in concurrent.futures.as_completed(fut_map):
          fi= fut_map[fut]
          try:
            (ret_idx, frame, err)= fut.result()
            if err:
              print(f"[DEBUG] Worker error frame {ret_idx}: {err}")
            else:
              if frame is not None:
                writer.write(frame)
          except Exception as exc:
            print(f"[DEBUG] Crash frame {fi}: {exc}")
          if progress_bar:
            progress_bar["value"]+=1
            diag.update_idletasks()

      writer.release()

      chunk_time= time.time()- chunk_start_time
      c_mins= int(chunk_time//60)
      c_secs= int(chunk_time%60)
      if c_mins>0:
        print(f"[DEBUG] chunk {chunk_idx} done in {c_mins}min {c_secs}s.")
      else:
        print(f"[DEBUG] chunk {chunk_idx} done in {c_secs}s.")

      start_i= end_i
      chunk_idx+=1

    now_s= datetime.now().strftime("%Y%m%d_%H%M%S")
    list_path= os.path.join(f"chunk_{now_s}.txt")
    with open(list_path,"w", encoding="utf-8") as f:
      for cpath in chunk_paths:
        f.write(f"file '{cpath}'\n")

    final_mp4= os.path.join(out_folder, f"{file_tag}.mp4")
    cmd= [
      ffmpeg_path,
      "-f","concat",
      "-safe","0",
      "-i", list_path,
      "-c","copy",
      final_mp4
    ]
    print("[MERGE] running:", " ".join(cmd))
    ret= subprocess.run(cmd, check=False)
    if ret.returncode==0:
      print(f"[MERGE] success => {final_mp4}")
      # optional chunk deletion
      if delete_chunks:
        for cp in chunk_paths:
          try:
            os.remove(cp)
          except:
            pass
        try:
          os.remove(list_path)
        except:
          pass
    else:
      print(f"[MERGE] ffmpeg merge failed => code {ret.returncode}")
