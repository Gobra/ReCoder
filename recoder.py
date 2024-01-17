import os
import glob
import time
import shutil
import subprocess
import threading
import multiprocessing

from concurrent.futures import ThreadPoolExecutor

#---------------------------------------------
# FileSystem helper
#---------------------------------------------
class Files:
    # returns a list of files matching the wildcard
    def files_list(self, root_dir, wildcard, recursive=False):
        search_string = os.path.join(root_dir, wildcard)
        if recursive:
            search_string = os.path.join(root_dir, "**", wildcard)
        files = glob.glob(search_string, recursive=recursive)
        return sorted(files)
    
    # returns a dictionary of all files in the directory with the extension as key,
    # each item is a list of files with the following attributes:
    #   path: full path to the file
    #   ext: extension of the file
    #   size: size of the file in bytes
    def total_image(self, root_dir, recursive=False):
        result = {}
        for filename in self.files_list(root_dir, "*", recursive):
            # ignore directories
            if os.path.isdir(filename):
                continue

            # get file info
            _, extension = os.path.splitext(filename)
            extension = extension.lower()
            item = { "path": filename, "ext": extension, "size": os.path.getsize(filename) }

            # add to result or create new list
            if extension in result:
                result[extension].append(item)
            else:
                result[extension] = [item]
        return result
    
    # returns a list of dictionaries with the following attributes:
    #   ext: extension of the files
    #   files: number of files with the extension
    #   size: total size of all files with the extension in bytes
    def size_per_extension(self, root_dir, recursive=False):
        detailed_stats = helper.total_image(root_dir, True)

        summed_stats = []
        for ext in detailed_stats:
            files = detailed_stats[ext]
            total_size = 0
            for file in files:
                total_size += file["size"]

            # create summed stats
            item = { "ext": ext, "files": len(files), "size": total_size }
            summed_stats.append(item)

        # sort summed stats by size
        summed_stats = sorted(summed_stats, key=lambda d: d['size'], reverse=True)
        return summed_stats
    
    # takes the result of total_image as input, returns plain list of files with the given extensions
    # items in the list have the following attributes:
    #   path: full path to the file
    #   ext: extension of the file
    #   size: size of the file in bytes
    def extract_files(self, total_image, extensions):
        result = []
        for item in extensions:
            ext = item.lower()
            if ext in total_image:
                result += total_image[ext]
        return result
    
    # copies files to a new root directory, preserving the directory structure,
    # input files must be the result of extract_files or same structure
    def transfer(self, files, old_root, new_root, skip_existing=False):
        # create the same directory structure in the new root and copy files
        for file in files:
            path = file["path"]
            if not path.startswith(old_root):
                raise Exception("File '" + path + "' does not start with '" + old_root + "'")

            # get new path
            new_path = path.replace(old_root, new_root)

            # create directory
            new_dir = os.path.dirname(new_path)
            if not os.path.exists(new_dir):
                os.makedirs(new_dir)

            # copy file with overwrite
            print("- Copying '" + path + "' to '" + new_path + "'")
            if not skip_existing or not os.path.exists(new_path):
                shutil.copy2(path, new_path)

