import numpy as np
import os
import itertools
import pickle
import matplotlib.pyplot as plt
import matplotlib
import ast

import trajoptpy
import or_trajopt
import openravepy
from openravepy import *

from utils.openrave_utils import *
from planners.trajopt_planner import Planner

# feature constacts (update gains and max weights)
MIN_WEIGHTS = {'table':0.0, 'coffee':-1.0, 'laptop':0.0, 'human':0.0, 'efficiency':0.0}
MAX_WEIGHTS = {'table':1.0, 'coffee':1.0, 'laptop':1.0, 'human':1.0, 'efficiency':1.0}
FEAT_RANGE = {'table':1.0, 'coffee':1.0, 'laptop':1.6, 'human':1.6, 'efficiency':0.01}

class demoPlannerDiscrete(Planner):
	"""
	This class plans a trajectory from start to goal with TrajOpt.
	It supports learning capabilities from demonstrated human trajectories.
	"""

	def __init__(self, feat_list, task=None, traj_rand=None):

		# Call parent initialization
		super(demoPlannerDiscrete, self).__init__(feat_list, task)

		# ---- important internal variables ---- #
		self.weights = [0.0]*self.num_features
		self.beta = 1.0

		# trajectory paths
		here = os.path.dirname(os.path.realpath(__file__))
		if traj_rand is None:
			traj_rand = "/../traj_rand/traj_rand_merged_H.p"
		self.traj_rand = pickle.load( open( here + traj_rand, "rb" ) )

		# ---- important discrete variables ---- #
		weights_span = [None]*self.num_features
		for feat in range(0,self.num_features):
			weights_span[feat] = list(np.linspace(MIN_WEIGHTS[feat_list[feat]], MAX_WEIGHTS[feat_list[feat]], num=3))
		self.weights_list = list(itertools.product(*weights_span))
		if (0.0,)*self.num_features in self.weights_list:
			self.weights_list.remove((0.0,)*self.num_features)
		self.weights_list = [w / np.linalg.norm(w) for w in self.weights_list]
		self.weights_list = set([tuple(i) for i in self.weights_list])	     # Make tuples out of these to find uniques.
		self.weights_list = [list(i) for i in self.weights_list]
		self.betas_list = [0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0]
		self.betas_list.reverse()
		self.num_betas = len(self.betas_list)
		self.num_weights = len(self.weights_list)

		# Construct uninformed prior
		P_bt = np.ones((self.num_betas, self.num_weights))
		self.P_bt = 1.0/self.num_betas * P_bt

	# ---- here's our algorithms for modifying the trajectory ---- #

	def learnWeights(self, waypts_h):
		if waypts_h is not None:
			new_features = self.featurize(waypts_h)
			Phi_H = np.array([sum(x)/FEAT_RANGE[self.feat_list[i]] for i,x in enumerate(new_features)])
			print "Phi_H: ", Phi_H

			# Compute features for the normalizing trajectories.
			Phi_rands = []
			weight_rands = []
			num_trajs = len(self.traj_rand.keys())
			for rand_i, traj_str in enumerate(self.traj_rand.keys()):
				curr_traj = np.array(ast.literal_eval(traj_str))
				rand_features = self.featurize(curr_traj)
				Phi_rand = np.array([sum(x)/FEAT_RANGE[self.feat_list[i]] for i,x in enumerate(rand_features)])
				print "Phi_rand",rand_i, ": ",Phi_rand, "; weights: ", self.traj_rand[traj_str]
				Phi_rands.append(Phi_rand)
				weight_rands.append(self.traj_rand[traj_str])

			# Now compute probabilities for each beta and theta in the dictionary
			P_xi = np.zeros((self.num_betas, self.num_weights))
			for (weight_i, weight) in enumerate(self.weights_list):
				print "Initiating inference with the following weights: ", weight
				for (beta_i, beta) in enumerate(self.betas_list):
					# Compute -beta*(weight^T*Phi(xi_H))
					numerator = -beta * np.dot(weight, Phi_H)

					# Calculate the integral in log space
					logdenom = np.zeros((num_trajs+1,1))
					logdenom[-1] = -beta * np.dot(weight, Phi_H)

					# Compute costs for each of the random trajectories
					for rand_i in range(num_trajs):
						Phi_rand = Phi_rands[rand_i]

						# Compute each denominator log
						logdenom[rand_i] = -beta * np.dot(weight, Phi_rand)
					#if weight == [0.0,1.0,0.0]:
					#	import pdb;pdb.set_trace()
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
			print("observation model: ", P_obs)
			print("posterior: ", self.P_bt)
			print("theta marginal: " + str(P_weight))
			print("beta marginal: " + str(P_beta))
			print("theta average: " + str(curr_weight))
			print("beta average: " + str(self.beta))

			self.weights = curr_weight
			self.visualize_posterior(self.P_bt)
			print("\n------------ SIMULATED DEMONSTRATION DONE ------------\n")
			return self.weights

	def visualize_posterior(self, post):
		matplotlib.rcParams['font.sans-serif'] = "Arial"
		matplotlib.rcParams['font.family'] = "Times New Roman"
		matplotlib.rcParams.update({'font.size': 15})

		plt.imshow(post, cmap='Blues', interpolation='nearest')
		plt.colorbar(ticks=[0, 0.15, 0.3])
		plt.clim(0, 0.3)

		weights_rounded = [[round(i,2) for i in j] for j in self.weights_list]
		plt.xticks(range(len(self.weights_list)), weights_rounded, rotation = 'vertical')
		plt.yticks(range(len(self.betas_list)), list(self.betas_list))
		plt.xlabel(r'$\theta$', fontsize=15)
		plt.ylabel(r'$\beta$',fontsize=15)
		plt.title(r'Joint Posterior Belief b($\theta$, $\beta$)')
		plt.tick_params(length=0)
		plt.show()
		return