import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import time
import concurrent.futures
from collections import deque

from fading import FadingGenerator


def process_one_image(input_path):
    """
    This function runs in a separate process.
    It creates a FadingGenerator, processes the image, and returns a dict.
    """
    start_t = time.perf_counter()
    result_dict = {
        "success": True,
        "error": None,
        "output": None,
        "time": 0.0,
        "input_path": input_path
    }

    try:
        generator = FadingGenerator()
        # Construct output path if needed
        if input_path.endswith("_merge.png"):
            output_path = input_path.replace("_merge.png", "_fading.png")
        else:
            output_path = None

        result_output = generator.create_fading(input_path, output_path)
        result_dict["output"] = result_output

    except Exception as e:
        result_dict["success"] = False
        result_dict["error"] = str(e)

    end_t = time.perf_counter()
    result_dict["time"] = end_t - start_t
    return result_dict


def main():
    root = tk.Tk()
    root.title("Fading Generator (Multiprocessing)")

    frame = tk.Frame(root)
    frame.pack(pady=20, padx=20)

    # Progress bar
    progress_bar = ttk.Progressbar(
        root, orient="horizontal", length=300, mode="determinate")
    progress_bar.pack(pady=5)

    # Status labels
    status_label = tk.Label(
        root, text="Idle", font=("TkDefaultFont", 10, "bold"))
    status_label.pack(pady=5)

    time_label = tk.Label(root, text="", font=("TkDefaultFont", 10))
    time_label.pack(pady=5)

    # A label to show the final result in the main window (no popup)
    final_label = tk.Label(root, text="", font=(
        "TkDefaultFont", 10), fg="blue")
    final_label.pack(pady=5)

    # Detect CPU count
    cpu_count = os.cpu_count() or 1
    default_workers = max(1, cpu_count - 2)

    # Scale (slider) to select number of workers up to CPU count
    worker_count_var = tk.IntVar(value=default_workers)
    tk.Label(frame, text="Number of workers:").pack()
    workers_scale = tk.Scale(
        frame,
        from_=1,
        to=cpu_count,
        orient=tk.HORIZONTAL,
        variable=worker_count_var,
        length=200
    )
    workers_scale.pack(pady=5)

    # Buttons
    load_images_btn = tk.Button(frame, text="Load Images", width=20)
    load_directory_btn = tk.Button(frame, text="Load Directory", width=20)
    quit_btn = tk.Button(frame, text="Quit", width=20)

    load_images_btn.pack(pady=5)
    load_directory_btn.pack(pady=5)
    quit_btn.pack(pady=5)

    # Global references
    futures = []
    executor = None
    results_list = []
    errors_list = []
    all_image_times = []
    last_10_times = deque(maxlen=10)
    input_count = 0
    overall_start_time = 0
    processing_in_progress = False

    # For smoothing the ETA
    smoothed_eta = None
    alpha = 0.3  # smoothing factor

    # This variable will indicate if the user requested to cancel
    canceled = False

    def disable_ui():
        """Disable relevant UI elements (buttons, slider)."""
        load_images_btn.config(state="disabled")
        load_directory_btn.config(state="disabled")
        workers_scale.config(state="disabled")
        quit_btn.config(state="normal")

    def enable_ui():
        """Re-enable relevant UI elements."""
        load_images_btn.config(state="normal")
        load_directory_btn.config(state="normal")
        workers_scale.config(state="normal")
        quit_btn.config(state="disabled")

    def quit_processing():
        """
        Cancel the current batch.
        """
        nonlocal canceled, futures, executor
        if processing_in_progress and executor:
            canceled = True
            # This will (if Python >= 3.9) cancel all not-yet-started tasks
            # and shut down the pool. The ones that are running will be
            # terminated if `cancel_futures=True` is supported.
            executor.shutdown(cancel_futures=True)
            # Clear futures so we don't keep checking them
            futures = []
            status_label.config(text="Canceled by user")
            time_label.config(text="")
            final_label.config(text="")
            progress_bar["value"] = 0
            # Re-enable UI
            enable_ui()

    quit_btn.config(command=quit_processing, state="disabled")

    def process_load_images():
        filetypes = [
            ("Images", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"),
            ("All files", "*.*")
        ]
        input_paths = filedialog.askopenfilenames(
            title="Select images",
            filetypes=filetypes
        )
        if not input_paths:
            messagebox.showinfo("Canceled", "No images selected.")
            return
        process_images_mp(input_paths)

    def process_load_directory():
        directory = filedialog.askdirectory(title="Select directory")
        if not directory:
            messagebox.showinfo("Canceled", "No directory selected.")
            return

        paths = []
        for root_dir, _, files in os.walk(directory):
            for file in files:
                if file.endswith("_merge.png"):
                    paths.append(os.path.join(root_dir, file))

        if not paths:
            messagebox.showinfo(
                "No Files Found", "No *_merge.png files found in the selected directory.")
            return

        process_images_mp(paths)

    load_images_btn.config(command=process_load_images)
    load_directory_btn.config(command=process_load_directory)

    def process_images_mp(input_paths):
        """
        Start a new batch of processing with a new ProcessPoolExecutor.
        """
        nonlocal futures, executor, results_list, errors_list
        nonlocal all_image_times, last_10_times, input_count
        nonlocal overall_start_time, processing_in_progress, canceled
        nonlocal smoothed_eta

        canceled = False
        smoothed_eta = None

        # Clear old data
        futures = []
        results_list = []
        errors_list = []
        all_image_times = []
        last_10_times.clear()

        input_count = len(input_paths)
        progress_bar["maximum"] = input_count
        progress_bar["value"] = 0

        # Clear final_label from any previous run
        final_label.config(text="")

        # Start time for the entire batch
        overall_start_time = time.perf_counter()

        # UI changes
        disable_ui()
        processing_in_progress = True

        # Executor creation
        max_workers = worker_count_var.get()
        status_label.config(text=f"Starting with {max_workers} workers")
        executor = concurrent.futures.ProcessPoolExecutor(
            max_workers=max_workers)

        # Submit tasks
        for path in input_paths:
            f = executor.submit(process_one_image, path)
            futures.append(f)

        status_label.config(text=f"Submitted {input_count} tasks.")
        time_label.config(text="")
        root.update()

        # Start monitoring
        root.after(100, check_futures)

    def check_futures():
        """
        Periodically checks the futures' status.
        If canceled is True, we skip everything.
        """
        nonlocal smoothed_eta, canceled, processing_in_progress

        if canceled:
            # If the user canceled, just exit the loop
            return

        done_count = sum(f.done() for f in futures)
        progress_bar["value"] = done_count

        # Update basic status
        status_label.config(
            text=f"Processing... {done_count}/{input_count} done")

        # Collect results for newly finished futures
        for f in futures:
            if f.done() and not hasattr(f, '_already_handled'):
                setattr(f, '_already_handled', True)
                try:
                    result = f.result()
                    if result["success"]:
                        results_list.append(os.path.basename(result["output"]))
                    else:
                        errors_list.append(
                            f"{os.path.basename(result['input_path'])}: {result['error']}")
                    # Save the time for this image
                    img_time = result["time"]
                    all_image_times.append(img_time)
                    last_10_times.append(img_time)
                except Exception as exc:
                    errors_list.append(str(exc))

        done_count_now = len(all_image_times)
        if done_count_now > 0:
            # Average over last 10 images
            avg10 = sum(last_10_times) / len(last_10_times)
            total_elapsed = time.perf_counter() - overall_start_time
            remaining_images = input_count - done_count_now

            # Raw ETA based on avg of last 10
            if remaining_images > 0:
                raw_eta = avg10 * remaining_images
            else:
                raw_eta = 0

            # Exponential smoothing of ETA
            if smoothed_eta is None:
                smoothed_eta = raw_eta
            else:
                smoothed_eta = alpha * raw_eta + (1 - alpha) * smoothed_eta

            # Show the times in the label
            # Round or int() for seconds
            time_label.config(
                text=f"Avg (last 10): {avg10:.2f}s\n"
                f"Elapsed: {int(total_elapsed)}s, ETA: {int(smoothed_eta)}s"
            )

        # Check if we're done
        if done_count < input_count:
            # Not all done yet
            root.after(100, check_futures)
        else:
            # All done or maybe done
            finish_processing()

    def finish_processing():
        """Called when all tasks are done (success or fail)."""
        nonlocal executor, processing_in_progress

        status_label.config(text="All done")

        # Shut down the executor for this batch
        if executor:
            executor.shutdown(wait=False)

        # Summaries
        final_elapsed = time.perf_counter() - overall_start_time
        done_count_now = len(all_image_times)

        if done_count_now > 0:
            avg_all = sum(all_image_times) / done_count_now
            # Show final info directly in the main window
            final_label.config(
                text=(f"Finished {done_count_now} images.\n"
                      f"Average time per image: {avg_all:.2f}s\n"
                      f"Total time: {int(final_elapsed)}s")
            )
        else:
            final_label.config(text="No images processed (maybe all failed?).")

        # If there were errors
        if errors_list:
            final_label.config(
                text=final_label.cget("text") +
                "\nErrors:\n" + ", ".join(errors_list)
            )

        # Re-enable the UI
        enable_ui()
        processing_in_progress = False

    # Assign commands to the buttons
    load_images_btn.config(command=process_load_images)
    load_directory_btn.config(command=process_load_directory)

    enable_ui()  # make sure everything is enabled at startup

    root.mainloop()


if __name__ == "__main__":
    # Required under Windows for multiprocessing
    main()
