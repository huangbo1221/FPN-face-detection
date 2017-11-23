**FPN-face-detection**
========================
This repository contains source files of face detection using the FPN. It is developed based on the [FPN](https://github.com/xmyqsh/FPN) network.

**Requirements**
---------
1、tensorflow
2、For training,you'd better use a GPU

**Installation**
----------------
### 1、Clone this repository to your directory
    git clone --recursive git@github.com:huangbo1221/FPN-face-detection.git

### 2、Download the pre-trained models named [Resnet50.npy](https://pan.baidu.com/s/1gfOYAbD),password:kx45

### 3、Download the [FPN-MODELS](https://pan.baidu.com/s/1eS6JGUQ),password:e67q

**Test**
----------
After downloading the FPN-MODELS, place the weights file in FPN-face-detection/output/FPN_end2end/voc_2007_trainval. You should change some paths in FPN-face-detection/faster_rcnn/test_net.py. This file can use camera to capture your face,produce testing files in FDDB when you change inferences.

**Train**
----------
### 1、prepare training data
I use the wider-face dataset to train this network. Firstly you should transform this dataset to pascal voc dataset style.[Tutorial](http://blog.csdn.net/sinat_30071459/article/details/50723212) can help us a lot.

### 2、Create symlinks for the PASCAL VOC dataset
    ln -s your_Vocdevikit_path VOCdevkit2007

### 3、Run script to train model
    nohup ./experiments/scripts/FPN_end2end.sh 0 FPN pascal_voc2007 --set RNG_SEED 2 TRAIN.SCALES "[800]" > FPN.log 2>&1 &
