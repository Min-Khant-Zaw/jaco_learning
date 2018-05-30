from discrete_trajopt_planner import *
import pickle
import numpy as np
import itertools

if __name__ == '__main__':
	# Before calling this function, you need to decide what features you care
	# about, from a choice of table, coffee, human, origin, and laptop

	pick_basic = [104.2, 151.6, 183.8, 101.8, 224.2, 216.9, 310.8]
	place_lower = [210.8, 101.6, 192.0, 114.7, 222.2, 246.1, 322.0]

	# This is in case you care about coffee feature too
	pick_basic_EEtilt = [104.2, 151.6, 183.8, 101.8, 224.2, 216.9, 200.0]
	place_pose = [-0.46513, 0.29041, 0.69497]

	# initialize start/goal based on task 
	pick = pick_basic
	place = place_lower

	start = np.array(pick)*(math.pi/180.0)
	goal = np.array(place)*(math.pi/180.0)

	T = 20.0

	feat_method = "ALL"
	feat_list = "table"
	feat_list = [x.strip() for x in feat_list.split(',')]
	planner = DiscretePlanner(feat_method, feat_list)

	weights_pairs = planner.weights_dict
	num_trajs = len(weights_pairs)
	traj_optimal = [0] * num_trajs

	for (w_i, weights) in enumerate(weights_pairs):
		planner.replan(start, goal, weights, 0.0, T, 0.5)
		traj = planner.waypts
		traj_optimal[w_i] = traj

	traj_optimal = np.array(traj_optimal)
	print traj_optimal
	#print "-------"

	savestr = "_".join(feat_list)
	savefile = "traj_optimal_"+savestr+".p"

	pickle.dump(traj_optimal, open( savefile, "wb" ) )
