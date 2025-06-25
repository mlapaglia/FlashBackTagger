import os
from tkinter import Tk, Label, Entry, Button, filedialog, Canvas
from PIL import Image, ImageTk
import piexif
import subprocess
import argparse

# Rectangle bounds relative to top-left
RECT_LEFT = 250
RECT_TOP = 50
RECT_RIGHT = 1100
RECT_BOTTOM = 320


class FlashbackTagger:
    def __init__(self, master, folder_path, exclude=None):
        self.master = master
        self.folder_path = folder_path

        self.image_files = sorted([
            f for f in os.listdir(folder_path)
            if f.lower().endswith(('.jpg', '.jpeg', '.tif', '.tiff'))
            and '_original' not in f.lower()
            and (exclude is None or exclude.lower() not in f.lower())
        ])

        self.index = 0

        width = RECT_RIGHT - RECT_LEFT
        height = RECT_BOTTOM - RECT_TOP
        self.canvas = Canvas(master, width=width + 40, height=4 * height + 80)
        self.canvas.pack()

        self.label = Label(master, text="Enter date (MM.DD.YYYY):")
        self.label.pack()

        self.entry = Entry(master)
        self.entry.bind("<Return>", self.handle_return)
        self.entry.pack()

        self.button = Button(master, text="Next", command=self.save_and_next)
        self.button.pack()

        self.tk_crops = []
        self.image = None
        self.display_current_image()
        self.entry.focus_set()

    def crop_rotated_regions(self, image):
        w, h = image.size

        boxes = {
            "Top Left": (RECT_LEFT, RECT_TOP, RECT_RIGHT, RECT_BOTTOM),
            "Top Right": (w - RECT_RIGHT, RECT_TOP, w - RECT_LEFT, RECT_BOTTOM),
            "Bottom Left": (RECT_LEFT, h - RECT_BOTTOM, RECT_RIGHT, h - RECT_TOP),
            "Bottom Right": (w - RECT_RIGHT, h - RECT_BOTTOM, w - RECT_LEFT, h - RECT_TOP),
        }

        rotations = {
            "Top Left": 180,
            "Top Right": 180,
            "Bottom Left": 0,
            "Bottom Right": 0,
        }

        return [image.crop(boxes[k]).rotate(rotations[k], expand=True) for k in boxes]

    def set_tiff_date_with_exiftool(self, filepath, date_str):
        # Convert to EXIF format
        month, day, year = date_str.split('.')
        exif_date = f"{year}:{month.zfill(2)}:{day.zfill(2)} 00:00:00"

        subprocess.run([
            "exiftool",
            f"-DateTimeOriginal={exif_date}",
            f"-CreateDate={exif_date}",
            f"-ModifyDate={exif_date}",
            "-overwrite_original",
            filepath
        ])

    def display_current_image(self, force_show=False):
        if self.index >= len(self.image_files):
            print("All images processed.")
            self.master.quit()
            return

        image_path = os.path.join(self.folder_path, self.image_files[self.index])
        filename = os.path.basename(image_path)
        progress = f"Image {self.index + 1} of {len(self.image_files)}"
        self.master.title(f"FlashbackTagger – {progress} – {filename}")

        date = self.image_has_date(image_path)
        if date and not force_show:
            print(f"Skipping {os.path.basename(image_path)} — Date already set: {date}")
            self.index += 1
            self.display_current_image()
            return

        self.image = Image.open(image_path).copy()

        # Rotate portrait images to landscape
        w, h = self.image.size
        if h > w:
            self.image = self.image.rotate(-90, expand=True)

        crops = self.crop_rotated_regions(self.image)
        self.canvas.delete("all")
        self.tk_crops = [ImageTk.PhotoImage(crop) for crop in crops]

        # Stack vertically
        total_height = sum(img.height() for img in self.tk_crops) + len(self.tk_crops) * 10
        max_width = max(img.width() for img in self.tk_crops) + 20
        self.canvas.config(width=max_width, height=total_height)

        # Ensure window is positioned visibly on screen
        screen_height = self.master.winfo_screenheight()
        screen_width = self.master.winfo_screenwidth()

        window_width = self.canvas.winfo_reqwidth()
        window_height = self.canvas.winfo_reqheight() + 100

        # Cap window height to screen height if needed
        if window_height > screen_height:
            window_height = screen_height - 40
            self.canvas.config(height=window_height)

        # Center horizontally, raise vertically
        x = max(0, (screen_width - window_width) // 2)
        y = max(0, (screen_height - window_height) // 2)

        self.master.geometry(f"+{x}+{y}")

        y_offset = 10
        for crop_img in self.tk_crops:
            self.canvas.create_image(10, y_offset, anchor="nw", image=crop_img)
            y_offset += crop_img.height() + 10

    def save_and_next(self, event=None):
        date_str = self.entry.get().strip()
        image_file = self.image_files[self.index]
        image_path = os.path.join(self.folder_path, image_file)

        if date_str:
            try:
                month, day, year = date_str.split('.')
                exif_date = f"{year}:{month.zfill(2)}:{day.zfill(2)} 00:00:00"
                ext = image_file.lower()

                if ext.endswith((".jpg", ".jpeg")):
                    exif_dict = piexif.load(self.image.info.get("exif", b""))
                    exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = exif_date.encode()
                    exif_dict["0th"][piexif.ImageIFD.DateTime] = exif_date.encode()
                    exif_bytes = piexif.dump(exif_dict)
                    self.image.save(image_path, exif=exif_bytes)
                    print(f"Saved EXIF date to: {image_file}")
                elif ext.endswith((".tif", ".tiff")):
                    self.set_tiff_date_with_exiftool(image_path, date_str)
                    print(f"Set metadata via exiftool for: {image_file}")

            except Exception as e:
                print("Error saving date:", e)

        self.index += 1
        self.entry.delete(0, 'end')
        self.display_current_image()

    def go_back(self, event=None):
        if self.index > 0:
            self.index -= 1
            self.entry.delete(0, 'end')
            self.image = None
            self.display_current_image(force_show=True)
            print(f"Rewound to image: {self.image_files[self.index]}")
        else:
            print("Already at the first image. Cannot go back further.")

    def handle_return(self, event):
        if event.state & 0x0001:  # Shift is held (bitmask)
            self.go_back()
        else:
            self.save_and_next()

    def image_has_date(self, image_path):
        ext = image_path.lower()
        try:
            if ext.endswith((".jpg", ".jpeg")):
                exif_dict = piexif.load(image_path)
                dt_bytes = exif_dict["Exif"].get(piexif.ExifIFD.DateTimeOriginal)
                if dt_bytes:
                    return dt_bytes.decode()
            elif ext.endswith((".tif", ".tiff")):
                # Use exiftool to check metadata
                result = subprocess.run(
                    ["exiftool", "-DateTimeOriginal", "-s3", image_path],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                output = result.stdout.strip()
                if output and not output.startswith("0000"):
                    return output
        except Exception as e:
            print(f"Error checking date on {os.path.basename(image_path)}: {e}")
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FlashbackTagger")
    parser.add_argument("--exclude", help="Substring to exclude from filenames", default=None)
    args = parser.parse_args()

    root = Tk()
    root.title("FlashbackTagger")
    root.lift()
    root.attributes("-topmost", True)
    root.after_idle(root.attributes, "-topmost", False)
    folder = filedialog.askdirectory(title="Select Folder with Photos")
    if folder:
        app = FlashbackTagger(root, folder, exclude=args.exclude)
        root.mainloop()
