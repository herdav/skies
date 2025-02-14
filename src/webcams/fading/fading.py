from PIL import Image
import numpy as np


class FadingGenerator:
    def create_fading(self, input_path, output_path=None):
        # Open image and convert to RGB
        orig = Image.open(input_path).convert("RGB")
        w, h = orig.size

        # Convert to NumPy array
        orig_np = np.array(orig)  # shape: (h, w, 3)

        # Define fade width
        fade_w = 100

        # Create a fade array initialized with white (255,255,255)
        fade_np = np.full((h, fade_w, 3), 255, dtype=np.uint8)

        # Variables to store first and last row that is not completely white
        min_y, max_y = -1, -1

        # Process each row and compute the average color of non-white pixels
        for y in range(h):
            row = orig_np[y]  # shape: (w, 3)
            mask = ~((row[:, 0] == 255) & (
                row[:, 1] == 255) & (row[:, 2] == 255))
            valid_pixels = row[mask]

            if len(valid_pixels) > 0:
                avg_color = valid_pixels.mean(axis=0)
                avg_color = avg_color.astype(np.uint8)
            else:
                avg_color = np.array([255, 255, 255], dtype=np.uint8)

            # Update min_y and max_y if row is not all white
            if not np.array_equal(avg_color, [255, 255, 255]):
                if min_y < 0:
                    min_y = y
                max_y = y

            # Fill the current row in fade_np
            fade_np[y, :, :] = avg_color

        # Convert fade_np back to a PIL image
        fade_img = Image.fromarray(fade_np, 'RGB')

        # Crop if there is any non-white row, otherwise use the entire fade_img
        if min_y == -1:
            # Entire image is white
            cropped_img = fade_img
        else:
            cropped_img = fade_img.crop((0, min_y, fade_w, max_y + 1))

        # Resize to height 2180
        fade_resized_2180 = cropped_img.resize((fade_w, 2180), Image.LANCZOS)

        # Cut off the bottom 20 pixels
        # -> final height = 2180 - 20 = 2160
        final_height = 2180 - 20
        if final_height < 0:
            final_height = 0  # Safety check
        fade_final = fade_resized_2180.crop((0, 0, fade_w, final_height))

        # Determine output path if not provided
        if not output_path:
            dot_index = input_path.rfind(".")
            if dot_index == -1:
                output_path = input_path + "_fading"
            else:
                output_path = input_path[:dot_index] + \
                    "_fading" + input_path[dot_index:]

        # Save the final image
        fade_final.save(output_path)
        return output_path
