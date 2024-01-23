import os
from app import App

#---------------------------------------------
# Main
#---------------------------------------------
converter = App()

# all images -> AVIF, recursive, except those already transcoded
#converter.transcode_images_in_directory("/Users/gobra/Desktop/Transcode")

# all videos -> AV1, recursive, except those already transcoded
converter.transcode_movies_in_directory("/Users/gobra/Desktop/Transcode")

#converter.transcode_movies_in_directory("/Users/gobra/Desktop/Transcode/Babies/From parents/08-09.2016")