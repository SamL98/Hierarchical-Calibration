import os
from os.path import join, isfile, getsize
import numpy as np
from hdf5storage import loadmat, savemat
from scipy.stats import norm
from enum import Enum
import sys

'''
Statistics Utilities
'''
def conf_ints(acc_hist, count_hist, alpha):
	mask = count_hist > 0
	ranges = np.zeros_like(acc_hist)

	p, n = acc_hist[mask], count_hist[mask]
	
	z = norm.ppf(1 - alpha/2)
	pq = p * (1 - p)
	zn = z**2 / (4*n)
	
	if (pq < 0).sum() > 0:
		sys.stdout.write('acc_hist: ' + acc_hist.__repr__() + '\n')
		sys.stdout.flush()
		exit()

	conf_range = z * np.sqrt((pq + zn) / n) / (1 + zn*4)
	new_p = (p + zn*2) / (1 + zn*4)

	conf_range = np.clip(conf_range, 0, new_p)
	conf_range = np.minimum(conf_range, 1-new_p)

	acc_hist[mask] = new_p
	ranges[mask] = conf_range

	return acc_hist, ranges

def parzen_estimate(confs, bins, sigma):
	parzen = np.zeros_like(bins)
	for i, bn in enumerate(bins):
		z = (confs - bn) / sigma
		parzen[i] = (np.exp(-z**2 / 2)).sum()
	return np.round(parzen / np.maximum(1e-7, parzen.sum()) * len(confs))

class node_data_keys(Enum):
	C_HIST = 'c_hist'
	TOT_HIST = 'tot_hist'
	ACC_HIST = 'acc_hist'
	INT_RANGES = 'int_ranges'
	

class Node(object):
	def __init__(self, name, node_idx, terminals, data_dir='calib_data', is_main=False):
		self.uid = '%d-%s' % (node_idx, name)
		self.name = name
		self.node_idx = node_idx
		self.terminals = terminals
		self.data_dir = data_dir

		# Since we generally use multiple clones of each node to obtain the calibration data,
		# the pid is appended to the filenames of the node if we are a clone
		if is_main:
			pid = ''
		else:
			pid = '_' + str(os.getpid())

		if is_main:
			self.node_data_fname = join(self.data_dir, '%s_node_data.mat' % self.uid)
			if isfile(self.node_data_fname):
				self.load_node_data()

	def add_attr_if_not_exists(self, attr_name, attr_val):
		if not hasattr(self, attr_name):
			setattr(self, attr_name, attr_val)

	def load_node_data(self):
		self.node_data = loadmat(self.node_data_fname)
		self.acc_hist = self.node_data[node_data_keys.ACC_HIST.value]
		self.c_hist = self.node_data[node_data_keys.C_HIST.value]
		self.tot_hist = self.node_data[node_data_keys.TOT_HIST.value]
		self.int_ranges = self.node_data[node_data_keys.INT_RANGES.value]
		
	def _accum_stats(self, c_hist, tot_hist):
		self.add_attr_if_not_exists('c_hist', np.zeros_like(c_hist))
		self.add_attr_if_not_exists('tot_hist', np.zeros_like(tot_hist))

		self.c_hist += c_hist
		self.tot_hist += tot_hist

	def accum_scores(self, confs, correct_mask, nb, sigma):
		bins = np.linspace(0, 1, num=nb+1)
		c_hist = parzen_estimate(confs[correct_mask], bins, sigma)
		tot_hist = parzen_estimate(confs, bins, sigma)
		self._accum_stats(c_hist, tot_hist)
	
	def accum_node(self, node):
		self._accum_stats(node.c_hist, node.tot_hist)
			
	def generate_acc_hist(self, nb, alpha):
		attrs = ['c_hist', 'tot_hist']
		for attr in attrs:
			if not hasattr(self, attr): return
		
		acc_hist = self.c_hist.astype(np.float32) / np.maximum(1e-7, self.tot_hist.astype(np.float32))
		acc_hist = np.minimum(1, acc_hist)
		acc_hist, int_ranges = conf_ints(acc_hist, self.tot_hist, alpha)
		self.acc_hist = acc_hist
		self.int_ranges = int_ranges

		self.node_data = {
			node_data_keys.ACC_HIST.value: self.acc_hist,
			node_data_keys.C_HIST.value: self.c_hist,
			node_data_keys.TOT_HIST.value: self.tot_hist,
			node_data_keys.INT_RANGES.value: self.int_ranges
		}

		sys.stdout.write('Saving %s data\n' % self.name)
		sys.stdout.flush()
		savemat(self.node_data_fname, self.node_data)
			
	def get_conf_for_score(self, score):		
		if not hasattr(self, 'node_data'):
			assert isfile(join(self.node_data_fname))
			self.load_node_data()

		nb = len(self.acc_hist)
		res = 1./nb
		binno = np.floor(score/res)
		acc_val = self.acc_hist[binno]

		if hasattr(self, 'int_ranges'):
			acc_val -= self.int_ranges[i]

		return acc_val

	def get_conf_for_scores(self, scores):
		if not hasattr(self, 'node_data'):
			assert isfile(join(self.node_data_fname))
			self.load_node_data()

		nb = len(self.acc_hist)
		res = 1./nb

		bin_vec = np.floor(scores/res)
		accs = np.zeros((len(bin_vec)), dtype=np.float32)
		
		for binno in np.unique(bin_vec):
			bin_mask = bin_vec == binno
			accs[bin_mask] = self.acc_hist[binno]
			
			if hasattr(self, 'int_ranges'):
				accs[bin_mask] -= self.int_ranges[binno]

		return accs
