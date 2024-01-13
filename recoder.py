import os
import glob
import shutil
import subprocess

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
        detailed_stats = helper.total_image(source, True)

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

    def transcode_image_to_avif(self, input_path, output_path, params=BALANCED):
        command = ['avifenc']
        for key, value in params.items():
            command.extend(['--' + key, value])
        command.extend([input_path, output_path])
        subprocess.run(command, check=True)

    def transcode_images(self, image_files, params=BALANCED):
        with ThreadPoolExecutor() as executor:
            executor.map(self.transcode_image, image_files, [params] * len(image_files))

    def transcode_image(self, entry, params):
        file_path = entry["path"]
        file_dir, file_name = os.path.split(file_path)
        name, ext = os.path.splitext(file_name)
        new_file_path = os.path.join(file_dir, f"{name}.avif")
        
        print(f"Transcoding '{file_name}' to AVIF...")
        self.transcode_image_to_avif(file_path, new_file_path, params)
        print(f"Transcoded '{file_name}' to '{new_file_path}'.")

#---------------------------------------------
# Aux
#---------------------------------------------
def print_summed_stats(stats):
    for item in stats:
        nice_size = round(item["size"] / (1024 * 1024), 2)
        print(item["ext"] + ": " + str(item["files"]) + " files, " + str(nice_size) + " Mb")

def print_files(files):
    for file in files:
        nice_size = round(file["size"] / (1024 * 1024), 2)
        print(file["path"] + ": " + str(nice_size) + " Mb")

def copy_movies(source, destination, extensions):
    
    print("Scanning '" + source + "':")

    helper = Files()
    image = helper.total_image(source, True)
    movies = helper.extract_files(image, extensions)
    helper.transfer(movies, source, destination, False)

def transcode_movies(files):
    codec = Video()
    codec.transcode_videos(files)

def transcode_images(files):
    codec = Image()
    codec.transcode_images(files)

#---------------------------------------------
# Main
#---------------------------------------------
movie_extensions = [".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".mpg", ".mpeg", ".m4v", ".3gp", ".3g2"]
image_extensions = [".jpg", ".jpeg", ".png", ".tga", ".bmp", ".gif", ".tiff", ".tif"]

# Transcoding video files
#helper = Files()
#image = helper.total_image("/Users/gobra/Desktop/Transcode/Camera", False)
#videos = helper.extract_files(image, movie_extensions) 
#transcode_movies(videos)

# Transcode image files
helper = Files()
image = helper.total_image("/Users/gobra/Desktop/Transcode/Big Photos", False)
images = helper.extract_files(image, image_extensions)
transcode_images(images)