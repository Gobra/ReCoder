import os
import glob
import shutil

#---------------------------------------------
# FileSystem helper
#---------------------------------------------
class FSHelper:
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
        detailed_stats = self.total_image(root_dir, True)

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