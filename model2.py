# -*- coding: utf-8 -*-
"""Seq1.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1vci3HH6FHVVRxxUfAWKIMm2HA450Loi4
"""

import os
import zipfile
from glob import glob
from pathlib import Path

import imageio as imageio
import matplotlib.pyplot as plt
import numpy as np
import requests
import tqdm
import time
import random

import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision
from torch.utils.data import Dataset, DataLoader

from matplotlib import colors
from scipy.optimize import linear_sum_assignment
from skimage.measure import label
from skimage.metrics import contingency_table, peak_signal_noise_ratio
from skimage.segmentation import find_boundaries, watershed
from skimage.util import random_noise

torch.cuda.empty_cache()

# create a root folder where to save the data for this exercise in Kaggle
root_folder = "/"
os.makedirs(root_folder, exist_ok=True)

'''
# importing required modules
from zipfile import ZipFile

# specifying the zip file name
file_name = "dataset_1.zip"

# opening the zip file in READ mode
with ZipFile(file_name, 'r') as zip:
	# printing all the contents of the zip file
	zip.printdir()

	# extracting all the files
	zip.extractall()
 '''
from PIL import Image

def gray(mypath):
# Open the image file
  img = Image.open(mypath)

  # Convert the image to grayscale
  gray_img = img.convert('L')

  # Save the grayscale image to the same file
  gray_img.save(mypath)


# Sampleing 
#mask_paths = random.sample(mask_paths, int(len(mask_paths) * 0.2))
assert len(image_paths) == len(mask_paths)

#print(image_paths)
#print(os.path.join(data_folder, "/Org/", "*.png"))
#for i in image_paths:
#  gray(i)
#for i in mask_paths:
#  gray(i)
def get_random_colors(labels):
    n_labels = len(np.unique(labels)) - 1
    cmap = [[0, 0, 0]] + np.random.rand(n_labels, 3).tolist()
    cmap = colors.ListedColormap(cmap)
    return cmap

def plot_sample(image_path, mask_path):
    image, mask = imageio.imread(image_path), imageio.imread(mask_path)
    fig, ax = plt.subplots(1, 2)
    ax[0].axis("off")
    ax[0].imshow(image, cmap="gray")
    # visualize the masks with random colors
    ax[1].axis("off")
    ax[1].imshow(mask, cmap=get_random_colors(mask), interpolation="nearest")
    plt.show()


device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

class NucleiDataset(Dataset):
    def __init__(self, images, masks, image_transform=None, mask_transform=None, transform=None):
        assert len(images) == len(masks)
        self.images = images
        self.masks = masks
        self.image_transform = image_transform
        self.mask_transform = mask_transform
        self.transform = transform

    def __getitem__(self, index):
        image, mask = self.images[index], self.masks[index]

        # crop the images to have the shape 256 x 256, so that we can feed them into memory
        # despite them having different sizes
        crop_shape = (256, 256)
        shape = image.shape
        if shape != crop_shape:
            assert image.ndim == mask.ndim == 2
            crop_start = [np.random.randint(0, sh - csh) if sh != csh else 0 for sh, csh in zip(shape, crop_shape)]
            crop = tuple(slice(cs, cs + csh) for cs, csh in zip(crop_start, crop_shape))
            image, mask = image[crop], mask[crop]
              
        # apply the transforms if given
        if self.image_transform is not None:
            image = self.image_transform(image)
        if self.mask_transform is not None:
            mask = self.mask_transform(mask)
        if self.transform is not None:
            image, mask = self.transform(image, mask)
        
        # make sure we have numpy arrays and add a channel dimension for the image data
        image, mask = np.array(image), np.array(mask)
        if image.ndim == 2:
            image = image[None]
        return image, mask
        
    def __len__(self):
        return len(self.images)

def msk_transform(mask):
    t = np.array(mask)
    t[t != 0] = 1
    return torch.from_numpy(t).unsqueeze(0)


class DownConv(nn.Module):
    
    def __init__(self, in_channels, out_channels, pooling=True):
        super().__init__()

        self.in_channels = in_channels
        self.out_channels = out_channels
        self.pooling = pooling
        self.conv1 = nn.Conv2d(in_channels, out_channels, 
                               kernel_size=3, stride=1, padding=1, bias=True)
        self.conv2 = nn.Conv2d(out_channels, out_channels, 
                               kernel_size=3, stride=1, padding=1, bias=True)
        if self.pooling:
            self.pool = nn.MaxPool2d(kernel_size=2, stride=2)

    def forward(self, x):
        x = F.relu(self.conv1(x))
        x = F.relu(self.conv2(x))
        before_pool = x
        if self.pooling:
            x = self.pool(x)
        return x, before_pool

    
class UpConv(nn.Module):
    
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.upconv = nn.ConvTranspose2d(self.in_channels, self.out_channels, 
                                         kernel_size=2, stride=2)
        self.conv1 = nn.Conv2d(2*self.out_channels, self.out_channels, 
                                kernel_size=3, stride=1, padding=1, bias=True)
        self.conv2 = nn.Conv2d(self.out_channels, self.out_channels, 
                               kernel_size=3, stride=1, padding=1, bias=True)

    def forward(self, from_down, from_up):
        from_up = self.upconv(from_up)
        x = torch.cat((from_up, from_down), 1)
        x = F.relu(self.conv1(x))
        x = F.relu(self.conv2(x))
        return x

    
