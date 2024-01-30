import os
import multiprocessing

from consoleutils import ConsoleUtils
from concurrent.futures import ThreadPoolExecutor

from fshelper import FSHelper
from taskcounter import TaskCounter
from transcoding import ImageTranscoder, VideoTranscoder

#---------------------------------------------
# Aux
#---------------------------------------------
class App:
    IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".tga", ".bmp", ".gif", ".tiff", ".tif"]
    MOVIE_EXTENSIONS = [".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".mpg", ".mpeg", ".m4v", ".3gp", ".3g2"]

    def __init__(self):
        self.imageCodec = ImageTranscoder()
        self.videoCodec = VideoTranscoder()
        self.fs = FSHelper()

    def print_summed_stats(self, stats):
        for item in stats:
            nice_size = round(item["size"] / (1024 * 1024), 2)
            print(item["ext"] + ": " + str(item["files"]) + " files, " + str(nice_size) + " Mb")

    def print_files(self, files):
        for file in files:
            nice_size = round(file["size"] / (1024 * 1024), 2)
            print(file["path"] + ": " + str(nice_size) + " Mb")

    def copy_files(self, source, destination, extensions):
        print("Scanning '" + source + "':")

        image = self.fs.total_image(source, True)
        movies = self.fs.extract_files(image, extensions)
        self.fs.transfer(movies, source, destination, False)

    def _video_codec_requires_transcoding(self, codec):
        return codec != "av1" and codec != "hevc"

    def _preprocess_movie_file(self, file, counter):
        file_path = file["path"]
        duration = None

        # report progress
        report = [file_path]
        counter.increment()
        counter.report_progress(50, custom_strings=report)

        # A. file is already transcoded
        if "_AV1" in file_path:
            return (None, duration, 'already transcoded')

        # check if there's a transcoded version of the file
        recoded_path = VideoTranscoder.transcoded_movie_path(file_path)
        if os.path.exists(recoded_path):
            valid, duration = self.videoCodec.check_transcoding_validity(file_path, recoded_path)
            if not valid:
                os.remove(recoded_path)

        # B. file is not transcoded, but there's a transcoded version
        if os.path.exists(recoded_path):
            return (None, duration, 'transcoded version exists and is valid')

        codec = self.videoCodec.get_video_info(file_path)['video_codec']
        if self._video_codec_requires_transcoding(codec):
            if duration is None:
                duration = self.videoCodec.get_video_info(file_path)['duration']

            # C. file is not transcoded, there's no transcoded version, and it's not AV1 or HEVC
            return (file, duration, 'OK')

        # D. file is not transcoded, there's no transcoded version, and it's AV1 or HEVC already
        return (None, None, 'already AV1 or HEVC')

    def transcode_movies(self, files):
        # Transcoded videos will be saved in the same directory as the source file
        # with '_AV1' before the extension, e.g. 'video.mp4' -> 'video_AV1.mp4'
        #
        # hence, filter out files that contain '_AV1' suffix or have a copy with '_AV1' siffux in the same directory
        print(f"Scanning {len(files)} video files:")

        # initialize TaskCounter
        counter = TaskCounter(0.1)
        counter.start(len(files))

        # test, get info about the first file
        file = files[0]
        file_path = file["path"]

        # process files using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda file: self._preprocess_movie_file(file, counter), files))

        # summarize results
        valid_files = []
        total_duration = 0.0
        for (file, duration, reason) in results:
            if file is not None:
                valid_files.append(file)
                total_duration += duration

        # clear console
        print(ConsoleUtils.UP, end="", flush=True)
        ConsoleUtils.clear_lines(3)

        # transcode valid files
        self.videoCodec.transcode_movies(valid_files, total_duration)

    def transcode_movies_in_directory(self, dir):
        image = self.fs.total_image(dir, True)
        movies = self.fs.extract_files(image, App.MOVIE_EXTENSIONS)
        self.transcode_movies(movies)

    def transcode_images(self, files, power_factor=1):
        # transcoded images will be saved in the same directory as the source file
        # with '.avif' extension, e.g. 'image.jpg' -> 'image.avif'
        #
        # filter out files that already have '.avif' version in the same directory
        input = files
        files = []
        for file in input:
            recoded_path = FSHelper.replace_file_extention(file["path"], ".avif")
            if not os.path.exists(recoded_path):
                files.append(file)
        
        half_power = multiprocessing.cpu_count() * power_factor
        self.imageCodec.transcode_images(files, threads=half_power)

    def transcode_images_in_directory(self, dir):
        image = self.fs.total_image(dir, True)
        images = self.fs.extract_files(image, App.IMAGE_EXTENSIONS)
        self.transcode_images(images)

    # Splits processed directory into the new destination, producing:
    # - directory with all images transcoded to AVIF
    # - directory with all movies transcoded to AV1 or those that were already AV1 or HEVC
    # - directory with all all source files, without transcoded versions
    # - directory with all files that were not processed
    def split_directory(self, source, destination):
        total_image = self.fs.total_image(source, True)
        everything = self.fs.extract_files(total_image, [])

        # create destination directories
        dir_sources = os.path.join(destination, "Source")
        dir_transcoded = os.path.join(destination, "Transcoded")
        dir_unknown = os.path.join(destination, "Unknown")

        os.makedirs(destination, exist_ok=True)
        os.makedirs(dir_sources, exist_ok=True)
        os.makedirs(dir_transcoded, exist_ok=True)
        os.makedirs(dir_unknown, exist_ok=True)

        # A. images are simple, every .avif and .heic is a transcoded image,
        # everything rest is 'source'
        # B. movies are more complicated, we need to check if they are already transcoded
        # by checking the codec
        print(f"\Transferring {len(everything)} files:")
        
        counter = TaskCounter(0.1)
        counter.start(len(everything))

        # process files using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as executor:
            executor.map(lambda file: self._move_single_split_file(file, source, dir_sources, dir_transcoded, dir_unknown, counter), everything)

    # process split files using ThreadPoolExecutor
    def _move_single_split_file(self, file, source, dir_sources, dir_transcoded, dir_unknown, counter):
        EFF_IMAGES = [".avif", ".heic"]

        ext = file["ext"].lower()
        target_dir = None

        # new images
        if ext in EFF_IMAGES:
            target_dir = dir_transcoded
        # old images, source ones
        elif ext in App.IMAGE_EXTENSIONS:
            target_dir = dir_sources
        # movies
        elif ext in App.MOVIE_EXTENSIONS:
            codec = self.videoCodec.get_video_info(file["path"])["video_codec"]
            if self._video_codec_requires_transcoding(codec):
                target_dir = dir_sources
            else:
                target_dir = dir_transcoded
        # unknown
        else:
            target_dir = dir_unknown

        # move file
        self.fs.transfer_file(file, source, target_dir, skip_existing=False, erase_original=False)

        # report progress
        report = [file["path"]]
        counter.increment()
        counter.report_progress(50, custom_strings=report)
            
        