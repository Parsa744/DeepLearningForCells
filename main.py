# put sere of photos in standard format for epyseg object detection
# 1. rename
# 2. put in folder

import os
import shutil
import sys
import time

# get the path of the folder
path = os.getcwd()
# get the list of files
files = os.listdir(path)
files = [file for file in files if os.path.splitext(file)[1].lower() in ['.tif','.jpg', '.jpeg', '.png', '.gif']]

# get the number of files
num_files = len(files)

for i in range(num_files):
    if i == 0:
        folder_name = str('handCorrection' )
    else:
        folder_name = str('handCorrection' + str(i))
    os.mkdir(folder_name)

    shutil.move(files[i] , folder_name)

    print('moved file ' + files[i] + ' to folder ' + folder_name)
    os.chdir(folder_name)
    os.rename( files[i], 'handCorrection.tif')
    os.chdir('..')
    print('renamed file ' + files[i] + ' to handCorrection')