#---------------------------------------------
# Video transcoding
#---------------------------------------------
class Video:
    def get_codec_info(self, file_path):
        # get codec information of the video file
        cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.decode().strip()

    def transcode_to_hevc_apple(self, input_path, output_path, quality=65):
        """
        Transcode the video file to HEVC using Apple's hardware encoder.
        :param input_path: Path to the input video file.
        :param output_path: Path for the output video file.
        :param quality: Quality setting for the encoder.
        """
        cmd = [
            "ffmpeg", "-i", input_path, "-c:v", "hevc_videotoolbox", "-q:v", str(quality),
            "-tag:v", "hvc1", "-c:a", "copy", output_path
        ]
        subprocess.run(cmd)

    def transcode_to_av1_svt(self, input_path, output_path, crf=21, row_mt=1, irefresh_type=2, gop_size=30):
        """
        Transcode the video file to AV1 using the SVT-AV1 encoder.
        :param input_path: Path to the input video file.
        :param output_path: Path for the output video file.
        :param crf: Constant Rate Factor for video quality.
        :param row_mt: Row-based multithreading setting (1 for enabled, 0 for disabled).
        :param irefresh_type: Intra refresh type setting for the encoder.
        :param gop_size: Size of the Group of Pictures (GOP).
        """
        cmd = [
            "ffmpeg", "-i", input_path, "-c:v", "libsvtav1", "-crf", str(crf), "-b:v", "0",
            "-g", str(gop_size), "-c:a", "copy", "-row-mt", str(row_mt),
            "-svtav1-params", f"irefresh-type={irefresh_type}", output_path
        ]
        subprocess.run(cmd)

    def transcode_videos(self, video_files, exclude_codecs=["hevc", "av1", "h265", "x265"]):
        # process each video file
        for entry in video_files:
            file_path = entry["path"]
            codec = self.get_codec_info(file_path)

            if codec not in exclude_codecs:
                file_dir, file_name = os.path.split(file_path)
                name, ext = os.path.splitext(file_name)
                new_file_path = os.path.join(file_dir, f"{name}_AV1{ext}")
                
                print(f"Transcoding '{file_name}' to HEVC...")
                self.transcode_to_av1_svt(file_path, new_file_path)
                print(f"Transcoded '{file_name}' to '{new_file_path}'.")

#---------------------------------------------
# Image transcoding
#---------------------------------------------
class Image:
    QUALITY = {'min': '10', 'max': '20', 'speed': '0', 'depth': '10', 'yuv': '444'}
    BALANCED = {'min': '15', 'max': '25', 'speed': '4', 'depth': '8', 'yuv': '420'}
    SPEED = {'min': '20', 'max': '30', 'speed': '8', 'depth': '8', 'yuv': '420'}

    def __init__(self):
        self.counter = TaskCounter(0)

    def transcode_image_to_avif(self, input_path, output_path, params=BALANCED):
        command = ['avifenc']
        for key, value in params.items():
            command.extend(['--' + key, value])
        command.extend([input_path, output_path])
        with open(os.devnull, 'wb') as devnull:
            subprocess.run(command, stdout=devnull, stderr=devnull, check=True)

        self.counter.increment()
        self.counter.report_progress(50)

    def transcode_image(self, entry, params):
        file_path = entry["path"]
        file_dir, file_name = os.path.split(file_path)
        name, ext = os.path.splitext(file_name)
        new_file_path = os.path.join(file_dir, f"{name}.avif")
        
        self.transcode_image_to_avif(file_path, new_file_path, params)

    def transcode_images(self, image_files, threads=multiprocessing.cpu_count(), params=BALANCED):
        # report how many images are being transcoded
        print(f"Transcoding {len(image_files)} images...")

        self.counter.start(len(image_files))
        with ThreadPoolExecutor(max_workers=threads) as executor:
            executor.map(self.transcode_image, image_files, [params] * len(image_files))

