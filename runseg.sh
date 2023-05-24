#!/bin/bash

#SBATCH -A all
#SBATCH -p gpu
#SBATCH -C scratch
#SBATCH -N 1
#SBATCH -n 10
#SBATCH -G gtx1080:2
#SBATCH -o /scratch/users/hariri/output1.%J
#SBATCH -c 1
#SBATCH --mail-type=BIGIN,END
#SBATCH -t 2-00:00
#SBATCH --mail-user=parsahariri@gmail.com


#Run Python script
export PATH=$PATH:/bin/../loadModules.sh

module load anaconda3

source activate DeepLearningModel1

python seg1.py
