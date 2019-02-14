import numpy as np
from hdf5storage import loadmat, savemat
from os.path import join
import sys

from util import *

tree_fname = sys.argv[1]
slices = read_slices(tree_fname)

for slc in slices:
	for cluster in slc:
		cluster.corr_hist[:] = 0
		cluster.count_hist[:] = 0

imset = 'val'
if len(sys.argv) > 2:
	imset = sys.argv[2]

ds_path = 'D:/datasets/processed/voc2012'
ds_info = loadmat(join(ds_path, 'dataset_info.mat'))
#m = ds_info['num_'+imset]
m = 350
nc = 20

logit_path = join(ds_path, 'deeplab_prediction', imset, imset+'_%06d_logits.mat')
gt_path = join(ds_path, 'truth', imset, imset+'_%06d_pixeltruth.mat')	

nb = len(slices[0][0].acc_hist)
res = 1./nb

def accum_calib(idx, nb, nc, slices):
	logits = loadmat(logit_path % idx)['logits_img'].reshape(-1, nc+1)
	logits[:,0] = 0

	gt = loadmat(gt_path % idx)['truth_img'].ravel()

	fg_mask = (gt>0) & (gt<=nc)
	logits = logits[fg_mask]
	gt = gt[fg_mask]

	for i, slc in enumerate(slices):
		slc_logits = np.array([remap_logits(logit_vec, slc) for logit_vec in logits])
		slc_gt = np.array([remap_gt(lab, slc) for lab in gt])
		
		slc_exp_logits = np.exp(slc_logits)
		slc_sm = slc_exp_logits / np.maximum(np.sum(slc_exp_logits, axis=-1)[...,np.newaxis], 1e-7)

		for j, cluster in enumerate(slc):
			pred_labels = np.argmax(slc_sm, axis=-1)
			argmax_mask = pred_labels == j

			slc_gt_masked = slc_gt[argmax_mask]
			slc_sm_masked = slc_sm[argmax_mask]

			sm_conf = slc_sm_masked[:,j]
			bins = np.floor(sm_conf/res).astype(np.uint8)
			bins = np.minimum(bins, nb-1)

			cluster.corr_hist[bins] += slc_gt_masked == j
			cluster.count_hist[bins] += 1


for idx in range(1, m+1):
	accum_calib(idx, nb, nc, slices)


for slc in slices:
	for cluster in slc:
		cluster.acc_hist[:] = cluster.corr_hist.astype(np.float32) / cluster.count_hist.astype(np.float32)

save_slices(tree_fname, slices)