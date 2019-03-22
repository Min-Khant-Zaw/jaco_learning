import numpy as np
from numpy import linalg
import time
import math
import json

from scipy.optimize import minimize, newton
from scipy.stats import chi2

import trajoptpy
import or_trajopt
import openravepy
from openravepy import *

import openrave_utils
from openrave_utils import *

import copy
import os
import itertools
import pickle
import matplotlib.mlab as mlab

from trajopt_planner import Planner

# feature constacts (update gains and max weights)
UPDATE_GAINS = {'table':0.1, 'coffee':0.02, 'laptop':0.3, 'human':0.5}
MIN_WEIGHTS = {'table':-1.0, 'coffee':0.0, 'laptop':0.0, 'human':0.0}
MAX_WEIGHTS = {'table':1.0, 'coffee':1.0, 'laptop':8.0, 'human':10.0}
FEAT_RANGE = {'table':0.6918574, 'coffee':1.87608702, 'laptop':1.00476554, 'human':3.2}

# table is relatively symmetric: [-1.0, 0.75]
# coffee: [-0.06, 1.0] OR [-0.03, 0.7]
# laptop: [0.0, 7.51]
# human: [0.0, 10.0]

# feature learning methods
ALL = "ALL"					# updates all features
MAX = "MAX"					# updates only feature that changed the most
BETA = "BETA"				# updates beta-adaptive features 

class demoPlannerDiscrete(Planner):
	"""
	This class plans a trajectory from start to goal with TrajOpt.
	It supports learning capabilities from demonstrated human trajectories.
	"""

	def __init__(self, feat_method, feat_list, task=None, traj_cache=None, traj_rand=None):

		# Call parent initialization
		super(demoPlannerDiscrete, self).__init__(feat_list, task, traj_cache)

		# ---- important internal variables ---- #
		self.feat_method = feat_method	# can be ALL, MAX, or BETA
		self.weights = [0.0]*self.num_features
		self.beta = 1.0
		self.updates = [0.0]*self.num_features

		# trajectory paths
		self.traj_rand = traj_rand

		# ---- important discrete variables ---- #
		weights_span = [None]*self.num_feats
		for feat in range(0,self.num_feats):
			weights_span[feat] = list(np.linspace(0.0, MAX_WEIGHTS[feat_list[feat]], num=5))

		weight_pairs = list(itertools.product(*weights_span))
		self.weights_list = [list(i) for i in weight_pairs]
		self.betas_list = [0.01, 0.03, 0.1, 0.3, 1.0]

		self.num_betas = len(self.betas_list)
		self.num_weights = len(self.weights_list)

		# Construct uninformed prior
		P_bt = np.ones((self.num_betas, self.num_weights))
		self.P_bt = 1.0/self.num_betas * P_bt

	# ---- here's our algorithms for modifying the trajectory ---- #

	def learnWeights(self, waypts_h):
	
		if waypts_h is not None:
			old_features = self.featurize(self.traj)
			self.traj = traj
			new_features = self.featurize(self.traj)
			Phi_p = np.array([new_features[0]] + [sum(x) for x in new_features[1:]])
			Phi = np.array([old_features[0]] + [sum(x) for x in old_features[1:]])

			# Determine alpha and max theta
			update_gains = [0.0] * self.num_feats
			max_weights = [0.0] * self.num_feats
			feat_range = [0.0] * self.num_feats
			for feat in range(0, self.num_feats):
				update_gains[feat] = UPDATE_GAINS[self.feat_list[feat]]
				max_weights[feat] = MAX_WEIGHTS[self.feat_list[feat]]
				feat_range[feat] = FEAT_RANGE[self.feat_list[feat]]
			update = Phi_p - Phi

			if self.feat_method == ALL:
				# update all weights 
				curr_weight = self.weights - np.dot(update_gains, update[1:])
			elif self.feat_method == MAX:
				print("updating max weight")
				change_in_features = np.divide(update[1:], feat_range)

				# get index of maximal change
				max_idx = np.argmax(np.fabs(change_in_features))

				# update only weight of feature with maximal change
				curr_weight = [self.weights[i] for i in range(len(self.weights))]
				curr_weight[max_idx] = curr_weight[max_idx] - update_gains[max_idx]*update[max_idx+1]
			elif self.feat_method == BETA:
				# Now compute probabilities for each beta and theta in the dictionary
				P_xi = np.zeros((self.num_betas, self.num_weights))
				for (weight_i, weight) in enumerate(self.weights_list):
					for (beta_i, beta) in enumerate(self.betas_list):
						# Compute -beta*(weight^T*Phi(xi_H))
						numerator = -beta * np.dot([1.0] + weight, Phi_p)

						# Calculate the integral in log space
						num_trajs = self.traj_rand.shape[0]
						logdenom = np.zeros((num_trajs,1))

						# Compute costs for each of the random trajectories
						for rand_i in range(num_trajs):
							curr_traj = self.traj_rand[rand_i]
							rand_features = self.featurize(curr_traj)
							Phi_rand = np.array([rand_features[0]] + [sum(x) for x in rand_features[1:]])

							# Compute each denominator log
							logdenom[rand_i] = -beta * np.dot([1.0] + weight, Phi_rand)
						# Compute the sum in log space
						A_max = max(logdenom)
						expdif = logdenom - A_max
						denom = A_max + np.log(sum(np.exp(expdif)))
						# Get P(xi_H | beta, weight) by dividing them
						P_xi[beta_i][weight_i] = np.exp(numerator - denom)

				P_obs = P_xi / sum(sum(P_xi))
				
				# Compute P(weight, beta | xi_H) via Bayes rule
				posterior = np.multiply(P_obs, self.P_bt)

				# Normalize posterior
				posterior = posterior / sum(sum(posterior))

				# Compute optimal expected weight
				P_weight = sum(posterior, 0)
				curr_weight = np.sum(np.transpose(self.weights_list)*P_weight, 1)

				P_beta = np.sum(posterior, axis=1)
				self.beta = np.dot(self.betas_list,P_beta)
				self.P_bt = posterior
				print("observation model:", P_obs)
				print("posterior", self.P_bt)
				print("theta marginal:", P_weight)
				print("beta average:", self.beta)
				print("update:", update[1:])
			print("curr_weight after = " + str(curr_weight))

			# clip values at max and min allowed weights
			for i in range(self.num_feats):
				curr_weight[i] = np.clip(curr_weight[i], 0.0, max_weights[i])

			self.weights = curr_weight
			return self.weights

	def visualize_posterior(self, post):
		fig2, ax2 = plt.subplots()
		plt.imshow(post, cmap='RdBu', interpolation='nearest')
		plt.colorbar()
		plt.xticks(range(len(self.weights_list)), list(self.weights_list), rotation = 'vertical')
		plt.yticks(range(len(self.betas_list)), list(self.betas_list))
		plt.xlabel(r'$\theta$')
		plt.ylabel(r'$\beta$')
		plt.title("Joint posterior belief")
		plt.show()