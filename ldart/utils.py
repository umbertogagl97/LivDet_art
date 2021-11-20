#----------------------------------------------------library

import torch
import numpy as np
import cv2
from google.colab.patches import cv2_imshow
import torch.nn as nn
import pandas as pd
import matplotlib.pyplot as plt
from art.utils import to_categorical
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True
import random
from torchvision import datasets, models, transforms
from typing import Optional

import torch.optim as optim

import torchvision

#import time
#import os
#import shutil
#import copy


import sys

from torchvision.transforms.functional import InterpolationMode

#from torch.utils.data import TensorDataset, DataLoader


#----------------------------------------------------------------transforms

data_transform_test= transforms.Compose([transforms.Resize([224,224],interpolation=InterpolationMode.NEAREST),
          transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
          ])
transf_resize=transforms.Resize([224,224],interpolation=InterpolationMode.NEAREST)

transf_load= transforms.Compose([transforms.ToTensor(),
                                 #transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
          ])
trans_norm=transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])

#--------------------------------------------------------------functions

def compute_transf_init(size_init):
  return transforms.Resize(size=(size_init[0],size_init[1]),interpolation=InterpolationMode.NEAREST)


def enhanc(img,mask,size_out : Optional[int]=0): 
  '''
  img: ndarray 1x3xnxm
  mask: ndarray nxm (same dim of size_out)
  size_out: (int) effettua un resize dell'immagine prima dell'enhancement (se 0 dà in uscita l'img con le stesse dim dell'input)
  return: img_en 1x3xnxm
  '''

  from FingerprintImageEnhancer import *

  res=False
  #res=True
  r, g, b = img[0,0,:,:],img[0,1,:,:],img[0,2,:,:]
  img_g = 0.2989 * r + 0.5870 * g + 0.1140 * b
  size_init=img_g.shape
  #img_g=img_g.astype('float32')
  finger_en=FingerprintImageEnhancer()
  #img=img[0].transpose(1,2,0)
  if size_out==0: #se non voglio una dimensione specifica in uscita trasformo l'img finale con le dim iniziali
    if size_init[0]<350: res=True
    out,failed = finger_en.enhance(img=img_g,resize=res,size=350)
    if res:
      out = cv2.resize(np.array(out), (size_init[0],size_init[1]),interpolation=cv2.INTER_NEAREST)
  else:
    #inserire controllo se size_out<350
    res=True
    out,failed = finger_en.enhance(img=img_g,resize=res,size=size_out)

  size_out=out.shape[0]
  if failed==False:
    out=1-out
    img=np.zeros([1,3,size_out,size_out])#size_init[0],size_init[1]])
    for i in range(3):
      img[0,i,:,:]=out
    img=np.where(mask == 0.0, 1, img)
  else: 
    print("failed enhanc")

  return img


def compute_mask(img,n_contours=3):
  '''
  img: tensor 1x3xnxm
  n_contours: numero di contorni da tracciare nel passo intermedio (consigliati: 3 per img 224x224, 6 per img 500x500)
  '''
  #img iniziale [0,1]
  img=np.array(img[0])
  img=img.transpose(1,2,0)

  #trasforma in gray
  r, g, b = img[:,:,0], img[:,:,1], img[:,:,2]
  gray = 0.2989 * r + 0.5870 * g + 0.1140 * b
  #scala in [0,255]
  gray = (gray - np.min(gray)) / (np.max(gray) - np.min(gray))
  gray=gray*255
  gray=gray.astype('uint8')
  #cv2_imshow(gray)
  #calcola immagine binaria
  ret, imgf = cv2.threshold(gray, 0,255, cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)

  image_contours = np.zeros((imgf.shape[1],
                            imgf.shape[0]),
                            np.uint8)

  image_binary = np.zeros((imgf.shape[1],
                          imgf.shape[0]),
                          np.uint8)

  #cerca i contorni nell'immagine binaria
  contours =cv2.findContours(imgf, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)[0]
  cv2.drawContours(image_contours,
                      contours, -1,
                      (255,255), n_contours)
  #cv2_imshow(image_contours)
  contours = cv2.findContours(image_contours, cv2.RETR_LIST,
                            cv2.CHAIN_APPROX_SIMPLE)[0]
  #disegna solo il contorno più esterno
  cv2.drawContours(image_binary, [max(contours, key = cv2.contourArea)],
                  -1, (255, 255),-1)
  #restituisce immagine [0,1]
  return image_binary/255


def test_average(classifier,input,transf_init):
  '''
  classifier: model trained
  test_loader: dataloader
  transf_init: resize immagine a risoluzione originale
  return: pred: classe predetta, probabilities, values
  '''
  import torch.nn as nn
  import pandas as pd

  def calc_size(n):
    '''
    n: int 
    return: 80% of n
    '''
    return tuple(int(np.ceil(i * (80/100))) for i in n)
  
  preds=[]
  #value=[]
  prob=nn.Softmax(dim=0)
  
  if input.shape[2]==224:
    input=transf_init(input)

  n=input.shape
  n_mod=calc_size(n[2:4])
  crop_transform=transforms.TenCrop((n_mod[0],n_mod[1]))
  crops=crop_transform(input)
  live=0
  spoof=0
  for crop in crops:
    crop=data_transform_test(crop) #resize 224
    outputs = classifier.predict(crop)
    live+=outputs[0][0]
    spoof+=outputs[0][1]
  live=live/10
  spoof=spoof/10
  values=[live,spoof]
  predicted=np.argmax(values)
  probabilities=prob(torch.Tensor(values)).numpy()

  return predicted,probabilities,values


