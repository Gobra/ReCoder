import os
from app import App

#---------------------------------------------
# Main
#---------------------------------------------
app = App()

# all images -> AVIF, recursive, except those already transcoded
#app.transcode_images_in_directory("/Users/gobra/Desktop/Transcode")

# all videos -> AV1, recursive, except those already transcoded
#app.transcode_movies_in_directory("/Users/gobra/Desktop/Transcode")

# full transfter
app.split_directory("/Volumes/WD_BLACK/Transcode", "/Users/gobra/Desktop/Transcode_Done")