#---------------------------------------------
# Task counter and reporter
#---------------------------------------------
class TaskCounter:
    def __init__(self, total, interval=1):
        self.count = 0
        self.total = total
        self.start_time = None
        self.last_report_time = 0
        self.report_interval = interval  # Report interval in seconds
        self.lock = threading.Lock()

    def start(self, total):
        with self.lock:
            self.count = 0
            self.total = total
            self.start_time = time.time()
            self.last_report_time = self.start_time

    def increment(self):
        with self.lock:
            self.count += 1
            current_count = self.count
        return current_count
    
    def progress(self):
        return self.count / self.total
    
    def report_progress(self, max_length):
        """
        Creates a console progress bar.
        
        :param progress: Current progress (between 0 and 1).
        :param max_length: The total length of the progress bar in characters.
        :param file_path: The path of the last file being processed.
        :param max_path_length: Maximum length of the displayed file path.
        """

        current_time = time.time()
        if current_time - self.last_report_time < self.report_interval:
            return
        self.last_report_time = current_time

        # Ensure progress is within bounds
        value = min(max(self.progress(), 0), 1)

        # Calculate the number of '#' characters
        num_hashes = int(value * max_length)

        # Create the bar string
        bar = '#' * num_hashes + '.' * (max_length - num_hashes)

        # Create the progress display string
        time_estimate = self.time_report()
        progress_display = f"[{self.count}/{self.total}] {bar} {value * 100:.2f}% {time_estimate}"

        # Print the progress bar
        print(progress_display, end='\r', flush=True)
    
    def time_report(self):
        with self.lock:
            if self.count == 0:
                return "Estimating time..."
            else:
                elapsed_time = time.time() - self.start_time
                average_time_per_task = elapsed_time / self.count
                remaining_time = average_time_per_task * (self.total - self.count)
                return self.format_time(remaining_time)

    @staticmethod
    def format_time(seconds):
        hours, remainder = divmod(int(seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

#---------------------------------------------
# Aux
#---------------------------------------------
class Transcoder:
    def __init__(self):
        self.imageCodec = Image()
        self.videoCodec = Video()
        self.fs = Files()

    def print_summed_stats(self, stats):
        for item in stats:
            nice_size = round(item["size"] / (1024 * 1024), 2)
            print(item["ext"] + ": " + str(item["files"]) + " files, " + str(nice_size) + " Mb")

    def print_files(self, files):
        for file in files:
            nice_size = round(file["size"] / (1024 * 1024), 2)
            print(file["path"] + ": " + str(nice_size) + " Mb")

    def copy_movies(self, source, destination, extensions):
        print("Scanning '" + source + "':")

        image = self.fs.total_image(source, True)
        movies = self.fs.extract_files(image, extensions)
        self.fs.transfer(movies, source, destination, False)

    def transcode_movies(self, files):
        # transcoded videos will be saved in the same directory as the source file
        # with '_AV1' before the extension, e.g. 'video.mp4' -> 'video_AV1.mp4'
        #
        # hence, filter out files that already have '_AV1' in the same directory
        files = [file for file in files if not os.path.exists(file["path"].replace(file["ext"], "_AV1" + file["ext"]))]

        self.videoCodec.transcode_videos(files)

    def transcode_movies_in_directory(self, dir):
        movie_extensions = [".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".mpg", ".mpeg", ".m4v", ".3gp", ".3g2"]

        image = self.fs.total_image(dir, True)
        movies = self.fs.extract_files(image, movie_extensions)
        self.transcode_movies(movies)

    def transcode_images(self, files, power_factor=1):
        # transcoded images will be saved in the same directory as the source file
        # with '.avif' extension, e.g. 'image.jpg' -> 'image.avif'
        #
        # filter out files that already have '.avif' version in the same directory
        files = [file for file in files if not os.path.exists(file["path"].replace(file["ext"], ".avif"))]
        
        half_power = multiprocessing.cpu_count() * power_factor
        self.imageCodec.transcode_images(files, threads=half_power)

    def transcode_images_in_directory(self, dir):
        image_extensions = [".jpg", ".jpeg", ".png", ".tga", ".bmp", ".gif", ".tiff", ".tif"]

        image = self.fs.total_image(dir, True)
        images = self.fs.extract_files(image, image_extensions)
        self.transcode_images(images)

#---------------------------------------------
# Main
#---------------------------------------------
coder = Transcoder()

# all images -> AVIF, recursive, except those already transcoded
#coder.transcode_images_in_directory("/Users/gobra/Desktop/Transcode")

# all videos -> AV1, recursive, except those already transcoded
coder.transcode_movies_in_directory("/Users/gobra/Desktop/Transcode")