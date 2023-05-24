import torch
import numpy as np
from glob import glob
import matplotlib.pyplot as plt
from pathlib import Path
from zipfile import ZipFile
from seg1 import UNet
  
# Model class must be defined somewhere
model = torch.load('model.pth')
unet_model = UNet()
unet_model.load_state_dict(model)

unet_model.eval()

file_name = "realWorldData.zip"

# opening the zip file in READ mode
with ZipFile(file_name, 'r') as zipp:
        # printing all the contents of the zipp file
        zipp.printdir()

        # extracting all the files
        zipp.extractall()
reall_test = glob(os.path.join("realWorldData/", "*.png"))
reall_test.sort()
for i in reall_test:
  gray(i)
print(len(reall_test))
imgs = [imageio.imread(i) for i in  reall_test]

ims_flat = np.concatenate([im.ravel() for im in imgs])
mean, std = np.mean(ims_flat), np.std(ims_flat)
test_images = [(im.astype("float32") - mean) / std for im in imgs]
print((test_images[0]))
# check out instance segmentation for a few test images
#from zipfile import ZipFile as zip
counter = 0
from builtins import zip
zipped = list(zip(test_images, test_masks))

with torch.no_grad():
    for im, mask in zip(test_images, test_masks):
        # predict with the model and apply sigmoid to map the prediction to the range [0, 1]
        pred = unet_model(torch.from_numpy(im[None, None]).to(device))
        pred = torch.sigmoid(pred).cpu().numpy().squeeze()
        # get tbe nucleus instance segmentation by applying connected components to the binarized prediction
        nuclei = label(pred > 0.5)
        fig, ax = plt.subplots(1, 4, figsize=(16, 16))
        ax[0].axis("off")
        ax[0].imshow(im, cmap="gray")
        ax[1].axis("off")
        #ax[1].imshow(mask, cmap=get_random_colors(mask), interpolation="nearest")
        ax[2].axis("off")
        ax[2].imshow(pred, cmap="gray")
        ax[3].axis("off")
        ax[3].imshow(nuclei, cmap=get_random_colors(nuclei), interpolation="nearest")
        plt.savefig('realWorld'+str(format(int(time.time())))+'.png', dpi=600, bbox_inches='tight')
        plt.show()

        counter += 1

end_time = time.time()
runtime = end_time - start_time

