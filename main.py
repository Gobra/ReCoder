import os
import multiprocessing

from fshelper import FSHelper
from transcoding import ImageTranscoder, VideoTranscoder

#---------------------------------------------
# Aux
#---------------------------------------------
class Converter:
    def __init__(self):
        self.imageCodec = ImageTranscoder()
        self.videoCodec = VideoTranscoder()
        self.fs = FSHelper()

    def replace_file_extention(self, file_path, ext):
        file_dir, file_name = os.path.split(file_path)
        name, _ = os.path.splitext(file_name)
        return os.path.join(file_dir, f"{name}{ext}")
    
    def add_file_suffix(self, file_path, suffix):
        file_dir, file_name = os.path.split(file_path)
        name, ext = os.path.splitext(file_name)
        return os.path.join(file_dir, f"{name}{suffix}{ext}")

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
        # hence, filter out files that contain '_AV1' suffix or have a copy with '_AV1' siffux in the same directory
        input = files
        files = []
        for file in input:
            recoded_path = self.add_file_suffix(file["path"], "_AV1")
            if "_AV1" not in file["path"] and not os.path.exists(recoded_path):
                files.append(file)

        self.videoCodec.transcode_movies(files)

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
        input = files
        files = []
        for file in input:
            recoded_path = self.replace_file_extention(file["path"], ".avif")
            if not os.path.exists(recoded_path):
                files.append(file)
        
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
converter = Converter()

# all images -> AVIF, recursive, except those already transcoded
converter.transcode_images_in_directory("/Users/gobra/Desktop/Transcode")

# all videos -> AV1, recursive, except those already transcoded
#converter.transcode_movies_in_directory("/Users/gobra/Desktop/Transcode")