class UNet(nn.Module):
    
    def __init__(self, in_channels=1,out_channels=1):
        super().__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.start_filts = 64
        self.depth = 5
        self.down_convs = []
        self.up_convs = []
        
        outs = None
        
        # encoder 
        for i in range(self.depth):
            ins = self.in_channels if i == 0 else outs
            outs = self.start_filts*(2**i)
            pooling = True if i < self.depth-1 else False

            down_conv = DownConv(ins, outs, pooling=pooling)
            self.down_convs.append(down_conv)
            
        # decoder 
        # depth-1 blocks
        for i in range(self.depth-1):
            ins = outs
            outs = ins // 2
            up_conv = UpConv(ins, outs)
            self.up_convs.append(up_conv)
            
        # 1x1 conv
        self.conv_final = nn.Conv2d(outs, self.out_channels, 
                                   kernel_size=1, stride=1)
        
        self.down_convs = nn.ModuleList(self.down_convs)
        self.up_convs = nn.ModuleList(self.up_convs)


    def forward(self, x):
        x = x.float()
        encoder_outs = []
        # encoder
        for i, module in enumerate(self.down_convs):
            x, before_pool = module(x)
            encoder_outs.append(before_pool)
        
        # decoder
        for i, module in enumerate(self.up_convs):
            before_pool = encoder_outs[-(i+2)]
            x = module(before_pool, x)
        
        x = self.conv_final(x)
        return x


def normalize(tensor):
  eps = 1e-6
  normed = tensor.numpy()
  minval = normed.min(axis=(0, 2, 3), keepdims=True)
  normed = normed - minval
  maxval = normed.max(axis=(0, 2, 3), keepdims=True)
  normed = normed / (maxval + eps)
  return torch.from_numpy(normed)

# train the model for one epoch
def train_epoch(model, loader, loss, metric, optimizer):
    model.train()
    for i, (x, y) in enumerate(loader):
        optimizer.zero_grad()
        x, y = x.to(device), y.to(device)
        pred = model(x)
        loss_value = loss(pred, y)
        loss_value.backward()
        optimizer.step()
        if metric is not None:
            metric_value = metric(pred, y)


# validate the model
def validate(model, loader, loss, metric):
    model.eval()
    n_val = len(loader)
    metric_value, loss_value = 0.0, 0.0
    with torch.no_grad():
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            pred = model(x)
            loss_value += loss(pred, y).item()
                metric_value += metric(pred, y).item()
    if n_val == 0 :
      metric_value = 0
      loss_value = 0  
    else:  
      metric_value /= n_val
      loss_value /= n_val    

# run the whole training
def run_training(
    model, train_loader, val_loader, loss, metric, optimizer, n_epochs
):
    epoch_len = len(train_loader)
    step = 0
    for epoch in tqdm.trange(n_epochs):
        train_epoch(model, train_loader, loss, metric, optimizer)
        step = epoch_len * (epoch + 1)
        validate(model, val_loader, loss, metric)

loss = nn.BCEWithLogitsLoss()

# TODO implement the dice score as a function.
# HINTS: 
# - for later parts of this exercises, you should implement it in such a way that
# the function can compute the dice score for input and target with multiple channels,
# and so that it is computed independently per channel and the channel average is returned
# - since we don't have an activation in the U-Net you need to bring the predictions in range [0, 1] using torch.sigmoid
# - the dice score can be formulated for continuous predictions in [0, 1]; DO NOT threshold the predictions

def dice_score(input_, target, multiclass=False):
    if multiclass:
        input_ = input_.flatten(0, 1)
        target = target.flatten(0, 1)
        
    epsilon = 1e-6
    sum_dim = (-1, -2)

    inter = 2 * (input_ * target).sum(dim=sum_dim)
    sets_sum = input_.sum(dim=sum_dim) + target.sum(dim=sum_dim)

    dice = (inter + epsilon) / (sets_sum + epsilon)
    return dice.mean()


def precision(tp, fp, fn):
    return tp / (tp + fp) if tp > 0 else 0


def compute_ious(seg, mask):
    overlap = contingency_table(seg, mask).toarray()
    n_pixels_pred = np.sum(overlap, axis=0, keepdims=True)
    n_pixels_true = np.sum(overlap, axis=1, keepdims=True)
    eps = 1e-7
    ious = overlap / np.maximum(n_pixels_pred + n_pixels_true - overlap, eps)
    # ignore matches with zero (= background)
    ious = ious[1:, 1:]
    n_pred, n_true = ious.shape
    n_matched = min(n_pred, n_true)
    return n_true, n_matched, n_pred, ious

    
def compute_tps(ious, n_matched, threshold):
    not_trivial = n_matched > 0 and np.any(ious >= threshold)
    if not_trivial:
        # compute optimal matching with iou scores as tie-breaker
        costs = -(ious >= threshold).astype(float) - ious / (2*n_matched)
        pred_ind, true_ind = linear_sum_assignment(costs)
        assert n_matched == len(true_ind) == len(pred_ind)
        match_ok = ious[pred_ind, true_ind] >= threshold
        tp = np.count_nonzero(match_ok)
    else:
        tp = 0
    return tp


def intersection_over_union(seg, mask, threshold=0.5):
    if seg.sum() == 0:
        return 0.0
    n_true, n_matched, n_pred, ious = compute_ious(seg, mask)
    tp = compute_tps(ious, n_matched, threshold)
    fp = n_pred - tp
    fn = n_true - tp
    ap = precision(tp, fp, fn)
    return ap






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