def compute_perturb(x,x_adv,transf_init):
  '''
    x: img originali
    x_adv: img contraddittorie
    return: pertubazioni
  '''
  #calcola la perturbazione con img 224x224
  if x_adv.shape[2]==224:
    x=np.array(transf_resize(torch.Tensor(x)))
  perturb=x_adv-x
  
  perturb=np.array(transf_init(torch.Tensor(perturb)))
  
  return perturb


def print_subplot(perturb,x_test,y_test,preds,x_test_adv,value_preds_adv):
  '''
    perturb: perturbazioni
    x_test: img originali
    y_test: classi originali
    preds: classi predette per img originali
    x_test_adv: img contraddittoria
    value_preds_adv: probabilità predette img contraddittorie
    normalize: se True normalizza le immagini
  '''
  import matplotlib.pyplot as plt

  classes_name=['Live','Spoof']
  #nel seguente ciclo for si crea un vettore delle classi predette ordinato per probabilità decrescente
  for i in range(len(x_test)):#(x_test.shape[0]):
    value=value_preds_adv[i]*100
    value_sorted=sorted(value,reverse=True)
    classes=[]
    for j in range(value.size) :
      ind=np.where(value==value_sorted[j]) #restituisce l'indice in value del valore uguale a value_sorted[i], quindi è la classe
      classes.append(classes_name[ind[0][0]]) #classes è il vettore finale
    
    value_sorted=[ round(elem, 2) for elem in value_sorted ]

    val_pert=np.mean(np.abs(perturb[i]))
    pert_min,pert_max=np.min(perturb[i]),np.max(perturb[i])
    #perturb,val_pert,perturb_norm=compute_perturb(x_test,x_test_adv)
    perturb[i]=np.clip(perturb[i],0,1) #rimuovo i valori negativi poiché non posso visualizzarli
    #in seguito per ogni immagine del test set si stampa un subplot
    fig = plt.figure(figsize=[20,20])
    #plt.subplots_adjust(wspace=0.9)
    print('\033[1m'+"IMMAGINE "+'\033[1m',i) #valore END: '\033[0m'
    #originale
    ax1 = fig.add_subplot(131) #subplot con 3 righe e due colonne
    ax1.axis('off')
    #ax1.imshow(cv2.rotate(x_test[i],cv2.cv2.ROTATE_90_CLOCKWISE))
    ax1.imshow(x_test[i].transpose(1,2,0))
    ax1.title.set_text("ORIGINALE\nclasse reale: "+classes_name[np.argmax(y_test[i])]+"\nclasse predetta: "+str(preds[i]))
    #perturbazione
    ax2 = fig.add_subplot(132)
    #ax2.imshow(cv2.rotate(perturb_norm[i],cv2.cv2.ROTATE_90_CLOCKWISE))
    ax2.imshow(perturb[i].transpose(1,2,0),cmap='gray')
    #ax2.imshow(perturb[i],cmap='gray')
    ax2.axis('off')
    ax2.title.set_text("PERTURBAZIONE\nvalore medio: "+str(round(val_pert,4))+"\nmin: "+str(pert_min)+"\nmax: "+str(pert_max))
    #perturbata
    ax3 = fig.add_subplot(133)
    #ax3.imshow(cv2.rotate(x_test_adv[i],cv2.cv2.ROTATE_90_CLOCKWISE))#,aspect='auto')
    ax3.imshow(x_test_adv[i].transpose(1,2,0))
    ax3.axis('off')
    ax3.title.set_text("PERTURBATA\nclassi predette: "+str(classes)+"\ncon valori: "+str(value_sorted))
    plt.show()
          

def save_read(x,classifier,transf_init):
  print("valori img originale:")
  _,p,_=test_average(classifier,torch.Tensor(x).unsqueeze_(0),transf_init)
  print(p)
  x=x.transpose(1,2,0)*255
  #plt.imsave('prova.bmp',x)
  cv2.imwrite('prova.png',x)
  #plt.imshow(x)
  #cv2_imshow(x)

  x=cv2.imread('prova.png')
  x=x/255
  #x=plt.imread('prova.png')/255
  #plt.imshow(prova_arr*255)
  #cv2_imshow(x*255)
  print("valori dopo salvataggio/lettura:")
  _,p,_=test_average(classifier,torch.Tensor(x.transpose(2,0,1)).unsqueeze_(0),transf_init)
  print(p)
          
          
def accuracy_class(class_str,pd_class):
  '''
  class_str: string class
  pd_class: dataframe
  '''

  n=np.sum(pd_class['real']==class_str)
  print("# img"+class_str+": "+str(n))

  p=pd_class.loc[pd_class['real']==class_str]
  p=p.loc[p['predicted']==p['real']]
  n_class=p.count(0)[0]
  print("Numero di predizioni "+class_str+" giuste: "+str(n_class))
  print("Accuracy : "+str(round(n_class/n*100,2)))
          
          
def print_acc(pd_preds):
  '''
  stampa accuracy usando il dataframe con le predizioni
  pd_preds: dataframe
  '''
  true_label = pd_preds.real.values
  predicted = pd_preds.predicted.values
  accuracy=round((np.sum((true_label == predicted).astype(int)))/pd_preds.shape[0],4)*100
  print("\nAccuracy: {0}".format(accuracy))
  print("Shape dataframe: {0}".format(pd_preds.shape))
          
          
          
